# 从 Hermes `customer-profiling` 拆成两个 Octop 专家

> 依据：`feature/skills/example/research/customer-profiling/`（v1.3.0 六阶段单体技能）、`feature/knowledge/guide.md`、`feature/docs/weknora-org-center-dual-plane.md`、WeKnora 连接器实现（只读 retrieve）。  
> 目标：共享专家 **企业探索** 负责企业事实采集并沉淀到公司公共知识库；销售专家 **客户营销分析** 只消费这些事实，再做芯片需求、品牌匹配与评分，自己不去爬工商/年报。

---

## 1. 结论先行

`customer-profiling` 现在是一条「查公司 + 做销售判断」的单体流水线。在 Octop 里应拆成：

| 产物 | 形态 | 职责 |
|------|------|------|
| **企业探索** | 共享公共专家（`is_shared`，不是 `kind=team`） | 核验主体、采集工商/法人/股东/财报/公告/风险/公开产品线，写成「企业档案」入库 |
| **客户营销分析** | 销售中心专家 | 先检索公共库；缺档或过期则 `ask_agent` 企业探索；再用销售技能做需求推断、品牌匹配、评分；**按输出模板把结果直接回给用户**（本轮不做 Word/PPT） |
| 技能包 A `enterprise-research` | 全局 skill package，只挂企业探索 | 可扩展的采集技能（工商、上市公告、风险、产品专利…） |
| 技能包 B `semicon-sales-intel` | 全局 skill package，只挂客户营销分析 | 芯片字典、授权品牌、评分框架、画像报告 |

**不要**把这两人做成「专家团队主持人」。`kind=team` 的主持人不挂技能、连接器、知识库，干不了采集。正确关系是：**两个普通专家 + 共享可见 + `ask_agent` / `@企业探索`**。

**WeKnora 怎么接（P0 能落地的部分）**：两个专家都绑连接器「公司公共知识」；营销分析另绑「销售中心知识」。技能里禁止写 Key / 调 WeKnora HTTP。专家用连接器工具 `search` / `read_document` / `list_knowledge_bases`。

**输出与 Hermes 的差别（本轮约束）**：Hermes `customer-profiling` 阶段六强制双格式落盘（`.md` + `md2docx.py` → `.docx` + 下载链接）。Octop **不走这条链路**。客户营销分析只按技能里的**输出模板**把 Markdown 报告作为对话回复交给用户；用户若要 Word，由其它 Octop 插件转换，**本轮不设计、不选型 `docx` 技能、不带 `md2docx.py`**。企业探索对调用方同样只返回档案正文/摘要，不导出 Office 文件。

**必须正视的缺口**：当前 WeKnora 适配器是只读的（`list_knowledge_bases` / `search` / `read_document`），retrieve Key 不能 ingest。企业探索「把每次采集写进公共库」**不能**走现有连接器。P0 用「工作区档案 → 知识管理员（或独立 ingest 通道）入 WeKnora」；P1 再给企业探索加一把 **ingest-only** 连接器（与 retrieve Key 严格分离）。见 §6。

---

## 2. 原技能包在干什么（拆分切面）

六阶段里，前半是**可共享的企业事实**，后半是**销售私有判断**（授权品牌、独立分销字典、110 分评分、切入策略）。

```text
Hermes customer-profiling
├── 阶段零   记忆/Obsidian 去重          → Octop：WeKnora 公共库检索（替代 Obsidian）
├── 阶段一   工商/法人/股东/规模/上市/风险 → 企业探索
├── 阶段二   产品/供应链公开信息/财报COGS → 企业探索
│            决策人公开名单               → 企业探索（事实）
│            联系窗口深挖 b2b-contact     → 客户营销分析（销售动作）
│            现有分销商 vs 我司差异化     → 客户营销分析（销售判断）
├── 类型判定 制造/贸易/平台/EMS/软件      → 企业探索给出「业务形态」；营销分析选择评分框架
├── 阶段三～五 芯片需求/品牌匹配/量化评分 → 客户营销分析
└── 阶段六   按输出模板回复用户（Octop 不生成 docx/PPT） → 客户营销分析
```

同目录里其它 Hermes 技能的归属：

| 原技能 | 归谁 |
|--------|------|
| `customer-profiling` 阶段一、二（事实）+ `chinese-sme-search-strategies` / `public-company-financial-research` / `english-name-and-entity-system-discovery` | 企业探索技能包 |
| `industry-chip-dictionary`、`device-chip-mapping.md`、行业客户专项（IPC/座舱/电源…） | 销售技能包 |
| `authorized-brands.md`、`distributor-advantage-brand-dictionary` | 销售技能包（也可再进销售中心知识库） |
| `b2b-contact-finder` | 销售（或以后独立「联系人」专家）；不要进公共企业档案正文 |
| `sales-rep-portfolio-analysis` / `sales-team-portfolio-analysis` | 另做组合分析专家，不塞进这两个 |
| 内部成交流水 / `session_search` | **禁止**进公司公共库；只留销售中心库或专家工作区 |

Hermes 的 Obsidian `客户画像/` 把「工商事实」和「我司品牌推荐」写在同一份报告里。搬到 WeKnora 后必须拆成两份文档，否则全员公共库会泄露授权品牌策略与客户等级。

---

## 3. 两个专家怎么分工

### 3.1 企业探索（公共专家）

| 项 | 设定 |
|----|------|
| 可见性 | `is_shared`（或公司组）；描述写明「使用公司公共知识」 |
| 默认连接器 | **只绑「公司公共知识」**，不绑任何中心库（符合 guide §3.1） |
| 技能 | 技能包 `enterprise-research`（见 §4.1） |
| 子智能体 | 可选：`工商核验员`、`上市公告研究员`、`风险扫描员`（并行长任务；主专家编排） |
| 工具 | 网页搜索、文件读写、WeKnora 检索；**不**挂授权品牌/芯片字典 |
| SOUL 一句话 | 你只产出可核验的企业事实档案；不做采购推荐、不评分、不写销售话术 |

**每次任务的强制顺序（写入 `AGENTS.md`）**：

1. 用连接器 `search` 查公共库：`公司全称` / 曾用名 / 统一社会信用代码。  
2. 命中且 `updated` 未过期（建议工商 90 天、年报到下一财年）→ `read_document` 返回档案，只对缺失字段补采。  
3. 未命中或过期 → 按技能采集 → 写出标准「企业档案」Markdown（§5）→ **入 WeKnora**（§6）。  
4. 返回给调用方的只是档案摘要 + WeKnora `knowledge_id` / 文档标题，不塞 2 万字搜索草稿。

### 3.2 客户营销分析（销售中心专家）

| 项 | 设定 |
|----|------|
| 可见性 | 销售中心用户组 |
| 默认连接器 | **销售中心知识 + 公司公共知识**（guide §3.2） |
| 技能 | 技能包 `semicon-sales-intel`（从 `customer-profiling` 砍掉采集段） |
| 子智能体 | 可选：`芯片需求推断员`、`品牌匹配员`、`评分员`（都只读档案，不联网查工商） |
| SOUL 硬规则 | **禁止**自行检索工商/天眼查/年报 PDF。企业资料一律来自公共库或 `ask_agent(企业探索)` |

**每次画像任务**：

1. 连接器搜公共库「{公司} 企业档案」。  
2. 无档 / 过期 / 关键字段空 → `ask_agent` 企业探索（sync；超长上市年报可用 background）。对方未 running 则失败回叫，不自动启动（与现网互调语义一致）。  
3. 用户也可在输入框 `@企业探索`，结果注入本轮再继续。  
4. 拿到档案后走阶段三～五，再按 **输出模板**（原 `SKILL.md`「输出报告模板」章节，去掉 Word/归档步骤）把完整结果作为本轮回复发给用户。  
5. （可选）把同一份 Markdown 写入**销售中心知识库**或本专家工作区，**不要**覆盖公共企业档案。不调用 `docx` / `md2docx` / PPT 技能。

销售专家可以读公共库里的企业档案，但 **不能写** 公共库。

### 3.3 对用户的输出形态（相对 Hermes 的删减）

| | Hermes `customer-profiling` | Octop 客户营销分析（本轮） |
|--|------------------------------|----------------------------|
| 主交付 | `exports/*.md` + `md2docx.py` → `*.docx` + `MEDIA:` 下载链 | **对话里按输出模板返回**完整 Markdown 报告 |
| PPT | `templates/ppt-template.js` 等 | **不做** |
| 归档 | 同步 Obsidian `客户画像/` + README 索引 | 公共事实进 WeKnora（企业探索）；销售报告可选进销售中心库 |
| Word 需求 | 本技能内转换 | **其它 Octop 插件**；本轮不选型 `docx`、不打包 `scripts/md2docx.py` |

裁切 `customer-opportunity` 时：保留 `SKILL.md` 从「输出报告模板」到各章节结构（基本信息速览、芯片需求、双源品牌表、评分、切入策略等）；删除「报告输出格式要求」里生成 `.docx`、点击下载、`python-docx` 依赖、Obsidian `cp`/`md5sum` 各条。模板本身仍是销售交付的真源，只是载体从文件变成回复。

---

## 4. 技能包怎么切

技能不内嵌凭证、不直连 WeKnora（guide §4）。知识需求用「需要公司公共知识 / 需要销售中心知识」声明。

### 4.1 技能包 `enterprise-research`（只挂企业探索）

从原 `SKILL.md` 阶段一、二 + `references/` 里「怎么搜到事实」的文档抽出，拆成可独立演进的技能（扩展点就在这里）：

| slug | 来源 | 采集什么 |
|------|------|----------|
| `company-identity` | 阶段一 1/1a/1c/1d | 全称消歧、曾用名、母子/跨境实体表、注册资本、法人、股东、参保 |
| `company-listings` | 阶段一第 2 步 + `public-company-financial-research.md` | 上市代码、年报/半年报/公告、营收毛利、问询函 |
| `company-risk` | 阶段一第 3 步 | 诉讼角色、被执行、失信、税务信用、财务造假专项 |
| `company-products-public` | 阶段二 2a/2b 公开部分 | 官网产品线、专利/软著、工厂分布、公开 COGS/供应链新闻 |
| `company-officers-public` | 阶段二 2c 公开部分 | 年报董事、官网 leadership（**到职位级，不下私人手机/个人邮箱**） |

以后要加深「工商 / 风鸟 / 招投标」：把 SkillHub 的 `company-search-fengniao`、`precision-bid-customer-ai-engine` **加进这个包**，不要加给营销分析。Key 走连接器或环境变量，不进 SKILL 正文。

主专家 `AGENTS.md` 点名：缺工商 → `company-identity`；是上市公司 → 再派 `company-listings`；始终跑 `company-risk`。

**子智能体（可选，不是必须）**：技能负责「怎么采」；子智能体负责「并行跑完一类源」。例如上市集团可同时派 `上市公告研究员`（读 PDF）和 `工商核验员`（大陆子公司）。子智能体仍落在企业探索工作区 `.octop/agents/`，不单独绑 WeKnora。

### 4.2 技能包 `semicon-sales-intel`（只挂客户营销分析）

| slug | 来源 |
|------|------|
| `customer-opportunity` | 原 `customer-profiling` 阶段三～六 + 类型分支 + **输出模板**（**删除全部联网工商步骤与 Word/PPT/Obsidian 归档**；开头改为「输入=企业档案」；阶段六 = 按模板回复用户） |
| `device-chip-mapping` | `references/device-chip-mapping.md` + 各行业 `*-customers.md` |
| `authorized-product-line-reference` | 现有独立权威包 `feature/skills/example/research/authorized-product-line-reference/`（a/c 表）；不要再从画像 `references/authorized-brands.md` 派生第二份 |
| `distributor-advantage-brand-dictionary` | 现有独立字典技能包 |
| `b2b-contact-finder` | 联系窗口；产出进销售报告第四章，不写公共档案 |

`industry-chip-dictionary` 若仍是独立技能，挂进同一 skill package 或拷进工作区 `skills/`。

---

## 5. 两份文档，两座库（替代 Hermes 一份画像）

### 5.1 公司公共库：企业档案（企业探索写）

面向全员检索。只含公开事实，字段从原 frontmatter 的 **L0 事实侧**抽出，去掉等级/已供品类/授权品牌。

建议文件名：`{统一社会信用代码或英文slug}_企业档案.md`

```yaml
---
title: 研华科技 企业档案
doc_type: enterprise-dossier          # 固定，检索过滤用
company_legal_name: 研华科技（中国）有限公司
aka: [研华, Advantech]
credit_code: "…"
entity_graph: [台湾上市母公司, 昆山运营主体]
business_form: 制造型                  # 制造/贸易/平台/EMS/纯软件
listed: true
ticker: "2395.TW"
risk_flags: []                         # 不含「C级客户」这类销售评级
sources: [{title, url, retrieved}]
updated: 2026-11-01
fresh_until: 2026-12-31
---
```

正文固定六节：主体与股权、规模与市场地位、上市与公告要点、风险与合规、公开产品与供应链、数据局限。每条数字标注来源与采集日。查不到写「公开信息未披露」，禁止编造。

### 5.2 销售中心库：客户营销分析（营销分析写，可选）

可保留 Hermes L0 销售字段 + L1/L2：`cooperation_status`、`profile_grade`、`tags_l1_supplying`、`tags_l1_opportunity`。引用公共档案的 `knowledge_id`，不复制整份年报。

检索漏斗：公共库 L0 主体 → 销售库 L1 品类标签 → 精读营销报告。这与原 `customer-profile-frontmatter-schema.md` 三层漏斗一致，只是事实层改由 WeKnora 公共 Tenant 承担。

---

## 6. 专家如何连接 WeKnora

### 6.1 检索平面（P0，现网就能配）

按 `feature/knowledge/guide.md`：

```text
WeKnora Tenant company-public  ──retrieve Key──► Octop 连接器「公司公共知识」 visibility=all（或公司组）
WeKnora Tenant center-sales    ──retrieve Key──► Octop 连接器「销售中心知识」 visibility=groups → ug-center-sales
```

建壳时（zip 带不进去，必须 UI 勾选）：

| 专家 | `mcp_servers` / 默认连接器 | 不要勾 |
|------|------------------------------|--------|
| 企业探索 | 公司公共知识 | 任何中心连接器 |
| 客户营销分析 | 公司公共知识 + 销售中心知识 | 其它中心库 |

Prompt / SOUL **禁止**写 `tenant_id`、KB UUID、Key、内网 IP。只写连接器显示名：「先用公司公共知识检索企业档案」。

运行时工具来自 WeKnora gateway adapter（`src/octop/infra/connectors/gateway/adapters/weknora.py`）：

- `list_knowledge_bases`
- `search(query, knowledge_base_ids?)`
- `read_document(knowledge_id)`

技能通过「所在专家已绑定的连接器」间接触达这些工具，自己不发 HTTP。

### 6.2 写入公共库（规划要做、P0 连接器做不到）

双平面方案写明：**内容写入在 WeKnora 控制台由 Admin/Contributor 完成；Octop 连接器保持只读 retrieve。** 适配器也没有 ingest 工具。

因此「企业探索每次采集都入库」要分两期：

**P0 手工/半自动（与当前规范兼容）**

1. 企业探索把档案写到自己工作区 `dossiers/*.md`（可版本化）。  
2. 知识管理员（公共 Tenant Contributor）在 WeKnora 上传或更新同名文档，挂到公共 KB。  
3. 或用 **独立于 Octop retrieve 连接器** 的运维脚本（ingest Key 只放管理员密钥库）监听该目录并 upsert。脚本不属于技能、不进专家 zip。  
4. 营销分析下一轮 `search` 即可命中。

**P1 产品能力（若要专家自动入库）**

1. 另建 WeKnora **ingest-only** Key（能力含上传，白名单仅公共 KB；与 retrieve Key 分离）。  
2. 新增连接器实例「公司公共知识-写入」，**仅绑定企业探索**（或只给知识管理员角色），工具如 `upsert_document`。  
3. 技能仍然不持有 Key；由专家绑定满足「需要公共知识写入入口」。  
4. 营销分析专家 **禁止**绑定写入连接器。

在 P1 落地前，不要在技能里假装「已写入 WeKnora」。`AGENTS.md` 应写：完成本地档案后输出「待入库」状态，直到管理员确认。

### 6.3 调用时序

```text
销售用户 → 客户营销分析
    │  search「公司公共知识」：企业档案
    ├─ 命中且未过期 → 读档 → 销售技能按输出模板回复用户
    └─ 未命中/过期  → ask_agent(企业探索, sync)
                         │  search 公共库（避免重复采）
                         ├─ 仍缺 → skills 采集 → 写 dossiers/*.md
                         ├─ P0：提示入库 / 运维 upsert
                         └─ 返回 knowledge_id 或档案正文摘要
                      ← 营销分析继续阶段三～六
                      （可选）写入「销售中心知识」客户营销分析文档
```

企业探索必须 **running**，否则 `ask_agent` 失败。共享专家建议常驻，或销售侧栏提示先启动。

---

## 7. 不要踩的坑

| 做法 | 为什么不行 |
|------|------------|
| 做成 `kind=team` 主持人 + 两个成员 | 主持人不挂技能/连接器，企业探索无法采集 |
| 营销分析工作区再拷一份采集技能 | 会重新联网搜工商，双源打架 |
| 把完整「客户画像报告」上传公共库 | 含授权品牌与评分，违反最小可见 |
| 技能内写 WeKnora Key 或直调 HTTP | 违反 guide §4 |
| 用 `knowledge_base_ids` 代替连接器 | 规范是「专家绑定知识 = 绑定连接器实例」 |
| 企业探索绑销售中心库 | 公共专家只绑公共连接器 |
| 用 MEMORY.md / memory.sqlite 当公共库 | 不能跨专家、不能按组可见；MEMORY 只做本专家热索引 |
| 子智能体替代企业探索专家 | 子智能体不能被其它专家共享，也无法单独绑连接器给全员用 |
| 把 Hermes 的 `md2docx.py` / `docx` 技能塞进营销分析 | 本轮交付是模板化对话回复；Word 由其它插件支持，不在这两个专家包里 |

---

## 8. 落地顺序（建议）

1. **建壳**  
   - 企业探索：from-expert 空白壳 → 共享 → 只勾「公司公共知识」。  
   - 客户营销分析：销售组可见 → 勾「公司公共知识 + 销售中心知识」。  
2. **灌技能**  
   - 把 `customer-profiling` 按 §4 拆成两个目录，分别拷进两专家 `.octop/skills/`，或做成两个 skill package 再 `PUT /agents/{id}/skill-packages`。  
3. **写规程**  
   - 企业探索 `AGENTS.md`：WeKnora 先查、再采、再归档。  
   - 营销分析 `AGENTS.md`：禁止工商搜索；必须 `ask_agent` 企业探索。  
4. **WeKnora**  
   - 公共 Tenant 建 KB「企业档案」，retrieve Key 白名单仅此库。  
   - 销售 Tenant 建 KB「客户营销分析」（可选）。  
   - P0 定上传人；P1 再提 ingest 连接器。  
5. **互调验收**  
   - 用销售测试号：无档公司走一遍 `ask_agent`；有档公司确认不再触发联网工商。  
   - 用非销售号：能 `@企业探索` 查公开事实，看不到营销报告。

---

## 9. 给 Cursor 生成两个专家包时的任务句

企业探索：

> 按 `feature/experts/template.md` 生成「企业探索」Workspace Archive：SOUL 只做企业事实采集；AGENTS 强制先检索连接器「公司公共知识」再联网；技能用 `enterprise-research` 五个 slug；可选子智能体工商核验员/上市公告研究员/风险扫描员；PACK.md 写明只绑公共知识连接器、写入 WeKnora 走 P0 管理员入库；禁止授权品牌与评分。

客户营销分析：

> 按 `feature/experts/template.md` 生成「客户营销分析」Workspace Archive：SOUL 面向半导体分销销售；AGENTS 规定企业资料只来自公共库或 ask_agent 企业探索，禁止自行搜工商/年报；技能从 customer-profiling 阶段三～六 + authorized-brands + device-chip-mapping 裁出；阶段六按原「输出报告模板」把 Markdown 直接回复用户，删除 Word/PPT/Obsidian 归档；报告引用企业档案 knowledge_id；PACK.md 写明绑定公司公共知识 + 销售中心知识。禁止打包 docx 技能与 md2docx。

---

## 10. 做成两个专家包还差哪些资料

按 `feature/experts/design.md`：专家包 zip 只含工作区文件；连接器 / 模型 / 共享 / 用户组 **不进 zip**。因此缺口分三层：**① 还没有写成 Octop 技能的内容** → **② 技能齐了仍要写的专家骨架** → **③ 灌包后必须手工做的建壳（含 WeKnora，见 §11）**。

本轮 **不做** Word/PPT、`docx` 技能、ingest 连接器产品开发。

### 10.1 已经有、可直接当原料（不必再调研）

| 原料 | 路径 | 用途 |
|------|------|------|
| 拆分方案 | 本文 §1–§9 | 分工、调用顺序、禁止项 |
| 专家包规范 / 工厂 | `feature/experts/design.md`、`template.md` | 目录树、manifest、PACK.md |
| 单体技能 + 输出模板 | `feature/skills/example/research/customer-profiling/SKILL.md`（「输出报告模板」起） | 营销分析阶段三～六与回复格式 |
| 行业专项 | 同目录 `references/*-customers.md`、`device-chip-mapping.md` | `device-chip-mapping` 技能的 references |
| 工商/上市检索方法 | `references/chinese-sme-search-strategies.md`、`public-company-financial-research.md`、`english-name-and-entity-system-discovery.md` | 拆进企业探索技能 |
| 行业字典（可整包拷） | `feature/skills/example/research/industry-chip-dictionary/` | 销售技能包 |
| 授权品牌 a/c 表（可整包拷） | `feature/skills/example/research/authorized-product-line-reference/` | 销售技能包（优先于画像里那份 `authorized-brands.md`，避免双真源） |
| 独立分销字典（可整包拷） | `feature/skills/example/research/distributor-advantage-brand-dictionary/` | 销售技能包 |
| 联系人（可整包拷，需删私人联系写入公共档案的可能） | `feature/skills/example/research/b2b-contact-finder/` | 销售技能包 |
| SkillHub 可选加深 | `company-search-fengniao`、`deep-research-engine`、`precision-bid-customer-ai-engine` | **第二期**再挂企业探索；第一期 zip 可不带（缺 Key 会变成主路径失败） |
| 知识规范 | `feature/knowledge/guide.md` | 连接器绑定原则 |

### 10.2 技能包还没写出来的文件（卡专家包的主因）

规划里的 `enterprise-research` / `semicon-sales-intel` **目录尚不存在**。没有这些 `SKILL.md`，专家包的 `.octop/skills/` 是空的。

**技能包 A — 必须新写（Hermes 里没有独立 SKILL.md）：**

| 缺的文件 | 缺什么 |
|----------|--------|
| `company-identity/SKILL.md` | 从画像阶段一抽出；frontmatter `name`+`description`+`metadata.octop`；声明「需要公司公共知识」；**禁止**评分/品牌 |
| `company-listings/SKILL.md` | 同上，吃 `public-company-financial-research.md` |
| `company-risk/SKILL.md` | 诉讼角色、税务信用、造假专项 |
| `company-products-public/SKILL.md` | 产品/专利/公开供应链；不含「我司 vs 大联大」 |
| `company-officers-public/SKILL.md` | 到职位级；明确不下私人手机/个人邮箱 |
| **`enterprise-dossier.md` 正文模板** | §5.1 只有 YAML 示例 + 六个节名。专家/技能无法对齐结构。需要一份与销售「输出报告模板」同级的 **完整 Markdown 空模板**（含表头） |

**技能包 B — 必须改写 + 可拷贝：**

| 缺的文件 | 缺什么 |
|----------|--------|
| `customer-opportunity/SKILL.md` | **必须新写**：输入=企业档案（不是联网工商）；删除阶段一/二采集、Word、Obsidian、Hermes 路径；保留类型分支、评分、**输出报告模板**；分析师署名改成专家名 |
| `device-chip-mapping/SKILL.md` | 把 `device-chip-mapping.md` + `*-customers.md` 收成一个技能（现只是 references） |
| `industry-chip-dictionary/` | **拷贝**现成包即可 |
| `authorized-product-line-reference/` | **拷贝**现成包；不要再维护画像内 `authorized-brands.md` 第二份 |
| `distributor-advantage-brand-dictionary/` | **拷贝**现成包 |
| `b2b-contact-finder/` | **拷贝**；`AGENTS.md` 写明产出只进对话报告第四章 |

**两包共用、现在也没有的「契约」短文（各一页就够）：**

1. **互调输入输出**：营销分析 `ask_agent` 时必须带哪些字段（公司名/曾用名/信用代码/是否强制刷新）；企业探索返回什么（档案 Markdown 或「已入库标题 + 待入库」）。zip 里 **不能写死** 对方 `agent_id`（实例 ULID），只能写显示名「企业探索」。  
2. **过期规则**：工商 90 天、年报到下一财年——要写进企业探索技能，不能只出现在方案文档。  
3. **业务形态枚举**：制造 / 贸易 / 平台 / EMS / Design House / 纯软件，与营销分析分支框架一一对应。

### 10.3 技能齐了，专家包仍要新写的文件（design.md 必带）

这些 **不能**从 SKILL 自动长出来，要按 `template.md` 手写/生成：

| 文件 | 企业探索 | 客户营销分析 |
|------|----------|----------------|
| `SOUL.md` | 只做事实；不评分、不推荐品牌 | 销售判断；禁止自行搜工商 |
| `AGENTS.md` | WeKnora 先查 → 技能采集 → 写档案 → 待入库；点名五个采集 slug + 可选子智能体 | 先搜公共库 → `ask_agent` 企业探索 → `customer-opportunity`；点名销售技能 slug |
| `BOOTSTRAP.md` | 首次确认：搜哪家公司、是否强制刷新 | 首次确认：分析哪家、已合作还是潜在 |
| `.octop/manifest.json` | id/label/welcome/`quick_prompts`（查工商/补档/读已有档案） | 做画像/已合作客户/只出评分 等 6 张卡；`icon_name` 用仪表盘安全名 |
| `PACK.md` | 见下表「zip 带不走」 | 同左 |
| `MEMORY.md` | 可选：本专家热索引，**不是**公共库 | 可选 |
| `.octop/agents/*.md` | **可推迟**：工商核验员等三个子智能体不是第一期必做 | **可推迟**：芯片需求推断员等 |

`USER.md` / `PROACTIVE.md` / `knowledge-base/` 本地目录：**不要带**（平台会注入空模板；知识走 WeKnora）。

### 10.4 zip 带不走、建壳时你必须准备的信息（资料不是文件，是决策）

| 项 | 企业探索 | 客户营销分析 | 现在缺不缺 |
|----|----------|----------------|------------|
| 显示名 / 是否共享 | 共享公共专家 | 仅销售组 | 名称已定；**用户组 ID**（如 `ug-center-sales`）要你在 Octop 里建 |
| Craft + 默认模型 | 建议 Craft | 建议 Craft | 选哪家模型——你定，不进包 |
| 存储后端与工作区根 | 专用目录，勿 `/` | 同左 | 你定 |
| 默认连接器 | 只绑「公司公共知识」 | 「公司公共知识」+「销售中心知识」 | **WeKnora 侧尚未按本方案建 Tenant/KB/Key** → §11 |
| 网页搜索 | 企业探索需要 | 营销分析原则上不需要（联系人技能除外） | Octop 搜索/网页能力是否已开——你确认 |
| 风鸟 / 世舶 Key | 第一期可没有 | 不要配 | 有 Key 再拷 SkillHub 技能 |
| 对方专家已启动 | 建议常驻 | `ask_agent` 依赖企业探索 running | 运维约定，写进 PACK.md |

**第一期可以砍掉、不阻塞出包：** 子智能体、SkillHub 风鸟/招投标、销售中心库（营销报告可只活在对话里）、P1 ingest 连接器。

**第一期砍不掉：** §10.2 五个采集技能 + 企业档案模板 + 改写后的 `customer-opportunity` + 两份 SOUL/AGENTS/manifest/PACK + §11 两套连接器（至少公共库）。

### 10.5 手工 zip 形态（上传前再核对一次）

| 包 | zip 根布局 | 上传位置 | 备注 |
|----|------------|----------|------|
| 专家 Workspace Archive | `SOUL.md`、`AGENTS.md`、`BOOTSTRAP.md`、`PACK.md`、`.octop/manifest.json`、`.octop/skills/<slug>/SKILL.md`、可选 `.octop/agents/*.md` | 已创建且运行中的专家 → 工作区 archive 导入 | 本轮推荐；技能直接随专家走，无需先建全局技能包 |
| 单技能 zip | zip 根直接是 `SKILL.md`， sibling 目录为 `references/`、`scripts/` 等 | 专家技能页或技能包详情的 ZIP 导入 | 适合单独补一个技能 |
| 多技能 zip | 每个顶层目录是一个 slug，目录内含自己的 `SKILL.md`；不要再多套一层无关外壳 | 专家技能页或技能包详情的 ZIP 导入 | 适合 `enterprise-research` / `semicon-sales-intel` 一批导入 |
| 全局技能包 | zip 只携带技能文件，不携带包名、图标、共享、挂载关系 | 先在 UI 建空技能包，再导入 zip，再到专家建壳勾选 | 若要跨专家复用才做；本方案两个技能包都只服务一个专家，可不做 |

注意：仪表盘 ZIP 导入器会把「单个非技能外壳目录」剥掉，但手打包仍应按上表直接放到 zip 根，避免依赖容错。

---

## 11. WeKnora 手工创建设置指引（P0）

Octop 包和技能 **都不含** Tenant / Key / KB UUID。下面只给你在 WeKnora 控制台 + Octop 连接器里点的步骤。实例 IP、现有 Key 文件位置见 `docs/connectors-weknora.md`（内网参数，不要写进专家 zip 或 SOUL）。

### 11.1 在 WeKnora 建两个平面（建议）

**A. 公司公共（企业探索写、全员可读）**

1. 新建 Tenant，id 建议 `company-public`（或沿用现有企业共享空间，但 **不要** 和销售库混在同一 KB）。  
2. 在该 Tenant 建知识库，显示名 **「企业档案」**。Embedding 模型必须配好，否则检索 200 但空结果。  
3. 建一把 **retrieve-only** API Key：能力仅检索；白名单 **只含「企业档案」这一个 KB**；备注 `company-public-retrieve-octop`。  
4. （P0 入库）指定一名知识管理员为该 Tenant 的 **Contributor**：负责把企业探索工作区 `dossiers/*.md` 上传/覆盖为同名文档。retrieve Key **不要**给写入权限。

**B. 销售中心（可选，第一期可缓）**

1. 另建 Tenant `center-sales`（组织中心 = Tenant，**不要**把销售库建进公共 Tenant）。  
2. 建知识库 **「客户营销分析」**。  
3. 另建 retrieve-only Key，白名单仅该 KB；备注 `center-sales-retrieve-octop`。  
4. 该 Tenant 的 viewer / Octop 可见性只给销售组。

### 11.2 在 Octop 配连接器

1. 若 `base_url` 是内网 `http://`（非 localhost）：在 **Octop 进程**环境变量设  
   `OCTOP_WEKNORA_TEST_HTTP_ORIGIN=<与 base_url 完全相同的 origin>`  
   （无路径、无 `/api/v1`）。HTTPS 私有 CA 再配 `OCTOP_WEKNORA_CA_BUNDLE`。  
2. 连接器 → 内置 WeKnora，新建实例：  
   - 显示名必须是 **「公司公共知识」**（专家 SOUL 用这个名字，不要用 UUID）。  
   - 填 `base_url`、公共 Tenant、retrieve Key、**显式** KB id（企业档案）。  
   - 可见性：`all` 或公司组。保存前必须探测成功。  
3. （可选）第二实例显示名 **「销售中心知识」**：销售 Tenant + 销售 Key + 销售 KB；可见性 `groups` → 只挂 `ug-center-sales`。禁止 `visibility=all`。  
4. **同一 Tenant 不要建两条重叠连接器。** 平台管理 Key / SystemAdmin JWT 不要填进连接器。

### 11.3 绑到两个专家（灌 zip 之后）

| 专家 | 默认连接器 | 不要勾 |
|------|------------|--------|
| 企业探索 | 仅「公司公共知识」 | 销售中心、其它中心 |
| 客户营销分析 | 「公司公共知识」+（若已建）「销售中心知识」 | 写入类、其它中心 |

专家描述写清知识范围，便于审可见性。SOUL 只写连接器显示名。

### 11.4 P0 入库与验收

1. 企业探索产出 `dossiers/{信用代码或slug}_企业档案.md`（结构见将来的档案模板）。  
2. 知识管理员在 WeKnora 公共 KB **上传或覆盖**同名文档（标题含公司名 +「企业档案」，便于 `search`）。  
3. 营销分析下一轮应对「公司名 企业档案」能 `search` 到，再 `read_document`。  
4. 抽查：销售测试号能搜到公共档案、搜不到不该看的中心库；非销售号不能用「销售中心知识」。  
5. 检索 200 无结果：库空、未索引或该 Tenant 未配 Embedding——先查 WeKnora，再查连接器 KB id 是否填错。

第一期没有销售 Tenant 时：营销分析仍绑公共连接器读企业档案；销售报告只出现在对话里，不入库。这不阻塞两个专家包出包。
