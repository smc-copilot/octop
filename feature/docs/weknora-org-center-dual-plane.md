# WeKnora 组织中心双平面共享方案

> 状态：**方案确认稿**；落地范围 = **P0 手工运维**（不实施 P1/P2）  
> 日期：2026-10-31  
> 范围：Casdoor 用户 + Octop 用户组 + WeKnora Tenant，支撑「本中心库 + 公司级公共库」  
> 操作手册：见文末 **附录 A**

## 1. 背景与目标

### 1.1 已解决

- 企业侧共用一套 WeKnora 只读检索凭证（非每人私库开户）。
- Casdoor 用户通过 **共享连接器可见**（`shared` / `visibility`）即可使用，无需每人手工填表。

### 1.2 本方案要解决

公司存在多个**组织中心**，需要：

- 各中心有自己的共有知识库，只对本中心用户组可见/可用；
- 另有**公司级公共库**，供公共专家与全员（或公司组）使用；
- 同一用户可同时连接多个 WeKnora（例如公共 + 所属中心）；
- **三方全同步**：Casdoor ↔ Octop 用户组 ↔ WeKnora Tenant 成员（viewer）。

### 1.3 非目标（本轮 / 首期）

- WeKnora Organization / KB 跨 Tenant share（中心之间任意互享）。
- 每人私有知识库开通（`enterprise-user-private-knowledge`）。
- 把 Octop 聊天检索改为员工个人 WeKnora JWT。
- Casdoor 写回、中心内容写入走 Octop（写入仍在 WeKnora 控制台）。

## 2. 决策摘要

| 项 | 选择 |
| --- | --- |
| 身份/凭证模型 | 企业共享只读 retrieve Key（检索平面） |
| 组织中心映射 | **组织中心 = WeKnora Tenant** |
| 知识范围 | **本中心库 + 公司级公共库** |
| 多连接 | 允许；每 Tenant 一条（共享）连接器实例 |
| 同步 | **Casdoor ↔ Octop 用户组 ↔ WeKnora Tenant viewer** |
| 编排架构 | **方案 1：Octop 编排双平面** |

曾对比未采纳：

- **方案 2**（WeKnora Organization 为主）：与当前 retrieve API Key 路径难对齐，改造面大。
- **方案 3**（只同步 Casdoor→Octop，WeKnora 仅管理员）：不满足三方全同步。

## 3. 硬约束：双平面必须分开

Octop 聊天检索当前走 **Tenant 级 retrieve API Key**，不是员工个人 WeKnora JWT。

| 平面 | 作用 | 不能指望它单独做什么 |
| --- | --- | --- |
| **检索平面** | 共享连接器 + 每 Tenant 一把受限 retrieve Key；用 Octop 用户组 / `visibility` 控制谁能看见连接器 | 不能单靠「同步了 WeKnora viewer」就按人隔离检索 |
| **成员平面** | Casdoor→组→WeKnora 用户与 Tenant `viewer`；控制台可见、审计、未来人身访问 | 不能单靠成员表决定 Octop 能否搜索 |

两边都同步才叫边界完整；检索隔离仍依赖：

1. 每 Tenant 独立 retrieve Key（尽量 KB 白名单）；  
2. Octop 连接器按组暴露；  
3.（可选增强）企业知识插件的员工 grant / `allowed_kb_ids`。

## 4. 拓扑与职责

### 4.1 对象对应

```
Casdoor Org/Group          Octop                         WeKnora
─────────────────          ─────                         ───────
公司/全员组       ──同步──► ug-company（或等价）  ──同步成员──► Tenant company-public (viewer)
中心组 center-A   ──同步──► ug-center-A           ──同步成员──► Tenant center-A (viewer)
中心组 center-B   ──同步──► ug-center-B           ──同步成员──► Tenant center-B (viewer)
用户 (OIDC)       ──SSO───► users + 组成员         ──确保用户──► WeKnora user（按邮箱稳定关联）
```

管理员配置、**不随成员同步自动创建**的检索平面：

| Octop 连接器 | 指向 | 可见性 |
| --- | --- | --- |
| 公司公共知识 | Tenant `company-public` 的 retrieve Key | `visibility=all`（或仅公司组） |
| 中心 A 知识 | Tenant `center-A` 的 retrieve Key | `visibility=groups` → `ug-center-A` |
| 中心 B 知识 | Tenant `center-B` 的 retrieve Key | `visibility=groups` → `ug-center-B` |

### 4.2 硬规则

1. **一个组织中心 = 一个 WeKnora Tenant**；公司公共 = 独立 Tenant，不并入某一中心。  
2. **首期不启用** WeKnora Organization / KB cross-share。  
3. **内容写入**在 WeKnora 由各 Tenant 的 Admin/Contributor 完成；Octop 连接器保持只读 retrieve。  
4. **Octop 是编排器**：Casdoor 为身份源；Octop 用户组为授权源；WeKnora 成员为镜像。冲突以 Casdoor→Octop 对账结果为准再推 WeKnora。

### 4.3 目标体验

- 只属于中心 A：可见「公司公共」+「中心 A」（若公共对全员开放）。  
- 同时属于 A、B：可见公共 + A + B。  
- 公共专家：绑定「公司公共」连接器即可读公共数据，不必绑齐所有中心。

## 5. 同步设计（方案级）

### 5.1 真相源与方向

```
Casdoor ──► Octop user_group / members ──► WeKnora user + tenant_members(viewer)
                │
                └── 已有 SSO：确保 Octop users 存在
```

- Casdoor → Octop：组与成员（及必要的显示名）。  
- Octop → WeKnora：按映射表把「用户组」投影为「Tenant viewer 成员」。  
- 不反向用 WeKnora 成员改 Casdoor / Octop 组。

### 5.2 映射配置（逻辑模型）

每条组织映射至少包含：

| 字段 | 含义 |
| --- | --- |
| `casdoor_group_id` / 稳定外部键 | Casdoor 侧组标识 |
| `octop_user_group_id` | Octop 用户组 |
| `weknora_tenant_id` | 对应 Tenant |
| `kind` | `company_public` \| `center` |
| `connector_instance_id`（可选） | 已配置的共享连接器，便于运维核对 |

公司公共可映射「全员」或显式公司组；中心必须 1:1。

### 5.3 触发点

| 触发 | 行为 |
| --- | --- |
| 周期对账 | 拉 Casdoor 组员 → 对齐 Octop 组员 → 对齐 WeKnora viewer |
| SSO 首次/登录 | 加速：确保本用户的 Octop 组与 WeKnora 成员落齐（不替代周期对账） |
| 管理员改映射 | 触发相关 Tenant/组的定向对账 |
| 失败 | 记录可重试状态；**不阻断** Casdoor 登录 Octop |

### 5.4 WeKnora 侧动作（概念）

依赖 SystemAdmin（或等价管理）能力，而非 retrieve Key：

1. 按规范邮箱确保远端用户存在（幂等；冲突进人工核对，不自动接管异账号）。  
2. 将用户加入映射 Tenant 的 `viewer`（已在则跳过）。  
3. 对账发现「已不在 Casdoor/Octop 对应组」→ 从该 Tenant 移除 viewer（不删除远端用户，避免误伤其他 Tenant）。  
4. 公司公共 Tenant：凡应见公共库的用户保持 viewer。

### 5.5 与「每人私库」开通的关系

本方案**不**创建个人 Tenant / 个人 retrieve Key。  
成员平面的 WeKnora 用户仅服务 Tenant 成员镜像；检索仍用管理员配置的 Tenant Key。  
若日后启用私库开通，应另开变更，避免与本映射抢同一远端用户身份策略。

## 6. 凭证与安全

| 凭证 | 用途 | 存放 |
| --- | --- | --- |
| 各 Tenant retrieve API Key | Octop 检索平面 | 现有连接器加密凭证；Dashboard 不回显明文 |
| WeKnora SystemAdmin JWT（或管理会话） | 用户创建 / 成员变更 | 仅服务端；只暴露「是否已配置 / 是否过期」 |
| Casdoor 管理 API 凭据 | 拉组与成员 | 仅服务端 |

要求：

- retrieve Key：`capabilities` 尽量仅 `retrieve`，并限制到该 Tenant 允许的 KB。  
- 管理凭据与检索凭据分离；平台 Key 不代替开户/加成员。  
- 非 loopback 的 `http` base_url 继续遵守现有 `OCTOP_WEKNORA_TEST_HTTP_ORIGIN` 等部署约束（见 `docs/connectors-weknora.md`）。

## 7. 与现有 Octop 能力的衔接

| 能力 | 用法 |
| --- | --- |
| 连接器多实例 + `shared` / `visibility=groups` | 每 Tenant 一条共享连接器；中心用组可见，公共用全员或公司组 |
| `resource_group_grant` + `user_group` | 成员授权源；同步写入/维护组成员 |
| Casdoor/OIDC `resolve_or_create_sso_user` | 保证 Octop 用户存在；登录可 wake 加速同步 |
| 企业知识插件五层交集 | 可选增强（员工 grant、专家 binding）；**首期可用内置 weknora 连接器满足「可见即可检索」** |
| `notify_user_created` | 可作为同步加速钩子，可靠性仍靠周期对账 |

## 8. 实施分期

### 当前落地：P0 手工运维（已选定）

用户量少时：**不推进 P1 / P2**。Casdoor 组员、Octop 用户组成员、WeKnora Tenant viewer（若需要进控制台）均由管理员按附录手工对齐。检索可用性只依赖 P0：Tenant + retrieve Key + Octop 用户组 + 共享连接器可见性。

1. 在 WeKnora 建好 `company-public` 与各 `center-*` Tenant 及公共/中心 KB。  
2. 每 Tenant 发 retrieve Key。  
3. Octop 建对应用户组与共享连接器，设好 `visibility`。  
4. 公共专家只绑公司公共连接器。  
5. 新用户：Casdoor SSO 登录 Octop 后，手工加入对应 Octop 用户组（见附录）。

### P1 / P2 / P3 — 暂缓

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| P1 | Casdoor → Octop 组同步 | **不做**（用户少，手工维护） |
| P2 | Octop → WeKnora Tenant viewer 镜像 | **不做** |
| P3 | 企业知识插件 grant / 公共专家默认源加固 | 可选，未排期 |

下文 §5–§6 中的自动同步与管理凭据描述保留为远期参考，**当前不实施**。

## 9. 验收标准（P0 / 手工）

1. 中心 A 用户能看见并使用「公司公共」+「中心 A」连接器；看不见中心 B。  
2. 跨中心用户能同时看见其所属全部中心连接器 + 公共。  
3. 公共专家仅绑公共连接器即可检索公共库。  
4. 从某中心 Octop 用户组移除成员后，该用户立即（或重新登录/刷新后）失去对应中心连接器可见性。

## 10. 开放问题（若日后重启 P1/P2 再定）

1. Casdoor 组标识与 Octop `user_group_id` 的稳定键格式（name vs id）。  
2. 无邮箱的 Casdoor 账号：成员平面是否跳过 WeKnora、仅保留 Octop 组。  
3. 公司公共是「全员 `visibility=all`」还是必须加入显式公司组。  
4. WeKnora 管理 API 以当前部署版实测合同为准，冻结后再编码。  
5. 是否强制每 Key 绑定 `knowledge_base_ids` 白名单。

## 11. 相关文档

- `docs/connectors-weknora.md` — 连接器字段、凭证与本机部署参数  
- `docs/connectors.md` — 连接器总览、共享与 Composio 例外  
- `openspec/changes/enterprise-user-private-knowledge/` — 每人私库（本方案非目标）  
- Octop `infra/users/groups.py` — 用户组与 `resource_group_grant` 可见性层  

---

## 附录 A — 运维配置（映射表 + 步骤）

> 适用：**当前 P0 手工模式**。三方自动同步未启用；以本附录为日常操作手册。

### A.1 映射表（示例，按实装改名）

用户关联键优先用 **邮箱**（Casdoor email → Octop email；若进 WeKnora 控制台则同邮箱建/加成员）。

| kind | Casdoor 组（示意） | Octop `user_group_id` | WeKnora Tenant（示意名） | Octop 连接器显示名 |
| --- | --- | --- | --- | --- |
| company_public | `org/company` 或「全员」 | `ug-company`（可选） | `company-public` | 公司公共知识 |
| center | `org/center-rd` | `ug-center-rd` | `center-rd` | 研发中心知识 |
| center | `org/center-ops` | `ug-center-ops` | `center-ops` | 运营中心知识 |

运维应另建一张**实装表**，补齐：WeKnora 数值 `tenant_id`、retrieve Key 存放位置、连接器 `instance_id`、各 KB UUID。不要把 Key 明文写进本仓库文档。

### A.2 配置顺序总览

```
1. Casdoor：OIDC 应用 + 组 + 用户入组
2. WeKnora：每组织一行 Tenant + KB + retrieve Key
3. Octop：用户组 + 每 Tenant 一条共享 WeKnora 连接器（visibility）
4. 公共专家：只绑「公司公共知识」
5. 日常：SSO 新用户 → 手工加入 Octop 对应用户组（与 Casdoor 组对齐）
```

### A.3 Casdoor

1. 创建/确认 OIDC 应用，Redirect URI 指向 Octop OIDC 回调；在 Octop 管理后台完成 SSO/OIDC 配置。  
2. 按映射表创建组织/用户组（公司组 + 各中心组）。  
3. 用户放入对应组；保证稳定、唯一邮箱。一人多中心则同时加入多个中心组。  
4. **说明**：Casdoor 组成员不会自动写入 Octop；登录只保证 Octop 账号存在，组员仍按 A.6 手工维护。

### A.4 WeKnora

对映射表每一行：

1. 创建独立 **Tenant**（公司公共一个，每个中心一个）。公共库不要建在某个中心 Tenant 内。  
2. 在该 Tenant 创建 KB 并导入文档。  
3. 签发 **retrieve-only** API Key（建议绑定该 Tenant 允许的 KB 白名单）。  
4. 记录：`base_url`、`tenant_id`、`api_key` 保管位置、可选 `knowledge_base_ids`。  
5. 内容管理员使用 Admin/Contributor 在对应 Tenant 维护文档。  
6. （可选）若员工需要登录 WeKnora 控制台：按邮箱手工加为该 Tenant **viewer**。检索不依赖此步。

### A.5 Octop 用户组与共享连接器

**用户组**（管理后台 → 用户组）：

1. 创建 `ug-center-rd`、`ug-center-ops` 等（`user_group_id` 建议与映射表一致）。  
2. 若公司公共不用 `visibility=all`，再创建 `ug-company` 并只把应见公共库的人加进去。

**连接器**（每 Tenant 一条 WeKnora 实例）：

| 字段 | 公司公共 | 中心（例：研发） |
| --- | --- | --- |
| 显示名称 | 公司公共知识 | 研发中心知识 |
| 服务地址 | 同一 WeKnora `base_url` | 同左 |
| API Key | `company-public` 的 Key | `center-rd` 的 Key |
| Tenant ID | 公司公共 `tenant_id` | 研发 `tenant_id` |
| 知识库 ID | 公共库 ID（建议显式） | 该中心库 ID |
| 可见性 | `all`，或 `groups` → `ug-company` | **`groups` → `ug-center-rd`** |

探测成功后保存。中心连接器勿误设为全员可见。

**公共专家**：Agent/专家只绑定「公司公共知识」连接器。

### A.6 日常：新用户 / 调组 / 离职

| 场景 | 操作 |
| --- | --- |
| 新员工 | Casdoor 建用户并入组 → 用 SSO 登录一次 Octop → 在 Octop 将用户加入对应 `ug-center-*`（及可选 `ug-company`） |
| 调中心 | Casdoor 改组 + Octop 改用户组成员（与映射表一致）；必要时改 WeKnora viewer |
| 兼多个中心 | Octop 同时加入多个中心用户组 → 自动看见多条中心连接器 + 公共 |
| 离职/撤权 | 从 Octop 对应用户组移除；连接器立即不可见。可选：WeKnora 去掉对应 Tenant viewer；Casdoor 禁用账号 |

### A.7 三层对齐关系（手工模式下的数据流）

```
Casdoor 用户 ∈ org/center-rd
    ↓ SSO 登录
Octop 用户存在
    ↓ 管理员手工加入 ug-center-rd
看见连接器「研发中心知识」+「公司公共知识」
    ↓ 连接器内 Key + Tenant
检索 → WeKnora center-rd / company-public
    ↓（可选）同邮箱加为 Tenant viewer
可进 WeKnora 控制台只读对应空间
```

- **能否在 Octop 检索**：Octop 用户组 + 连接器 `visibility` + retrieve Key。  
- **能否进 WeKnora 控制台**：Tenant viewer（与检索平面分开，可暂不配）。

### A.8 最小验收清单

1. 仅研发组用户：能看到「公司公共」+「研发中心」，看不到「运营中心」。  
2. 跨组用户：能看到其所有中心连接器 + 公共。  
3. 公共专家只绑公共连接器，能检索公共库。  
4. 从 `ug-center-rd` 移除用户后，该用户不再看见「研发中心知识」。

