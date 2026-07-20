# Codex Daily Report 项目总文档

本目录承载 `daily-report-skill` 的需求、计划、规格、测试和变更记录。
Skill 本体只保留可复用的运行工作流；开发过程文档全部与 skill 目录平级。

## 当前状态

- 项目类型：Codex 开发支持 skill，不是 QiClaw 运行时业务 skill；目录为
  `daily-report-skill`，显式调用名为 `$daily-report`。
- 当前阶段：已实现会话枚举、结构化摘要写入、脱敏、中文 briefing、朗读日报、
  `SNAPSHOT`/`FINAL` 水位线复扫与 automation 自身 ID 排除；更新后的 Codex Scheduled
  自身排除端到端验证仍需执行。
- 分发默认输出根目录：`%LOCALAPPDATA%\daily-report-skill\`；可通过
  `DAILY_REPORT_ROOT` 或写入器的显式 `--report-root` 覆盖。开发机既有的
  `D:\OtherDev\codex-daily-reports\` 仅作为历史测试产物，不是分发默认值。

## 文档导航

- [project plan/PROJECT_PLAN.md](project%20plan/PROJECT_PLAN.md)：裁剪后的 harness 阶段、交付边界和实施顺序。
- [project plan/CAPABILITY_SPEC.md](project%20plan/CAPABILITY_SPEC.md)：已确认的行为与输出契约。
- [project plan/TEST_CONTRACT.md](project%20plan/TEST_CONTRACT.md)：真实本地验证和验收条件。
- [project plan/FILE_SCOPE.md](project%20plan/FILE_SCOPE.md)：当前允许创建或修改的文件范围。
- [project plan/DEVELOPMENT_TASKS.md](project%20plan/DEVELOPMENT_TASKS.md)：尚未执行的实现任务。
- [注释代码/skill的业务链路.md](注释代码/skill的业务链路.md)：从调度触发到会话筛选、脱敏写入和重跑的业务链路说明。
- [CHANGELOG.md](CHANGELOG.md)：项目变更历史。

## 目录

```text
daily report 总文档/
├── daily-report-skill/
│   ├── SKILL.md
│   ├── agents/openai.yaml
│   ├── references/operation-contract.md
│   └── scripts/
├── README.md
├── project plan/
│   ├── PROJECT_PLAN.md
│   ├── CAPABILITY_SPEC.md
│   ├── TEST_CONTRACT.md
│   ├── FILE_SCOPE.md
│   └── DEVELOPMENT_TASKS.md
├── 注释代码/
│   ├── enumerate_daily_sessions.py
│   ├── write_report_bundle.py
│   └── skill的业务链路.md
└── CHANGELOG.md
```

`daily-report-skill/scripts/` 包含确定性的会话枚举与报告写入辅助脚本。
`注释代码/` 是便于阅读和审阅的注释副本；其 Python 逻辑与当前 production scripts 一致，不能替代 skill 安装目录中的脚本。
