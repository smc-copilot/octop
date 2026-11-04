# 邮件专家功能需求 PRD

| 项 | 内容 |
|----|------|
| 标题 | 邮件专家（连接器凭据 + 聊天 `octop_ui` 卡片）功能需求 |
| 版本 | v0.2 |
| 日期 | 2026-11-04（Asia/Shanghai） |
| 状态 | 方案定稿（v0.2 经三轮 grilling 评审，全部开放问题已决策）；**尚未实现** |
| 基线分支 | [`feature/ver1.0`](https://github.com/smc-copilot/octop/tree/feature/ver1.0)（本地 `D:\git_ai\octop`，提交 `34ee168f` 附近） |
| 关联验收清单 | Cursor Page「邮件专家验收清单」（`5529fce5-5b7d-4b1c-a2dc-37e6e6ae456f`）；本 PRD 将清单条目产品化为可实现需求 |
| 受众 | 产品、企业插件/连接器研发、测试 |

**v0.2 变更摘要：** §1 新增 14 项决策记录（D1–D14）；§5.1 分层图重写（连接器工具=卡片数据源 + 插件宿主桥）；PRE-3 改为「会话选择本人实例」；LIST-2/3/4 改为结构化参数口径（LIST-2 升 P0）；LIST-4 时区改为 `default_timezone`；DETAIL-1 补 `BODY.PEEK` 与 text-only 约定；REPLY-4 两阶段确认改「必须」；新增 LIST-7（浏览免模型往返）；§8 开放问题全部关闭并指向决策记录。

---

## 1. 文档信息

本文描述 Octop「邮件专家」能力的功能边界与验收口径。

**已拍板的架构决策（实现不得偏离）：**

1. **配置只在连接器**：每位聊天用户为自己的邮箱创建/授权连接器实例（IMAP + SMTP）；凭据与探测在连接器层完成。
2. **使用入口**：启用了相关插件能力、并在会话中选择了本人邮箱连接器实例的「邮件专家」。
3. **UI**：聊天内 `octop_ui` 卡片（非独立 Dashboard 邮件页，非 page 类插件）。
4. **凭据隔离**：邮箱账号/密码/授权码**不得**进入 tool `config_fields`、不得以明文进入模型上下文、不得进入卡片 `data`。
5. **插件 kind 仅有** `tool` / `skill` / `hook` / `channel`（见 `feature/plugins/plugin-developer-guide.md`）；**没有** page kind。
6. **明确否决** [PR #5](https://github.com/smc-copilot/octop/pull/5) 路径：在 tool 管理用 `config_fields` 配置 POP3/SMTP 的 `mail-client` demo。

### 1.1 决策记录（v0.2 grilling 评审结论）

| ID | 决策 | 结论 | 关闭的开放问题 |
|----|------|------|----------------|
| D1 | 卡片数据通路 | **连接器工具直接返回 `{octop_ui, data, text}` 信封**；凭据不出连接器层；专家包只贡献渲染器与技能。渲染器按 `octop_ui.renderer` id 匹配（`dashboard/src/plugins/toolRenderers/types.ts`），IM 自动走 `text` 回退 | — |
| D2 | 「绑定」语义 | 复用基线机制：**当前聊天用户在本轮会话中选择自己的连接器实例**，凭据按 `connector_user_id` 解析（`prepare_chat_mcp`，`src/octop/infra/agents/manager.py`）。不新增「专家静态绑定」实体 | — |
| D3 | 协议范围 | **本期仅 IMAP + SMTP**；POP3 降级为连接器层后续扩展，不进入本期验收 | OPEN-1 |
| D4 | 过滤实现 | 连接器 `search_emails` 扩展**结构化参数**（`unread?` / `from?` / `since_days?` / `limit?`），服务端拼 IMAP SEARCH（`UNSEEN`/`FROM`/`SINCE`）；禁止把原始 IMAP 语法作为产品契约暴露给模型 | OPEN-2、OPEN-3 |
| D5 | 时区口径 | 列表/明细的时间展示与日期边界一律按**服务器 `default_timezone`**（`OctopConfig.default_timezone`），不硬编码 Asia/Shanghai，不用浏览器时区 | — |
| D6 | 写操作确认 | **P0 强制两阶段**：首次调用 dry-run 返回 `confirmation_required` + `confirmation_token` + 摘要；带 token 的二次调用走 Octop 现有聊天内 HITL 工具审批，批准后网关消费令牌真正发送。pending 状态存**连接器网关层内存表**（token → 参数快照 + `user_id` + 实例 id + TTL≈10 分钟 + 一次性消费），不进 DB | OPEN-4 |
| D7 | 专家包装与分发 | **单一 bundled 专家包** = `kind: skill` 插件（分析/模板/润色技能）+ `ui/` 渲染器；随 wheel 发布（`seed_bundled_plugins` / 市场安装）；内置专家配方引用它。不发明 page kind | OPEN-5 |
| D8 | 卡片交互回传 | **混合模式**：只读浏览（刷新/过滤/翻页/明细）走**新增插件宿主桥接能力**（卡片 → `host.request` → 邮件专家插件 action → 桥 → 按 `actor.user_id` 解析本人实例 → IMAP → `patchResult` 原地刷新）；生成类（分析/模板/润色）与写操作（发送）留在模型回合 | — |
| D9 | 发送呈现 | 卡片**不放**直发按钮；草稿在卡片中展示，用户回复「发送」→ 模型带 token 二次调用 → 聊天内 HITL 审批 UI → 批准即发 | — |
| D10 | 已读状态 | 读信用 **`BODY.PEEK[]`，不置 `\Seen`**；「在专家里看过」不改动用户邮箱的已读状态 | — |
| D11 | 回复 threading | 连接器新增 **`reply_email(uid, body)`** 工具：服务端按 UID 取原信 `Message-ID`/`References`/`Subject`，自动拼 threading 头与 `Re:`；同样走 D6 两阶段 | — |
| D12 | 正文与附件 | 本期 **text-only**：HTML 邮件抽取文本、不渲染 HTML；附件仅列出文件名，不支持下载 | OPEN-8 |
| D13 | Agent Mail 后端 | **不引入** Agent Mail 作为可选后端；其两阶段确认 / 不可信包裹模式已拆解吸收进 D6 / NFR-3 | OPEN-7 |
| D14 | 回复编辑态落点 | **卡片内编辑**：草稿在卡片 `draft` 视图内可编辑；「生成模板/润色/发送」按钮把当前正文作为**预填消息**经渲染器消息回调送入模型回合（现 prop 名 `onAcpPermissionSelect`，本期在渲染器 props 层泛化出语义中性别名 `onSendMessage`，旧名保留兼容） | — |

---

## 2. 背景与问题

企业内部希望在 Octop 对话中完成「看信 → 分析 → 拟回复 → 发送」闭环，而不是再开一套网页邮箱客户端。

当前基线已有两类与邮件相关、但**不足以单独满足「邮件专家」产品形态**的能力：

| 现有能力 | 路径/文档 | 与本需求的关系 |
|----------|-----------|----------------|
| 个人邮箱连接器 `qq-mail`（目录名「个人邮箱」） | `src/octop/infra/connectors/gateway/adapters/qq_mail.py`、`docs/connectors.md`、`catalog.json` kind=`qq-mail`，auth=`imap_app_password`，mcp_mode=`gateway` | **IMAP 收信 + SMTP 纯文本发信**；工具：`search_emails` / `read_email` / `send_email`；`probe_credentials` 走 IMAP 登录并 SELECT INBOX。主机预设见 `mail_servers.py`（QQ / Gmail / 网易 163·126·yeah）。**本期在其上扩展**（D4/D6/D10/D11）。 |
| Agent Mail（`agently-cli`） | `docs/connectors-agently-mail.md`、`adapters/agently_cli.py` | 腾讯 Agent 专用邮箱 + CLI OAuth；两阶段确认 + HITL + 不可信包裹的**模式来源**（已被 D6/NFR-3 吸收）；不作为本期后端（D13）。 |
| PR #5 `plugins/mail-client` | 打开的 PR，base=`feature/ver1.0` | POP3+SMTP + 聊天卡片 demo，但凭据落在 **tool config_fields**，与已定架构冲突，**本期不做、不合并为验收路径**。 |
| 插件与卡片 | `feature/plugins/plugin-developer-guide.md`、bundled `weather` 等、`docs/octop-ui-payload-offload.md` | 确立 `octop_ui` 信封、`text` 回退、IM 不渲染卡片只发 text 的既有行为。 |

**已核实的基线机制（v0.2 补充）：**

- 连接器实例按用户隔离：`connectors.user_id` + `shared` 标志（`infra/db/migrations/013_connector_instances.sql`）；任何登录用户可自助创建本人实例（`POST /api/connector-instances`）。
- 连接器工具经 `prepare_chat_mcp(agent_id, names, connector_user_id=uid)` 在每轮会话按调用方选择加载（D2 的载体）。
- 插件宿主动作桥已存在 HTTP 面：`POST /api/plugin-host/{plugin_id}/actions/{action}`（`src/octop/api/routers/plugin_actions.py`），handler 收到带 `user_id` 的 `PluginActor`；D8 的桥接 capability 在其上新增「调用连接器只读工具」一项。
- 渲染器宿主 API：`patchResult`（前端内存内刷新卡片）、`request`（带 JWT 的 `/api` 调用）、`openSidePanel`；卡片可经渲染器 props 的消息发送回调（现名 `onAcpPermissionSelect`，本期泛化出语义中性别名 `onSendMessage`）以当前用户身份发送预填消息。

**问题陈述：**缺少一条「连接器管凭据与协议探测 → 邮件专家在聊天卡片里优化列表/分析/回复」的产品闭环；若沿用 PR #5，会把服务器密码再次塞进工具管理，并与「每用户连接器实例」隔离模型冲突。

---

## 3. 目标与非目标

### 3.1 目标

1. 登录用户可为自己配置并探测可用的邮箱连接器实例（IMAP 收信 + SMTP 发信；D3）。
2. 「邮件专家」会话中选择本人实例后，在 Dashboard 聊天中用 `octop_ui` 卡片完成：收件列表与过滤、明细阅读、一键技能分析、回复模板/润色、经两阶段确认后发送。
3. 多用户之间邮箱内容隔离；未选择实例/探测失败时给出可行动引导（指向连接器配置，而非工具管理填主机）。
4. IM 通道至少保证 `text` 回退可用；卡片体验以 Dashboard 聊天为准。

### 3.2 非目标（本期明确不做）

- 独立 Dashboard「邮件客户端」页面或 page 类插件。
- 在 plugin tool `config_fields` 中再次收集 POP3/SMTP/密码（PR #5）。
- 全员共用一套管理员邮箱实例冒充「每用户」。
- 把 Agent Teams 的 `HarnessAgentInbox`（`docs/agent-interop-mailbox.md`）当作用户邮箱；那是 Agent 互调队列，与 RFC 邮箱无关。
- POP3 收信（D3）、HTML 渲染与附件下载（D12）、Agent Mail 可选后端（D13）。
- 完整网页邮箱功能集（文件夹管理、复杂规则、日历、大附件工作流等）——仅覆盖验收清单所列闭环。

---

## 4. 用户与场景

| 角色 | 诉求 |
|------|------|
| 业务用户（邮件专家使用者） | 在对话里快速扫未读/按人/按时间找信，读懂内容，用专家技能分析与起草回复，确认后发出。 |
| 同一租户的另一用户 | 绑定自己的邮箱；绝不能看到他人邮箱列表或正文。 |
| 管理员 | 安装/启用邮件相关插件与连接器目录项；不代替用户保管个人邮箱密码。 |
| 研发/测试 | 按编号需求与验收标准实现与回归；开放问题已全部关闭，见 §1.1 决策记录。 |

**主场景（用户 A）：** 创建/授权个人邮箱连接器并完成探测 → 邮件专家会话选择本人实例 → 列表 → 过滤 → 读信 →「用本专家技能分析」→ 生成模板/润色 → 卡片确认草稿 → 回复「发送」→ HITL 批准 → 卡片/text 中看到成功/失败。

**对照场景（用户 B）：** 选择另一邮箱实例；全流程仅见自己的数据。

**降级场景（IM）：** 同一专家在 IM 通道被调用时，至少返回可读 `text`（列表摘要、正文摘要、发送结果）；不要求 IM 渲染 `octop_ui`。

---

## 5. 架构与边界

### 5.1 分层（v0.2 重写，对应 D1/D2/D8）

```text
[连接器层]  个人邮箱实例：主机/账号/授权码、IMAP+SMTP、probe
            工具（返回 {octop_ui, data, text} 信封，D1）：
              search_emails(unread?/from?/since_days?/limit?)   ← D4 结构化参数
              read_email(uid)          ← D10 BODY.PEEK，不置已读
              send_email / reply_email ← D6 两阶段 dry-run + token；D11 threading
                 │
                 │ 会话内选择本人实例；凭据按 connector_user_id 解析（D2）
                 ▼
[邮件专家包]  bundled 插件（kind: skill + ui/ 渲染器，D7）
            · 技能：分析 / 回复模板 / 润色（模型回合内）
            · 渲染器 mail_card：list / detail / draft 视图
            · 插件 actions（只读浏览桥，D8）：
              列表刷新 / 过滤 / 明细加载 → 按 actor.user_id 调连接器只读工具
                 │
                 ▼
[Dashboard 聊天] 渲染卡片；patchResult 原地刷新；预填消息触发模型回合；
                 发送经聊天内 HITL 审批（D9）。IM 仅 text 回退
```

**凭据流向红线：** 凭据只存在于连接器密钥存储与网关内存；插件 action 桥**只暴露白名单只读工具**（`search_emails` / `read_email`），按 `actor.user_id` 解析实例，权限边界与 `prepare_chat_mcp` 的 `connector_user_id` 解析保持一致；桥不返回凭据字段，错误不echo 输入。

### 5.2 与 PR #5 的差异

| 维度 | PR #5（否决） | 本 PRD（采纳） |
|------|---------------|----------------|
| 凭据位置 | Agent 工具管理 `config_fields`（POP3/SMTP/password） | **仅连接器**实例凭据 |
| 收信协议 | POP3（demo） | IMAP（D3）；未来若需 POP3 在**连接器层**扩展 |
| 多用户 | 易变成「同一 Agent 工具配置被多人复用」 | 每用户自己的连接器实例；会话选择 + `connector_user_id` 解析（D2） |
| UI | 聊天卡片（可借鉴交互） | 同样聊天卡片，但信封由连接器工具产出（D1），渲染器在专家包（D7） |
| 插件形态 | `kind: tool` demo 包 | `kind: skill` + `ui/` 单包（D7）；**禁止**发明 page kind |

### 5.3 基线能力映射（实现时应复用，而非平行造轮）

| 需求能力 | 基线现状（`feature/ver1.0`） | 本期动作 |
|----------|------------------------------|----------|
| IMAP 列表字段 from/subject/date/uid | `qq_mail.search_emails`（原始 query 字符串） | **扩展结构化参数**（D4），返回 `octop_ui` 信封（D1） |
| 读正文 | `qq_mail.read_email`（UID + RFC822 纯文本） | 改 `BODY.PEEK[]`（D10）；返回信封（D1）；HTML 抽取文本（D12） |
| SMTP 发送 | `qq_mail.send_email`（纯文本直发） | 加**两阶段 dry-run + token**（D6） |
| 回复 threading | 无 | 新增 `reply_email(uid, body)`（D11），同样两阶段 |
| 探测 | `qq_mail.probe_credentials`（IMAP 登录 + SELECT INBOX） | 复用；失败信息可读（NFR-6） |
| 主机预设 | `mail_servers.resolve_mail_servers`（qq / gmail / netease） | 复用 |
| 两阶段 + HITL | Agent Mail 文档：dry-run + `confirmation_token` + 聊天内工具审批 | **对齐复用**（D6/D9）；pending 存网关内存表 |
| 未读过滤 | IMAP `UNSEEN` 准则 | 经 D4 `unread` 参数暴露，可验收 |
| 每用户实例 | `connectors.user_id` + `prepare_chat_mcp(connector_user_id=…)` | 复用（D2），零新表 |
| 卡片交互基建 | `host.request` / `patchResult` / 插件 actions 路由 / 消息发送回调 | 复用；新增「插件 action → 连接器只读工具」桥接 capability（D8） |

---

## 6. 功能需求

优先级：P0 必须交付；P1 强烈建议与 P0 同版本；P2 可随后门禁。
验收标准直接对应「邮件专家验收清单」；实现前全部为未完成状态。

### 6.1 前置条件（PRE）

| ID | 描述 | 验收标准 | 优先级 |
|----|------|----------|--------|
| PRE-1 | 存在可用的**邮箱连接器**，个人实例可配置主机/账号/授权码并完成探测 | 用户保存实例后可成功 probe；失败信息可读。协议为 IMAP + SMTP（D3） | P0 |
| PRE-2 | 登录用户能为**自己**创建/授权邮箱连接器实例 | 不依赖「管理员配一个共用邮箱给全员」；实例归属当前用户（基线 `POST /api/connector-instances` 已满足，需安装说明走查） | P0 |
| PRE-3 | 邮件专家会话可选择**本人的**邮箱连接器实例（D2） | 会话内选择后，专家使用该用户的实例凭据调用收发能力；未选择则不静默落到他人或管理员实例 | P0 |
| PRE-4 | 邮件专家包已安装启用 | bundled 专家包（skill + ui，D7）全局启用且该专家/Agent 未关闭；模型可调用连接器邮件工具，Dashboard 可加载渲染器。插件未安装时卡片天然降级为 `text`/JSON 展示 | P0 |
| PRE-5 | 未选择实例或探测失败时，卡片（或 text）明确引导用户去**连接器配置** | 文案可行动（例如「请先在连接器中配置个人邮箱并完成探测」）；**不**要求用户去「工具管理」填写 IMAP/SMTP | P0 |

### 6.2 卡片 1 — 收件列表（LIST）

| ID | 描述 | 验收标准 | 优先级 |
|----|------|----------|--------|
| LIST-1 | 默认展示当前用户已选实例的收件列表 | 卡片展示来自**本人实例**收件箱的条目；非空邮箱至少能看到近期邮件 | P0 |
| LIST-2 | 支持按**未读**过滤 | 经 D4 `unread` 参数走 IMAP `UNSEEN`；开启后仅展示未读 | P0 |
| LIST-3 | 支持按**指定发件人**过滤 | 经 D4 `from` 参数走服务端 `FROM` 搜索；匹配规则：From 头**子串匹配、大小写不敏感**（实现说明中写清） | P0 |
| LIST-4 | 支持按**日期范围**过滤 | 经 D4 `since_days`（或起止日期）走 `SINCE`/`BEFORE`；日期边界与展示按**服务器 `default_timezone`**（D5） | P0 |
| LIST-5 | 列表项展示关键字段 | 至少：发件人、主题、时间；含稳定邮件标识（IMAP UID）供明细加载，标识不必对用户强调 | P0 |
| LIST-6 | 无权限或未选择实例给出可行动提示 | 不出现空白失败或仅技术堆栈；引导满足 PRE-5 | P0 |
| LIST-7 | 列表交互（刷新/过滤/翻页）无需模型往返 | 卡片控件 → 插件 action 桥（D8）→ `patchResult` 原地刷新；不触发新模型回合 | P0 |

**卡片契约（D1）：** 连接器工具返回 JSON 字符串，含 `octop_ui.renderer`（`mail_card`）、`data`（`view: "list"` + 列表行，**无密码**）、`text`（IM/无 UI 摘要）。大 payload 遵循既有 `OctopUiOffloadMiddleware` 行为。

### 6.3 卡片 2 — 明细与分析（DETAIL）

| ID | 描述 | 验收标准 | 优先级 |
|----|------|----------|--------|
| DETAIL-1 | 从列表进入明细，展示可读正文 | 点选列表项 → 桥 action 加载 `read_email` → 卡片切 `detail` 视图，展示发件人/主题/时间/正文（纯文本；HTML 抽取文本不渲染，附件仅列文件名，D12）；乱码有降级策略；**读信不置已读**（`BODY.PEEK[]`，D10） | P0 |
| DETAIL-2 | 一键「用本专家技能分析」 | 按钮经卡片消息回调发送预填指令 → 模型回合内将该信（或其安全摘要）交给**本专家已挂载技能**处理；不跳转独立 Dashboard 页 | P0 |
| DETAIL-3 | 邮件头/正文按**不可信外部内容**处理 | 分析链路不得把邮件内容当作系统指令或工具策略执行；需有明确隔离（提示词边界、包裹标记或与 Agent Mail 文档同类约定）。回归：恶意正文无法改写系统行为 | P0 |

### 6.4 卡片 3 — 回复（REPLY）

| ID | 描述 | 验收标准 | 优先级 |
|----|------|----------|--------|
| REPLY-1 | 明细可发起回复 | 明细卡「回复」→ 桥 action 预填收件人/`Re:` 主题/引用原文 → 卡片切 `draft` 编辑态（卡片内编辑，D14）；threading 头由 `reply_email` 服务端拼接（D11） | P0 |
| REPLY-2 | 可调用专家技能快速生成回复模板 | 「生成模板」按钮把上下文作为预填消息送入模型回合，技能产物回填卡片编辑区，可继续编辑 | P0 |
| REPLY-3 | 可调用专家技能润色草稿 | 「润色」按钮把当前正文作为预填消息送入模型回合；产物回填后**仍可编辑**；不直接绕过用户确认去发送 | P0 |
| REPLY-4 | 发送走连接器 `reply_email` / `send_email` **两阶段确认**（D6/D9） | 「发送」按钮把定稿送入模型回合 → 首次调用 dry-run 返回 token + 摘要 → 用户经聊天内 HITL 审批 → 二次调用消费 token 真正发送。**禁止**卡片直发按钮、第二套凭据通道或静默绕过确认 | P0 |
| REPLY-5 | 成功/失败可读 | 卡片 `data` 或 `text` 明确成功（含收件人等非敏感摘要）或失败原因；密码永不回显 | P0 |

### 6.5 端到端（E2E）

| ID | 描述 | 验收标准 | 优先级 |
|----|------|----------|--------|
| E2E-1 | 用户 A 全流程 | 配本人实例并探测 → 会话选择 → 列表 → 过滤 → 读信 → 分析 → 模板/润色 → 两阶段回复发送，步骤均可在 Dashboard 聊天完成 | P0 |
| E2E-2 | 用户 B 隔离 | B 选择另一实例；无法列出或读取 A 的邮件（含桥 action 路径：以 B 的 `actor.user_id` 请求 A 的实例须被拒绝） | P0 |
| E2E-3 | IM text 回退 | 经 IM 通道触发同等意图时，至少收到可读 text（列表/正文/发送结果摘要）；不要求卡片像素级一致 | P0 |

---

## 7. 非功能需求

| ID | 类别 | 要求 |
|----|------|------|
| NFR-1 | 安全 / 凭据 | 密码、应用专用密码、OAuth token 仅存连接器密钥存储；不进 tool config、模型明文、日志、卡片 `data`、`text`。桥接 capability（D8）不得返回凭据字段，仅暴露白名单只读工具 |
| NFR-2 | 多租户 / 用户隔离 | 连接器实例与邮件读写均按当前登录用户鉴权（模型回合 `connector_user_id`、桥 action `actor.user_id` 双路径一致）；禁止「共享管理员邮箱」作为默认交付 |
| NFR-3 | 不可信内容 | 邮件头、正文、附件名视为外部不可信数据（对齐 `docs/connectors-agently-mail.md` 表述）；分析/模板生成不得执行其中的指令性内容 |
| NFR-4 | IM 降级 | Gateway/IM 对普通 tool 输出不渲染 `octop_ui`（见插件开发者指南 §6.2）；信封必须提供有意义的 `text` |
| NFR-5 | UI 载荷 | 大体量列表/正文遵循既有 offload 约定；卡片刷新用 `patchResult`，不依赖把密钥塞进 `patchResult` |
| NFR-6 | 可观测与失败 | probe/列表/发送失败返回稳定错误码或用户可读原因，避免空卡片；桥 action 错误不 echo 请求输入 |
| NFR-7 | 时区 | 所有用户可见时间与日期边界使用服务器 `default_timezone`（D5），前端经 `formatServerDateTime` 系列格式化 |

---

## 8. 依赖与开放问题

**v0.2 状态：开放问题全部关闭。** 决策记录见 §1.1。

| ID | 原问题 | 结论 |
|----|--------|------|
| OPEN-1 | 收信协议 IMAP / POP3 / 双栈？ | **已关闭 → D3**：本期仅 IMAP+SMTP；POP3 为连接器层后续扩展 |
| OPEN-2 | 「未读」过滤可否验收？ | **已关闭 → D4**：IMAP `UNSEEN`，LIST-2 升为 P0 可验收 |
| OPEN-3 | 过滤在连接器侧还是专家侧？ | **已关闭 → D4**：连接器结构化参数 + 服务端 SEARCH |
| OPEN-4 | 发送是否强制两阶段 + HITL？ | **已关闭 → D6/D9**：P0 强制，复用聊天内 HITL 审批 |
| OPEN-5 | 专家制品形态？ | **已关闭 → D7**：单一 bundled 包（skill + ui）+ 内置专家配方 |
| OPEN-6 | 连接器实例创建权限？ | **已关闭（事实确认）**：基线 `POST /api/connector-instances` 已支持登录用户自助创建本人实例；安装说明按现网 Dashboard 连接器页走查后编写 |
| OPEN-7 | 是否复用 Agent Mail 作为可选后端？ | **已关闭 → D13**：不引入；模式已吸收 |
| OPEN-8 | HTML 邮件与附件？ | **已关闭 → D12**：本期 text-only；附件仅列名 |

---

## 9. 明确不做

1. 独立 Dashboard 邮件客户端页面 / page 类插件。
2. 再次采用 PR #5：在 tool `config_fields` 配置 POP3/SMTP/密码。
3. 全员共用管理员邮箱冒充每用户隔离。
4. 将 Agent Teams Inbox（`docs/agent-interop-mailbox.md`）误当作邮箱产品。
5. 在未评审情况下安装任意外网 ZIP 插件并把邮箱密钥写入插件目录。
6. 卡片上的直发按钮或任何绕过聊天内 HITL 审批的发送通道（D9）。
7. 插件 action 桥暴露写操作工具或凭据字段（D8/NFR-1）。

---

## 10. 里程碑建议（方案级，无虚构人日）

| 阶段 | 产出 | 退出条件 |
|------|------|----------|
| M0 对齐 | 本 PRD v0.2 + 验收清单；D1–D14 决策记录（§1.1） | 已完成（2026-11-04 grilling 评审） |
| M1 连接器就绪 | `search_emails` 结构化参数（D4）、`read_email` 改 `BODY.PEEK`（D10）、`octop_ui` 信封（D1）、`send_email`/`reply_email` 两阶段（D6/D11）；实例可配可探；失败引导到连接器 | PRE-1～PRE-5 可演示；连接器层单测覆盖 |
| M2 列表与明细卡片 | 专家包渲染器 + 插件 action 只读桥（D8）；LIST-*、DETAIL-1 | Dashboard 可列表/过滤/读信且无需模型往返；E2E-2 桥路径隔离对测通过 |
| M3 分析与回复 | 技能包（分析/模板/润色）、DETAIL-2/3、REPLY-*；HITL 链路 | 分析不中指令注入；发送必须过两阶段审批 |
| M4 E2E 与隔离 | E2E-1～3；双用户对测；IM text 抽检；安装说明（OPEN-6 走查结论） | 验收清单主路径可勾选 |

**测试策略（实现职责，已约定）：** IMAP/SMTP 用进程内替身（stub `imaplib.IMAP4` / `smtplib.SMTP`）覆盖搜索、读信（含 `BODY.PEEK` 不置已读回归）、两阶段发送与 token 一次性消费；E2E-2 用双用户 + 各自实例对测；遵循仓库跨平台测试约定（`tmp_path` / `OCTOP_HOME` 环境隔离 / `uv run pytest`）。

---

## 附录 A. 参考路径（本地仓库 / 基线分支）

- `feature/plugins/plugin-developer-guide.md` — 插件四 kind、禁止 Dashboard 页、`octop_ui` 契约、`ui/` 清单
- `docs/connectors.md` — 内置连接器目录；`qq-mail` / `agently-cli`
- `docs/connectors-agently-mail.md` — Agent Mail 工具、HITL、不可信内容（D6/D9/NFR-3 模式来源）
- `src/octop/infra/connectors/gateway/adapters/qq_mail.py` — IMAP/SMTP 工具与 probe（本期扩展点）
- `src/octop/infra/connectors/mail_servers.py` — 邮箱主机预设
- `src/octop/infra/connectors/catalog.json` — 连接器元数据源
- `src/octop/infra/agents/manager.py` — `prepare_chat_mcp`（D2 会话选择 + `connector_user_id` 解析）
- `src/octop/api/routers/plugin_actions.py` + `src/octop/infra/agents/plugins/host.py` — 插件宿主动作面（D8 桥接 capability 落点）
- `dashboard/src/plugins/toolRenderers/` — 聊天卡片宿主（`types.ts` / `parseToolOutput.ts` / `host.ts`）
- `src/octop/infra/agents/middleware/octop_ui_offload.py` — 大卡片 offload
- PR #5 `https://github.com/smc-copilot/octop/pull/5` — **否决的** tool-config 凭据路径（可借鉴卡片交互，不采纳配置模型）

## 附录 B. 需求 ID 与验收清单对照

| 清单章节 | 需求 ID |
|----------|---------|
| 前置条件 | PRE-1 … PRE-5 |
| 卡片 1 收件列表 | LIST-1 … LIST-7 |
| 卡片 2 明细与分析 | DETAIL-1 … DETAIL-3 |
| 卡片 3 回复 | REPLY-1 … REPLY-5 |
| 端到端 | E2E-1 … E2E-3 |
| 决策记录 | §1.1 D1 … D14 |
| 明确不验收 | §3.2 / §9 |

---

*文档结束。*
