# Changelog

## 2026-07-20 — 修复新建 Scheduled 缺失自身 session ID

- 不再因新 Scheduled 任务的初始上下文缺少 `memory.md` 或自身 session ID 而安全停止。
- 枚举器仅在本地会话结构表明 `thread_source=automation`、且 scheduler 注入指令同时包含 `Automation ID:` 与日报调用标记时，排除日报自身任务；不排除其他 automation 会话。
- 该判断只在内存中产生布尔值，`excluded_sessions` 只记录稳定 ID 与 `daily_report_automation_signature` 原因，不写出原始指令。
- 已用本机 2026-07-20 会话验证：2 个日报 automation 被排除，1 个非日报 automation 仍被纳入。

## 2026-07-20 — 水位线复扫、前日封存与 automation 自身排除实现

- `$daily-report` 的默认内部流程改为：先复扫最近一个已有的前日 `SNAPSHOT`，再创建或复扫当天 `SNAPSHOT`；不增加新的显式命令。
- 会话枚举脚本新增重复 `--exclude-session-id`，按稳定 ID 记录并排除 automation/new-task 自身任务。
- 报告写入器新增水位线比较 `--check-delta` 和仅状态封存 `--finalize-existing`；状态记录 `phase`、会话水位线、封存时间、排除 ID 和失败详情。
- 已通过隔离回归：自身排除、水位线增量/无增量、前日无增量封存、中文 UTF-8 输入和脱敏。真实 Scheduled 自身排除验证待执行。

## 2026-07-20 — 快照、增量复扫与自身排除计划

- 确认唯一显式调用为 `$daily-report`；不创建或支持 `$daily-report-skill`。
- 计划将日报状态扩展为兼容既有 `state` 的 `SNAPSHOT` / `FINAL` 阶段，并以每会话 `last_user_message_at` 与用户消息数作为增量水位线。
- 计划使每次 `$daily-report` 先封存已有前日快照、再处理当天；无增量时不改写并返回覆盖完成提示。
- 计划按稳定 session ID 排除当前 automation/new-task 自身，修复 automation 报告自身的行为。

## 2026-07-20 — 注释代码与业务链路

- 在根目录新增 `注释代码/`，提供与当前两份生产脚本逻辑一致、仅补充解释性注释的源码副本。
- 新增 `注释代码/skill的业务链路.md`，说明 Scheduled 触发、会话筛选、结构化摘要、脱敏写入、状态提交与显式重跑边界。

## 2026-07-20 — 触发时间由 Codex Scheduled 控制

- 移除 skill 内固定的 18:45、工作日与“周末补充到周一”规则；Codex Scheduled 任务的 UI 配置成为唯一触发时间来源。
- 默认枚举不再应用时间边界；保留可选 `--cutoff` 作为显式调用者提供的兼容性边界。
- 将活跃状态从 `active_at_cutoff` 改为 `active_at_report_run`，报告文字改为“生成时状态”。

## 2026-07-20 — Windows PowerShell 中文输入修复

- `write_report_bundle.py` 新增 `--input-file`，以 UTF-8 或 UTF-8 with BOM 读取结构化 JSON。
- skill 与运行契约禁止通过 Windows PowerShell stdin 管道或 `Get-Content` 转发 JSON，避免中文在写入前被替换为 `?`。

## 2026-07-20 — 发布前可移植性与一致性修复

- 会话枚举默认尊重 `CODEX_HOME`，未设置时回退至 `~/.codex`；显式会话根目录参数也支持环境变量展开。
- 删除分发 skill 与能力规格中的个人 Windows 用户路径；改用 `$CODEX_HOME` / `~/.codex` 表达会话位置。
- 同日重跑改为记录新的 `generated_at` 与 `run_id`，并从既有状态文件保留 `recovered_at`。
- 更新根 README 以反映已实现脚本，并适配 `project plan/` 文档目录。

## 2026-07-20 — 分发默认产物目录

- 将分发默认报告根目录改为 `%LOCALAPPDATA%\daily-report-skill\`，不再假设用户存在 `D:` 盘或 `OtherDev` 工作区。
- 新增 `DAILY_REPORT_ROOT` 环境变量覆盖；保留写入器现有的显式 `--report-root` 单次覆盖。
- 补充默认目录与覆盖优先级的规格、测试契约和文件范围；不包含 Trae 的会话读取或调度适配。

## 2026-07-15 — 初始化

- 创建项目总目录和 `daily-report-skill`。
- 记录已确认的日报、历史检阅、脱敏、保留、失败和补跑规则。
- 建立裁剪后的 harness 计划、测试契约、文件范围和开发任务。
- 未实现会话采集、报告生成、Codex Automation 或 Windows 补跑任务。
- `skill-creator` 的 `quick_validate.py` 已尝试执行，但 Bundled Python 缺少 `PyYAML` 而被阻塞；已完成 frontmatter、必需文件、TODO 占位符和文档引用的手动结构检查。

## 2026-07-15 — 显式入口调整

- 保留目录名 `daily-report-skill`，将显式调用名调整为 `$daily-report`。
- 明确 `$daily-report` 在截止后检查当日报告：完整则返回现有产物，缺失或失败才生成/补跑。
- 明确截止前调用不生成最终日报。

## 2026-07-15 — 调度与失败语义收口

- 确认主调度采用 Codex 界面的“已安排任务”，以“新任务”运行于 `OtherDev` 项目。
- 明确单会话失败后的总体状态为 `COMPLETE_WITH_FAILURES`；`$daily-report` 返回既有日报，不自动重试。
- 新增未来显式 `--retry-failed` 的边界，并补充对应测试。
- 修正实现前文件范围的歧义；新增 90 天单窗口摘要清理任务。

## 2026-07-15 — DR-T02 调度探针

- 成功创建并删除一次性“新任务”本地 Automation 探针。
- 在计划时刻后未观察到独立执行线程或本地执行日志；未验证项目 skill 读取和线程工具调用。
- DR-T02 标为 blocked，未扩展脚本、报告输出或生产调度的文件范围；详见 `DR-T02_EVIDENCE.md`。

## 2026-07-15 — DR-T02 人工复验通过，进入 DR-T03

- 用户人工验证 Scheduled 独立新任务按设定时间执行，并成功调用全局 `$handoff`。
- 更正先前对普通线程列表的错误验收方式：独立任务结果应在 Scheduled 查看。
- 解除 DR-T03 所需的最小脚本范围，开始实现北京时间日内会话枚举。

## 2026-07-15 — DR-T03 完成

- 新增 `scripts/enumerate_daily_sessions.py`：递归读取本机 session JSONL，以稳定会话 ID 聚合，不输出消息正文、推理或工具输出。
- 默认范围按北京时间、用户消息和 18:45 截止筛选；延续会话不会因创建日期较早而遗漏。
- `active_at_cutoff` 只接受调用方在截止时刻取得的线程状态快照，JSONL 无法证明活跃时明确标为未观察。
- Windows 默认 Python 缺少 IANA tzdata 时，脚本披露并使用 UTC+08:00 兼容回退；当前及 1991 年后的中国标准时间有效。
- 真实验证通过：多会话、旧会话当日继续、active 状态传播与截止后消息分流均有本机证据。
- 默认日报分支已明确为读取全部纳入会话的当日必要内容，而非只读取 Scheduled 新任务自身上下文。

## 2026-07-15 — DR-T04 完成

- 新增 `scripts/write_report_bundle.py`：只接受结构化摘要，拒绝原始 transcript、推理和工具输出字段，并对常见密钥、token、邮箱、手机号、证件和银行卡模式脱敏。
- 状态文件先写入 `WRITING`，仅在所有单会话摘要、manifest 和总日报成功写入后提交 `COMPLETE` 或 `COMPLETE_WITH_FAILURES`。
- 隔离真实写入验证覆盖失败会话继续、脱敏、原始字段拒绝和同日重跑清除旧摘要。

## 2026-07-15 — 中文日报与朗读稿

- 规定所有面向人的日报叙述使用简体中文，保留 ID、路径、时间戳、代码标识和状态常量原样。
- briefing 的完成事项、阻塞和下一步将标注“项目名｜窗口名”。
- 新增“朗读日报”的大纲与 2–3 分钟中文文本契约；写入器校验朗读文本长度为 350–900 个非空白字符。
- 已同步更新全局安装的 skill 和工作日 Scheduled 任务提示词；变更从下一次生成生效。

## 2026-07-15 — 中文重生成包与 DR-T05 验证

- 用户确认首个工作日 Scheduled 主任务正常生成报告，DR-T05 通过。
- 未覆盖原始英文包；在 `D:\OtherDev\codex-daily-reports\regenerated-2026-07-15-zh-CN\` 生成独立中文版本。
- 中文包包含 7 个单会话摘要、按“项目名｜窗口名”标注的 briefing，以及大纲和朗读文本。
