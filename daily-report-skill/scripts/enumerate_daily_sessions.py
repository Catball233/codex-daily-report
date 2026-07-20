#!/usr/bin/env python3
"""Enumerate local Codex sessions with qualifying user messages for one Beijing date.

This script emits structural metadata only. It never emits message text, tool output,
or reasoning content, and it does not write report files.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


try:
    BEIJING = ZoneInfo("Asia/Shanghai")
    TIMEZONE_SOURCE = "IANA Asia/Shanghai"
except ZoneInfoNotFoundError:
    # Some Windows-embedded Python builds do not bundle the IANA tzdata package.
    # China Standard Time has been UTC+08:00 without DST since 1991.
    BEIJING = timezone(timedelta(hours=8), name="Asia/Shanghai")
    TIMEZONE_SOURCE = "fixed UTC+08:00 fallback (valid for dates from 1991)"
DEFAULT_CODEX_HOME = Path(
    os.path.expandvars(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
).expanduser()
DEFAULT_SESSIONS_ROOT = DEFAULT_CODEX_HOME / "sessions"
DEFAULT_SESSION_INDEX = DEFAULT_CODEX_HOME / "session_index.jsonl"


def expanded_path(value: str) -> Path:
    return Path(os.path.expandvars(value)).expanduser()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--date",
        dest="report_date",
        help="Beijing business date in YYYY-MM-DD (default: today in Asia/Shanghai).",
    )
    parser.add_argument(
        "--cutoff",
        help="Optional inclusive Beijing HH:MM boundary. Omit to include all activity on the reporting date.",
    )
    parser.add_argument(
        "--sessions-root",
        type=expanded_path,
        default=DEFAULT_SESSIONS_ROOT,
        help="Root containing Codex session JSONL files.",
    )
    parser.add_argument(
        "--session-index",
        type=expanded_path,
        default=DEFAULT_SESSION_INDEX,
        help="Codex session index JSONL used only for titles.",
    )
    parser.add_argument(
        "--active-session-id",
        action="append",
        default=[],
        help="Session ID observed active when the report was run; repeat as needed.",
    )
    parser.add_argument(
        "--exclude-session-id",
        action="append",
        default=[],
        help="Session ID to omit from the report scope; repeat as needed.",
    )
    return parser.parse_args()


def parse_report_date(value: str | None) -> date:
    if value is None:
        return datetime.now(BEIJING).date()
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("--date must be YYYY-MM-DD") from exc


def parse_cutoff(value: str | None) -> time | None:
    if value is None:
        return None
    try:
        parsed = time.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("--cutoff must be HH:MM") from exc
    if parsed.second or parsed.microsecond:
        raise ValueError("--cutoff must not contain seconds")
    return parsed


def parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(BEIJING)
    except ValueError:
        return None


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON at line {line_number}") from exc
            if isinstance(value, dict):
                yield value


def load_titles(index_path: Path) -> dict[str, str]:
    if not index_path.is_file():
        return {}

    titles: dict[str, str] = {}
    try:
        records = read_jsonl(index_path)
        for record in records:
            session_id = record.get("id")
            title = record.get("thread_name")
            if isinstance(session_id, str) and isinstance(title, str) and title.strip():
                titles[session_id] = title.strip()
    except (OSError, ValueError):
        return {}
    return titles


def session_id_from_record(record: dict[str, Any]) -> str | None:
    payload = record.get("payload")
    if not isinstance(payload, dict):
        return None
    for key in ("session_id", "id"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def response_item_text(record: dict[str, Any]) -> str:
    """Return transient user text used only for an in-process automation signature.

    The caller must never place the returned value in the enumerator output.  It is
    intentionally limited to the local fallback needed to prevent the daily-report
    Scheduled task from reporting itself when Codex does not expose its session ID.
    """
    payload = record.get("payload")
    if not isinstance(payload, dict) or payload.get("role") != "user":
        return ""
    content = payload.get("content")
    if not isinstance(content, list):
        return ""
    return "\n".join(
        item["text"]
        for item in content
        if isinstance(item, dict) and isinstance(item.get("text"), str)
    )


def has_daily_report_automation_signature(
    thread_source: str | None, automation_user_texts: list[str]
) -> bool:
    """Identify only the Scheduled task that invokes this daily-report skill.

    Requiring the scheduler-injected ``Automation ID:`` label as well as a
    daily-report marker preserves unrelated automation sessions.  Raw prompt text
    remains in memory only for this boolean decision and is never emitted.
    """
    if thread_source != "automation":
        return False
    for text in automation_user_texts:
        normalized = text.casefold()
        has_scheduler_label = "automation id:" in normalized
        invokes_daily_report = (
            "$daily-report" in normalized
            or "daily-report skill" in normalized
            or "daily report skill" in normalized
        )
        if has_scheduler_label and invokes_daily_report:
            return True
    return False


def inspect_session(
    path: Path,
    report_date: date,
    cutoff: time | None,
    active_session_ids: set[str],
    titles: dict[str, str],
) -> tuple[dict[str, Any] | None, str | None]:
    session_id: str | None = None
    cwd: str | None = None
    thread_source: str | None = None
    automation_user_texts: list[str] = []
    qualifying_times: list[datetime] = []
    excluded_by_optional_cutoff_count = 0

    try:
        records = read_jsonl(path)
        for record in records:
            if record.get("type") == "session_meta":
                session_id = session_id or session_id_from_record(record)
                payload = record.get("payload")
                if isinstance(payload, dict) and isinstance(payload.get("cwd"), str):
                    cwd = payload["cwd"]
                if isinstance(payload, dict) and isinstance(payload.get("thread_source"), str):
                    thread_source = payload["thread_source"]
                continue

            if record.get("type") == "response_item":
                text = response_item_text(record)
                if text:
                    automation_user_texts.append(text)
                continue

            if record.get("type") != "event_msg":
                continue
            payload = record.get("payload")
            if not isinstance(payload, dict) or payload.get("type") != "user_message":
                continue

            event_time = parse_timestamp(record.get("timestamp"))
            if event_time is None or event_time.date() != report_date:
                continue
            if cutoff is None or event_time.time() <= cutoff:
                qualifying_times.append(event_time)
            else:
                excluded_by_optional_cutoff_count += 1
    except (OSError, ValueError) as exc:
        return None, f"{path.name}: {exc}"

    if not qualifying_times:
        return None, None

    resolved_id = session_id or path.stem
    is_active = resolved_id in active_session_ids
    return {
        "session_id": resolved_id,
        "title": titles.get(resolved_id),
        "cwd": cwd,
        "source_files": [str(path)],
        "user_message_count_before_cutoff": len(qualifying_times),
        "first_user_message_at": min(qualifying_times).isoformat(),
        "last_user_message_at": max(qualifying_times).isoformat(),
        "user_message_count_excluded_by_optional_cutoff": excluded_by_optional_cutoff_count,
        "status_at_report_run": "active_at_report_run" if is_active else "not_observed_active",
        "status_source": "caller_thread_snapshot" if is_active else "not_observed_by_jsonl",
        "is_daily_report_automation": has_daily_report_automation_signature(
            thread_source, automation_user_texts
        ),
    }, None


def main() -> int:
    try:
        args = parse_args()
        report_date = parse_report_date(args.report_date)
        cutoff = parse_cutoff(args.cutoff)
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2

    sessions_root: Path = args.sessions_root
    if not sessions_root.is_dir():
        print(json.dumps({"error": f"sessions root not found: {sessions_root}"}), file=sys.stderr)
        return 2

    titles = load_titles(args.session_index)
    active_session_ids = set(args.active_session_id)
    excluded_session_ids = set(args.exclude_session_id)
    automatically_excluded_session_ids: set[str] = set()
    results_by_session_id: dict[str, dict[str, Any]] = {}
    excluded_by_session_id: dict[str, dict[str, str]] = {}
    failures: list[str] = []
    scanned_files = 0

    for path in sorted(sessions_root.rglob("*.jsonl")):
        scanned_files += 1
        item, failure = inspect_session(path, report_date, cutoff, active_session_ids, titles)
        if item is not None:
            session_id = item["session_id"]
            if session_id in automatically_excluded_session_ids:
                continue
            if item.pop("is_daily_report_automation"):
                automatically_excluded_session_ids.add(session_id)
                results_by_session_id.pop(session_id, None)
                excluded_by_session_id[session_id] = {
                    "session_id": session_id,
                    "reason": "daily_report_automation_signature",
                }
                continue
            if session_id in excluded_session_ids:
                excluded_by_session_id[session_id] = {
                    "session_id": session_id,
                    "reason": "caller_exclude_session_id",
                }
                continue
            existing = results_by_session_id.get(session_id)
            if existing is None:
                results_by_session_id[session_id] = item
            else:
                existing["source_files"].extend(item["source_files"])
                existing["user_message_count_before_cutoff"] += item[
                    "user_message_count_before_cutoff"
                ]
                existing["user_message_count_excluded_by_optional_cutoff"] += item[
                    "user_message_count_excluded_by_optional_cutoff"
                ]
                existing["first_user_message_at"] = min(
                    existing["first_user_message_at"], item["first_user_message_at"]
                )
                existing["last_user_message_at"] = max(
                    existing["last_user_message_at"], item["last_user_message_at"]
                )
                if existing["cwd"] is None:
                    existing["cwd"] = item["cwd"]
                if existing["title"] is None:
                    existing["title"] = item["title"]
                if item["status_at_report_run"] == "active_at_report_run":
                    existing["status_at_report_run"] = "active_at_report_run"
                    existing["status_source"] = "caller_thread_snapshot"
        if failure is not None:
            failures.append(failure)

    results = sorted(
        results_by_session_id.values(),
        key=lambda item: (item["last_user_message_at"], item["session_id"]),
    )
    response = {
        "schema_version": 1,
        "reporting_timezone": "Asia/Shanghai",
        "timezone_source": TIMEZONE_SOURCE,
        "report_date": report_date.isoformat(),
        "optional_cutoff": cutoff.strftime("%H:%M") if cutoff else None,
        "selection_rule": (
            "at least one user_message on report_date at or before optional_cutoff"
            if cutoff
            else "at least one user_message on report_date"
        ),
        "scanned_session_files": scanned_files,
        "eligible_sessions": results,
        "excluded_sessions": sorted(
            excluded_by_session_id.values(), key=lambda item: item["session_id"]
        ),
        "failed_session_files": failures,
        "notes": [
            "Message text, reasoning, and tool output are intentionally excluded.",
            "active_at_report_run is only asserted for IDs supplied from a caller thread snapshot.",
            "Sessions listed in excluded_sessions were omitted either by a caller-supplied ID or by the daily-report automation signature.",
        ],
    }
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
