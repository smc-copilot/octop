# Octop 插件开发者指南

面向要编写**企业内插件**的开发者：读完应能知道要创建哪些文件、实现哪些接口、如何安装启用，以及常见陷阱。

本文只描述本仓库**当前代码**的行为，不改产品实现。部分 README / `docs/cli.md` / `docs/configuration.md` 仍写着旧的「启动时自动拷贝 bundled 插件」流程；以本文引用的实现为准，差异见 [§12](#12-仓库内已有文档与代码的差异)。

| 项 | 值 |
|----|-----|
| 代码基准 | 本仓库当前树（`octop-harness>=1.0.5`） |
| 运行时 SDK | 独立包 `octop-harness`（PyPI / [TencentCloud/octop-harness](https://github.com/TencentCloud/octop-harness)） |
| 宿主管理 | `src/octop/infra/agents/plugins/` |
| 安装目录 | `{OCTOP_HOME}/plugins/`，默认 `~/.octop/plugins/`（`src/octop/infra/utils/paths.py`） |

**不是**本系统的东西（避免混用）：

- Connector / MCP（`src/octop/infra/connectors/`，`docs/connectors.md`）
- 技能包（SkillHub / `skill_packages`）
- 专家库里的 **Cowork** 插件（`.claude-plugin/plugin.json`，见 `src/octop/infra/agents/experts/library/cowork-plugin-management/`）
- Dashboard 业务页面、HTTP 路由、Slash 命令 —— 第三方插件**不能**注册这些

---

## 1. 架构：谁负责什么

插件**加载与注册**发生在 `octop-harness`；Octop 是宿主：发现磁盘包、装 ZIP、开关、把工具/中间件/技能/通道接到 Agent 与 Gateway，并给 Dashboard 送预构建 UI。

```
插件包 (plugin.yaml + main.py [+ skills/] [+ ui/])
        │
        ▼
octop-harness.plugins
  PluginManifest → load_plugin_dir → setup(ctx) → PluginRegistry
        │
        ▼
Octop PluginManager          (~/.octop/plugins + config.json)
        │
        ├── AgentManager     工具 / hook / skill 同步
        ├── plugin_channels  kind: channel → octop-gateway
        ├── FastAPI          /api/plugins/*
        └── Dashboard        管理页 + 聊天卡片渲染
```

关键入口：

| 层 | 路径 |
|----|------|
| Harness SDK | `octop_harness.plugins`：`PluginContext`、`PluginManifest`、`load_plugin_dir`、`build_plugin_tools` |
| 宿主管理器 | `src/octop/infra/agents/plugins/manager.py` |
| 市场目录 / bundled | `src/octop/infra/agents/plugins/bundled/`（`default_bundled_plugins_root()`） |
| 升级种子 | `src/octop/infra/agents/plugins/seed.py` |
| 通道桥 | `src/octop/infra/gateway/plugin_channels.py` |
| HTTP | `src/octop/api/routers/plugins.py` |
| CLI | `src/octop/cli/commands/plugin.py` |
| Dashboard API | `dashboard/src/api/modules/plugins.ts` |
| 聊天 UI 加载 | `dashboard/src/plugins/toolRenderers/` |
| 开机 | `src/octop/infra/server.py`：`seed_bundled()` → `load_installed()` → `_apply_plugin_channels()` |
| 演示包 | 仓库根 `plugins/`（**不是**产品市场目录） |

`PluginContext` **没有** workspace / agent 句柄。工具是普通 Python 函数，在 Octop 进程内执行。见 `docs/octop-ui-payload-offload.md` F12。

---

## 2. 包布局与必填文件

### 2.1 目录

Harness 只认「含 `plugin.yaml` 的一层目录」（`discover_plugin_dirs`）。Octop 安装后的目录名等于 **`plugin.yaml` 的 `id`**，不是你打包时的文件夹名。

```text
my-internal-lookup/                 # 开发时目录名建议与 id 相同
├── plugin.yaml                     # 必填
├── main.py                         # 默认入口；必须定义 setup(ctx)
├── requirements.txt                # 可选；load 时 pip install -r（失败不中断）
├── icon.svg                        # 可选；Dashboard 卡片
├── README.md                       # 可选
├── skills/                         # 仅 kind: skill
│   └── polite-greeting/
│       └── SKILL.md
└── ui/                             # 可选；预构建 ESM（安装时不跑 npm）
    ├── index.js                    # bundled 插件常用此路径
    └── manifest.json
    # 或 ui/dist/index.js + ui/dist/manifest.json（demos 文档约定）
```

### 2.2 `plugin.yaml`

Harness 解析字段（`octop_harness/plugins/manifest.py` → `PluginManifest.from_dict`）：

| 字段 | 必填 | 说明 |
|------|------|------|
| `id` | 是 | 非空字符串。安装目标为 `~/.octop/plugins/{id}`。**必须是单一路径段**（见 [§10.1](#101-id--命名)） |
| `version` | 是 | 非空字符串。比较时按 `.` 分段转 `int`（`1.2.3` → `(1,2,3)`；非数字段当 `0`） |
| `kind` | 否 | `tool`（默认）/ `skill` / `hook` / `channel`。其它值加载失败 |
| `entry` | 否 | 相对插件根的入口文件，默认 `main.py` |
| `name` | 否 | 展示名，默认等于 `id` |
| `description` | 否 | 列表/市场文案 |
| `requires` | 否 | **pip 需求字符串列表**，如 `httpx>=0.27`。不是 Python 包名随意数组以外的结构 |

Octop **额外**读取、Harness 忽略的字段（`manager.py`：`parse_plugin_*`）：

| 字段 | 说明 |
|------|------|
| `icon` | emoji、`http(s)://` / `/api/` / `data:image/` URL，或插件内图片（`.svg/.png/.jpg/.jpeg/.webp/.gif`），解析成 `/api/plugins/{id}/ui/...` |
| `group` | 小写 slug，`[a-z0-9-]`，最长 64。已知值：`lifestyle` `news` `finance` `media` `fun` `games` `tools` `ops`（`PLUGIN_GROUPS` / `dashboard/.../pluginGroups.ts`）。未知值仍会原样返回 |
| `ui.entry` | 预构建 ESM，默认 `ui/dist/index.js`。文件不存在则整段 `ui` 视为缺失 |
| `ui.manifest` | 默认 `ui/dist/manifest.json`。禁止 `..` 路径段 |

`name` / `description` / `icon` **没有** i18n 键。文案写在 yaml 里。后端 `src/octop/i18n/{en,zh}.json` 的 `plugins.*` 目前只有内置 `arxiv-search` 的运行时字符串；第三方不要依赖往核心 i18n 加键。聊天 UI 可用 `host.getToolContext().locale`。

完整示例（bundled 天气）：

```yaml
id: weather
version: 0.2.2
name: 天气
description: 查询全球城市天气与未来预报，在聊天中展示天气卡片
icon: icon.svg
group: tools
kind: tool
entry: main.py
requires:
  - httpx>=0.27
ui:
  entry: ui/index.js
  manifest: ui/manifest.json
```

来源：`src/octop/infra/agents/plugins/bundled/weather/plugin.yaml`。

### 2.3 入口 `setup(ctx)`

`load_plugin_dir`（harness `loader.py`）：

1. 读 `plugin.yaml`
2. 若 `install_deps=True` 且存在 `requires` 或 `requirements.txt`：`python -m pip install`（`check=False`，失败只记日志）
3. 把入口加载为模块名 `harness_plugin_{id.replace("-", "_")}`
4. 要求存在可调用的 `setup`
5. `setup(PluginContext)`，再 `PluginRegistry.register`

旧插件 `from harness_agent.plugins import PluginContext` 仍可用：Octop 在加载前挂别名（`src/octop/infra/agents/plugins/legacy_imports.py`）。**新代码请写 `octop_harness.plugins`。**

`kind` 与 `ctx.*` 必须匹配，否则 `setup` 里立刻 `ValueError`：

| `kind` | 允许的 API | 禁止 |
|--------|------------|------|
| `tool` | `ctx.tool(...)` | `skills` / `middleware` / `channel` |
| `skill` | `ctx.skills("相对路径")` | 其它 |
| `hook` | `ctx.middleware(instance, priority=...)` | 其它 |
| `channel` | `ctx.channel(kind, ChannelClass, ...)` | 其它 |

一个包只有一个 `kind`。要同时提供工具和技能，做两个插件。

---

## 3. 扩展点与精确契约

插件**能**注册的只有下表。没有「注册 FastAPI 路由 / Connector / Slash / 侧栏页面」的 API。

### 3.1 `kind: tool` —— 模型可调用工具

```python
from octop_harness.plugins import PluginContext, get_tool_config

async def echo_prefix(message: str) -> str:
    cfg = get_tool_config("echo_prefix") or {}
    return f"{cfg.get('prefix') or ''}{message}"

def setup(ctx: PluginContext) -> None:
    ctx.tool(
        "echo_prefix",
        echo_prefix,
        description="Echo a message with a configurable prefix",
        config_fields=[{"name": "prefix", "type": "text", "required": False}],
    )
```

`PluginContext.tool`（harness `context.py`）：

| 参数 | 类型 | 说明 |
|------|------|------|
| `name` | `str` | 非空。配置键用**这个原名** |
| `fn` | sync 或 `async` | 参数名/类型变成 LLM 工具 schema（`StructuredTool.from_function`） |
| `description` | `str` | 给模型看的说明；默认等于 `name` |
| `config_fields` | `list[dict]` | 管理端表单。Dashboard 认 `name` `label` `type` `required` `placeholder` `help`；`type`：`text`（默认）/ `password` / `number` |

返回值：字符串最稳妥。聊天卡片请返回 **JSON 字符串**，见 [§4](#4-可选-ui仪表盘卡片)。

运行时配置：`get_tool_config(tool_name)` 读当前 turn 的 `configurable.plugin_tool_configs`。Octop 在 `_prepare_stream_request`（`src/octop/infra/agents/manager.py`）里用 `collect_plugin_tool_configs` 注入。**键是插件注册的原名**，不是清洗后的 ASCII 名。

绑定条件（harness `tools.py` `_tool_enabled` + Octop `plugin_tool_defaults.py`）：

1. `config.json` → `plugins.{id}.enabled === false` → 整个插件不 load，无工具。
2. Agent `config_json.plugins.{id}.enabled === false` → 该 Agent 不挂此插件。
3. `plugins.{id}.tools.{name}.enabled === false` → 关掉单个工具。
4. 缺省：**开**。全局启用后不必再在每个 Agent 上点一次「启用工具」。

Team **host** 不挂插件工具（`manager.py` `_build_harness_config`）。Team member 是独立 Agent，正常挂载。

中文/非法工具名：Octop 在绑定前 `sanitize_plugin_tool_names`（`plugin_tool_names.py`），改成 `^[a-zA-Z0-9_-]{1,64}$`（有 `pypinyin` 则转拼音）。描述加 `[原名: …]`。配置键仍用原名。**新插件请直接用 ASCII 名。**

参考：`plugins/demo-toolkit/`、`tests/fixtures/plugins/echo-tool/`、`src/octop/infra/agents/plugins/bundled/weather/`。

### 3.2 `kind: skill` —— 往工作区同步 SKILL.md

```python
def setup(ctx: PluginContext) -> None:
    ctx.skills("skills")   # 相对插件根；目录必须存在
```

每个 `skills/<name>/` 必须有 `SKILL.md`。Agent 启动时 `PluginManager.sync_skills_to_workspace`：

- 插件全局启用 **且** 该 Agent 未关掉该插件
- 工作区还没有 `skills/<name>/SKILL.md` 才拷贝（**已有文件不覆盖**）
- 经 `BackendWorkspace.upload_many`，不直接写本地路径

关掉的 skill 插件，其 skill 目录名会进入 `plugin_skills_disabled`。

`SKILL.md` 用常规 frontmatter（`plugins/demo-greeting-skill/skills/polite-greeting/SKILL.md`）：

```yaml
---
name: polite-greeting
description: >
  Use a concise, polite greeting ...
metadata:
  octop:
    emoji: "👋"
---
```

Skill 插件**不**注册可调用工具。

### 3.3 `kind: hook` —— AgentMiddleware

```python
from octop_harness.plugins import AgentMiddleware, PluginContext

class TurnLoggerMiddleware(AgentMiddleware):
    def before_model(self, state, runtime):
        return None
    async def abefore_model(self, state, runtime):
        return self.before_model(state, runtime)
    def after_model(self, state, runtime):
        return None
    async def aafter_model(self, state, runtime):
        return self.after_model(state, runtime)

def setup(ctx: PluginContext) -> None:
    ctx.middleware(TurnLoggerMiddleware(), priority=100)
```

- `kind` 必须是 `hook`
- `priority` 默认 `100`，**越小越先跑**
- 只挂**全局启用**的 hook（`PluginRegistry.build_middleware_chain`）
- Octop 把插件中间件放在配额 / 知识提示 / UI offload 等**前面**（`manager.py` `agent_middleware`）

参考：`plugins/demo-turn-logger/`。

### 3.4 `kind: channel` —— 第三方 IM 通道

契约见 `docs/plugin-channels.md` + harness `PluginContext.channel`。

```python
def setup(ctx: PluginContext) -> None:
    ctx.channel(
        "acme",
        AcmeChannel,          # 必须是 class，继承 octop_gateway.channel.BaseChannel
        label="Acme IM",
        icon="",
        intro_url="https://example.com/docs",
        fields=[{"name": "token", "label": "Token", "type": "password", "required": True}],
    )
```

| 参数 | 说明 |
|------|------|
| `kind` | 写入通道表的类型字符串，小写。插件 ID **拥有**该 kind；冲突拒绝 |
| `channel_cls` | **类**，不是工厂函数 |
| `label` / `icon` / `intro_url` | 通道目录展示 |
| `fields` | 与 Dashboard `ChannelField` 同形：`name` `label` `type`（`text`/`password`/`textarea`/`json`/`switch`）`placeholder` `required` `helpKey`。空则退回 JSON 文本框 |

Octop 在 load / reload / 安装 / 开关 / 卸载后走 `apply_plugin_channels`（`src/octop/infra/gateway/plugin_channels.py`），再 `octop_gateway.channels.register_channel_kind`。只重建 **kind / plugin_id / 类** 有变化的插件通道；内置通道不重启。失败写入 `registration_error`，不拖垮其它插件。

本仓库**没有**可安装的 channel 示例；测试夹具在独立的 `octop-harness` 仓库。需要配套的 gateway 动态注册接口（见 `docs/plugin-channels.md`）。

### 3.5 插件做不到的

| 能力 | 现状 |
|------|------|
| FastAPI 路由 | 无扩展点 |
| Connector / MCP server | 走 `infra/connectors`，不是插件 |
| Slash | `infra/gateway/slash/` |
| Dashboard 页面 / 导航 | 只有聊天 tool-result 卡片 |
| 改 `ChannelKind` 枚举 | 不需要；动态注册即可 |
| 签名 / 公证 | **没有**签名、证书或哈希校验 |

---

## 4. 可选 UI（仪表盘卡片）

Harness 不读 `ui:`。Octop 用它给聊天页动态加载 ESM。

### 4.1 清单

```yaml
ui:
  entry: ui/index.js          # 或 ui/dist/index.js
  manifest: ui/manifest.json
```

`ui/manifest.json` 示例（`bundled/weather/ui/manifest.json`）：

```json
{ "renderers": [{ "id": "weather_card", "tools": ["get_weather"] }] }
```

Dashboard 实际以 `setup(host)` 注册为准；manifest 作声明。

### 4.2 工具返回值

```json
{
  "octop_ui": { "renderer": "weather_card", "version": 1 },
  "data": { "city": "北京", "current": { "temp": 18 } },
  "text": "☀️ 北京 · 晴 18°C"
}
```

- `octop_ui.renderer` 对应 `host.registerRenderer({ id })`
- `data` 给 React 组件 `props.data`
- `text`：无 UI / IM / 模型摘要回退
- 必须是 **JSON 字符串**（工具返回 `str`）

`data` 整段 ≥ 4000 字符时，`OctopUiOffloadMiddleware` 把 `data` 挪到 `ToolMessage.artifact`，content 留 `data_ref: "artifact"`。含 `file://` 则不剥离。详见 `docs/octop-ui-payload-offload.md`、`src/octop/infra/agents/middleware/octop_ui_offload.py`。

### 4.3 前端模块

自包含 ESM。React 由 Dashboard 注入：

```js
const React = window.__OCTOP_REACT__;
const { jsx: _jsx, jsxs: _jsxs } = window.__OCTOP_JSX__;

function WeatherCard(props) { /* props.data, props.host, props.callId, ... */ }

export function setup(host) {
  host.registerRenderer({
    id: "weather_card",
    tools: ["get_weather"],
    component: WeatherCard,
  });
}
```

`OctopPluginUIHost`（`dashboard/src/plugins/toolRenderers/types.ts` + `host.ts`）：

| 方法 | 作用 |
|------|------|
| `registerRenderer({ id, tools?, component })` | 注册卡片 |
| `getToolContext()` | `{ agentId, threadId, locale, theme }` |
| `patchResult(callId, nextData)` | L2：只改前端内存里的 `data`，不重跑模型、不写回服务器（刷新即丢） |
| `request(path, init?)` | 已带 JWT 的 `/api` 请求 |
| `openSidePanel` / `closeSidePanel` | 聊天侧栏 |

加载：`GET /api/plugins/{id}/ui/{path}`（需登录）→ blob URL `import()`。**禁止相对 import**；服务器不跑 `npm install`。路径防穿越（`PluginManager._resolve_plugin_asset`）。

参考：`src/octop/infra/agents/plugins/bundled/weather/ui/`。`plugins/demo-ui-card/` 声明了 `ui/dist/`，但本树可能没有预构建文件；以 bundled 为准。

---

## 5. 生命周期

### 5.1 发现

`discover_plugin_dirs(~/.octop/plugins)`：子目录且含 `plugin.yaml`。子目录名应以 `id` 为准（`install_path` 拷到 `plugins_dir / manifest.id`）。

### 5.2 安装

| 方式 | 代码 | 全局 `enabled` |
|------|------|----------------|
| 本地目录 | `PluginManager.install_path`；CLI `octop plugin install ./dir` | **不写** config → 缺省 **开** |
| 本地 ZIP | `install_archive`；Dashboard 上传 / `POST /api/plugins/upload` | 同上 |
| HTTP(S) ZIP | `install_url`；CLI URL；`POST /api/plugins/install` | 同上 |
| 市场 | `install_from_market`：从 in-tree bundled **copytree** | **显式 `enabled: true`** |

CLI **不能**装本地 `.zip`（只接受目录或 `http(s)://`）。本地 ZIP 用 Dashboard 上传或自己调 upload API。

ZIP 规则（`manager.py`）：

- 魔数 `PK`
- 压缩包 ≤ **100 MiB**；解压合计 ≤ **64 MiB**；单文件 ≤ 64 MiB
- ≤ **2000** 条目
- 压缩比（文件 > 1 MiB）≤ **100**
- 拒绝 `..` 穿越
- **恰好一个**含 `plugin.yaml` 的根（zip 根或唯一一层子目录）
- GitHub `/blob/` URL 会改写成 `raw.githubusercontent.com`（`normalize_plugin_download_url`）

`force=True` 先 `rmtree` 再拷贝。已存在且非 force → `PLUGIN_ALREADY_EXISTS`（409）。

装完会 `unload_plugin` 再 `load_plugin_dir(..., install_deps=True)`。HTTP/上传成功后，若 `octop run` 已在跑：刷新通道并 `reload_all` agents。

**CLI 安装不会更新正在跑的进程。** 需要 `POST /api/plugins/reload`（管理页 Reload）或重启。CLI 会打印这句提示。

### 5.3 启用 / 禁用

两层开关：

```
有效 = config.json.plugins.{id}.enabled（缺省 true）
     AND agent.config_json.plugins.{id}.enabled（缺省 true）
     AND（对单个工具）tools.{name}.enabled（缺省 true）
```

全局关：`PATCH /api/plugins/{id}` `{ "enabled": false }` → `set_enabled` → unload，所有 Agent 立刻没这套工具/技能/hook。Dashboard 仍能列出工具元数据（内存 `_tool_catalog`）。

还可设可见性：`visibility: "all" | "groups"` + `group_ids`（`RESOURCE_PLUGIN`，`infra/users/groups.py`）。非成员在 Agent 个性化页看不到该插件。

### 5.4 加载 / 卸载

| 函数 | 行为 |
|------|------|
| `load_installed` | `PluginRegistry.clear()` 后只 load 全局未关闭的。坏包记日志并跳过。`kind: channel` 用目录指纹，未改则复用类 |
| `load_missing` | 不 clear；给「CLI 已拷盘、进程还在」补 load |
| `set_enabled(False)` / `uninstall` / `unload_plugin` | 从 registry 拿掉，并丢掉 `harness_plugin_{id}` 模块 |

关了的插件**不会 import** `main.py`（`load_installed` 在 load 前就 continue）。

### 5.5 更新

没有独立的「update」命令。

- 第三方：带 `--force` / `force=true` 再装同一 `id`
- bundled / 市场：`list_market` 的 `update_available` = 目录版本 > 已装版本；再 `install_from_market(..., force=True)`
- `seed_bundled_plugins`：仅当 `~/.octop/plugins/{id}` **已存在**且 bundled 版本更新时覆盖，**保留** `enabled`

版本只比点分整数。`1.0.0-rc` 不会大于 `1.0.0`。

### 5.6 卸载

`uninstall(id)`：unload、清 catalog 缓存、`rmtree` 目录。HTTP 还会清 group 可见性并 reload agents/通道。

**不**删除 `config.json` 里的 `plugins.{id}`。种子**不会**把已删的 id 装回来（因为只升级已存在目录）。再出现只能市场安装或手动 ZIP。

---

## 6. 与 Harness / Gateway / Agent / 安全

### 6.1 Harness

- 进程内单例 `PluginRegistry`
- `build_plugin_tools` → `StructuredTool` 列表，并入 Agent 工具集（与 cron / knowledge / mobile 并列）
- hook 进 middleware 链
- `PluginContext` 无 workspace；工具自己 `httpx` / 读本机。`server-status` 用 `psutil` 读的是 **Octop 所在主机**，不是 Agent 沙箱

### 6.2 Gateway

仅 `kind: channel`。`OctopServer.refresh_plugin_channels` → 停变化的插件通道 → `apply_plugin_channels` → 按 DB 行重建。内置 Feishu/Telegram 等不重启。插件没了，DB 行还在，界面显示运行失败；装回后 reload/重启即可。见 `docs/plugin-channels.md`。

IM 对普通 **tool** 插件：只发 tool_start/tool_end 提示，不渲染 `octop_ui`。卡片只在 Dashboard 聊天。

### 6.3 Agent

启动（`AgentManager`，非 team host）：

1. 同步内置 skills
2. `sync_skills_to_workspace`
3. `_build_harness_config`：按全局+Agent 开关 `build_plugin_tools`，再清洗工具名
4. 挂 hook 中间件 + `OctopUiOffloadMiddleware`

每轮 stream：`collect_plugin_tool_configs` → `configurable.plugin_tool_configs`。

Agent 级开关：`PATCH /api/plugins/agents/{agent_id}`（权限 `agent_plugins`）。单工具：`PATCH /api/plugins/agents/{agent_id}/tools` 或 Experts → 工具管理（权限 `tools`）。存储都在 `agents.config_json.plugins`。

### 6.4 安全（审批、沙箱、签名）

**没有插件签名。** ZIP/目录里的 Python 会在 Octop 进程里执行，权限等于服务账号。企业内插件按**可信代码**做评审。

| 机制 | 与插件的关系 |
|------|----------------|
| Docker / 远端 workspace 沙箱 | 管的是 Agent **工作区文件与 execute 工具**，不是 `ctx.tool` 函数 |
| FilesystemGuard / tool_guard | Harness 文件/shell 工具；插件函数不自动套一层 |
| HITL | 进程级 `SecurityPolicy`（`infra/agents/security/policy_store.py`）。打开后 harness 可能在工具调用前暂停；插件工具是普通 StructuredTool，会走同一套工具节点。插件**不能**自己声明审批策略 |
| JWT / 可见性 | 管理 API 要 `plugins` / `plugin_market`；UI 静态资源要登录；Agent 列表受 group 过滤 |
| ZIP 防护 | 体积、穿越、zip bomb 比、单根目录 —— **不是**代码审计 |

`host.request` 带着当前用户 JWT，能打到该用户能打的 `/api`。插件 UI 视为 XSS 面：只加载已安装、已评审的包。

备份默认 `include_plugins=true`，会打进 `~/.octop/plugins/`（`infra/backup/system_archive.py`）。

---

## 7. Bundled、市场、第三方

| 位置 | 角色 |
|------|------|
| `src/octop/infra/agents/plugins/bundled/<id>/` | **产品市场目录**（随 wheel）。`list_market()` 扫这里。目录名 = `id` |
| `~/.octop/plugins/<id>/` | **已安装**（第三方 + 从市场拷来的） |
| 仓库根 `plugins/` | **开发演示**，不自动进市场 |

当前 bundled（均为 `kind: tool` + `ui/`）：

`air-quality` `arxiv-search` `bilibili-anime` `color-convert` `daily-english` `fortune` `fun-facts` `github-trending` `hot-topics` `ip-lookup` `market-quotes` `meme-maker` `mini-games` `movie-search` `parcel-tracker` `pomodoro` `qrcode` `server-status` `short-link` `slack-calendar` `sports-scores` `tetris` `travel-inspire` `unit-convert` `weather` `what-to-eat` `wiki-summary`

`seed_bundled_plugins`（`seed.py`，`octop init` 与 `octop run` 都会调）：

- **不会**装尚未出现在 `~/.octop/plugins/` 的新 id
- 只覆盖「已安装且 bundled 版本更新」的目录
- 保留 `enabled`
- 卸载后的 id **不会**复活
- `bundled_plugins_seeded` **已不再使用**（测试里只是历史字段）

新 bundled 要出现在用户机器上：管理页 **插件市场** → 安装（`POST /api/plugins/market/{id}/install`），或等价 CLI 目录安装。

企业内插件**不要**放进 `bundled/`（那是产品发布物）。放到你们的 git，用目录/`ZIP`/内网 URL 安装。

`plugins/server-status/README.md` 仍写「init 会复制」——对应当前 `seed.py` 已过时。

---

## 8. CLI 与 Dashboard / HTTP

### 8.1 `octop plugin`（离线，不启 HTTP）

`src/octop/cli/commands/plugin.py`，`docs/cli.md` 归类 Offline：

| 命令 | 行为 |
|------|------|
| `octop plugin list` | `list_installed()`；`--json` 为 JSON |
| `octop plugin install <dir-or-url> [--force]` | 目录或 http(s) ZIP，**不是** git URL，**不是**本地 zip |
| `octop plugin uninstall <id>` | 删目录 + unload |
| `octop plugin reload` | 本进程 `load_installed(install_deps=False)`。对已在跑的 `octop run` **无效** |

### 8.2 HTTP（前缀 `/api`）

实现：`src/octop/api/routers/plugins.py`。`docs/api.md` 表格不完整，以本表为准。

| 方法 | 路径 | 权限 | 作用 |
|------|------|------|------|
| `GET` | `/plugins` | 登录用户 | 已安装列表 + 可见性 |
| `POST` | `/plugins/reload` | `plugins` | 从磁盘重载 + 刷新通道 + `reload_all` agents |
| `POST` | `/plugins/install` | `plugins` | body `{ "url" }` |
| `POST` | `/plugins/upload` | `plugins` | multipart ZIP；`force=true` 可覆盖 |
| `GET` | `/plugins/market` | `plugin_market` | in-tree 市场 |
| `POST` | `/plugins/market/{id}/install` | `plugin_market` | 拷贝 catalog；`?force=true` |
| `GET` | `/plugins/market/{id}/ui/{path}` | `plugin_market` | 市场图标等（仅图片后缀） |
| `PATCH` | `/plugins/{id}` | `plugins` | `{ enabled?, visibility?, group_ids? }` |
| `DELETE` | `/plugins/{id}` | `plugins` | 卸载 |
| `GET` | `/plugins/{id}/ui/{path}` | 登录用户 | 已装 UI 资源 |
| `GET` | `/plugins/agents/{agent_id}` | 登录 + 属主 | 该 Agent 的插件（已滤可见性） |
| `PATCH` | `/plugins/agents/{agent_id}` | `agent_plugins` | `{ plugins: { id: { enabled } } }` |
| `GET` | `/plugins/agents/{agent_id}/tools` | 登录 + 属主 | 工具 + config_fields + 当前 config |
| `PATCH` | `/plugins/agents/{agent_id}/tools` | `tools` | 合并工具 enabled/config，热更新 denylist |

错误码（`infra/errors.py`）：`PLUGIN_INVALID_ARCHIVE` 400、`PLUGIN_INSTALL_FAILED` 502、`PLUGIN_ALREADY_EXISTS` 409。

权限定义：`infra/users/permissions.py`。`plugins` 页会展开 `plugin_market`。上传集成测试里非 admin 为 403（`tests/integration/test_plugin_upload.py`）。

### 8.3 Dashboard

- 管理：Admin → 插件（`dashboard/src/pages/Admin/Plugins/`）
  - **已安装**：列表/卡片、开关、可见性、URL 安装、ZIP 上传（可勾覆盖）、Reload、卸载
  - **市场**：bundled 目录，安装/更新
- Agent：个性化 → 插件（`AgentPluginsPanel.tsx`）—— 每 Agent 开关 + 工具 config_fields
- 聊天：`usePluginToolUis` 拉 `GET /plugins` 并加载 `ui.entry`

前端封装：`dashboard/src/api/modules/plugins.ts`。

---

## 9. 仓库内示例与文档

### 9.1 演示（`plugins/`）

| 目录 | kind | 要点 |
|------|------|------|
| `demo-toolkit` | tool | 时间 / 字数 / `get_tool_config` |
| `demo-greeting-skill` | skill | `ctx.skills("skills")` |
| `demo-turn-logger` | hook | `AgentMiddleware` 打日志 |
| `demo-ui-card` | tool + ui | `octop_ui` 信封（检查是否带了预构建 `ui/`） |
| `server-status` / `bilibili-anime` | — | 指向 bundled 的说明，不是第二份市场 |

说明：`plugins/README.md`、`plugins/README_CN.md`（种子描述已过时，接口仍对）。

### 9.2 测试夹具

`tests/fixtures/plugins/echo-tool/` —— 最小 tool + `config_fields`。

### 9.3 文档 / 技能

| 路径 | 内容 |
|------|------|
| 本文 | 企业插件开发（本文件） |
| `docs/plugin-channels.md` | 通道插件 |
| `docs/octop-ui-payload-offload.md` | 大卡片 payload |
| `docs/architecture.md` | 开机顺序里的 PluginManager |
| `AGENTS.md` §5 / §7 | 模块边界；**不是**插件作者手册 |
| `CONTRIBUTING.md` | **无**插件章节 |
| `.cursor` skills | **无** Octop 插件脚手架技能 |
| `cowork-plugin-management` 专家 | **Claude Cowork** 插件，不是 Octop |

校验（仓库根，需已安装 `octop-harness`）：

```bash
uv run python - <<'PY'
from pathlib import Path
from octop_harness.plugins import PluginRegistry, load_plugin_dir

for name in ("demo-toolkit", "demo-greeting-skill", "demo-turn-logger"):
    PluginRegistry.reset()
    p = load_plugin_dir(Path("plugins") / name, install_deps=False)
    print(p.manifest.id, p.manifest.kind, len(p.tools), p.skills_dir)
PY
```

---

## 10. 约束与陷阱

### 10.1 `id` / 命名

- 用小写 `[a-z0-9]+(-[a-z0-9]+)*`，与目录名相同（市场按**目录名**找，安装按 **manifest.id** 落盘）。
- **不要**用 `..`、`/`、`\`。`market_plugin_dir` 会拒；`install_path` 在本树是 `plugins_dir / manifest.id`。历史上出现过 id 逃出插件目录的问题（TencentCloud/Octop #1692）。企业包必须当单一目录名。
- 工具名用 ASCII `^[a-zA-Z0-9_-]{1,64}$`，避免和 cron/knowledge/mobile 重名。

### 10.2 依赖

- 只写纯 Python wheel 能 `pip install` 的东西。
- `requires` + 可选 `requirements.txt`。`pip` 使用 **Octop 的解释器**，`check=False`：**装失败仍会继续 import**，缺包会在 `setup` 或首次调用爆。
- 不要假设能编译原生扩展或系统包。
- 服务器**不**执行 `npm`。UI 必须预构建并打进 ZIP。

### 10.3 打包

```bash
# 正确：一层插件根
zip -r corp-lookup.zip corp-lookup/

# 错误：多个插件、或缺 plugin.yaml 的散文件、或把仓库根打进去
```

含 UI 时把 `ui/index.js`（或 `ui/dist/`）一并打进包。

### 10.4 签名

无。内网分发靠：评审、固定 URL/制品库、管理权限、（可选）安装后核对目录。

### 10.5 进程与热更新

- CLI install ≠ 正在跑的 server 已 load。
- 关插件会 unload；工具函数改代码通常要 reload/重启。
- channel 指纹未变则复用 class；改 `main.py` 才会换实现。
- `patchResult` 不持久化。

### 10.6 安全与隔离

- 插件代码 = 进程内任意代码。不要装未审计的外网 ZIP。
- 工具能读到的是 **宿主机**（`server-status`），不是 Agent workspace，除非你自己去调 workspace API（`PluginContext` 不提供）。
- Team host 没有插件工具。
- 已有 `SKILL.md` 不会被 skill 插件覆盖。
- 不要 `import octop.*` 写第三方插件。bundled `arxiv-search` 用 `octop.i18n` 是因为它活在 Octop 包内；企业插件应自包含。旧 `harness_agent` 导入仅兼容。

### 10.7 其它

- 一个 zip / 一个 kind / 一个 id。
- 缺省全开：装完就可能进模型上下文。企业环境若要「先装后开」，装完立刻 `PATCH` 关掉，或先装到未跑服务的机器再改 `config.json`。
- 市场安装会 **强制 enabled=true**。
- `docs/cli.md` 写的「git URL」「`bundled_plugins_seeded`」与当前 CLI/种子不符。

---

## 11. 企业内插件最小配方

目标：Octop 能接受、管理员能装、某个 Agent 能调到一个内部查询工具。

### 步骤

1. **定 id**：`corp-employee-lookup`（单一小写段，与目录名相同）。
2. **建树**：

```text
corp-employee-lookup/
├── plugin.yaml
├── main.py
└── icon.svg          # 可选
```

3. **`plugin.yaml`**：

```yaml
id: corp-employee-lookup
version: 1.0.0
name: 员工查询
description: 按工号或姓名查询内网员工目录（只读）
icon: "🔎"
group: tools
kind: tool
entry: main.py
requires:
  - httpx>=0.27
```

4. **`main.py`**：只在 `setup` 里 `ctx.tool`；函数参数即 schema；密钥走环境变量或 `config_fields`（`type: password`），不要写进仓库。

```python
from __future__ import annotations

import json
import os

import httpx
from octop_harness.plugins import PluginContext, get_tool_config

async def lookup_employee(query: str) -> str:
    cfg = get_tool_config("lookup_employee") or {}
    base = str(cfg.get("base_url") or os.environ.get("CORP_DIR_URL") or "").rstrip("/")
    if not base:
        return json.dumps({"error": "base_url not configured", "text": "未配置目录地址"}, ensure_ascii=False)
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{base}/employees", params={"q": query})
        resp.raise_for_status()
        data = resp.json()
    text = f"命中 {len(data) if isinstance(data, list) else 1} 条"
    return json.dumps({"text": text, "data": data}, ensure_ascii=False)

def setup(ctx: PluginContext) -> None:
    ctx.tool(
        "lookup_employee",
        lookup_employee,
        description="Look up an employee by name or employee id in the corporate directory.",
        config_fields=[
            {
                "name": "base_url",
                "type": "text",
                "required": False,
                "label": "Directory base URL",
                "help": "例如 https://dir.example.internal/api",
            }
        ],
    )
```

5. **离线校验**（开发机已 `uv sync` / 装了 `octop-harness`）：

```bash
uv run python - <<'PY'
from pathlib import Path
from octop_harness.plugins import PluginRegistry, load_plugin_dir
PluginRegistry.reset()
p = load_plugin_dir(Path("corp-employee-lookup"), install_deps=False)
assert p.manifest.id == "corp-employee-lookup"
assert p.manifest.kind == "tool"
assert [t.name for t in p.tools] == ["lookup_employee"]
print("ok", p.manifest.version)
PY
```

6. **安装**（本机开发）：

```bash
octop plugin install ./corp-employee-lookup --force
```

若 `octop run` 已在跑：管理页 Reload，或 `POST /api/plugins/reload`。

生产：`zip -r corp-employee-lookup.zip corp-employee-lookup/`，内网 HTTPS 直链或 Dashboard 上传。不要用 GitHub `/blob/` HTML 页。

7. **启用**
   - 全局：Admin → 插件，确认开关为开（目录安装缺省已开）。
   - 可见性：需要的话设为指定用户组。
   - Agent：个性化 → 插件确认有效；在工具管理填 `base_url`。
   - 缺省工具是开的；要默认关请在 Agent 上显式 `enabled: false`。

8. **验收**：对该 Agent 说「查一下工号 …」，应出现 `lookup_employee`。无卡片时用户看到 JSON/`text`。要卡片再按 [§4](#4-可选-ui仪表盘卡片) 加 `octop_ui` + `ui/index.js`。

### 配方变体

| 需求 | kind | 最小增量 |
|------|------|----------|
| 只往工作区丢操作手册 | `skill` | `ctx.skills("skills")` + `skills/<slug>/SKILL.md` |
| 模型调用前后审计 | `hook` | `AgentMiddleware`，不要改消息除非评审过 |
| 内部 IM | `channel` | `BaseChannel` + `ctx.channel`；先读 `docs/plugin-channels.md` |
| 聊天卡片 | `tool` + `ui` | 预构建 ESM + `octop_ui` 信封 |

---

## 12. 仓库内已有文档与代码的差异

下列说法以**本文件引用的实现**为准：

| 文档 | 过时说法 | 当前代码 |
|------|----------|----------|
| `plugins/README.md`、`README_CN.md`、`plugins/server-status/README.md` | `octop init` / `octop run` 把缺失 bundled 拷到 `~/.octop/plugins/` 并全局关闭 | `seed.py` **不**装新 id；只升级已装且版本更新的。新插件走市场安装 |
| `docs/cli.md`、`docs/configuration.md` | `bundled_plugins_seeded` 阻止卸载后复活 | 该键不再参与种子。卸载 = 删目录，种子不重建 |
| `docs/cli.md` | `install` 支持 git URL | CLI 只接受**目录**或 **http(s) ZIP** |
| `docs/architecture.md` | 「bundled default off」 | 种子不再自动拷贝；市场安装写 `enabled: true`；其它安装缺省开 |
| `docs/api.md` | 仅列出部分 `/plugins` | 完整表见 [§8.2](#82-http前缀-api) |
| README 路线图 | 远程插件市场、对话式脚手架 | 市场仍是 in-tree `bundled/`；注释写明未来改远程 ZIP |

---

## 附录 A. `PluginContext` 速查

来源：harness `plugins/context.py`（本仓库通过 `octop_harness` 依赖使用）。

```
plugin_id: str
source_path: Path
tool(name, fn, *, description="", config_fields=None)      # kind=tool
middleware(instance, *, priority=100)                      # kind=hook
channel(kind, channel_cls, *, label="", icon="",
        intro_url="", fields=None)                         # kind=channel
skills(relative_path)                                      # kind=skill
model_factory / get_protocol / bind_model_factory /
    get_model_access(...)                                  # 宿主绑定模型后才有；setup() 期间为 None
```

`get_tool_config(name)` 在 `octop_harness.plugins`（`tools.py`），不是 Context 方法。

## 附录 B. `config.json` / Agent 配置形状

```json
{
  "plugins": {
    "corp-employee-lookup": { "enabled": true }
  }
}
```

Agent `config_json.plugins`：

```json
{
  "corp-employee-lookup": {
    "enabled": true,
    "tools": {
      "lookup_employee": {
        "enabled": true,
        "config": { "base_url": "https://dir.example.internal/api" }
      }
    }
  }
}
```

合并函数：`merge_plugins_enabled_settings` / `merge_plugins_tool_settings`（`plugin_tool_defaults.py`）。

## 附录 C. 相关测试

| 文件 | 覆盖 |
|------|------|
| `tests/unit/test_plugins.py` | harness load、default-on、sanitize |
| `tests/unit/test_plugin_manager.py` | 安装、ZIP、开关、UI 路径、legacy import、channel 指纹 |
| `tests/unit/test_plugin_seed.py` | 种子只升级、不装新 id |
| `tests/unit/test_bundled_plugins_layout.py` | bundled 必须有 main + ui；市场安装 |
| `tests/unit/test_plugin_channels.py` | 通道桥 |
| `tests/integration/test_plugin_upload.py` | 上传 ZIP |
| `tests/integration/test_plugin_market.py` | 市场 API |
| `tests/integration/test_plugin_tool_disable.py` | Agent 关工具 |

---

维护：实现变了先改代码，再改本节引用的路径与表格。不要把「计划中的远程市场」写成已经存在的能力。
