# 源码扫描证据（实施前阶段门）

**扫描 UTC：** 2026-11-10T23:35:00Z（代码未写）  
**复验 UTC：** 2026-11-11T00:20:00Z `git fetch origin feature/ver1.0`  
**origin/feature/ver1.0 HEAD：** `116b57db97bcbba4e10dae9ad82142656d039d07`  
**实现分支：** `cursor/business-ui-plugin-a7f2`（从上述 SHA 切出，未 rebase/force-push）

完整仓库级盘点见 `/opt/cursor/artifacts/business-ui-plugin-source-scan.md`。本文件是插件树内副本要点。

## 覆盖声明

未宣称逐行读完仓库。盘点了包布局、插件加载、Host、Dashboard renderer/Dock、JWT/admin、凭据 CAS、聊天历史、登出/OIDC；深读与本功能相关的调用链。

## 已核实、实际使用的 Host 面

- `register_host_setup` + `register_action(..., permission in {authenticated,admin,agent_owner})`
- `PluginActor`：HTTP 层 `user.is_admin` ← `users.role == admin`；`context.agent_id/thread_id` 由宿主校验线程 `user_id`
- `reauthorize_actor`：停用账号、角色刷新
- `stage_credential` / `commit` CAS / `resolve_credential` / `get_record` / `list_records`
- UI：`registerRenderer` `getToolContext` `patchResult` `request` `openSidePanel` `closeSidePanel`
- 安装：ZIP → `$OCTOP_HOME/plugins/{id}`；ESM `GET /api/plugins/{id}/ui`

## 明确不用 / 不存在则失败关闭

- 生产 ExecutionTicket 不用于草稿授权 → claim 只走 HTTP + 宿主 scope
- 无 Host iframe API → 插件自绘 iframe（与 Dock 同一 React 树）
- 无 Adapter→Octop webhook → 拉收据
- 无登出通知钩子 → **不实现、不伪造**
- 无 `registerSurface` 设置页 → 配置卡用 `octop_ui` renderer
- 不 import 私有 repo / 不改 `src/octop` / `dashboard` / Casdoor
