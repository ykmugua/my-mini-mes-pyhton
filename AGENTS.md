# 长期偏好

- 优先使用 PowerShell 7 (pwsh) 执行 PowerShell 脚本和命令；仅当 pwsh 不可用时回退到 Windows PowerShell 5.1。
- 当前机器 pwsh 默认指向商店版 **PS 7.7.0**（C:\Program Files\WindowsApps\Microsoft.PowerShell_7.7.0.0_x64__8wekyb3d8bbwe\pwsh.exe，经 WindowsApps 别名 stub 转发）；另有 MSI 版 7.6.10 在 C:\Program Files\PowerShell\7\pwsh.exe。直接写 pwsh 即可，实测启动本工程脚本正常。

- `/sync-save` 仅当用户主动说出时才执行；我不要自动执行。
---
你有 context-sync MCP 工具。开发过程中：

- 踩坑了 → write_context 写到 gotchas
- 做了架构决策 → 写到 architecture
- 发现 API 特殊行为 → 写到 api_notes
- 完成阶段任务 → 更新 progress
- 仅更新 progress 不等于保存详情；具体踩坑/决策/API 行为必须写入 gotchas / architecture / api_notes，否则 `/sync-load` 只能恢复进度标记
- 用户说 /sync-init、初始化上下文同步、初始化这个仓库的 context sync → 调 sync_init
- 用户说 /sync-save、sync push、保存上下文、上传上下文 → 调 sync_push
- 用户说 /sync-load、sync pull、拉取上下文、恢复上下文、新设备恢复上下文 → 调 sync_load
- `sync_push` / `sync_load` 是内部工具名；对用户统一使用 `/sync-save` 和 `/sync-load`，不要说 `/sync-push`
- 这个 MCP 同步的是项目内 `.context/` 里的结构化上下文，不依赖某一个特定 Agent；因此同一份上下文可以在 Claude、Codex、Gemini 等不同 Agent 之间继续使用
