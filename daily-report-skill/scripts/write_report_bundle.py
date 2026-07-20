#!/usr/bin/env python3
"""Write a redacted Daily Report bundle from structured JSON received on stdin.

The calling agent is responsible for deriving concise summaries from eligible daily
turns. This writer rejects raw-transcript fields, redacts common sensitive values,
and uses the status file as the report bundle's commit marker.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def expanded_path(value: str) -> Path:
    """Resolve a user path while preserving Windows environment-variable support."""
    return Path(os.path.expandvars(value)).expanduser()


# Distribution-safe default: keep per-user artifacts outside the installed skill.
# Expand both the default Windows variable and a user-supplied override.
DEFAULT_REPORT_ROOT = expanded_path(
    os.environ.get("DAILY_REPORT_ROOT", r"%LOCALAPPDATA%\daily-report-skill")
)
PROHIBITED_FIELDS = {"raw_prompt", "reasoning", "tool_output", "raw_tool_output", "transcript"}
SENSITIVE_PATTERNS = (
    (re.compile(r"(?i)\b(bearer)\s+[a-z0-9._~+\-/=]+"), r"\1 [REDACTED]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"), "[REDACTED_API_KEY]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED_ACCESS_KEY]"),
    (re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|token|password|passwd|secret|cookie)\b\s*([:=])\s*\S+"), r"\1\2[REDACTED]"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[REDACTED_EMAIL]"),
    (re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "[REDACTED_PHONE]"),
    (re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"), "[REDACTED_ID]"),
    # Do not match digit runs embedded in identifiers such as UUIDs.
    (re.compile(r"(?<![A-Za-z0-9])(?:\d[ -]?){12,18}\d(?![A-Za-z0-9])"), "[REDACTED_CARD]"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-root", type=expanded_path, default=DEFAULT_REPORT_ROOT)
    parser.add_argument(
        "--input-file",
        type=expanded_path,
        help="UTF-8 or UTF-8-with-BOM structured JSON input. Prefer this over a PowerShell stdin pipe.",
    )
    parser.add_argument(
        "--check-delta",
        action="store_true",
        help="Compare structured session watermarks with the existing status without writing a report.",
    )
    parser.add_argument(
        "--finalize-existing",
        action="store_true",
        help="Mark an existing report status as FINAL without rewriting report artifacts.",
    )
    parser.add_argument(
        "--business-date",
        help="Required with --finalize-existing; Beijing business date in YYYY-MM-DD.",
    )
    args = parser.parse_args()
    if args.check_delta and args.finalize_existing:
        parser.error("--check-delta and --finalize-existing cannot be combined")
    if args.finalize_existing and not args.business_date:
        parser.error("--finalize-existing requires --business-date")
    return args


def redact(value: Any) -> Any:
    if isinstance(value, str):
        result = value
        for pattern, replacement in SENSITIVE_PATTERNS:
            result = pattern.sub(replacement, result)
        return result
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, dict):
        if PROHIBITED_FIELDS.intersection(value):
            keys = ", ".join(sorted(PROHIBITED_FIELDS.intersection(value)))
            raise ValueError(f"raw content fields are not allowed: {keys}")
        return {key: redact(item) for key, item in value.items()}
    return value


def require_string(record: dict[str, Any], key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def string_list(record: dict[str, Any], key: str) -> list[str]:
    value = record.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{key} must be a list of strings")
    return [item.strip() for item in value if item.strip()]


def safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip(".-")
    return (cleaned or "untitled")[:80]


def list_markdown(items: list[str], fallback: str) -> str:
    return "\n".join(f"- {item}" for item in items) if items else f"- {fallback}"


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def load_input_payload(input_file: Path | None) -> Any:
    if input_file is None:
        return json.load(sys.stdin)
    with input_file.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def load_previous_status(status_path: Path) -> dict[str, Any]:
    if not status_path.is_file():
        return {}
    try:
        previous = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return previous if isinstance(previous, dict) else {}


def optional_string(record: dict[str, Any], key: str) -> str | None:
    value = record.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


def session_watermark(session: dict[str, Any]) -> dict[str, Any]:
    count = session.get("user_message_count", session.get("user_message_count_before_cutoff"))
    if count is not None and (isinstance(count, bool) or not isinstance(count, int) or count < 0):
        raise ValueError("user_message_count must be a non-negative integer when provided")
    return {
        "user_message_count": count,
        "last_user_message_at": optional_string(session, "last_user_message_at"),
    }


def source_watermarks(sessions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {require_string(session, "session_id"): session_watermark(session) for session in sessions}


def compare_watermarks(
    previous_status: dict[str, Any], sessions: list[dict[str, Any]]
) -> dict[str, Any]:
    previous = previous_status.get("source_watermarks")
    previous_watermarks = previous if isinstance(previous, dict) else {}
    current = source_watermarks(sessions)
    new_sessions = sorted(session_id for session_id in current if session_id not in previous_watermarks)
    changed_sessions = sorted(
        session_id
        for session_id, watermark in current.items()
        if session_id in previous_watermarks
        and previous_watermarks[session_id] != watermark
    )
    missing_prior_watermarks = bool(previous_status) and not isinstance(previous, dict)
    return {
        "has_existing_report": bool(previous_status),
        "phase": previous_status.get("phase", "SNAPSHOT"),
        "has_delta": bool(new_sessions or changed_sessions or missing_prior_watermarks),
        "new_session_ids": new_sessions,
        "changed_session_ids": changed_sessions,
        "missing_prior_watermarks": missing_prior_watermarks,
        "source_watermarks": current,
    }


def render_session(session: dict[str, Any], business_date: str) -> str:
    title = session.get("title") or "Untitled Codex session"
    status_at_report_run = session.get(
        "status_at_report_run", session.get("status_at_cutoff", "not_observed_active")
    )
    summary_status = session.get("summary_status", "COMPLETE")
    lines = [
        f"# 单会话日报交接 — {title}",
        "",
        f"- 业务日期：{business_date}",
        f"- 会话 ID：{session['session_id']}",
        f"- 项目目录：{session.get('cwd') or '未获取'}",
        f"- 当天活动：{session.get('first_user_message_at', '未获取')} 至 {session.get('last_user_message_at', '未获取')}",
        f"- 生成时状态：{status_at_report_run}",
        f"- 摘要状态：{summary_status}",
        "",
    ]
    if summary_status == "FAILED":
        lines.extend(["## 失败原因", list_markdown(string_list(session, "failure_reasons"), "未提供原因。"), ""])
    else:
        sections = (
            ("当天目标", "daily_goal", "当天允许范围内未能确认目标。"),
            ("已完成事项", "completed_items", "未能确认完成证据。"),
            ("验证证据", "validation_evidence", "未能确认验证证据。"),
            ("阻塞或未完成事项", "blockers", "未记录。"),
            ("建议下一步", "next_steps", "未能确认下一步。"),
            ("关联文件", "associated_files", "未记录。"),
        )
        for heading, key, fallback in sections:
            lines.extend([f"## {heading}"])
            if key == "daily_goal":
                lines.append(session.get(key) or fallback)
            else:
                lines.append(list_markdown(string_list(session, key), fallback))
            lines.append("")
    lines.extend(["## 范围说明", "这是生成时已发生的当天活动的脱敏结构化摘要；不包含原始 prompt、推理或工具输出。", ""])
    return "\n".join(lines)


def source_label(session: dict[str, Any]) -> str:
    cwd = session.get("cwd")
    project = Path(cwd).name if isinstance(cwd, str) and cwd else "未识别项目"
    window = session.get("title") or session["session_id"]
    return f"{project}｜{window}"


def tagged_items(sessions: list[dict[str, Any]], key: str) -> list[str]:
    return [
        f"【{source_label(session)}】{item}"
        for session in sessions
        if session.get("summary_status", "COMPLETE") != "FAILED"
        for item in string_list(session, key)
    ]


def render_reading_report(bundle: dict[str, Any], sessions: list[dict[str, Any]]) -> list[str]:
    reading = bundle.get("reading_report")
    if isinstance(reading, dict):
        outline = string_list(reading, "outline")
        script = reading.get("script")
        if not isinstance(script, str) or not script.strip():
            raise ValueError("reading_report.script must be a non-empty string")
        normalized_length = len(re.sub(r"\s+", "", script))
        if not 350 <= normalized_length <= 900:
            raise ValueError("reading_report.script must target 2–3 minutes: 350–900 non-space characters")
        return ["## 朗读日报", "", "### 大纲", list_markdown(outline, "未提供大纲。"), "", "### 文本", script.strip(), ""]

    labels = [source_label(session) for session in sessions if session.get("summary_status", "COMPLETE") != "FAILED"]
    fallback = "今日工作涉及" + "、".join(labels) + "。请结合 briefing 中按项目和窗口标注的完成事项、阻塞与下一步进行朗读。"
    return ["## 朗读日报", "", "### 大纲", list_markdown(labels, "无可朗读的工作项目。"), "", "### 文本", fallback, ""]


def render_briefing(bundle: dict[str, Any], sessions: list[dict[str, Any]], overall_status: str) -> str:
    business_date = bundle["business_date"]
    completed = tagged_items(sessions, "completed_items")
    blockers = tagged_items(sessions, "blockers")
    next_steps = tagged_items(sessions, "next_steps")
    active = [
        session
        for session in sessions
        if session.get("status_at_report_run", session.get("status_at_cutoff"))
        in {"active_at_report_run", "active_at_cutoff"}
    ]
    failed = [session for session in sessions if session.get("summary_status") == "FAILED"]
    covered = [f"【{source_label(session)}】会话 ID：{session['session_id']}" for session in sessions]
    lines = [
        f"# 日报 — {business_date}",
        "",
        f"- 总体状态：{overall_status}",
        f"- 覆盖会话数：{len(sessions)}",
        f"- 生成时活跃会话数：{len(active)}",
        f"- 失败会话数：{len(failed)}",
        "",
        "## 覆盖项目与窗口",
        list_markdown(covered, "无。"),
        "",
        "## 已完成工作",
        list_markdown(completed, "未能确认完成证据。"),
        "",
        "## 生成时仍活跃",
        list_markdown([f"【{source_label(item)}】后续仍可能变化。" for item in active], "未观察到。"),
        "",
        "## 阻塞与未完成工作",
        list_markdown(blockers, "未记录。"),
        "",
        "## 失败或未覆盖会话",
        list_markdown([f"【{source_label(item)}】" + "；".join(string_list(item, "failure_reasons")) for item in failed], "无。"),
        "",
        "## 下一步",
        list_markdown(next_steps, "未能确认下一步。"),
        "",
    ]
    lines.extend(render_reading_report(bundle, sessions))
    lines.extend(["本日报是脱敏的原始工作记录，不自动构成正式 Handoff 或 Lesson。", ""])
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    try:
        if args.finalize_existing:
            business_date = args.business_date
            datetime.strptime(business_date, "%Y-%m-%d")
            status_path = args.report_root / "status" / f"{business_date}.json"
            previous_status = load_previous_status(status_path)
            if not previous_status:
                raise ValueError(f"existing status not found: {status_path}")
            if previous_status.get("state") not in {"COMPLETE", "COMPLETE_WITH_FAILURES"}:
                raise ValueError("only a completed report status can be finalized")
            finalized_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            previous_status["phase"] = "FINAL"
            previous_status["last_reconciled_at"] = finalized_at
            previous_status["finalized_at"] = finalized_at
            atomic_write_json(status_path, previous_status)
            print(
                json.dumps(
                    {
                        "state": previous_status.get("state"),
                        "phase": "FINAL",
                        "status": str(status_path),
                        "changed_report_artifacts": False,
                    },
                    ensure_ascii=False,
                )
            )
            return 0

        payload = load_input_payload(args.input_file)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        bundle = redact(payload)
        business_date = require_string(bundle, "business_date")
        datetime.strptime(business_date, "%Y-%m-%d")
        sessions = bundle.get("sessions")
        if not isinstance(sessions, list) or (not sessions and not args.check_delta):
            raise ValueError("sessions must be a non-empty list")
        if not all(isinstance(session, dict) for session in sessions):
            raise ValueError("each session must be an object")
        for session in sessions:
            require_string(session, "session_id")
            summary_status = session.get("summary_status", "COMPLETE")
            if summary_status not in {"COMPLETE", "FAILED"}:
                raise ValueError("summary_status must be COMPLETE or FAILED")

        status_path = args.report_root / "status" / f"{business_date}.json"
        previous_status = load_previous_status(status_path)
        if args.check_delta:
            print(json.dumps(compare_watermarks(previous_status, sessions), ensure_ascii=False))
            return 0

        run_id = bundle.get("run_id") or str(uuid.uuid4())
        generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        handoff_dir = args.report_root / "handoffs" / business_date
        briefing_path = args.report_root / "briefings" / f"{business_date}.md"
        manifest_path = handoff_dir / "manifest.json"
        requested_recovered_at = bundle.get("recovered_at")
        recovered_at = (
            requested_recovered_at.strip()
            if isinstance(requested_recovered_at, str) and requested_recovered_at.strip()
            else optional_string(previous_status, "recovered_at")
        )
        phase = bundle.get("phase", "SNAPSHOT")
        if phase not in {"SNAPSHOT", "FINAL"}:
            raise ValueError("phase must be SNAPSHOT or FINAL")
        excluded_automation_session_ids = string_list(bundle, "excluded_automation_session_ids")
        watermarks = source_watermarks(sessions)
        snapshot_generated_at = optional_string(previous_status, "snapshot_generated_at") or generated_at
        overall_status = "COMPLETE_WITH_FAILURES" if any(session.get("summary_status") == "FAILED" for session in sessions) else "COMPLETE"

        # Mark a replacement in progress before touching any current report files.
        atomic_write_json(
            status_path,
            {
                "business_date": business_date,
                "run_id": run_id,
                "state": "WRITING",
                "phase": phase,
                "generated_at": generated_at,
            },
        )

        manifest_sessions: list[dict[str, Any]] = []
        expected_files: set[Path] = {manifest_path}
        for session in sessions:
            filename = f"{session['session_id']}-{safe_filename(session.get('title') or 'untitled')}.md"
            destination = handoff_dir / filename
            expected_files.add(destination)
            atomic_write(destination, render_session(session, business_date))
            manifest_sessions.append({
                "session_id": session["session_id"],
                "title": session.get("title"),
                "file": filename,
                "summary_status": session.get("summary_status", "COMPLETE"),
                "status_at_report_run": session.get(
                    "status_at_report_run", session.get("status_at_cutoff", "not_observed_active")
                ),
            })

        if handoff_dir.exists():
            for stale_file in handoff_dir.glob("*.md"):
                if stale_file not in expected_files:
                    stale_file.unlink()

        manifest = {
            "business_date": business_date,
            "generated_at": generated_at,
            "run_id": run_id,
            "phase": phase,
            "excluded_automation_session_ids": excluded_automation_session_ids,
            "sessions": manifest_sessions,
        }
        atomic_write_json(manifest_path, manifest)
        atomic_write(briefing_path, render_briefing(bundle, sessions, overall_status))
        failed_sessions = [
            {
                "session_id": session["session_id"],
                "failure_reasons": string_list(session, "failure_reasons"),
                "recovery_gap": optional_string(session, "recovery_gap") or "未提供恢复缺口。",
            }
            for session in sessions
            if session.get("summary_status") == "FAILED"
        ]
        final_status = {
            "business_date": business_date,
            "run_id": run_id,
            "state": overall_status,
            "phase": phase,
            "generated_at": generated_at,
            "recovered_at": recovered_at,
            "snapshot_generated_at": snapshot_generated_at,
            "last_reconciled_at": generated_at,
            "finalized_at": generated_at if phase == "FINAL" else None,
            "session_count": len(sessions),
            "failed_session_ids": [item["session_id"] for item in failed_sessions],
            "failed_sessions": failed_sessions,
            "source_watermarks": watermarks,
            "excluded_automation_session_ids": excluded_automation_session_ids,
        }
        atomic_write_json(status_path, final_status)
        print(
            json.dumps(
                {
                    "state": overall_status,
                    "phase": phase,
                    "briefing": str(briefing_path),
                    "manifest": str(manifest_path),
                    "status": str(status_path),
                },
                ensure_ascii=False,
            )
        )
        return 0
    except (json.JSONDecodeError, ValueError, OSError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
