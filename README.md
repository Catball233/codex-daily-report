# Daily Report for Codex

将当天实际推进过的 Codex 工作，整理成一份可追溯、脱敏、可朗读的中文日报。

它不是“总结当前窗口”的小工具。它会在本机范围内查找当天有用户消息的
Codex 会话，分别生成简短 handoff，再汇总为 briefing；你仍然掌握触发时间、
输出位置和历史读取范围。

## 快速开始

1. 克隆或下载本仓库。
2. 选择一种安装方式：

   - **手动复制**：将 `daily-report-skill/` 安装为 Codex 全局 skill：

     ```powershell
     $codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME '.codex' }
     $destination = Join-Path $codexHome 'skills\daily-report'
     New-Item -ItemType Directory -Path $destination -Force | Out-Null
     Copy-Item -Path '.\daily-report-skill\*' -Destination $destination -Recurse -Force
     ```

   - **交给 IDE**：直接在支持 agent skills 的 IDE 中打开本仓库，并让 agent 将
     `daily-report-skill/` 安装到 `$CODEX_HOME/skills/daily-report`。不需要手动理解
     项目计划或脚本；安装后按下一步调用即可。

3. 在 Codex 中输入：

   ```text
   $daily-report
   ```

4. 打开回复中的日报链接。默认产物位置是：

   ```text
   %LOCALAPPDATA%\daily-report-skill
   ```

`$daily-report` 是唯一普通入口；不要使用 `$daily-report-skill`。默认只读取
当天（Asia/Shanghai）活动过的会话。读取历史时必须明确给出范围，例如：

```text
$daily-report --history 2026-07-20..2026-07-21
$daily-report --history --session <session-id>
$daily-report --history all
```

## 为什么需要它

多窗口并行工作时，最容易丢失的是“今天到底推进了什么、证据在哪、明天从哪里继续”。
Daily Report 将这些信息压缩为两层记录：

- 每个会话一份脱敏 handoff：目标、完成事项、验证证据、阻塞、下一步与关联文件。
- 一份总 briefing：按“项目名｜窗口名”归并工作，并附 2–3 分钟中文朗读稿。

它刻意不替你接管项目管理流程：不创建会话、不发送消息、不发布内容，也不会把日报
自动升级为正式 Handoff 或 Lesson。

## 日常使用

### 手动生成

任何时候运行 `$daily-report`。首次生成当天报告时状态为 `SNAPSHOT`；同日再次运行会
比较每个会话的用户消息数和最后消息时间，只有新增内容才重写。没有增量时会直接返回
既有日报。

下一次调用会先复查最近一个未封存的前日 `SNAPSHOT`，必要时按原日期补写并封存为
`FINAL`。这避免把晚间新增内容错误算入次日。

### 定时生成

在 Codex 的“已安排任务”中创建“新任务”，选择你希望的项目、频率和时间。提示词只需：

```text
执行已安装的 $daily-report。
```

时间、工作日和频率完全由 Codex Scheduled UI 控制；skill 不内置 18:45、工作日或
“周末归入周一”规则。尚未验证 Codex 关闭时的离线触发行为，因此不要把它当作后台服务。

## 输出

默认目录结构：

```text
%LOCALAPPDATA%\daily-report-skill\
├── briefings\YYYY-MM-DD.md
├── handoffs\YYYY-MM-DD\
│   ├── <session-id>-<title>.md
│   └── manifest.json
└── status\YYYY-MM-DD.json
```

最终回复只链接 briefing，并同时给出可复制的纯文本路径；`manifest.json` 与状态文件保留在
本地，供排查或后续自动化读取。若需要改变存储位置，设置 `DAILY_REPORT_ROOT`；临时运行可
由调用方显式传入 `--report-root`。

## 它会读什么，不会读什么

默认范围是目标北京时间当天至少有一条用户消息的本机 Codex 会话，包括当天继续的旧会话。
它保留其他 automation 会话，但会自动排除“正在运行日报”的 Scheduled 任务本身，避免报告递归。

默认不会读取前日内容、浏览器存储或完整历史。历史读取必须使用显式 `--history` 范围。生成的
报告不包含原始 prompt、模型推理或完整工具输出；密码、密钥、token、cookie、邮箱、手机号和常见
证件/银行卡信息会被脱敏。

## 适配与验证

所有面向人的报告使用简体中文。写入器通过原子提交写入报告，并在单个会话失败时继续处理其他会话，
将总体状态标记为 `COMPLETE_WITH_FAILURES`。

Windows 用户请注意：不要通过 PowerShell stdin 或默认编码的 `Get-Content` 将中文 JSON 管道传给
Python；请使用 UTF-8（可带 BOM）临时文件和 `--input-file`。否则中文可能在写入前变成 `?`。

## 许可证

本项目采用 MIT License，可用于使用、修改与再分发。

## 开发者自定义（可选）

如果你 fork 本仓库并需要适配自己的目录、摘要格式或调度策略，可修改
`daily-report-skill/` 后重新同步到 `$CODEX_HOME/skills/daily-report`，再用本机会话做回归验证。
