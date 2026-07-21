---
name: daily-report
description: Generate or inspect local daily Codex conversation handoff summaries. Use only when explicitly invoked as $daily-report or by its scheduled daily-report automation; default to the Beijing-date daily scope, and read historical sessions only after an explicit --history scope or --history all request.
disable-model-invocation: true
---

# Daily Report Skill

Create traceable, local daily reports from Codex conversations without opening each
window. This is a Codex development-support skill, not a QiClaw runtime skill.

## Load the operating contract

Read [references/operation-contract.md](references/operation-contract.md) before
planning, generating, inspecting, or recovering a report. Treat it as the authority
for scope, redaction, storage, and recovery behavior.

## Select the branch

### Default daily branch

Use this branch for `$daily-report` and for the weekday scheduled job.

1. Use the Beijing reporting date. The Codex Scheduled task determines when a report
   is triggered; do not impose a fixed clock time or weekday rule in this skill.
2. Before handling today, inspect status records for the most recent earlier report
   with `phase=SNAPSHOT`. This is a narrow reconciliation exception, not history
   search: read only that existing report date. Re-enumerate its metadata and use
   `write_report_bundle.py --check-delta --input-file <candidate-json>`.
   - When there is a delta, regenerate that original date from its current-date turns
     and write it with `phase=FINAL`.
   - When there is no delta, run `--finalize-existing --business-date <date>`; do not
     rewrite handoffs, manifest, or briefing.
   - Do not retry an already failed session during reconciliation unless the user
     explicitly requests a future `--retry-failed` capability.
3. Inspect today's status. A missing report becomes `SNAPSHOT`; an existing
   `SNAPSHOT` is re-enumerated and compared through `--check-delta`; an existing
   `FINAL` is returned unchanged. When a same-day `SNAPSHOT` has no delta, return:
   `已覆盖<业务日期>所有窗口，无增加会话内容。` plus the existing briefing path.
4. Include a session when it has a user message on the reporting date before the
   report run begins. Preserve unrelated automation sessions. The local enumerator
   automatically skips only a Scheduled/new-task session whose structural metadata is
   `thread_source=automation` and whose scheduler-injected user instruction contains
   both `Automation ID:` and a daily-report invocation marker. It records only the
   stable ID and exclusion reason; it never emits the instruction text. Do not exclude
   by mutable title. A caller may additionally pass known IDs with
   `--exclude-session-id`, but a new Scheduled task must not stop merely because it
   cannot expose its own session ID in context.
5. Enumerate every eligible session through Codex thread tools first, then read the
   necessary same-day turn content available at the report run. Never summarize only the
   scheduled task's own new-task context. Use matching local session JSONL only when
   thread data is insufficient; do not read prior-date content in this branch.
   Run `scripts/enumerate_daily_sessions.py` to derive the JSONL fallback scope; pass
   IDs observed active at report run with repeated `--active-session-id` values.
   Preserve each eligible session's user-message count and `last_user_message_at` in
   the structured input so the writer can persist source watermarks.
6. Generate one redacted window handoff summary and one redacted daily briefing.
   Pass only structured summaries to `scripts/write_report_bundle.py`; it rejects raw
   transcript fields, redacts common sensitive values, and commits the bundle through
   its status record.
   Write all human-readable report narrative in Simplified Chinese; preserve IDs,
   paths, timestamps, code identifiers, and status constants unchanged.
   In the briefing, tag each completed item, blocker, and next step with its project
   name and window title. Add `reading_report.outline` and a 350–900-character
   Simplified-Chinese `reading_report.script` suitable for a two-to-three-minute
   spoken daily report; mention the relevant projects in that script.
   Pass the writer's structured JSON through a UTF-8 or UTF-8-with-BOM input file and
   invoke `scripts/write_report_bundle.py --input-file <path>`. Do not pipe JSON through
   Windows PowerShell stdin or through `Get-Content`; its code-page conversion can replace
   Chinese characters with `?`. Delete the staged input after a successful write.
   Include `phase` and `excluded_automation_session_ids` in the structured input.
7. Mark a still-running session as `active_at_report_run`; never use that display-only
   status as an increment decision.
8. Write only to the configured report root and record run metadata. The default is
   `%LOCALAPPDATA%\\daily-report-skill`; expand `DAILY_REPORT_ROOT` when it is set.
   Pass `--report-root` only for an explicit caller-provided override.
9. In the final user-facing reply, provide only the generation status, covered-session
   count, failed-session count, and the briefing. Render the briefing as a clickable
   Codex Desktop local Markdown link using its absolute path, for example
   `[打开日报](C:/Users/<user>/AppData/Local/daily-report-skill/briefings/YYYY-MM-DD.md)`.
   On the following line retain the same absolute briefing path as plain text for
   clients that do not render local links. Do not link the manifest or status file in
   the normal reply.

Do not read a session's whole history in this branch. Apart from the one existing
prior-date `SNAPSHOT` reconciliation above, do not read prior-date content. Do not use Chromium data under
`AppData\\Roaming\\Codex` as a conversation source.

### Explicit history branch

Use this branch only when the user writes one of the following:

- `$daily-report --history <date-range>`
- `$daily-report --history --project <path>`
- `$daily-report --history --session <id>`
- `$daily-report --history all`

Require a scope for every history request except the exact `--history all` form.
Apply the same redaction rules and report every session and date range read. Historical
reports are evidence only; never promote them automatically to a formal Handoff or
Lesson.

## Recovery and failure rules

- Treat a missing primary report as recoverable. Preserve the report's business date
  and add `recovered_at` when a later run creates it.
- Continue when an individual session cannot be read or summarized. Record that
  session as `FAILED` in the briefing and status record.
- Set the overall result to `COMPLETE_WITH_FAILURES` when other required outputs
  succeed. Do not retry those failed sessions unless a future explicit
  `--retry-failed` command is implemented.
- Overwrite a report only through an atomic successful write after watermarks show a
  new session or changed user-message count / `last_user_message_at`. Record a new
  `generated_at` and `run_id` for the new run, while retaining any `recovered_at` value.
- Never claim the scheduled automation works while Codex is closed until the project
  validation plan has proven it.

## Boundaries

- Never create or modify a Codex conversation, send a message to another thread, or
  publish a report externally.
- Never include raw prompts, reasoning, full tool output, secrets, credentials, or
  personally identifying data in the generated reports.
- Do not alter the existing `handoff` or `grill-me` skills.

## Project material

Use project-level documents beside this skill for development decisions, tests, task
scope, and changelog history. Do not copy those documents into this skill.
