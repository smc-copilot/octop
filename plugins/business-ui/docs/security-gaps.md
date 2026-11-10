# 安全与已知缺口

## 硬缺口（验收必须看见）

### Octop 登出不会立即作废业务会话 — UNSUPPORTED

宿主零改动下没有 logout → Adapter 通知。本插件 **不** 实现、不伪造 Host 钩子。  
业务系统必须独立做：短 TTL 会话、主动撤销、账号停用、每次 save/submit/detail 重鉴权。

浏览器第三方存储 / iframe `sandbox` / `SameSite=None` **需要实机验证**。POST 兑票只证明一次兑换，不证明 cookie 能写进第三方上下文。

## 已做的失败关闭

- 管理员：Host `permission=admin` + `reauthorize_actor`（DB `role==admin`，停用拒绝）
- 草稿不授予所有权；无 verified `agent_id`+`thread_id` 则 claim 拒绝
- `callId` 绑定哈希含 agent+thread；跨用户/跨线程拒绝
- namespaced `issuer|user_id`
- 密钥只经配置卡 → action → Host 凭据；记录与列表只有元数据
- 出站 SSRF 策略；metadata 不可 allowlist；无私网一键放行
- 票据一次性；postMessage 校验 origin/source/interaction/nonce 仍只是提示
- `allowedActions` 仅 UI；服务端再授权
- 不信任远端自报 origin；必须落在已批准连接注册表

## 参考 Adapter 边界

`adapter/` 是协议夹具：内存态、自签 TLS、样例招聘 formRef。不得当作客户生产集成证据。
