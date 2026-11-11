# 多实例 BUSINESS_UI_* 部署（无聊天配置）

目标：约 10 台 Octop 各自用**全局环境变量**落下 Adapter URL 与用户授权方式，管理员不必在聊天里填配置卡。每位用户仍走现有激活（OAuth / 业务账号 / PAT）。

Plugin Management **没有**配置表单（宿主只渲染 `plugin.yaml` 的 `description`：已安装卡片两行截断，详情抽屉普通段落、无 Markdown、换行会收成空格）。中文键名与必填说明写在该 description 里；完整表与可复制模板以本文为准。

## 宿主环境何时生效（已核对源码）

| 改法 | 进程 `os.environ` | 插件连接记录 |
|------|-------------------|--------------|
| Dashboard **高级设置 → 环境变量**（`PUT /api/envs`） | **立刻** `apply_env_file_replace`（`src/octop/api/routers/envs.py`） | 下一次 `connections.list` / `claim` / `connections.test` 或后台 `env_sync`（约 20s）写入 Host records。**不必重启 Octop** |
| 只改磁盘 `~/.octop/env`、不走 API | **不会**自动加载 | `OctopServer.start` 才 `apply_env_file`。**必须重启** |
| systemd / Docker `-e` / 进程环境 | 启动时带入 | **改这些必须重启进程** |
| 只改密钥**文件内容**（路径不变） | 无 | 下次 sync 按文件哈希重写 Host 凭据；用户激活指纹不变则不必重新登录 |

`BUSINESS_UI_*` **不是** `OCTOP_*`，会被 overlay 进 MCP stdio 与 agent shell（`env_file.overlay_stdio_spec_env` 只跳过 `OCTOP_*` 与 HOME/USER）。因此**禁止**把密码 / PAT / 用户令牌 / 服务或 client secret 写进环境变量值。

环境页**没有** Test Connection 按钮（不改 Dashboard）。健康检查用插件 CLI。

## 键（与 `env_config.ENV_KEY_SPECS` / `plugin.yaml` description 同步）

未设 `BUSINESS_UI_BASE_URL`：不做环境引导。一旦设置，下列「已设后必填」缺一则失败关闭。取值与默认来自 `parse_env_spec`。

| 变量 | 必填性 | 用途 | 默认 / 取值 |
|------|--------|------|-------------|
| `BUSINESS_UI_BASE_URL` | 已设后必填（未设则跳过引导） | HTTPS Adapter 基址；无 URL 用户信息/fragment | 无 |
| `BUSINESS_UI_INSTANCE_ISSUER` | 已设后必填 | 本 Octop 实例 https 源，每台唯一 | 无 |
| `BUSINESS_UI_OPERATOR_USER_ID` | 已设后必填 | 持有服务凭据的本地 admin 数字 user_id，不是用户名 | 无 |
| `BUSINESS_UI_SERVICE_SECRET_FILE` | 已设后必填 | 服务 Bearer 绝对路径；缺文件失败关闭，不跳过鉴权 | 无 |
| `BUSINESS_UI_CONNECTION_ID` | 可选（有默认） | 稳定连接 id，跨重启不变 | `default` |
| `BUSINESS_UI_DISPLAY_NAME` | 可选（有默认） | 列表显示名 | 等于 CONNECTION_ID |
| `BUSINESS_UI_AUTH_METHOD` | 可选（有默认） | Octop→Adapter 服务身份 | `api_token`；`api_token` / `authorization_code` |
| `BUSINESS_UI_USER_AUTH_METHOD` | 可选（有默认） | 每位用户激活方式 | `oauth2`；`oauth2` / `native_login` / `personal_access_token` |
| `BUSINESS_UI_ENABLED` | 可选（有默认） | 是否启用 | `1`；`0`/`false`/`off` 停用 |
| `BUSINESS_UI_OAUTH_SCOPES` | 可选（有默认） | OAuth scope | `openid profile` |
| `BUSINESS_UI_OAUTH_CLIENT_ID` | oauth2 条件必填 | OAuth/OIDC client id | 无 |
| `BUSINESS_UI_OAUTH_DISCOVERY_URL` | oauth2 条件（与成对 URL 二选一） | RFC 8414 / OIDC discovery | 无 |
| `BUSINESS_UI_OAUTH_AUTHORIZE_URL` | oauth2 条件（无 discovery 时与 token 成对） | 授权端点 | 无 |
| `BUSINESS_UI_OAUTH_TOKEN_URL` | oauth2 条件（无 discovery 时与 authorize 成对） | 换票端点 | 无 |
| `BUSINESS_UI_OAUTH_REVOKE_URL` | 可选 | token 吊销 | 无 |
| `BUSINESS_UI_OAUTH_CLIENT_SECRET_FILE` | 可选 | oauth2 机密客户端 secret 绝对路径，0600 | 无 |
| `BUSINESS_UI_PRIVATE_ALLOW` | 可选 | 内网/回环显式 CIDR 或 host；禁止 169.254.0.0/16 | 无 |
| `BUSINESS_UI_EXTRA_ORIGINS` | 可选 | 额外 HTTPS origin | 无 |
| `BUSINESS_UI_TLS_CA_FILE` | 可选 | 自签 CA PEM，允许 0644 | 无 |

若设置了 `BUSINESS_UI_SERVICE_SECRET` 等内联密钥键：**失败关闭**。密钥只用 `*_FILE`。

## 可复制最小模板

native_login（无 OAuth）：

```
BUSINESS_UI_BASE_URL=https://adapter.example.com
BUSINESS_UI_INSTANCE_ISSUER=https://octop.example.com
BUSINESS_UI_OPERATOR_USER_ID=1
BUSINESS_UI_SERVICE_SECRET_FILE=/etc/octop/business-ui/service.token
BUSINESS_UI_USER_AUTH_METHOD=native_login
```

oauth2（discovery）：

```
BUSINESS_UI_BASE_URL=https://adapter.example.com
BUSINESS_UI_INSTANCE_ISSUER=https://octop.example.com
BUSINESS_UI_OPERATOR_USER_ID=1
BUSINESS_UI_SERVICE_SECRET_FILE=/etc/octop/business-ui/service.token
BUSINESS_UI_USER_AUTH_METHOD=oauth2
BUSINESS_UI_OAUTH_CLIENT_ID=replace-me
BUSINESS_UI_OAUTH_DISCOVERY_URL=https://idp.example.com/.well-known/openid-configuration
```

回环 Adapter 再加 `BUSINESS_UI_PRIVATE_ALLOW=127.0.0.1/32`。带占位符的完整稿：`docs/env.template`。

## 密钥文件

```bash
install -d -m 0700 /etc/octop/business-ui
umask 077
printf '%s' 'ADAPTER_SERVICE_TOKEN' > /etc/octop/business-ui/service.token
chmod 0600 /etc/octop/business-ui/service.token
# 同样方式写 oauth-client.secret；CA 可用 0644
```

插件拒绝：相对路径、缺失、空文件、world-writable、密钥文件 world-readable。内容不进 `plugin_records`、不进日志、不进 `connections.list`。写入 Host `stage_credential`，与聊天保存的凭据同一保护。

## 优先级（无重复）

- `managed_by=env` 的 `CONNECTION_ID`：**环境变量为准**；聊天保存/删除返回 `ENV_MANAGED`
- 聊天不得再创建**同一 Adapter URL** 的第二条连接
- 其它 chat-managed 连接仍可在配置卡上管
- 去掉 `BUSINESS_UI_BASE_URL`（或换了 `CONNECTION_ID`）：原先 env 行改回 `managed_by=chat`，**不删记录、不关服务鉴权**；管理员随后可在配置卡删除。畸形 env 失败关闭，不释放。
- 已存 issuer 与 `BUSINESS_UI_INSTANCE_ISSUER` 不一致：失败关闭，不覆盖
- `user_auth_method` / issuer / client_id / Adapter URL 变化会换 `config_fingerprint`，旧用户激活作废（`stale_config`），必须重新激活。服务密钥文件轮换只重写 Host 服务凭据，不继承到别的用户

## 健康检查（非聊天、非破坏）

环境变量页**不能**点 Test。在已安装插件目录：

```bash
cd ~/.octop/plugins/business-ui   # 或 $OCTOP_HOME/plugins/business-ui
python -m business_ui test
python -m business_ui plan
```

`test` 对 Adapter `POST /v1/handshake`（`destructive: false`），校验所选 `user_auth_method` 是否在 Adapter `features.user_auth_methods` 中。退出码 0/1。也可在 Octop 起来后由管理员打开配置卡点 Test Connection（同一 action）。

## 一台实例的操作顺序

1. 安装插件 ZIP（不含 `node_modules`）。
2. 在本机写好 0600 密钥文件（上表）。记下 admin 的数字 `user_id`。
3. 填 `docs/env.template`：每台机器换 issuer、CONNECTION_ID、URL、文件路径。
4. 写入 Dashboard 环境变量 **或** `~/.octop/env` 后**重启**（仅磁盘编辑时）。
5. `python -m business_ui test` 应 `ok: true`。
6. 启动/重载插件后等一次 list 或最多 ~20s 后台 sync（Host Event 是唤醒闩，不是停止信号）。
7. **每个**业务用户在草稿卡上激活；不要把用户 PAT 放进全局 env。

## 与分支策略

消费宿主：`src/octop/infra/utils/env_file.py`（`apply_env_file` / `apply_env_file_replace`）、`src/octop/api/routers/envs.py`、`PluginHost.stage_credential` / `commit`。不修改这些文件。见 `docs/branch-policy.md`。
