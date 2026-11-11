import { useEffect, useState } from "./host";
import type { PluginToolProps } from "./host";
import { runAction } from "./api";
import { ActivationPanel, methodLabel } from "./ActivationPanel";
import { btn, cardStyle, tone } from "./styles";

const emptyForm = {
  display_name: "",
  base_url: "",
  auth_method: "api_token",
  secret: "",
  extra_origins: "",
  private_allow: "127.0.0.1/32",
  tls_ca_pem: "",
  instance_issuer: "",
  enabled: true,
  user_auth_method: "oauth2",
  oauth_discovery_url: "",
  oauth_authorize_url: "",
  oauth_token_url: "",
  oauth_revoke_url: "",
  oauth_client_id: "",
  oauth_client_secret: "",
  oauth_scopes: "openid profile",
};

export function ConfigCard(props: PluginToolProps) {
  const dark = (props.host.getToolContext() || {}).theme === "dark";
  const host = props.host;
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [canManage, setCanManage] = useState(false);
  const [issuer, setIssuer] = useState("");
  const [error, setError] = useState("");
  const [test, setTest] = useState<Record<string, unknown> | null>(null);
  const [form, setForm] = useState(emptyForm);

  const reload = async () => {
    const res = await runAction<{
      connections?: Record<string, unknown>[];
      can_manage?: boolean;
      instance_issuer?: string;
      env_sync_error?: string | null;
    }>(host, "connections.list", {}, false);
    setRows(res.connections || []);
    setCanManage(!!res.can_manage);
    setIssuer(res.instance_issuer || "");
    if (res.env_sync_error) setError(String(res.env_sync_error));
  };

  useEffect(() => {
    reload().catch((err) => setError(String((err as Error)?.message || err)));
  }, [host]);

  const save = async () => {
    setError("");
    const payload: Record<string, unknown> = {
      display_name: form.display_name,
      base_url: form.base_url,
      auth_method: form.auth_method,
      extra_origins: form.extra_origins ? form.extra_origins.split(/\s+/).filter(Boolean) : [],
      private_allow: form.private_allow ? form.private_allow.split(/\s+/).filter(Boolean) : [],
      instance_issuer: form.instance_issuer || undefined,
      enabled: form.enabled,
      user_auth_method: form.user_auth_method,
      oauth_discovery_url: form.oauth_discovery_url || undefined,
      oauth_authorize_url: form.oauth_authorize_url || undefined,
      oauth_token_url: form.oauth_token_url || undefined,
      oauth_revoke_url: form.oauth_revoke_url || undefined,
      oauth_client_id: form.oauth_client_id || undefined,
      oauth_scopes: form.oauth_scopes || undefined,
    };
    if (form.secret) payload.secret = form.secret;
    if (form.tls_ca_pem) payload.tls_ca_pem = form.tls_ca_pem;
    if (form.oauth_client_secret) payload.oauth_client_secret = form.oauth_client_secret;
    try {
      await runAction(host, "connections.save", payload, false);
      setForm((prev) => ({ ...prev, secret: "", oauth_client_secret: "" }));
      await reload();
    } catch (err) {
      setError(String((err as Error)?.message || err));
    }
  };

  return (
    <div style={cardStyle(dark)} data-business-ui-config="1">
      <div style={{ fontWeight: 700 }}>Business UI 连接</div>
      <div style={{ fontSize: 12, opacity: 0.8, marginTop: 4 }}>
        连接密钥与用户令牌只经已认证 action 写入 Host 凭据。每位用户单独激活。多实例部署用全局
        BUSINESS_UI_*（密钥只用 *_FILE），不必在聊天里填；环境变量页没有 Test 按钮，请用
        python -m business_ui test。
      </div>
      {issuer ? <div style={{ fontSize: 12, marginTop: 6 }}>实例 issuer：{issuer}</div> : null}
      {error ? <div style={{ color: tone("err"), fontSize: 12 }}>{error}</div> : null}
      {rows.map((row) => {
        const envManaged = row.managed_by === "env";
        return (
        <div key={String(row.connection_id)} style={{ marginTop: 10, paddingTop: 8, borderTop: "1px solid var(--ant-color-border, #e2e8f0)", fontSize: 13 }}>
          <strong>{String(row.display_name)}</strong>
          <div>
            {String(row.base_url)} · 服务身份 {String(row.auth_method)} · 用户授权 {methodLabel(String(row.user_auth_method))}
            {row.enabled ? " · 启用" : " · 停用"}
            {envManaged ? " · 环境变量管理" : ""}
          </div>
          {envManaged ? (
            <div style={{ fontSize: 12, marginTop: 4, opacity: 0.8 }}>
              由全局 BUSINESS_UI_* 管理，聊天里不能改 URL/授权方式。每位用户仍需单独激活。
            </div>
          ) : null}
          <ActivationPanel host={host} connection={row} onChanged={reload} />
          {canManage ? (
            <div>
              <button
                type="button"
                style={btn(false)}
                onClick={async () => setTest(await runAction(host, "connections.test", { connection_id: row.connection_id }, false))}
              >
                Test Connection
              </button>
              {envManaged ? null : (
              <button
                type="button"
                style={btn(false)}
                onClick={async () => {
                  await runAction(host, "connections.delete", { connection_id: row.connection_id }, false);
                  await reload();
                }}
              >
                删除
              </button>
              )}
            </div>
          ) : null}
        </div>
        );
      })}
      {canManage ? (
        <div style={{ marginTop: 12 }}>
          <input placeholder="显示名" value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} style={{ display: "block", width: "100%", marginTop: 6 }} />
          <input placeholder="HTTPS Adapter 地址" value={form.base_url} onChange={(e) => setForm({ ...form, base_url: e.target.value })} style={{ display: "block", width: "100%", marginTop: 6 }} />
          <input placeholder="本实例 issuer https://octop.example.com" value={form.instance_issuer} onChange={(e) => setForm({ ...form, instance_issuer: e.target.value })} style={{ display: "block", width: "100%", marginTop: 6 }} />
          <select value={form.auth_method} onChange={(e) => setForm({ ...form, auth_method: e.target.value })} style={{ marginTop: 6 }}>
            <option value="api_token">服务身份：可复用 API token</option>
            <option value="authorization_code">服务身份：一次性授权码</option>
          </select>
          <input type="password" autoComplete="new-password" placeholder="服务密钥 / 授权码（不回显）" value={form.secret} onChange={(e) => setForm({ ...form, secret: e.target.value })} style={{ display: "block", width: "100%", marginTop: 6 }} />
          <select value={form.user_auth_method} onChange={(e) => setForm({ ...form, user_auth_method: e.target.value })} style={{ marginTop: 6, display: "block" }}>
            <option value="oauth2">用户授权：标准 OAuth2/OIDC + PKCE</option>
            <option value="native_login">用户授权：业务系统账号登录</option>
            <option value="personal_access_token">用户授权：个人访问令牌</option>
          </select>
          {form.user_auth_method === "oauth2" ? (
            <div>
              <input placeholder="OAuth discovery URL（可选 RFC 8414）" value={form.oauth_discovery_url} onChange={(e) => setForm({ ...form, oauth_discovery_url: e.target.value })} style={{ display: "block", width: "100%", marginTop: 6 }} />
              <input placeholder="Authorize URL（无 discovery 时必填）" value={form.oauth_authorize_url} onChange={(e) => setForm({ ...form, oauth_authorize_url: e.target.value })} style={{ display: "block", width: "100%", marginTop: 6 }} />
              <input placeholder="Token URL（无 discovery 时必填）" value={form.oauth_token_url} onChange={(e) => setForm({ ...form, oauth_token_url: e.target.value })} style={{ display: "block", width: "100%", marginTop: 6 }} />
              <input placeholder="Revocation URL（可选）" value={form.oauth_revoke_url} onChange={(e) => setForm({ ...form, oauth_revoke_url: e.target.value })} style={{ display: "block", width: "100%", marginTop: 6 }} />
              <input placeholder="OAuth client id" value={form.oauth_client_id} onChange={(e) => setForm({ ...form, oauth_client_id: e.target.value })} style={{ display: "block", width: "100%", marginTop: 6 }} />
              <input type="password" autoComplete="new-password" placeholder="OAuth client secret（不回显）" value={form.oauth_client_secret} onChange={(e) => setForm({ ...form, oauth_client_secret: e.target.value })} style={{ display: "block", width: "100%", marginTop: 6 }} />
              <input placeholder="scopes" value={form.oauth_scopes} onChange={(e) => setForm({ ...form, oauth_scopes: e.target.value })} style={{ display: "block", width: "100%", marginTop: 6 }} />
            </div>
          ) : (
            <div style={{ fontSize: 12, marginTop: 6, opacity: 0.8 }}>
              {form.user_auth_method === "native_login"
                ? "用户在插件表单输入业务账号；密码只经 action 交给 Adapter，插件不落盘。"
                : "用户在插件表单粘贴个人访问令牌；令牌写入 Host 凭据，不进 URL/聊天。"}
            </div>
          )}
          <textarea placeholder="可选：内网适配器 TLS CA PEM" value={form.tls_ca_pem} onChange={(e) => setForm({ ...form, tls_ca_pem: e.target.value })} style={{ display: "block", width: "100%", marginTop: 6, minHeight: 64 }} />
          <input placeholder="额外 origin（空格分隔）" value={form.extra_origins} onChange={(e) => setForm({ ...form, extra_origins: e.target.value })} style={{ display: "block", width: "100%", marginTop: 6 }} />
          <input placeholder="私有网段例外 CIDR/host" value={form.private_allow} onChange={(e) => setForm({ ...form, private_allow: e.target.value })} style={{ display: "block", width: "100%", marginTop: 6 }} />
          <button type="button" style={btn(true)} onClick={() => save()}>
            保存连接
          </button>
        </div>
      ) : (
        <div style={{ fontSize: 12, marginTop: 8 }}>仅管理员可新增连接。角色由 Host JWT 判定。</div>
      )}
      {test ? (
        <div style={{ marginTop: 12, fontSize: 12 }} data-connection-test="1">
          <div>
            Test {test.ok ? "未完全等同浏览器嵌入" : "失败"} · {String(test.unsupported_reason || test.protocol || "")}
          </div>
          {Array.isArray(test.stages)
            ? (test.stages as { ok: boolean; name: string; detail: string }[]).map((s) => (
                <div key={s.name}>
                  {s.ok ? "✓" : "✗"} {s.name} — {s.detail}
                </div>
              ))
            : null}
        </div>
      ) : null}
      <div style={{ fontSize: 11, marginTop: 10, opacity: 0.7 }}>
        UNSUPPORTED：Octop 登出不会立即作废已兑业务会话。浏览器第三方存储需实测，POST 兑票不能保证 cookie。
      </div>
    </div>
  );
}
