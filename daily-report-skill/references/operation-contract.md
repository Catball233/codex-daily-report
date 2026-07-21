# Daily Report Operating Contract

## Scope

This skill runs only through an explicit `$daily-report` invocation or an
automation prompt that explicitly invokes it. The ordinary branch reads the Beijing
reporting date only. It does not open Codex windows or alter threads.

## Reporting policy

- The Codex Scheduled task determines when the primary job runs; this skill does not
  impose a fixed clock time, weekday rule, or weekend carryover rule.
- Include sessions with a user message on the Beijing reporting date before the report
  run begins, including sessions created on earlier dates and unrelated automation
  sessions. Exclude only the Scheduled/new-task session that invokes Daily Report. The
  local fallback recognizes it from `thread_source=automation` plus one
  scheduler-injected user instruction containing both `Automation ID:` and a
  daily-report invocation marker. Never exclude based on a mutable title, and never
  persist the instruction text: record only the stable session ID and exclusion reason.
  A missing current-session ID in a new automation is therefore not a reason to stop.
- Mark still-active sessions `active_at_report_run`.
- Treat each Beijing calendar date independently. Weekend activity is reported only
  when a run is explicitly triggered for that weekend date.
- Recover missed reports under the original reporting date and add `recovered_at`.
- A report has `phase=SNAPSHOT` until it has been reconciled after its business date,
  then `phase=FINAL`. `state` remains the write-success state (`COMPLETE`,
  `COMPLETE_WITH_FAILURES`, or `WRITING`).

## Read policy

Use thread tools first. If they do not provide enough information to establish the
daily scope or summary, match the stable session ID to
`$CODEX_HOME/sessions/**/*.jsonl` (default: `~/.codex/sessions/**/*.jsonl`) and
read only the needed record. Never treat `AppData\\Roaming\\Codex` browser storage
as transcript data.

Default runs read the necessary daily turn content and essential metadata from every
included session, not merely the scheduled task's own new-task context. Before handling
today, they may reconcile only the most recent pre-existing earlier `SNAPSHOT` date;
this is not historical review and remains limited to that date's necessary turn content.
All other prior-date content remains history. History requires a date range, project path,
or session ID; only `--history all` authorizes all available historical sessions.

`$daily-report` compares each target date's source watermarks before rewriting. A
watermark is the stable session ID plus its daily user-message count and
`last_user_message_at`; `active_at_report_run` is not a watermark. No delta leaves
current-day artifacts unchanged and returns `已覆盖<业务日期>所有窗口，无增加会话内容。`.
For a prior `SNAPSHOT` with no delta, only its status is updated to `FINAL`. The schedule
controls trigger time; the skill contains no clock-based branch.

The deterministic writer supports `--check-delta --input-file <candidate-json>` for the
non-writing comparison and `--finalize-existing --business-date <date>` for the
status-only prior-date transition. The enumerator automatically excludes only the
daily-report automation signature and accepts repeated `--exclude-session-id` values as
an additional explicit caller override.

## Output policy

所有面向人的标题、摘要、列表项和说明必须使用简体中文。保留会话 ID、文件路径、时间戳、代码标识和状态常量（如 `COMPLETE`）的原始形式。

Write reports under the configured report root. The distribution default is
`%LOCALAPPDATA%\\daily-report-skill\\`; this keeps artifacts outside the installed
skill. Expand `DAILY_REPORT_ROOT` when set. `--report-root` is a higher-priority,
explicit per-run override. Do not assume a `D:` drive or a developer workspace.

Under that root, write:

- `handoffs/YYYY-MM-DD/` for one redacted summary per session and a manifest.
- `briefings/YYYY-MM-DD.md` for the daily rollup.
- `status/YYYY-MM-DD.json` for success, failure, and recovery metadata.

## Reply policy

The final user-facing reply reports generation status, covered-session count,
failed-session count, and the briefing only. Present the briefing as a clickable
Codex Desktop local Markdown link whose target is the absolute briefing path, then
include that same path as plain text on the following line for clients that do not
render local links. Do not normally link the manifest or status file.

The status file also records `phase`, `snapshot_generated_at`, `last_reconciled_at`,
`finalized_at`, `source_watermarks`, and `excluded_automation_session_ids`. These values
are structural metadata only and must not contain message text.

Write atomically. A same-date rerun replaces the current report only after a complete
successful write and only when a watermark delta exists. Each replacement records a new
`generated_at` and `run_id`; it retains any previously recorded `recovered_at`. Retain per-session summaries for 90 days and
daily briefings indefinitely.

## Encoding policy

Write report JSON to `write_report_bundle.py` through `--input-file` using UTF-8 or
UTF-8 with BOM. Do not use a Windows PowerShell pipeline or `Get-Content` to forward
JSON into the writer: that path can convert Chinese characters to literal `?` before
the writer receives them. The writer accepts stdin only for non-PowerShell callers.

## Redaction policy

Redact passwords, secrets, API keys, access tokens, cookies, complete environment
variable values, email addresses, phone numbers, national IDs, and bank-card numbers.
Do not preserve raw prompts, reasoning, raw tool output, or unredacted sensitive
content. Preserve only the traceability needed for work: session ID, project name,
relative paths, commit IDs, status, and validation conclusions.

## Failure policy

Continue if one session fails. Mark it `FAILED` in the briefing and status file with
a reason and recovery gap. A report is evidence only; it is never automatically a
formal Handoff or Lesson.
