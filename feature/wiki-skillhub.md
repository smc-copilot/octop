# SkillHub Project Semantic Overview

## Purpose

SkillHub 本质上是**企业私有 Agent Skill 注册与治理平台（Registry & Governance）**，不是技能内容集合、不是 Agent Runtime、不是技能执行器。它对应 npm/Maven registry 在 "SKILL.md 格式技能包" 领域的等价物：托管、版本化、发现、访问控制、分发。技能内容的权威格式是外部生态标准（Anthropic Agent Skills / OpenSkills 的 `SKILL.md` + frontmatter），SkillHub 只是基础设施层。 [1](#0-0) [2](#0-1) 

明确不是：不执行技能（Runtime trace 的权威源在 Agent Runtime 侧），不生成/修改客户端 `AGENTS.md`（客户端职责），不返回 `location` 字段，不做多租户 SaaS（单实例 + Namespace 隔离）。

## Core Architecture

分层模块化单体（layered modular monolith），非微服务：

- **`server/` (Java 21 / Spring Boot 3.x, Maven 多模块）**：`skillhub-app`（Controller/HTTP 层，含 `SkillController`、`ClawHubCompatController`）→ `skillhub-domain`（领域服务：`SkillPublishService`、`SkillQueryService`、`SkillMetadataParser`、Namespace/RBAC 服务）→ `skillhub-storage`（`ObjectStorageService` 抽象 → `LocalFile` / `S3StorageService` / MinIO 实现）。
- **`web/` (React 19 SPA)**：`ApiClient` + feature hooks + TanStack Router 页面层。
- **`cli/`（第一方 CLI，npm 包 `@astron-team/skillhub`）**：publish/install/sync，负责客户端侧 AGENTS.md 生成、`.astron/metadata.json` 私有元数据、安装目录约定。
- **`plugins/dsh/`**：DeepSeek Harness 原生插件，消费 `.skillhub/examples.json` 任务模板协议。
- **`github-sync-go/`**：Go 编写的 GitHub 技能同步 worker + 控制面内部 API。
- **`builtin-skills/`**：官方 starter 技能源集合 + 确定性 ZIP 构建（`make build-builtin-skills`）+ `evals.json` 回归用例 + `catalog.json` 溯源。
- **`scanner/`**：技能包安全扫描服务。
- **基础设施**：PostgreSQL（元数据 + 全文搜索）、Redis、对象存储。

所有 REST 响应遵循统一包络 `{code, msg, data, timestamp, requestId}`，见 `docs/06-api-design.md`。

## Stable Abstractions vs Volatile Details

**稳定抽象（改动需谨慎、有兼容成本）**：

- `SKILL.md` 契约：`name`/`description` 必需 frontmatter；`name` → `skill.slug` 且首发布后不可变；目录名 = slug 作为客户端 lookup key。
- 坐标系 `@{namespace}/{slug}` 与 ClawHub canonical slug `{namespace}--{slug}` 双向映射。
- 安装目录优先级 `.agents/skills → ~/.agents/skills → .claude/skills → ~/.claude/skills`（与 OpenSkills 互操作硬约定）。
- 统一 API 响应包络、Namespace 作为唯一治理边界、`latest` 为系统保留只读标签。
- `x-astron-` 前缀私有扩展命名空间（如 `x-astron-compliance` → 版本级 `complianceSnapshot` + `digest`）。

**易变实现细节**：存储后端（LocalFile/S3/MinIO 可插拔）、搜索排序权重、Web UI 呈现、CLI 私有 `.astron/metadata.json`、`<skills_system>` 区块内部格式、扫描器内部规则。

## Key Modules

- `server/skillhub-domain/.../skill/metadata/SkillMetadataParser.java`：SKILL.md frontmatter/正文 → 归一化 `SkillMetadata`，YAML 有安全限制（alias≤20、深度≤20、code points≤200k）。 [3](#0-2) 
- `SkillPublishService` + `SkillPackageValidator`：发布流水线（解析→校验→扫描→写存储→落库）。
- `ClawHubCompatController`：ClawHub/OpenClaw 协议适配层，只覆盖 search/inspect/install，**不覆盖 publish**。
- `plugins/dsh/src/host/skill-format.ts`：复用官方 `FileSystemSkillProvider` 校验 staged SKILL.md，不注册 provider。 [4](#0-3) 

## Lifecycle

技能：`publish`（解析 SKILL.md → 包校验白名单/大小/数量 → 安全扫描 → 元数据快照含 `parsed_metadata_json`/`complianceSnapshot` → 状态进入审核）→ 命名空间 Admin 审核 → 平台 Admin 提升到 `@global` → 打 tag（`beta`/`stable`，`latest` 自动追踪）→ 下载/CLI 安装 → 可撤下回退（展示名/摘要随版本回滚）。见 `docs/14-skill-lifecycle.md`、`docs/05-business-flows.md`。

部署生命周期：`make dev-all` 起本地栈 → Flyway 迁移 Postgres → builtin-skills 清单初始化 `@global` 内置技能（manifest 钉住 CDN URL + SHA-256，字节校验后才解压）。

## Extension Points

- **新存储后端**：实现 `ObjectStorageService` 接口，勿动 domain 层。
- **新客户端/Agent 平台**：优先走 `--dir` 显式安装目录 + ClawHub 兼容 slug 映射；只有需要协议级适配时才加 Controller（参照 `ClawHubCompatController` 模式）。
- **新技能元数据**：用 `x-astron-` 前缀 frontmatter 扩展，禁止占用生态标准字段；发布校验 + 版本快照 + 详情展示 + 审核 diff 是扩展元数据的完整路径（参照 `x-astron-compliance` 实现）。
- **新内置技能**：`builtin-skills/skills/<slug>/` 加包 + `catalog.json` 溯源 + `evals.json` 用例 + `make test-builtin-skills`；进 runtime manifest 前必须有不可变 CDN URL + SHA-256。
- **新 Web 页面**：`web/src/pages/` + hooks + `ApiClient`，勿绕过统一响应包络。
- **新 GitHub 同步源**：`github-sync-go` worker 侧，经内部控制面 API 对接。

## Constraints / Invariants

- `skill.slug` 源自 SKILL.md `name`，发布后**不可变**；`metadata.display-name` 仅展示用（≤200 字符，trim 空回退 name），历史快照非法值只读回退不阻塞流程。
- 文件白名单 `.md/.txt/.json/.yaml/.yml/.js/.cjs/.mjs/.ts/.py/.sh/.png/.jpg/.svg`；单文件 1MB、总包 10MB、100 文件（可配）。
- `packaged-file` 证据路径禁止 `../` 逃逸；同版本内 `standard+version+controlId` 不可重复。
- 服务端**永不**生成 AGENTS.md / `location`；`.skillhub/metadata.json` 的 installer 权威性不可被上传内容覆盖。
- Namespace 是唯一隔离边界，禁止引入 tenant 概念。
- `latest` 标签系统保留只读。
- 线程/并发模型：Spring 同步 MVC + DB 约束保证版本/tag 指针一致；版本指针（`latest_version_id`/published pointer）是单一事实源。
- builtin 包 ZIP 须确定性（无压缩、可复现 hash）。

## SKILL 模板设计、市场适配与二开

**模板即协议**：SKILL 模板不是服务端模板引擎，而是 `SKILL.md` 文件协议本身——frontmatter（`name`/`description` 必需，`version`、`metadata.display-name`、`x-astron-*` 可选）+ Markdown 指令正文 + 约定目录 `references/ scripts/ assets/`。服务端职责止于解析（`SkillMetadataParser`）、校验、快照入库；模板渲染/执行完全在 Agent 侧。

**市场适配**：Marketplace（`/search`、landing 热门/最新区块、`SkillCard`）只消费服务端投影出的元数据（name/display-name/summary/标签/下载量/合规投影），不读包内容。适配路径为：搜索索引文档构建（Postgres FTS，visibility 过滤）→ 列表/详情 API → 前端卡片。新增展示字段需同时更新版本快照 + 搜索投影 + API DTO + i18n locale。

**二开边界**：对上游 `anthropics/skills` 等包的二次开发是纯内容层行为——fork 包目录、改 SKILL.md/资源、遵守各自 LICENSE、用 CLI `publish` 进私有 namespace；平台侧二开（改协议字段、坐标规则、兼容层）属于高风险修改，会破坏与 OpenSkills/Claude/ClawHub/DSH 客户端的互操作不变式。

## 智能体专家模板、市场适配与二开

代码库中**不存在独立的 "expert/agent 模板" 领域实体**——"智能体专家" 在系统中就是技能包本身（把专家知识沉淀为 SKILL.md 指令 + 脚本 + 参考文件）。最接近"专家模板"机制的是 `.skillhub/examples.json` 任务模板协议：包内固定路径、多语言集合（`id`/`title`/`prompt` + `defaultLocale`）、`{{skill}}` 占位符由消费端替换为已验证的本地调用方式，由 `plugins/dsh` 等客户端在 composer 上方内联呈现。 [5](#0-4) 

**适配要点**：examples.json 无效/缺失时不阻塞发布（降级为普通包内容 + 提示），消费端按宿主语言精确匹配→父标签→声明默认值回退，禁止自动翻译/混语言；模板与**具体版本**绑定，跨版本/scope 不得复用。 [6](#0-5) 

**二开**：新增消费端须自行实现"精确 `{{skill}}` 占位符替换 + 已验证调用注入"，不得做模板表达式求值或从 market slug 推断调用名；旧客户端/旧技能必须保持可用。

## Risk Hotspots

高危修改：`SkillMetadataParser` 解析规则、坐标/slug 映射、安装目录约定、统一响应包络、版本指针与 `latest` 语义、`.skillhub/` 协议文件、审核/提升状态机——这些都牵动外部客户端兼容性与治理不变式。相对安全：存储实现、搜索排序、UI 层、`x-astron-` 前缀内的新增可选字段（向后兼容前提下）。

### Citations

**File:** README.md (L484-495)
```markdown
SkillHub is where your organization **hosts, versions, governs, and distributes**
those skills privately.

|  | [`anthropics/skills`](https://github.com/anthropics/skills) | **SkillHub** |
|---|---|---|
| What it is | A curated collection of example Agent Skills + the format spec | A self-hosted registry & governance platform for skills |
| Layer | Content — the skills themselves | Infrastructure — hosting, versioning, discovery, access control |
| Hosting | Public GitHub repository | Your own infrastructure, behind your firewall |
| Versioning | Git history | Semantic versions, tags (`beta` / `stable`), `latest` tracking |
| Access control | Public | Namespaces, RBAC, review & audit logging |
| Distribution | Clone / copy files | Full-text search + CLI install |

```

**File:** docs/07-skill-protocol.md (L102-108)
```markdown
Runtime 集成边界：

- SkillHub 是技能元数据和版本级 `complianceSnapshot` 的权威源。
- Agent Runtime 是执行 trace 的权威源。
- Runtime 如需在执行链路中记录合规上下文，应引用 SkillHub 返回的不可变版本 `id`
  和 `complianceSnapshot.digest`，而不是复制或改写 SkillHub 的声明内容。
- SkillHub 当前不记录 Agent 执行输入输出、Runtime trace 或实际调用结果。
```

**File:** server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/skill/metadata/SkillMetadataParser.java (L15-22)
```java
public class SkillMetadataParser {

    private static final String FRONTMATTER_DELIMITER = "---";
    private static final int MAX_YAML_ALIASES = 20;
    private static final int MAX_YAML_NESTING_DEPTH = 20;
    private static final int MAX_YAML_CODE_POINTS = 200_000;

    public SkillMetadata parse(String content) {
```

**File:** plugins/dsh/src/host/skill-format.ts (L6-22)
```typescript
export async function validateDshSkill(ctx: Context, directory: string, signal: AbortSignal): Promise<void> {
  signal.throwIfAborted();
  const provider = new FileSystemSkillProvider(ctx, { signal, invalidate: () => {} }, {
    providerName: 'skillhub-install-validation', includeDefaultRoots: false, customSkillDirs: [directory], watch: false,
  });
  try {
    const result = await provider.list({ signal });
    signal.throwIfAborted();
    if (!Array.isArray(result) && !result.complete) throw new Error('DSH skill validation could not complete');
    const candidates = Array.isArray(result) ? result : result.candidates;
    const candidate = candidates.find(item => item.path === join(directory, 'SKILL.md'));
    if (!candidate) throw new Error('Package SKILL.md is not a valid DSH skill');
    const skill = await provider.get(candidate, { signal });
    if (!skill || skill.resourceBase?.kind !== 'directory' || skill.resourceBase.path !== directory) {
      throw new Error('DSH skill resources do not resolve to the package directory');
    }
  } finally { await provider.dispose(); }
```

**File:** openspec/changes/add-dsh-native-plugin/specs/dsh-native-experience/spec.md (L455-473)
```markdown
#### Scenario: Example protocol is invalid or the file is absent
- **WHEN** the fixed file is absent or has invalid JSON or an invalid example structure
- **THEN** the skill remains usable through custom task entry without fabricated examples
- **AND** an existing invalid file is retained as ordinary versioned skill content with a non-blocking publication notice, subject to all normal package safety checks.

#### Scenario: A similarly named file or unsafe package is uploaded
- **WHEN** JSON is supplied at another path or package content violates general safety rules
- **THEN** other-path JSON is not interpreted as task examples and unsafe content follows existing rejection rules
- **AND** uploaded content never overrides or gains the authority of installer-internal `.skillhub/metadata.json`.

#### Scenario: Skill content passes through publishing and local lifecycle operations
- **WHEN** supported CLI, Web and DSH consumers publish, install, retry, sync, upgrade, remove or recover a skill containing the fixed file
- **THEN** package manifests, fingerprints, backups and directory checks consistently account for that file, including protocol-invalid ordinary content
- **AND** local modifications retain existing overwrite protection rather than being ignored as cache changes.

#### Scenario: Version or installation scope differs
- **WHEN** a user selects a different installed version, source or user/project installation
- **THEN** templates come from that exact selected installation, never from another version or scope
- **AND** existing native invocation, current-session and draft checks still apply.
```

**File:** openspec/changes/add-dsh-native-plugin/specs/dsh-native-experience/spec.md (L494-505)
```markdown
### Requirement: Structured examples and verified skill placeholder
Each example SHALL contain a stable id, display title and editable prompt. IDs SHALL be unique within each language collection; translations of the same logical example SHALL use the same id without requiring equal collection sizes. String-only entries SHALL be protocol-invalid. The consumer SHALL replace only the exact `{{skill}}` placeholder in prompt with the verified native skill invocation and SHALL NOT evaluate template expressions or infer the invocation from the market slug.

#### Scenario: A localized structured example is chosen
- **WHEN** the user confirms an example selected by language and id
- **THEN** the current file digest and installation are revalidated and the current matching prompt is used
- **AND** all exact skill placeholders are replaced with the verified invocation while title remains presentation text.

#### Scenario: Prompt has no supported skill placeholder
- **WHEN** the chosen prompt has no exact skill placeholder
- **THEN** the consumer supplies the verified invocation separately and preserves the chosen task text
- **AND** other template-like text remains literal, with no code evaluation or automatic sending.
```
