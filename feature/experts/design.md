# Octop 专家包设计规范

> 真源：**本仓库当前源码**（已于 2026-10-31 逐条核验，证据见 `research/code-verification.md`；实证样本分析见 `research/example-workspace.md`；官方文档对照见 `research/docs-synthesis.md`）。早期版本声称的真源分支 `smc-copilot/octop@feature/ver1.0` 不再作为依据。  
> 用途：供 Cursor 生成、人工打包为 `.zip`、再上传安装的业务专家包。  
> 推荐形态：**Workspace Archive 精简包**；子智能体落在 `agents/*.md`；技能 / 知识库 / 模型 / 连接器按「包内可带」与「安装后 UI 配」拆开。  
> 配套文档：手把手创建示例模板见 `feature/experts/template.md`。

## 结论先行

手打包应做成「工作区归档 zip（workspace archive）」，上传到**已创建且正在运行**的专家：

```http
POST /api/agents/{agent_id}/workspace/archive?mode=merge|replace
```

它**不会新建专家**。模型、知识库 ID、连接器、MBTI、通道、插件等多数在创建向导 / 专家菜单里配，**不进 zip**。

单靠上传 zip 不会创建新专家；也不会写入 `default_model`、`knowledge_base_ids`、`mcp_servers`、`persona_mbti`。那些在 `agents` 表 / `config_json`，不在 archive。

---

## 1. 专家包是什么、怎么装

Octop 专家 = 数据库里的 agent 行（模型、后端、知识库 ID、MCP/连接器、MBTI…）+ 工作区文件（提示词、skills、子智能体、可选本地知识目录、欢迎元数据）。本规范「专家包」专指后者的可移植 zip，供人工上传灌入已有专家工作区。

| 步骤 | 动作 | 说明 |
|------|------|------|
| ① 建壳 | UI：从「小通 · 通用助手」（`general-assistant`，向导默认）或隐藏空白模板「通用专家」（`default`，仅 `AGENTS.md`、不出现在库列表，可经 `from-expert/default` 使用）等模板新建 | 在此选 Craft/模型/存储后端/根目录，并勾选知识库、技能包、连接器 |
| ② 灌包 | 专家运行中 → 导入工作区 zip | API：`POST …/workspace/archive`；`mode=merge`（默认）或 `replace` |
| ③ 补齐 | 菜单：技能/子智能体/工具/插件/MBTI/记忆/通道 | 包里没有或无法携带的运行时项在此完成 |

---

## 2. 两种包形态对比（必须分清）

| 维度 | Workspace Archive（推荐手打包） | Library / Published 快照 |
|------|--------------------------------|--------------------------|
| 用途 | 灌入已有专家工作区 | `from-expert` / 已发布专家安装时种子工作区 |
| 入口 | `GET/POST /api/agents/{id}/workspace/archive` | `POST /api/agents/from-expert/{id}`；published install |
| manifest | 运行时在 `.octop/manifest.json`（根路径兼容可读） | 种子目录根 `manifest.json`，seed 时拷到 `.octop/manifest.json` |
| skills / agents | 现代 agent 物理多在 `.octop/skills`、`.octop/agents`（export 如此） | 种子用根目录 `skills/`、`agents/*.md` |
| 是否新建专家 | 否，只覆盖/合并文件 | 是，创建 agent 并 seed |
| 内容白名单 | 几乎任意工作区文件（import 仅跳过 `_builtin_skills`） | 库 seed 全量拷贝；**published 快照是白名单**：仅根 `SOUL/IDENTITY/USER/AGENTS/TOOLS/HEARTBEAT/PROACTIVE.md` + `skills/**` + `agents/*.md`——`MEMORY.md`、`BOOTSTRAP.md`、`knowledge-base/` 等**不进发布快照**（`publish.py`，测试 `test_expert_publish_snapshot.py` 实证） |
| 噪声 | 原始 export 常含 `_builtin_skills`、`memory.sqlite*`（export 不过滤；**import 只跳过 builtin，不跳过 sqlite/.env**，手传前必须自行剔除） | 发布导出会剔除 session/inbound/memory.sqlite/.env/builtin 等 |
| 大小上限 | 上传 200MB | 由安装链路约束，不是本手传入口 |

**本规范推荐**：Cursor 按「Workspace Archive 精简包」生成目录 → 人工 zip → 上传到目标专家。若以后要进官方 library / 发布市场，再按 Library 扁平布局改一份（根 `skills/` + `agents/` + `manifest.json`）。

### 2.1 三条安装链总览（不要混用）

```text
链 1 内置库（官方 UI 主路径）：
  GET /api/experts → POST /api/agents/from-expert/{expert_id}   新建 agent + seed 库目录
链 2 手传 zip（本规范主路径）：
  POST /api/agents 建壳 → start → POST …/workspace/archive       不新建；只灌工作区文件
链 3 发布 / 市场：
  POST /api/agents/{id}/publish-expert → POST /api/experts/published/{id}/install
  或 SkillHub：POST /api/experts/hub/{slug}/install              新建 agent + seed 快照/skillset
```

- 三条链的请求体（`POST /api/agents`、`from-expert`、published/hub install）都可带 `skill_package_ids`、`knowledge_base_ids`、`mcp_servers`、`backend`、`conversation_mode`——这正是「建壳时勾选、不进 zip」的 HTTP 落点。
- 全部需要 JWT；链 3 的市场入口还要求权限 `expert_market`，并受实例 `market_mode`（`public/off/allowlist/mirror_only`）闸门约束；**链 2 手传 archive 不受市场闸门约束**（只需 owner + 专家运行中），这是它在受控实例上的运维优势。
- 带 `knowledge-base/` 本地知识 + `MEMORY.md` 的包只能走链 2（或做成内置 library 种子）；published 快照会丢掉它们（见上表白名单行）。

---

## 3. 推荐目录树（业务专家骨架）

以下为手打包上传用的精简骨架，对齐 `feature/ver1.0` 的 export 物理布局，并去掉运行态噪声。**zip 根目录 = 工作区根**，不要再套一层文件夹名。

```text
业务专家包/
├── AGENTS.md                 # 操作规程 / schema（必）
├── SOUL.md                   # 人设与分工（必）
├── BOOTSTRAP.md              # 首次对话引导（建议）
├── MEMORY.md                 # 热索引 Markdown（可选；不是 sqlite）
├── USER.md                   # 用户档案模板（可选）
├── PROACTIVE.md              # 主动消息规则（可选）
├── TOOLS.md / IDENTITY.md / HEARTBEAT.md   # 按需
├── <业务数据目录>/            # 如 knowledge-base/、playbooks/（可选）
│   └── …
└── .octop/
    ├── manifest.json         # 欢迎页元数据（强烈建议）
    ├── skills/
    │   └── <skill-slug>/
    │       ├── SKILL.md      # 必
    │       └── references|scripts|…
    └── agents/
        └── <subagent-slug>.md
```

| 项 | 说明 |
|----|------|
| skills 兼容路径 | 发现根：`.octop/skills` 与 `skills/`（`skills_discovery_roots`） |
| 子智能体规范路径 | 逻辑路径 `agents/<slug>.md`；现代工作区物理多为 `.octop/agents/<slug>.md` |
| 安装 API 写入 | `POST …/subagents/install` → `agents/{slug}.md`（经 system_files 映射） |

---

## 4. 关键文件规范

### 4.1 `.octop/manifest.json`

欢迎元数据真源。库种子在目录根叫 `manifest.json`；进工作区后规范位置是 `.octop/manifest.json`（根路径仍可读作兼容）。`prompt_files` 只是仪表盘提示，人设正文读工作区 md。

```json
{
  "id": "acme-ops-expert",
  "scene": "office",
  "label": { "zh": "运维专家", "en": "Ops Expert" },
  "description": { "zh": "…", "en": "…" },
  "welcome_message": { "zh": "…", "en": "…" },
  "icon_name": "server",
  "color": "#0ea5e9",
  "icon_url": "可选；自定义头像 URL，优先级高于 icon_name",
  "prompt_files": ["SOUL.md", "AGENTS.md", "BOOTSTRAP.md"],
  "quick_prompts": [
    {
      "title": { "zh": "巡检", "en": "Inspect" },
      "description": { "zh": "…", "en": "…" },
      "prompt": { "zh": "请…", "en": "Please…" },
      "color": "#e0f2fe",
      "icon_name": "list-checks"
    }
  ],
  "task_examples": {
    "zh": ["每天 21:00 …"],
    "en": ["Every day at 21:00 …"]
  }
}
```

### 4.2 根提示词 Markdown

| 文件 | 作用 | 打包建议 |
|------|------|----------|
| `SOUL.md` | 身份、分工、风格 | 必带；业务人设主文件 |
| `AGENTS.md` | 操作规程 / 知识 schema | 必带；写清工具与目录约定 |
| `BOOTSTRAP.md` | 首次对话步骤 | 建议 |
| `MEMORY.md` | 短热索引（导航用） | 可选；保持短，勿塞正文 |
| `USER.md` | 用户档案模板 | 可选；勿写真实隐私 |
| `PROACTIVE.md` | 主动消息输出约束 | 按需 |
| `TOOLS.md` | 工具使用备忘 | 按需；发布种子白名单含此名 |

### 4.3 `SKILL.md`（技能）

每个技能一个目录，内含 `SKILL.md`。YAML frontmatter 至少 `name` + `description`；Octop 扩展元数据放 `metadata.octop`。

```markdown
---
name: incident-triage
description: Triage production incidents… Use when on-call…
metadata:
  octop:
    emoji: "🚨"
    label: { zh: "故障分诊", en: "Incident triage" }
    summary: { zh: "…", en: "…" }
---

# 故障分诊

## 何时使用
…

## 步骤
1. …
```

- slug = 目录名。`validate_skill_slug` 实际只禁止：空串、前导 `.`、含 `/` `\` 或 NUL——**允许大写、下划线与 Unicode**；但为兼容外部技能生态（SkillHub 等），仍建议自限为 `[a-z0-9-]`
- `name` / `description` 建议必填；Octop 解析器实际有回落（缺 `name` 用 slug、缺 `description` 为空串），但缺失会损害模型触发与 UI 展示
- 不要把平台 `_builtin_skills` 拷进业务包
- 可从市场拷技能到 `skills/<slug>/`，或手写；全局 `skill_package_ids` 是 DB 字段，不是 zip 文件

### 4.4 子智能体 Markdown

单文件 = 一个子智能体。文件名 stem = slug（安装与列表以此为准）。必须有 `---` YAML frontmatter `---`；否则不被识别为 agent 文件。

```markdown
---
name: 变更评审员
emoji: "🔎"
color: "#dbeafe"
description: |
  在发布前评审变更风险与回滚方案。主线程工具输出过长或需并行评审时委托。
---

# 变更评审员

你是子智能体。调用方只看到你的最终助手消息。

## 行为准则
- …

## 输出
给出可直接转发给用户的结论与风险清单。
```

### 4.5 本地知识目录 vs 企业知识库

| 类型 | 如何表达 | 是否进 zip |
|------|----------|------------|
| 本地 Markdown 知识（如 Karpathy wiki） | 工作区目录 `knowledge-base/raw|wiki` + `MEMORY.md` + 技能指引 | 是 |
| 企业知识库（WeKnora 等） | 创建时勾选 → `agents.knowledge_base_ids` | 否；安装后/创建时 UI |
| 连接器 / MCP | `mcp_servers` 等 DB/配置 | 否；创建向导或专家菜单 |
| 默认模型 / Craft 模式 / 存储后端 | `default_model`；`config_json.conversation_mode` / `backend` / `workspace_dir` | 否 |

---

## 5. 能力映射：UI ↔ 包内 / 安装后

| UI（截图/菜单） | 落点 | 包内可带? | 说明 |
|-----------------|------|-----------|------|
| 标题语 / 欢迎 | `.octop/manifest.json` `welcome_message` + 可选 AGENT 名 | 可 | 名/描述也在 DB；manifest 驱动欢迎卡 |
| Craft / Ask / Plan | `config_json.conversation_mode` | 否 | 创建向导选择 |
| 默认模型 Auto | `agents.default_model` | 否 | 创建或设置 |
| 存储后端 + 根目录 `/` | `config_json.backend` / `workspace_dir` | 否 | `/` 表示整机 root；仅可信环境 |
| 提示词 `AGENTS.md` | 工作区根 `*.md` | 可 | composer 规则是正则白名单：任意 `^[A-Za-z0-9][A-Za-z0-9._-]*\.md$` 根 md + `skills/<slug>/…` + `agents/<slug>.md`；**明确拒绝 `.octop/…`**，所以 `.octop/manifest.json` 不能经创建向导 composer 写入，只能靠 archive 灌入或安装链 seed |
| 技能列表 | `.octop/skills` 或 `skills/` | 可 | 全局技能包 ID 另算 |
| 子智能体列表 | `agents/*.md`（物理常 `.octop/agents`） | 可 | UI 添加 = 写文件 + reload |
| 知识库勾选 | `knowledge_base_ids` | 否 | 本地目录知识可另打包 |
| 连接器 | `mcp_servers` / connectors | 否 | 安装后配置 |
| 全局技能包挂载 | `skill_package_ids` | 否 | DB 字段；`GET/PUT /api/agents/{id}/skill-packages`；与「拷进工作区的技能文件」是两回事 |
| 工具 / 插件 | 运行时配置（`config_json` / `agent_plugins`） | 否 | 菜单配置 |
| MBTI | `persona_mbti` | 否 | 菜单 |
| 记忆 | `MEMORY.md` 可带；`memory.sqlite` 运行态 | 部分 | 禁止打包 sqlite |
| 通道 | `channels` 表绑定 | 否 | 安装后 |
| 定时任务 | `cron_jobs` 表 | 否 | 安装后重建；manifest 的 `task_examples` 只是给用户的文案示例，不会自动建 cron |
| 模板来源 | `template_name` / `published_expert_id` | 否 | 由安装链自动写入 |
| 团队编制 | 主持人 `.octop/manifest.json` 的 `members`（本实例 agent_id） | 否 | **不要把团队主持人（`kind=team`）当业务专家打包**：主持人不挂技能/子智能体/插件，成员 id 跨实例不可移植；应分别打包成员专家，到目标实例再 `POST /api/teams` 组队 |
| Shared / 可见性 | `is_shared` / `resource_group_grant` | 否 | 与 zip 无关 |

---

## 6. 子智能体创建兼容

兼容 UI「添加子智能体」与 `POST /api/agents/{id}/subagents/install`：最终都是工作区 `agents/<slug>.md`。手打包请写入 **`.octop/agents/<slug>.md`**（对齐 export）；或依赖安装 API 写逻辑路径。

| 字段 | 来源 | 规则 |
|------|------|------|
| slug | 文件名 stem | 如 `change-reviewer.md` → `change-reviewer`；勿含 `/`；**frontmatter 里的 `id` 字段不会被解析**，slug 永远取自文件名 |
| name | frontmatter | 必填；展示名 |
| description | frontmatter | 必填语义；何时委托（bundled catalog 把它当硬要求） |
| emoji | frontmatter | 可选；UI 展示 |
| color | frontmatter | 可选；色名或 `#hex` |
| 正文 | frontmatter 后 Markdown | 指令内容；UI 表单「指令内容」 |

> 注意：没有 `---` YAML frontmatter 的 md **不会**被内置子智能体 catalog 识别（`is_agent_file` 为假）；工作区列表由 harness 读取，行为以 frontmatter 齐全为准，不要依赖无 frontmatter 的回落。

### 最小可创建模板

```markdown
---
name: 示例子智能体
emoji: "🤖"
description: |
  一句话说明何时由主专家委托本子智能体。
---

# 示例子智能体

调用方只看到最终回复。自主完成任务，返回可转发摘要。
```

补充约定：

- bundled catalog（`library/zh|en/…`）只用于「从目录安装」；业务包内嵌的是工作区副本，不依赖 `divisions.json`
- 装完或替换文件后需 reload 图（安装 API 会 reload；纯 zip 导入后若列表未刷新，在 UI 触发重载/重启专家）
- 主专家 `AGENTS.md` 应点名何时委派哪些 slug，避免孤儿子智能体

---

## 7. 打包与上传步骤

1. **用 Cursor 生成目录** — 按第 3–4 节骨架生成；业务技能与子智能体写全；manifest `id`/`label` 换成业务名  
2. **Trim 禁止项** — 删除 `.octop/_builtin_skills/**`、`memory.sqlite*`、`.env`、`credentials.json`、`sessions/`、`inbound/`、`uploads/`、`.git`。**这一步不可省**：archive export 不过滤 builtin/sqlite，而 import 只跳过 `_builtin_skills`，**不**跳过 sqlite/.env——打进 sqlite 会真实污染目标专家的记忆库  
3. **打 zip** — 在业务专家包目录**内**选中内容打包（zip 根直接是 `AGENTS.md` 与 `.octop/`），勿包一层外目录名  
4. **UI 建壳专家** — 从通用专家新建：设 Craft、模型、后端；需要时勾知识库/连接器；存储根慎用 `/`  
5. **导入 archive** — 专家运行中上传 zip。首灌可用 `replace`；迭代补丁用 `merge`。上限 200MB  
6. **验收** — 检查欢迎卡、技能列表、子智能体列表、提示词文件；按需 reload  

### merge vs replace

| 模式 | 行为 | 何时用 |
|------|------|--------|
| `merge`（默认） | 按路径覆盖同名文件，不删其它文件 | 增量更新技能/子智能体/提示词 |
| `replace` | 先清工作区可见非隐藏项，再写入；点文件（`.octop` 等）不整目录清空，但 zip 内路径会覆盖 | 用包完整替换业务内容；仍可能残留旧的 `.octop` 旁路文件 |

导入时路径落在 `_builtin_skills` 或 `.octop/_builtin_skills` 下的条目会被跳过（平台自有）。

---

## 8. 兼容性与坑

- **存储根目录 `/`**：等于整机文件系统；仅本机可信环境。业务专家应改到专用目录  
- **打错包形态**：Library 扁平包直接当 archive 传也可能部分工作（`skills/…`、`agents/…` 会被 system_files 映射重定位到 `.octop/` 下），但优先用第 3 节树  
- **把 builtin / sqlite 打进去**：增大体积；builtin 导入被跳过；sqlite 不被跳过、会污染记忆  
- **以为 zip 能带模型与企业知识库**：不能；必须在建壳时勾选  
- **Shared 专家**：可见性与分享和包无关；archive 导入要求 owner 且专家运行中  
- **团队主持人不可灌包**：`kind=team` 的主持人不挂技能/子智能体/插件/知识库，工具白名单极窄；把业务 zip 灌给主持人生效不了。团队协作应「分别打包成员专家 + 目标实例重新组队」  
- **archive 导入不会 reload 图**：技能/子智能体列表可能不刷新，需在 UI 触发重载或重启专家（install API 才会自动 reload）  
- **市场闸门不影响手传**：`market_mode=off/allowlist` 只会 403 掉 `/api/experts/hub*`、`/api/skills/hub*` 等市场路由；`workspace/archive` 是市场之外的 owner 接口，照常可用  
- **from-expert / published / hub**：另一条安装链（全部需要 JWT；hub 另需 `expert_market` 权限）；本手传流程只是不调用那条安装 API，并非那些接口无鉴权  
- **replace 对纯远程后端的限制**：无本地挂载时 replace 清不了远端文件（只写 warning），旧文件可能残留；此时应先手工清理或用 merge 精确覆盖  

---

## 9. Cursor 生成业务包检查清单

- [ ] 目录按 Workspace Archive 精简树，zip 根无多余外壳  
- [ ] 含 `SOUL.md` + `AGENTS.md` + `.octop/manifest.json`  
- [ ] 每个技能有 `skills` 或 `.octop/skills` 下 `SKILL.md`，frontmatter 合法  
- [ ] 每个子智能体为 `.octop/agents/<slug>.md`，含 `name`/`description` frontmatter  
- [ ] `AGENTS.md` 写明委派哪些子智能体 slug、读写哪些业务目录  
- [ ] 无 `_builtin_skills`、`memory.sqlite*`、`.env`、credentials  
- [ ] 未定制则不带平台注入物：`USER.md`、`PROACTIVE.md`、`.octop/agents/general-purpose.md`（规程未点名的子智能体是孤儿，见 `research/example-workspace.md` §5.2）  
- [ ] 不把团队主持人（`kind=team`）当打包对象  
- [ ] README 或附注列出「须在 UI 配置」：模型、后端、知识库 ID、连接器、MBTI、通道、插件  
- [ ] 本地知识仅放不可变样例/脚手架；不含用户隐私  
- [ ] `manifest.prompt_files` 与真实根 md 文件名一致  
- [ ] `quick_prompts` 的 `icon_name` 用仪表盘 `iconMap` 里存在的名字（如 `book-open`、`file-text`、`pen-tool`、`list-todo`、`globe`、`sparkles`），否则回退默认图标  
- [ ] 说明上传入口与 `merge`/`replace` 建议，并提醒「导入后需 reload/重启专家」  

### 给 Cursor 的一句话任务模板

> 按《Octop 专家包设计规范》生成 \<业务名\> 专家包目录：Workspace Archive 精简布局；含 SOUL/AGENTS/BOOTSTRAP、`.octop/manifest.json`、业务 skills、至少 N 个子智能体；附 `PACK.md` 写清 UI 必配项与 zip/上传步骤；禁止 builtin 与 sqlite。

---

## 10. 源码真源（本仓库当前代码，2026-10-31 核验）

| 主题 | 路径 |
|------|------|
| archive export/import | `src/octop/infra/backup/workspace_archive.py` |
| HTTP 上传/下载（200MB 上限、owner+running） | `src/octop/api/routers/workspace.py`（`…/workspace/archive`）、`src/octop/api/common/workspace.py` |
| 专家目录 / seed / manifest | `src/octop/infra/agents/experts/catalog.py` |
| 专家 HTTP 面（from-expert / publish / published install / hub） | `src/octop/api/routers/experts.py` |
| 发布编排（publish / refresh / unpublish / install） | `src/octop/infra/agents/experts/published_creation.py` |
| SkillHub 市场安装创建 | `src/octop/infra/agents/experts/market_creation.py` |
| 默认模板 id（`general-assistant`） | `src/octop/infra/agents/experts/default_agent.py` |
| 库种子示例 | `src/octop/infra/agents/experts/library/karpathy-knowledge-base/`（共 23 个库模板；隐藏空白壳 `default/`） |
| 发布快照裁剪（白名单） | `src/octop/infra/agents/experts/publish.py` |
| 创建时 composer 路径（正则白名单，拒绝 `.octop/`） | `src/octop/infra/agents/experts/composer_files.py` |
| 子智能体 API（`POST …/subagents/install`，需权限 `subagents`） | `src/octop/api/routers/subagents.py` |
| 子智能体 catalog（`library/zh\|en` + `divisions.json`，注意这是子智能体库、不是专家库） | `src/octop/infra/agents/subagents/catalog.py` |
| 工作区 SKILL.md 发现与 `metadata.octop` 展示元数据 | `src/octop/infra/skills/workspace_catalog.py`、`src/octop/infra/skills/presentation.py` |
| `validate_skill_slug`（仅禁空/前导 `.`/`/`/`\`/NUL） | `src/octop/infra/skills/skill_packages.py` |
| skills 发现根 | `src/octop/infra/agents/workspace/dir.py` → `skills_discovery_roots`（`.octop/skills` + `skills/`） |
| builtin 注入与跳过 | `src/octop/infra/agents/builtin_skills/__init__.py`（启动时 `sync_octop_builtin_skills` 覆盖写入） |
| system_files 映射（逻辑 `skills/`、`agents/` → 物理 `.octop/…`） | `src/octop/infra/agents/manager.py`（新 agent 恒 `system_files_path=.octop`）+ harness `apply_system_files_prefix` |
| frontmatter | `src/octop/infra/utils/frontmatter.py` |
| agent 行字段 | `src/octop/infra/db/repos/agents.py`（`knowledge_base_ids`、`mcp_servers`、`skill_package_ids`、`persona_mbti`、`template_name`、`welcome_message`、`icon_*`、`color`、`is_shared`、`kind`…） |
| 权限键（`experts` / `expert_market` / `subagents` / `skill_market` / `skill_packages`） | `src/octop/infra/users/permissions.py` |
| 行为证据（测试） | `tests/unit/backup/test_workspace_archive.py`、`tests/unit/agents/test_expert_catalog.py`、`test_expert_publish_snapshot.py`、`test_composer_files.py`、`tests/integration/test_experts_api.py`、`test_published_experts.py`、`test_subagents_api.py` |

**对照样本**：`参考示例/workspace-A73KWS/` 是 karpathy 专家的运行时导出（分析见 `research/example-workspace.md`）：根提示词 + `knowledge-base/` + `.octop/manifest.json` + `.octop/skills/llm-wiki`；应剔除 `_builtin_skills`、`memory.sqlite*`、平台注入的 `USER.md`/`PROACTIVE.md`/`general-purpose.md` 后再作业务包范本。

---

## 附录：包内可带 vs 仅安装后配置

### 包内可带

- `SOUL` / `AGENTS` / `BOOTSTRAP` 等提示词  
- `SKILL.md` 与技能附属文件  
- 子智能体 `agents/*.md`  
- `.octop/manifest.json` 欢迎元数据  
- 本地知识/剧本目录  
- `MEMORY.md` 热索引文本  

### 仅安装后 / 建壳时配置

- 默认模型、Provider  
- Craft / Ask / Plan  
- 存储后端与 `workspace_dir`  
- 企业知识库 ID  
- 连接器 / MCP 服务器列表  
- 全局 `skill_package_ids`  
- MBTI、通道、插件、工具开关  
- Shared 可见性  
- `memory.sqlite` 运行记忆  
