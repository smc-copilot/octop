# 需求覆盖 × 测试

Base `116b57db97bcbba4e10dae9ad82142656d039d07`。参考 Adapter ≠ 客户生产集成。

| 需求 | 实现 | 执行的测试 | 提议未跑 |
|------|------|------------|----------|
| 摘要卡 核对并编辑/取消 | `ui/dist/index.js` `business_ui_card` | 工具 JSON 草稿无所有权 | 全浏览器 E2E（环境未启动完整 Dashboard） |
| 侧栏 iframe POST 兑票 | FormFrame + Dock `openSidePanel` | Adapter redeem + replay 403 | iframe 第三方 cookie 实机 |
| 同一 callId 已提交 | `patchResult` + `interactions.get` | 提交后 get 为 submitted | 历史线程 UI 水合点击 |
| 七字段 / formRef 注册表 | 模型禁止 URL；Adapter FORMS | claim 拒绝 URL form_ref | — |
| 草稿非授权 | tool 不写 records | `test_draft_tool_does_not_grant_ownership` | — |
| claim 宿主身份 | `reauthorize_actor` + thread | 无 scope 403；跨用户 403；伪造 user_id extra forbid；停用用户 403 | — |
| 配置卡 admin | permission=admin + 插件 UI | 非管理员 save `denied` | Dashboard 配置卡点击 |
| 密钥不进 records | stage_credential | list/record 不含 token | — |
| api_token vs authorization_code | credential `single_use` | authorization_code `single_use True` | 一次性码兑换后拒绝重用（连接层） |
| 握手分阶段 | `connections.test` | 参考 Adapter ok；HTML 站 unsupported | 公网 example.com live |
| SSRF | `security.py` | http/userinfo/fragment；metadata；loopback 需例外；DNS rebinding mock；未批准 origin；redirect | DNS rebinding 实解析 |
| 乐观并发 / 幂等 / 取消 | Adapter 409/idempotent；cancel 仅草稿 | 双提交 idempotent；submitted 不能 cancel | 并发双 claim CAS 压力 |
| 详情失败保持已提交 | `last_error` + 重试按钮 | Adapter `fail_detail` 路径存在 | UI 点击重试 E2E |
| 登出即死 | **不实现** | 文档化 UNSUPPORTED | 不可测为成功 |
| 包安装 | ZIP | `test_manager_installs_zip` + `load_plugin_dir` | 真机 `/data` OCTOP_HOME 上传 |
| 无宿主 diff | 仅 `plugins/` `tests/unit/plugins/test_business_ui_*` | `git diff --name-only` 门禁 | — |
