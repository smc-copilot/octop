# 实施前需求矩阵（副本）

来源：`/opt/cursor/artifacts/business-ui-plugin-requirements-matrix.md`  
Base SHA `116b57db97bcbba4e10dae9ad82142656d039d07`。

| 需求 | 宿主能力 | 实现落点 | 缺口 |
|------|----------|----------|------|
| 摘要卡 核对并编辑/取消 | octop_ui + registerRenderer | 插件 ESM `business_ui_card` | — |
| 侧栏外部表单 | openSidePanel + 插件 iframe | dock 内 iframe | 无宿主 iframe API（不阻断） |
| 可信收据同一 callId | actions + plugin_records + hydrate | get_interaction overlay | 归档 PATCH 不做 |
| 七字段 / formRef 注册表 | 插件+Adapter | 服务端 resolve | — |
| 草稿非授权 | 无 ExecutionTicket | claim 仅 HTTP+宿主 thread | — |
| 管理员配置卡 | permission=admin | 插件配置卡 renderer | 不改 Plugin Management |
| 全局 env 引导连接 | `PUT /api/envs` / 进程 env | `BUSINESS_UI_*` + `*_FILE` + `env_sync` | 环境页无 Test 按钮 |
| 密钥 Host 凭据 | stage_credential | 仅 action POST | 不进 records/聊天 |
| 每用户激活（OAuth2/原生/PAT） | 凭据 owner=JWT 用户 | `activations.*` + Adapter AS | 无宿主 callback（Adapter 托管） |
| 连接握手 | 插件出站 HTTPS | Adapter /v1/handshake | 浏览器嵌入门未测则不绿 |
| SSRF | 插件自实现 | 显式 CIDR 例外 | 无 blanket 内网 |
| 登出即死 | 无 | 不实现 | **UNSUPPORTED** |
| 业务撤权 | Adapter 每次 save/submit/detail | 独立执行 | — |
