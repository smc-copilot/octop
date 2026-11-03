# Mail Client 插件（POP3 + SMTP）

企业 demo：`kind=tool`，在聊天里用 `octop_ui` 卡片收信 / 读信 / 发纯文本。**不是** Connector，也没有 Dashboard 页面或独立 HTTP 服务。

目录：`plugins/mail-client/`（id `mail-client`）。

## 安装与启用

```bash
octop plugin install ./plugins/mail-client --force
```

1. Admin → 插件：确认 `mail-client` 全局开启。
2. Agent → 个性化 → 插件：该 Agent 不要关掉此插件。
3. **工具管理**：为 `mail_list` / `mail_read` / `mail_send` / `mail_probe` 填写同一套邮箱配置（任一工具填完整即可，运行时会合并兄弟工具的配置）。
4. 聊天里让 Agent 调用这些工具；Dashboard 会渲染卡片。IM 通道只看到 `text` 回退。

安装包已带预构建 `ui/dist/`，服务器**不需要** `npm`。

## 配置字段（`config_fields`）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `pop3_host` | text | 收信要 | POP3 主机 |
| `pop3_port` | number | 否 | 默认 995（SSL）或 110 |
| `pop3_ssl` | text | 否 | `true`/`false`，默认 true |
| `smtp_host` | text | 发信要 | SMTP 主机 |
| `smtp_port` | number | 否 | 默认 587（STARTTLS）或 465 |
| `smtp_starttls` | text | 否 | `true`=SMTP+STARTTLS；`false`=SMTP_SSL |
| `email` | text | 是 | 邮箱地址（默认登录名 / From） |
| `username` | text | 否 | 登录名，空则用 email |
| `password` | password | 是 | 密码或授权码；**不会**进入工具返回或卡片 |
| `from_name` | text | 否 | 发件显示名 |

Dashboard 工具表单目前只有 `text` / `password` / `number`，没有开关。布尔项请填 `true`/`false` 文本。

缺必填项时工具返回明确错误（例如 `Mailbox not configured: missing pop3_host, password`），不会去连服务器。

## 工具

| 名称 | 作用 | 卡片 renderer |
|------|------|----------------|
| `mail_list` | POP3 列出/本地搜索最近邮件（subject/from/date/index/uid） | `mail_inbox_list` |
| `mail_read` | 按 index 或 UIDL 读一封正文 | `mail_message` |
| `mail_send` | SMTP 发纯文本；参数 `to` `subject` `body` 必填 | `mail_compose` |
| `mail_probe` | 验证 POP3 登录 + SMTP 登录，不发信 | `mail_probe` |

返回 JSON：`{ "octop_ui": { "renderer", "version": 1 }, "data", "text" }`。

## POP3 vs IMAP

现有 QQ 邮箱 Connector（`src/octop/infra/connectors/gateway/adapters/qq_mail.py`）走 **IMAP** 收信。本插件按产品要求用 **POP3**：

- 没有文件夹，通常只有收件箱。
- 没有服务端 SEARCH；`query` 是拉最近 N 封后在本地过滤 subject/from。
- POP3 序号是**当前会话**的 1..N，删信后会变；`uid` 来自 UIDL（服务器若不支持则回退为序号）。
- `TOP` 取头；不支持时退回 `RETR`。

不要把本插件当 IMAP 客户端，也不要和 Connector 混用同一套假设。

## 安全

- 密码只用于 `poplib` / `smtplib` 登录；卡片 `data`、`text`、错误信息都会打码。
- 邮件头/正文是**不可信外部内容**。UI 只用文本节点，不 `innerHTML`。
- v1 不发送 HTML；`subject` 会去掉换行以防头注入。
- 无新 HTTP 路由、无 Dashboard 页面注册；可信边界仍是 Octop 已有的插件工具通道。

## 依赖

仅标准库：`poplib`、`smtplib`、`email`。不需要 `requirements.txt`。宿主已提供 `octop-harness`（`ctx.tool` / `get_tool_config`）。

## 校验

```bash
uv run python - <<'PY'
from pathlib import Path
from octop_harness.plugins import PluginRegistry, load_plugin_dir
PluginRegistry.reset()
p = load_plugin_dir(Path("plugins/mail-client"), install_deps=False)
print(p.manifest.id, p.manifest.kind, [t.name for t in p.tools])
PY

uv run pytest tests/unit/plugins/test_mail_client.py -q
```
