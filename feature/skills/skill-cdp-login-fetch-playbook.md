# Skill + CDP 登录态取数：案例与开发设计规范

> 快速参考手册｜整理日期：2026-10-31（Asia/Shanghai）  
> 用途：后续扩展「需登录网站」取数 Skill 时复用架构、案例与清单  
> 来源：SkillHub 公开检索结果 + 本机已装 Skill 的 `SKILL.md` 结构归纳  
> 安装源优先级：SkillHub →（无匹配时）ClawHub，并说明回退

---

## 1. 结论先行

| 问题 | 答案 |
|------|------|
| 登录墙怎么破？ | **不破**。用户真人登录，Skill 只 **attach 已登录会话**。 |
| 反爬怎么应对？ | 用人机一体浏览器（真实 profile）+ 限速 + 停手策略；不做签名破解 / 批量撞风控。 |
| Skill 怎么分层？ | **底座（CDP 通用）** + **站点剧本（选点 / 翻页 / 字段）**。扩展新站只换剧本。 |
| 搜「CDP」注意 | 会混进 Coinbase / Segment「客户数据平台 CDP」，与 Chrome DevTools Protocol **无关**，忽略。 |

---

## 2. 推荐架构（两层）

```
┌─────────────────────────────────────────────┐
│  站点 Skill（剧本）                          │
│  入口 URL · 列表/详情选择器 · 翻页 · 字段导出 │
│  登录失效检测 · 验证码停手 · 限速与配额       │
└──────────────────▲──────────────────────────┘
                   │ attach / connectOverCDP
┌──────────────────┴──────────────────────────┐
│  底座 Skill（CDP / 浏览器桥）                 │
│  9222 · 扩展桥 · CDP Proxy · Playwright CDP  │
│  复用真实 Chrome profile / Cookie / 已开 tab │
└──────────────────▲──────────────────────────┘
                   │ 用户扫码 / 账密 / 二次验证
┌──────────────────┴──────────────────────────┐
│  真人会话（唯一权威登录态）                   │
└─────────────────────────────────────────────┘
```

### 2.1 三种常见 attach 方式

| 方式 | 典型 Skill | 适用 |
|------|------------|------|
| Chrome 远程调试 `localhost:9222` | `cdp-browser`、`chrome-cdp` | 本机已开调试 Chrome |
| CDP Proxy / 单连接代理 | `cdpproxy`、`browser-cdp` | 保 profile、多 target |
| 浏览器扩展桥 | `cdp-autorunner-skill`、`cdp-bridge` | 插件控真实浏览器 |
| Playwright `connectOverCDP` | `xianyu-automation` 等 | 脚本栈已是 Playwright |

### 2.2 登录态生命周期（规范）

1. **获取**：用户扫码 / 账密 / 短信；Skill **不存明文密码**。  
2. **引用**：只持有会话引用（调试端口、扩展会话、Cookie 档案路径）。  
3. **探活**：任务前检查「是否仍登录 / 是否跳转登录页」。  
4. **失效**：停手 → 提示用户重登 → 不重试撞风控。  
5. **脱敏**：日志、回执、报告中 **永不回显** Cookie / token 原文（参考金融爬虫登录档案做法）。

---

## 3. Skill 开发设计规范

### 3.1 目录与入口

建议最小结构：

```
my-site-fetch/
├── SKILL.md          # 必填：frontmatter + 全文规范
├── _meta.json        # 可选：商店元数据
├── references/       # 选择器、字段字典、风控说明
└── scripts/          # 可选：attach / export / verify
```

安装到 Agent 可发现目录（本环境常用 `agent-data/workflows`，CLI 用 `--dir` 指向），必要时做扁平 symlink。

### 3.2 `SKILL.md` frontmatter（推荐字段）

```yaml
---
name: my-site-fetch                 # kebab-case，与目录一致
slug: my-site-fetch
displayName: 「站点名」登录态取数
version: 0.1.0
description: |
  一句话能力 + 明确触发词 + 明确不做边界。
  当用户说「从 XX 拉…」「导出 XX 后台…」且已登录时使用。
  不用于绕过登录、越权抓取他人非公开数据、破解签名或验证码。
license: MIT-0                      # 按实际上架要求
---
```

**description 写作要点（决定路由准不准）**

- **何时用**：自然语言触发词写全（中英均可）。  
- **何时不用**：登录墙破解、批量扒号、无授权隐私数据等写死。  
- **依赖**：需 CDP 底座 / 已登录 Chrome / 扩展桥，写清楚。  
- **交付物**：CSV / JSON / Markdown / 截图清单，写清楚。

### 3.3 正文必备章节（站点取数类）

1. **角色与边界**：只读 / 可写（发帖上架）分开声明。  
2. **前置条件**：已登录目标站；调试口或扩展已就绪。  
3. **工作流**（逐步，禁止跳步）：探活 → 导航 → 列表 → 详情 → 导出 → 校验。  
4. **停手条件**：登录页、验证码、风控弹窗、选择器全空、连续失败 N 次。  
5. **限速**：间隔、并发=1（默认）、每日上限建议。  
6. **字段字典**：表格列出字段名、来源选择器、类型、是否必填。  
7. **排障**：登录失效、SPA 路由、shadow DOM、草稿丢失等（可参考小红书上传 Skill）。  
8. **合规声明**：仅操作用户本人授权账号与有权查看的数据。

### 3.4 行为铁律（建议原样写入 Skill）

- 先探活再抓；登录失效立即停。  
- 验证码 / 二次验证：**停并交给用户**，不自动破解。  
- 不编造抓取结果；空结果明确报 `E_SOURCE_EMPTY` 或同等语义。  
- 选择器失效时：记录当前 URL + 截图 + DOM 摘要，再请求更新 `references/`，禁止瞎猜点击。  
- 默认只读；涉及发布 / 下单 / 付款必须单独确认卡点。

### 3.5 与通用爬虫 Skill 的分工

| 类型 | 例子 | 职责 |
|------|------|------|
| 脚本工坊 / Scrapy 生成器 | `cd-scraper`、`scrapy-spider-generator` | 写可跑脚本、解析规则；**不替代登录态** |
| 级联抓取理解 | `self-dev-web-scraper` | HTTP → 解析 → Playwright 回退；公开页优先 |
| CDP 底座 | 见 §4 | 会话 attach |
| 站点剧本 | 小红书 / 闲鱼 / X / Gmail | 业务选点与字段 |

---

## 4. 底座案例清单（跨站复用）

| 名称 | Slug / 命名空间 | 版本（检索时） | 要点 | 链接 |
|------|-----------------|----------------|------|------|
| Cdp Browser | `@clawhub_gostlightai/cdp-browser` | 2.0.1 | `9222` 控 tab / 截图 / JS | https://skillhub.cn/skills/cdp-browser |
| CDP Autorunner | `@indiv-miaoo/cdp-autorunner-skill` | 1.4.0 | 扩展桥；复用登录态 | https://skillhub.cn/skills/cdp-autorunner-skill |
| CDP Proxy | `@user_b7fb1924/cdpproxy` | 1.0.0 | 持久单连接；保 profile | https://skillhub.cn/skills/cdpproxy |
| Browser CDP | `@clawhub_0xcjl/browser-cdp` | 1.0.0 | 真实 Chrome + 登录态交互 | https://skillhub.cn/skills/browser-cdp |
| chrome-cdp | `@clawhub_adminlove520/chrome-cdp` | 1.0.0 | 读已开标签（含登录页） | https://skillhub.cn/skills/chrome-cdp |
| CDP 浏览器大师 | `@clawhub_thcjp/cdp-browser-master` | 1.0.0 | SPA 等待、选择器失效、反检测策略说明 | https://skillhub.cn/skills/cdp-browser-master |
| CDP Bridge | `@clawhub_miyan1221/cdp-bridge` | 1.0.0 | 插件远程；读 Cookie / 扫页 | https://skillhub.cn/skills/cdp-bridge |
| chrome-cdp-skill | `@clawhub_web3toolshub/chrome-cdp-skill` | 1.0.6 | 用户明确要求时再交互已开页 | https://skillhub.cn/skills/chrome-cdp-skill |

安装示例：

```bash
skillhub install cdp-browser --namespace clawhub_gostlightai --dir <skills目录>
skillhub install cdp-autorunner-skill --namespace indiv-miaoo --dir <skills目录>
```

---

## 5. 站点剧本案例（登录态参考）

| 站点 / 场景 | Slug | 技术要点 | 链接 |
|-------------|------|----------|------|
| 小红书视频上传 / 草稿 | `@user_b2126c75/xiaohongshu-video-uploader` | **CDP 接管已登录 Chrome**；上传、话题、合集；登录失效 / 风控排障 | https://skillhub.cn/skills/xiaohongshu-video-uploader |
| 小红书视频发布 | `@user_b2126c75/xhs-video-publish` | 真实 Chrome + CDP；shadow DOM 坑位清单 | https://skillhub.cn/skills/xhs-video-publish |
| 小红书草稿填充 | `@user_cbbcbcca/xhs-draft-pusher` | **人工登录后**半自动填草稿 | https://skillhub.cn/skills/xhs-draft-pusher |
| 小红书博主采集分析 | `@user_d911eb9f/990320` | 自称无需 Cookie（公开主页向）；深度登录态数据仍不适用 | https://skillhub.cn/skills/990320 |
| 闲鱼自动上货 | `@user_f847d9d9/xianyu-automation` | **Python + Playwright CDP**；多店定时 | https://skillhub.cn/skills/xianyu-automation |
| X (Twitter) | `@clawhub_stwith/x-cdp` | 已登录 Chromium；发帖回复；无 API Key | https://skillhub.cn/skills/x-cdp |
| Gmail 发送 | `@clawhub_joustonhuang/cdp-gmail-delivery` | 操作员调试会话内发信 | https://skillhub.cn/skills/cdp-gmail-delivery |

### 5.1 相关但非「CDP 剧本」的爬虫参考

| 名称 | Slug | 说明 |
|------|------|------|
| 爬虫脚本工坊 | `@user_8ee65e73/cd-scraper` | 脚本交付；声明不用于绕过登录 |
| python 爬虫引导 | `@user_5548e881/python-crawler-guide` | 白话 → 脚本 + 审计清单 |
| 网页爬虫开发 | `@user_3c6cb52e/self-ent-tech-web-scraper` | 静/动态全流程指南 |
| 网页抓取与内容理解 | `@user_f12a44b7/self-dev-web-scraper` | 级联回退 |
| Scrapy 生成器 | `@user_3c6cb52e/scrapy-spider-generator` | 生产级 Scrapy 骨架 |
| 全能金融爬虫 | `@user_9d5a2a39/cnfinancialscraper` | Cookie 档案化 + 脱敏 + 探活分档（登录态范本） |

---

## 6. 新站点 Skill 脚手架（复制即用提纲）

把下面整段贴进新 `SKILL.md` 再按站点改名：

```markdown
---
name: <site>-login-fetch
displayName: <站点>登录态取数
version: 0.1.0
description: |
  在用户已登录的真实浏览器会话中，通过 CDP 只读采集 <站点> 的 <数据范围>。
  触发：从 <站点> 导出 / 拉取后台 / 同步列表。
  不做：绕过登录、破解验证码、越权他人非公开数据、高频撞风控。
---

# <站点>登录态取数

## 前置
- 用户已在 Chrome 登录 <站点>
- CDP 底座可用（9222 / 扩展桥 / Playwright connectOverCDP）

## 流程
1. 探活：打开 <入口 URL>，确认非登录页
2. 列表：进入 <列表路径>，按 `references/selectors.md` 抽取
3. 详情：按需进入详情，字段见 `references/fields.md`
4. 导出：写入约定目录（JSON/CSV），附 manifest（条数、时间、来源 URL）
5. 校验：必填字段空值率；失败条目进 `failures.json`

## 停手
登录墙 / 验证码 / 风控弹窗 / 选择器连续失败 → 截图 + URL + 停

## 限速
默认并发 1；请求间隔 ≥ Xs；单次任务上限 N 条
```

`references/selectors.md` 建议表头：`页面 | 元素含义 | CSS/XPath | 备注（SPA/shadow）`  
`references/fields.md` 建议表头：`字段 | 类型 | 必填 | 来源 | 样例`

---

## 7. 扩展多站点时的工程约定

1. **一个底座 + 多剧本**：底座只装 1～2 个；每站一个 Skill，避免巨型万能包难维护。  
2. **选择器外置**：改版只改 `references/`，少动主流程。  
3. **版本与备份**：改站点包前备份；上架保持 slug 稳定、版本递增。  
4. **双平台注意**：若同步 SkillHub / 扣子等，注意各自元数据清洗（参见专家锻造师类 Skill 的发布脚本实践）。  
5. **本机 Agent 路径**：`skillhub install … --dir <当前 Agent skills 目录>`，装完确认可被发现（扁平链接）。  
6. **安装前确认**：汇总来源、版本、风险（社区包质量参差）再装。

---

## 8. 合规与风险（必须写进每个取数 Skill）

- 仅使用**用户本人授权**的账号与其有权访问的数据。  
- 遵守目标站用户协议与 robots / 商家后台条款；企业场景走法务评审。  
- 禁止：撞库、打码破解、伪造设备农场、绕过付费墙、批量抓取他人隐私。  
- 日志脱敏；交付物可含业务字段，不可含完整会话密钥。  
- 金融 / 电商 / 社交通用同一原则：**登录外置、技能只带会话做事**。

---

## 9. 开发自检清单（发版前打勾）

- [ ] frontmatter：`name` / `description` 含触发词与「不做」边界  
- [ ] 写明 CDP 底座依赖与探活步骤  
- [ ] 停手条件完整（登录 / 验证码 / 风控 / 空选择器）  
- [ ] `references` 字段字典与选择器表  
- [ ] 限速与并发默认安全  
- [ ] 脱敏与失败清单  
- [ ] 只读默认；写操作有确认卡点  
- [ ] 本地用真实已登录会话跑通 1 条金路径  
- [ ] `skillhub search <slug>` 与安装命令验证  

---

## 10. 常用命令速查

```bash
skillhub search 小红书
skillhub search CDP
skillhub search <slug> --json

skillhub install <slug> --namespace <ns> --dir <skills目录>
skillhub list
skillhub upgrade
```

SkillHub 安装说明：https://skillhub.cn/install/skillhub.md  
商店：https://skillhub.cn/

---

## 11. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-10-31 | 初版：汇总 CDP 底座 / 小红书·闲鱼·X·Gmail 案例与登录态取数设计规范 |

