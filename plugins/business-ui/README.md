# Business UI Plugin

可复用的 **Business UI** 扩展：在聊天摘要卡中打开已发布的外部业务表单，在侧栏 iframe 中编辑/保存/提交，再通过已认证 Host action 拉取可信收据并**原地更新同一 `callId` 卡片**。

本目录是 **插件 + 参考 Adapter**，不是 Octop 宿主补丁，也不是客户生产系统对接。

开发分支、路径门禁、以及每次 Octop 上游升级后必须复检的宿主契约：见 [docs/branch-policy.md](docs/branch-policy.md)。

## 不是什么

- 不是表单设计器、平台选择器、按单据硬编码页面
- 不是共享管理员身份登录业务系统
- 不是 Adapter → Octop webhook
- 不是 Casdoor / `src/octop` / `dashboard/` 修改
- **不是** Octop 登出后立即作废业务会话（见下方 UNSUPPORTED）

## 安装（`OCTOP_HOME` 布局）

Octop 数据根目录：

| 环境 | 路径 |
|------|------|
| 默认 | `~/.octop` |
| 自定义 | `$OCTOP_HOME`（例如用户环境 `/data` → `/data`） |

插件安装位置：**`$OCTOP_HOME/plugins/business-ui/`**（默认 `~/.octop/plugins/business-ui/`）。

1. 使用管理员账号在 Dashboard 上传 `business-ui.zip`，或：
2. `octop` 插件上传 API：`POST /api/plugins/upload`（管理员）。
3. ZIP 内必须是**一个**带 `plugin.yaml` 的 `business-ui/` 目录。
4. 重启或等待插件加载后，Agent 即可使用工具 `business_ui_draft` / `business_ui_connections`；只读工具 `business_ui_receipt` 按 `interactionId` 取已核验收据，不会自动继续流程。

前端 UI 为预构建 ESM：`ui/index.js` + `ui/manifest.json`（路径避开仓库根 `dist/` gitignore），无需改 Dashboard。

## 全局环境变量（推荐多实例，不经过聊天）

约 10 台 Octop 用 Dashboard **高级设置 → 环境变量**（或进程环境）落下 Adapter URL 与用户授权方式，不必在聊天里填配置卡。密钥禁止写进 `BUSINESS_UI_*` 值（会进 agent shell / MCP）；只用绝对路径 `*_FILE`（0600）。每位用户仍要单独激活。

Plugin Management 详情抽屉只显示 `plugin.yaml` 的 **description**（列表卡片两行截断；抽屉是普通段落，无 Markdown）。中文键名/必填/生效方式写在该字段；完整表如下，可复制模板见 [docs/env-deploy.md](docs/env-deploy.md) 与 [docs/env.template](docs/env.template)。

| 变量 | 必填性 | 用途 |
|------|--------|------|
| `BUSINESS_UI_BASE_URL` | 已设后必填；未设则跳过引导 | HTTPS Adapter 基址 |
| `BUSINESS_UI_INSTANCE_ISSUER` | 已设后必填 | 本实例 https 源 |
| `BUSINESS_UI_OPERATOR_USER_ID` | 已设后必填 | 本地 admin 数字 user_id |
| `BUSINESS_UI_SERVICE_SECRET_FILE` | 已设后必填 | 服务密钥绝对路径 |
| `BUSINESS_UI_CONNECTION_ID` | 可选，默认 `default` | 稳定连接 id |
| `BUSINESS_UI_DISPLAY_NAME` | 可选，默认等于 CONNECTION_ID | 显示名 |
| `BUSINESS_UI_AUTH_METHOD` | 可选，默认 `api_token` | `api_token` / `authorization_code` |
| `BUSINESS_UI_USER_AUTH_METHOD` | 可选，默认 `oauth2` | `oauth2` / `native_login` / `personal_access_token` |
| `BUSINESS_UI_ENABLED` | 可选，默认 `1` | `0`/`false`/`off` 停用 |
| `BUSINESS_UI_OAUTH_SCOPES` | 可选，默认 `openid profile` | OAuth scopes |
| `BUSINESS_UI_OAUTH_CLIENT_ID` | oauth2 条件必填 | client id |
| `BUSINESS_UI_OAUTH_DISCOVERY_URL` | oauth2：discovery 或 authorize+token | discovery URL |
| `BUSINESS_UI_OAUTH_AUTHORIZE_URL` | oauth2 无 discovery 时与 token 成对 | 授权 URL |
| `BUSINESS_UI_OAUTH_TOKEN_URL` | oauth2 无 discovery 时与 authorize 成对 | token URL |
| `BUSINESS_UI_OAUTH_REVOKE_URL` | 可选 | 吊销 URL |
| `BUSINESS_UI_OAUTH_CLIENT_SECRET_FILE` | 可选 | 机密客户端 secret 文件 |
| `BUSINESS_UI_PRIVATE_ALLOW` | 可选 | 内网/回环 CIDR |
| `BUSINESS_UI_EXTRA_ORIGINS` | 可选 | 额外 origin |
| `BUSINESS_UI_TLS_CA_FILE` | 可选 | 自签 CA |

最小 native_login 模板：

```
BUSINESS_UI_BASE_URL=https://adapter.example.com
BUSINESS_UI_INSTANCE_ISSUER=https://octop.example.com
BUSINESS_UI_OPERATOR_USER_ID=1
BUSINESS_UI_SERVICE_SECRET_FILE=/etc/octop/business-ui/service.token
BUSINESS_UI_USER_AUTH_METHOD=native_login
```

Dashboard 保存环境变量立刻生效、不必重启；只改 `~/.octop/env` 磁盘或进程 `-e` 须重启。环境页无 Test：`python -m business_ui test`。

## 配置卡（插件自有；Plugin Management 无表单）

管理员也可在聊天中调用 `business_ui_connections`（或让模型打开配置卡）。`managed_by=env` 的连接只读，聊天不能改 URL/授权方式或删除：

| 字段 | 说明 |
|------|------|
| 显示名 | 普通用户下拉可见 |
| HTTPS Adapter 基址 | 已批准业务端点，禁止 URL 用户信息/fragment |
| 服务身份 | **可复用 API token** 与 **一次性授权码**（Octop↔Adapter 连接，不是用户登录） |
| 服务密钥 | 仅本表单掩码输入 → 已认证 `connections.save` → Host `stage_credential`。不进 tool args、聊天、`plugin_records`、localStorage |
| 用户授权方式 | 管理员三选一，**不绑定 Casdoor**：① 标准 OAuth2/OIDC authorization code + PKCE（任意合规 IdP：discovery 或 authorize/token/可选 revoke、client id/secret、scopes）；② 业务系统原生账号（插件表单 POST 到 Adapter，密码不保存）；③ 个人访问令牌 |
| OAuth 端点 | discovery 或显式 URL；IdP 若不同源须写入额外 origin |
| 额外 origin | 默认仅基址同源；仅当确实需要时由管理员精确批准 |
| 私网例外 | 显式 host/CIDR，**不是**一键放行全部私网。链路本地/云 metadata 永远拒绝 |
| 可选 TLS CA | 内网自签证书 PEM，随凭据加密存储 |
| Test Connection | 分阶段：DNS/可达、服务身份、协议版本与能力、**报告 Adapter 支持的 user_auth_methods** 并校验已选方式。**浏览器嵌入不做服务端绿灯**。任意网站 HTML/登录页记为 unsupported |

管理员角色来自 Host：`users.role == admin`（JWT `PluginActor.is_admin` + action `permission=admin` + `reauthorize_actor`）。前端 flag / 模型参数无效。

普通用户不能改连接密钥。**每位用户必须单独激活**（Activate / 重新连接 / 断开），令牌 per-user 存在 Host 凭据，绑定宿主校验的当前用户，永不进 URL/聊天/日志。未激活时卡片显示「需要激活/重新激活」。

服务凭据只证明 **Adapter 连接**，不能读取其他用户单据。主体为 `issuer|local_user_id`（实例 issuer + 本地用户整数，跨实例不碰撞）。宿主无插件 OAuth 回调：PKCE verifier 存 Host 凭据，Adapter 托管 `/v1/oauth/callback`，插件用服务凭据 consume 一次性 code。

## 样例 UX（招聘两名实施顾问）

仅作 **参考 Adapter 样例表单**，泛化核心只认逻辑 `formRef`（如 `generic.request.edit`），不写死招聘。

1. 模型调用 `business_ui_draft` → 摘要卡「核对并编辑 / 取消」。**草稿 ≠ 授权**，模型不得宣称已提交。
2. 用户选择已批准连接并点「核对并编辑」→ `interactions.claim` 用 Host 校验的当前用户 + `agent_id`/`thread_id` 绑定 `callId`。
3. 侧栏 iframe：插件 `POST` 一次性 ticket（不把 token 放进 URL）兑出表单。
4. 用户保存 ≠ 提交。提交后插件 `interactions.get` 拉收据，**同一 callId 卡变为已提交**（不追加新卡）。
5. 侧栏导航只读正式详情。关闭侧栏再开仍走详情。历史卡重新打开查询权威最新状态。
6. 提交后卡片变为统一 **BusinessReceiptCard**（SUCCESS / 业务拒绝 / 技术失败或 UNKNOWN），按 `interactionId` 原地更新同一 `callId`。
7. 成功且侧栏仍在编辑态时切只读详情；否则点「查看正式单据」。历史打开走 `interactions.lookup`，不改写聊天记录。

## 参考 Adapter（协议夹具，非生产）

```bash
cd plugins/business-ui
python -m adapter --host 127.0.0.1 --port 8443 --token dev-connection-token
```

自签证书仅供本地/测试。配置连接时粘贴 CA PEM，并把 `127.0.0.1/32` 写入私网例外。

招聘 `recruitment.request.*` 只存在于该参考服务的表单注册表。

## UNSUPPORTED（验收缺口，不实现宿主钩子）

**Octop 登出 → 业务会话立即作废：当前宿主零改动下不支持。**  
本插件不伪造 logout webhook。业务侧必须独立做会话过期、账号停用与权限重检。浏览器第三方 cookie / iframe CSP / `SameSite` 需在目标浏览器实测；**仅 POST 兑票不能保证 cookie 写入。**

## 构建 ZIP

```bash
python plugins/business-ui/scripts/pack_zip.py
# → plugins/business-ui/dist/business-ui.zip
```
