# Business UI 分支策略与上游契约

分支 **`cursor/business-ui-plugin-a7f2`** 只做 **Business UI Adapter / 插件**。

| 允许 | 禁止 |
|------|------|
| `plugins/business-ui/**` | `src/octop/**`、`dashboard/**`、Casdoor |
| `tests/unit/plugins/test_business_ui_*.py` | 改聊天历史、JWT 路由、Plugin Host、CSS 主题实现 |

零宿主 diff，以免拖累后续 Octop 上游 merge。PR **不要合并进宿主主干**，除非另有明确发布流程。

本插件**消费**下列宿主契约，**不修改**它们。每次把本分支 rebase / merge 到新的 Octop 上游之后，必须按下表复检。

## 宿主依赖清单

| 路径 | 本插件依赖的契约 |
|------|------------------|
| `dashboard/src/plugins/toolRenderers/types.ts` | `OctopPluginUIHost` 六个方法：`registerRenderer`、`getToolContext`、`patchResult`、`request`、`openSidePanel`、`closeSidePanel`。`OpenSidePanelOptions` 为 `{ callId, title?, toolName? }`。`PluginUiModule.setup(host)`。 |
| `dashboard/src/plugins/toolRenderers/host.ts` | `createPluginUiHost` 把 `patchResult` 转到 `chatStore.patchToolResultData`；`openSidePanel` / `closeSidePanel` 走 `setPluginUiDockHandlers`；`getToolContext().theme` 读 `html[data-theme]`。 |
| `dashboard/src/pages/Chat/hooks/chatStore.ts` | `patchToolResultData(callId, nextData)`：**内存**改写当前会话工具气泡 `output`（经 `mergePatchedToolOutput` 写入 JSON `data`），不写库。失败不得当后端失败。 |
| `dashboard/src/plugins/toolRenderers/parseToolOutput.ts` | `mergePatchedToolOutput` / `resolvePluginUiData`：`patchResult` 只替换 `data`，保留 `octop_ui`。 |
| `dashboard/src/plugins/toolRenderers/loader.ts` | 已认证 fetch + blob `import()` 自包含 ESM。`plugin.yaml` `ui.entry` 相对 `ui/`；本插件显式 `ui/index.js`（根 `dist/` gitignore）。 |
| `dashboard/src/plugins/toolRenderers/ensureBuiltins.ts` | `window.__OCTOP_REACT__` / `window.__OCTOP_JSX__`，供 `ui/build.mjs` host-react shim。 |
| `dashboard/src/pages/Chat/index.tsx` | `setPluginUiDockHandlers({ openSidePanel: openToolUiTab, closeSidePanel })`。 |
| `dashboard/src/pages/Chat/hooks/useChatDockPanel.ts` | `openToolUiTab({ callId, title?, toolName? })` 按 `callId` 去重侧栏 tab。 |
| `dashboard/src/pages/Chat/components/ChatDockToolUiContent.tsx` | 侧栏按 `callId` 渲染**同一**工具 UI（edit / 只读详情同源）。 |
| `dashboard/src/pages/Chat/hooks/useToolMessageByCallId.ts` | 侧栏订阅 `chatStore` 里该 `callId` 的工具消息；`patchResult` 后详情必须跟着变。 |
| `dashboard/src/styles/theme-vars.css` | `html[data-theme="light\|dark"]`。卡片用 `--ant-color-*`（Ant Design 注入，带 fallback）；升级后 dark/light 与侧栏宽度自适应不能坏。 |
| `src/octop/infra/db/repos/thread_messages.py` | `append_if_ready` **只追加**。收据更新禁止改 `thread_messages`。 |
| `src/octop/infra/history/service.py` | `HistoryArchive` 投影/归档只读组合；`interactions.lookup` 不改写历史。 |
| `src/octop/api/routers/chat/history.py` | Dashboard 历史 REST 无按 `callId` PATCH 工具 `output` 的接口。 |
| `src/octop/api/routers/plugin_actions.py` | JWT：`GET /api/plugins/{id}/actions`，`POST /api/plugins/{id}/actions/{name}`，信封 `{ api_version: 1, context?, payload }`。身份来自 `current_user`，不是模型参数。 |
| `src/octop/api/routers/plugins.py` | `prefix=/plugins` 挂到 `/api`。`GET /{plugin_id}/ui/{file_path}` 提供 ESM；`POST /upload` 安装 ZIP。 |
| `src/octop/infra/agents/plugins/host.py` | `register_host_setup`；`PluginHostFacade.register_action`（`permission` ∈ `authenticated\|admin\|agent_owner`）；`register_read_only_tools`；`register_background_worker`；`reauthorize_actor`；`current_execution`；`get_record` / `list_records`；`stage_credential` + `commit` CAS。 |
| `src/octop/infra/utils/env_file.py` | `apply_env_file`（启动合并，不删缺键）；`apply_env_file_replace`（Dashboard PUT 立刻改 `os.environ`）；`overlay_stdio_spec_env` 把非 `OCTOP_*` 键拷进 MCP stdio。`BUSINESS_UI_*` 会泄漏到 shell/MCP，故密钥只用 `*_FILE`。 |
| `src/octop/api/routers/envs.py` | `PUT /api/envs` 写 `~/.octop/env` 并 `apply_env_file_replace`；仅 `SEARCH_ENV_KEYS` 触发 agent reload。`BUSINESS_UI_*` **不必重启**即可被插件下次 sync 读到。磁盘直改 `~/.octop/env` 仍要重启。 |
| `src/octop/infra/agents/plugins/host_contracts.py` | `PluginActor`（`user_id`、`is_admin`、`agent_id`、`thread_id`）；`RecordWrite` / `RecordCheck`（`expected_revision`）；`CredentialActivation` / `CredentialDeletion`；`PluginActionError`。 |
| `src/octop/infra/db/repos/plugin_records.py` | `PluginRecordRepo.cas`：`expected_revision==0` INSERT，否则按 revision UPDATE。权威交互状态在此，不在聊天行。 |
| `src/octop/infra/agents/plugins/manager.py` | `PluginManifest.load`；`parse_plugin_ui_meta` 读 `plugin.yaml` 的 `ui.entry` / `ui.manifest`（缺省曾是 `ui/dist/index.js`）。`list_installed` 把 `manifest.description` 原样交给 Dashboard，无独立长描述字段。 |
| `dashboard/src/pages/Admin/Plugins/InstalledPluginsPanel.tsx` | 已安装卡片 `.cardDesc` **两行** `-webkit-line-clamp: 2`；详情抽屉 `<p class=drawerDesc>`，无 Markdown、无 `white-space: pre-wrap`。本插件把中文 `BUSINESS_UI_*` 引导写进 `plugin.yaml` `description`，不改此 CSS。 |
| `octop_harness.plugins.PluginManifest` | `plugin.yaml` 必填 `id`+`version`；`kind=tool`；`entry=main.py`；`requires` 为 pip 列表。Octop 额外键：`ui`、`icon`、`group`。 |

## 上游升级后的验证步骤

在记录「旧上游 SHA」与「新上游 SHA」后执行：

1. **插件测试**

   ```bash
   uv run pytest tests/unit/plugins/test_business_ui_*.py -q
   cd plugins/business-ui/ui && npx vitest run
   ```

2. **兼容 / 契约测试**（同目录 `test_business_ui_host_contract.py`）：断言上表文件仍暴露本插件用到的符号与方法，不改宿主代码。

3. **git diff 宿主契约面**（旧 SHA → 新 SHA）。有语义变化则先适配插件，再继续：

   ```bash
   git diff <old>..<new> -- \
     dashboard/src/plugins/toolRenderers/types.ts \
     dashboard/src/plugins/toolRenderers/host.ts \
     dashboard/src/plugins/toolRenderers/loader.ts \
     dashboard/src/plugins/toolRenderers/ensureBuiltins.ts \
     dashboard/src/plugins/toolRenderers/parseToolOutput.ts \
     dashboard/src/pages/Chat/hooks/chatStore.ts \
     dashboard/src/pages/Chat/hooks/useToolMessageByCallId.ts \
     dashboard/src/pages/Chat/hooks/useChatDockPanel.ts \
     dashboard/src/pages/Chat/components/ChatDockToolUiContent.tsx \
     dashboard/src/pages/Chat/index.tsx \
     dashboard/src/styles/theme-vars.css \
     src/octop/infra/db/repos/thread_messages.py \
     src/octop/infra/history/service.py \
     src/octop/api/routers/chat/history.py \
     src/octop/api/routers/plugin_actions.py \
     src/octop/api/routers/plugins.py \
     src/octop/infra/agents/plugins/host.py \
     src/octop/infra/agents/plugins/host_contracts.py \
     src/octop/infra/db/repos/plugin_records.py \
     src/octop/infra/agents/plugins/manager.py \
     src/octop/infra/utils/env_file.py \
     src/octop/api/routers/envs.py \
     dashboard/src/pages/Admin/Plugins/InstalledPluginsPanel.tsx \
     dashboard/src/pages/Admin/Plugins/index.module.less
   ```

4. **浏览器冒烟**（Dashboard 已加载本插件 UI）：草稿卡 → 认领 → 侧栏兑票 → 提交后**同一 `callId`** 变为 `BusinessReceiptCard`；成功且侧栏仍为 edit 时切只读详情；历史打开走 `interactions.lookup`（允许短暂草稿闪烁）；dark/light；UNKNOWN 只出现「查询状态」不自动重提。

路径门禁：`git diff --name-only <base>...HEAD` 只能出现 `plugins/business-ui/` 与 `tests/unit/plugins/test_business_ui_*.py`。
