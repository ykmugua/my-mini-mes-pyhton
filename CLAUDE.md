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
