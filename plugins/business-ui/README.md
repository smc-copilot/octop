# Business UI Plugin

可复用的 **Business UI** 扩展：在聊天摘要卡中打开已发布的外部业务表单，在侧栏 iframe 中编辑/保存/提交，再通过已认证 Host action 拉取可信收据并**原地更新同一 `callId` 卡片**。

本目录是 **插件 + 参考 Adapter**，不是 Octop 宿主补丁，也不是客户生产系统对接。

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
4. 重启或等待插件加载后，Agent 即可使用工具 `business_ui_draft` / `business_ui_connections`。

前端 UI 为预构建 ESM：`ui/index.js` + `ui/manifest.json`（路径避开仓库根 `dist/` gitignore），无需改 Dashboard。

## 配置卡（插件自有，不改 Octop 设置页）

管理员在聊天中调用 `business_ui_connections`（或让模型打开配置卡）：

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
6. 提交成功但详情失败：卡保持已提交，提供重试。

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
