import { useState } from "./host";
import type { PluginToolHost } from "./host";
import { runAction } from "./api";
import { btn, tone } from "./styles";

export function methodLabel(method: string | undefined) {
  if (method === "native_login") return "业务账号登录";
  if (method === "personal_access_token") return "个人访问令牌";
  return "OAuth2 / OIDC";
}

export function ActivationPanel(props: {
  host: PluginToolHost;
  connection: Record<string, unknown> | null;
  onChanged?: () => Promise<unknown> | unknown;
}) {
  const { host, connection, onChanged } = props;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [nativeUser, setNativeUser] = useState("");
  const [nativePass, setNativePass] = useState("");
  const [pat, setPat] = useState("");
  if (!connection || !connection.connection_id) return null;
  const status = String(connection.activation_status || "inactive");
  const method = String(connection.user_auth_method || "oauth2");
  const active = status === "active";
  const connectionId = String(connection.connection_id);

  const finish = async (job: () => Promise<void>) => {
    setBusy(true);
    setError("");
    try {
      await job();
      setNativePass("");
      setPat("");
      await onChanged?.();
    } catch (err) {
      setError(String((err as Error)?.message || err));
    } finally {
      setBusy(false);
    }
  };

  const startOauth = () =>
    finish(async () => {
      const started = await runAction<{ authorization_url?: string; state?: string; status?: string }>(
        host,
        "activations.start",
        { connection_id: connectionId },
        false,
      );
      if (!started.authorization_url || !started.state) throw new Error("authorization_url missing");
      const popup = window.open(started.authorization_url, "bui-oauth", "width=480,height=720");
      const deadline = Date.now() + 5 * 60 * 1000;
      while (Date.now() < deadline) {
        const done = await runAction<{ status?: string }>(host, "activations.complete", { state: started.state }, false);
        if (done && done.status === "active") {
          if (popup && !popup.closed) popup.close();
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, 1200));
      }
      throw new Error("activation timed out");
    });

  return (
    <div data-activation-panel="1" style={{ marginTop: 8, fontSize: 12 }}>
      <div>
        用户授权：{methodLabel(method)} · {active ? "已激活" : "需要激活/重新激活"}
      </div>
      {error ? <div style={{ color: tone("err"), marginTop: 4 }}>{error}</div> : null}
      {active ? (
        <div>
          {method === "oauth2" ? (
            <button type="button" style={btn(false, busy)} disabled={busy} onClick={startOauth}>
              重新连接
            </button>
          ) : null}
          <button
            type="button"
            style={btn(false, busy)}
            disabled={busy}
            onClick={() => finish(async () => {
              await runAction(host, "activations.disconnect", { connection_id: connectionId }, false);
            })}
          >
            断开
          </button>
        </div>
      ) : method === "oauth2" ? (
        <button type="button" style={btn(true, busy)} disabled={busy} onClick={startOauth}>
          激活（OAuth2）
        </button>
      ) : method === "native_login" ? (
        <div>
          <input placeholder="业务账号" autoComplete="username" value={nativeUser} onChange={(e) => setNativeUser(e.target.value)} style={{ display: "block", width: "100%", marginTop: 6 }} />
          <input type="password" placeholder="密码（不保存）" autoComplete="current-password" value={nativePass} onChange={(e) => setNativePass(e.target.value)} style={{ display: "block", width: "100%", marginTop: 6 }} />
          <button
            type="button"
            style={btn(true, busy || !nativeUser || !nativePass)}
            disabled={busy || !nativeUser || !nativePass}
            onClick={() =>
              finish(async () => {
                await runAction(host, "activations.native", { connection_id: connectionId, username: nativeUser, password: nativePass }, false);
              })
            }
          >
            登录并激活
          </button>
        </div>
      ) : (
        <div>
          <input type="password" placeholder="个人访问令牌（不回显）" autoComplete="off" value={pat} onChange={(e) => setPat(e.target.value)} style={{ display: "block", width: "100%", marginTop: 6 }} />
          <button
            type="button"
            style={btn(true, busy || pat.length < 8)}
            disabled={busy || pat.length < 8}
            onClick={() =>
              finish(async () => {
                await runAction(host, "activations.pat", { connection_id: connectionId, access_token: pat }, false);
              })
            }
          >
            保存令牌并激活
          </button>
        </div>
      )}
    </div>
  );
}
