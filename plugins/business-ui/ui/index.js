// src/host.ts
function react() {
  return window.__OCTOP_REACT__;
}
var Fragment = Symbol.for("react.fragment");
function useCallback(callback, deps) {
  return react().useCallback(callback, deps);
}
function useEffect(effect, deps) {
  react().useEffect(effect, deps);
}
function useMemo(factory, deps) {
  return react().useMemo(factory, deps);
}
function useRef(initial) {
  return react().useRef(initial);
}
function useState(initial) {
  return react().useState(initial);
}

// src/api.ts
var PLUGIN = "business-ui";
function ctxOf(host2) {
  const t = host2.getToolContext() || { agentId: null, threadId: null, locale: "en", theme: "light" };
  const context = {};
  if (t.agentId) context.agent_id = t.agentId;
  if (t.threadId) context.thread_id = t.threadId;
  return Object.keys(context).length ? context : void 0;
}
async function runAction(host2, name, payload, withScope) {
  const body = { api_version: 1, payload: payload || {} };
  if (withScope) {
    const context = ctxOf(host2);
    if (context) body.context = context;
  }
  const res = await host2.request("/plugins/" + PLUGIN + "/actions/" + name, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  if (res && typeof res === "object" && "result" in res && res.result) return res.result;
  return res;
}

// src/styles.ts
function cardStyle(dark) {
  return {
    fontFamily: "ui-sans-serif, system-ui, sans-serif",
    width: "100%",
    maxWidth: "100%",
    boxSizing: "border-box",
    border: "1px solid var(--ant-color-border, " + (dark ? "#334155" : "#e2e8f0") + ")",
    borderRadius: 12,
    padding: 16,
    background: "var(--ant-color-bg-container, " + (dark ? "#0f172a" : "#fff") + ")",
    color: "var(--ant-color-text, " + (dark ? "#e2e8f0" : "#0f172a") + ")"
  };
}
function btn(primary, disabled = false) {
  return {
    marginRight: 8,
    marginTop: 8,
    padding: "6px 12px",
    borderRadius: 8,
    border: "1px solid var(--ant-color-primary, " + (primary ? "#2563eb" : "#94a3b8") + ")",
    background: primary ? "var(--ant-color-primary, #2563eb)" : "transparent",
    color: primary ? "var(--ant-color-text-light-solid, #fff)" : "inherit",
    cursor: disabled ? "not-allowed" : "pointer",
    opacity: disabled ? 0.55 : 1
  };
}
function tone(kind) {
  if (kind === "ok") return "var(--ant-color-success, #15803d)";
  if (kind === "warn") return "var(--ant-color-warning, #b45309)";
  if (kind === "err") return "var(--ant-color-error, #b91c1c)";
  return "var(--ant-color-text-secondary, #64748b)";
}

// host-react:react/jsx-runtime
var host = window.__OCTOP_JSX__;
var jsx = (...args) => host.jsx(...args);
var jsxs = (...args) => host.jsxs(...args);
var Fragment2 = window.__OCTOP_REACT__.Fragment;

// src/ActivationPanel.tsx
function methodLabel(method) {
  if (method === "native_login") return "\u4E1A\u52A1\u8D26\u53F7\u767B\u5F55";
  if (method === "personal_access_token") return "\u4E2A\u4EBA\u8BBF\u95EE\u4EE4\u724C";
  return "OAuth2 / OIDC";
}
function ActivationPanel(props) {
  const { host: host2, connection, onChanged } = props;
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
  const finish = async (job) => {
    setBusy(true);
    setError("");
    try {
      await job();
      setNativePass("");
      setPat("");
      await onChanged?.();
    } catch (err) {
      setError(String(err?.message || err));
    } finally {
      setBusy(false);
    }
  };
  const startOauth = () => finish(async () => {
    const started = await runAction(
      host2,
      "activations.start",
      { connection_id: connectionId },
      false
    );
    if (!started.authorization_url || !started.state) throw new Error("authorization_url missing");
    const popup = window.open(started.authorization_url, "bui-oauth", "width=480,height=720");
    const deadline = Date.now() + 5 * 60 * 1e3;
    while (Date.now() < deadline) {
      const done = await runAction(host2, "activations.complete", { state: started.state }, false);
      if (done && done.status === "active") {
        if (popup && !popup.closed) popup.close();
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, 1200));
    }
    throw new Error("activation timed out");
  });
  return /* @__PURE__ */ jsxs("div", { "data-activation-panel": "1", style: { marginTop: 8, fontSize: 12 }, children: [
    /* @__PURE__ */ jsxs("div", { children: [
      "\u7528\u6237\u6388\u6743\uFF1A",
      methodLabel(method),
      " \xB7 ",
      active ? "\u5DF2\u6FC0\u6D3B" : "\u9700\u8981\u6FC0\u6D3B/\u91CD\u65B0\u6FC0\u6D3B"
    ] }),
    error ? /* @__PURE__ */ jsx("div", { style: { color: tone("err"), marginTop: 4 }, children: error }) : null,
    active ? /* @__PURE__ */ jsxs("div", { children: [
      method === "oauth2" ? /* @__PURE__ */ jsx("button", { type: "button", style: btn(false, busy), disabled: busy, onClick: startOauth, children: "\u91CD\u65B0\u8FDE\u63A5" }) : null,
      /* @__PURE__ */ jsx(
        "button",
        {
          type: "button",
          style: btn(false, busy),
          disabled: busy,
          onClick: () => finish(async () => {
            await runAction(host2, "activations.disconnect", { connection_id: connectionId }, false);
          }),
          children: "\u65AD\u5F00"
        }
      )
    ] }) : method === "oauth2" ? /* @__PURE__ */ jsx("button", { type: "button", style: btn(true, busy), disabled: busy, onClick: startOauth, children: "\u6FC0\u6D3B\uFF08OAuth2\uFF09" }) : method === "native_login" ? /* @__PURE__ */ jsxs("div", { children: [
      /* @__PURE__ */ jsx("input", { placeholder: "\u4E1A\u52A1\u8D26\u53F7", autoComplete: "username", value: nativeUser, onChange: (e) => setNativeUser(e.target.value), style: { display: "block", width: "100%", marginTop: 6 } }),
      /* @__PURE__ */ jsx("input", { type: "password", placeholder: "\u5BC6\u7801\uFF08\u4E0D\u4FDD\u5B58\uFF09", autoComplete: "current-password", value: nativePass, onChange: (e) => setNativePass(e.target.value), style: { display: "block", width: "100%", marginTop: 6 } }),
      /* @__PURE__ */ jsx(
        "button",
        {
          type: "button",
          style: btn(true, busy || !nativeUser || !nativePass),
          disabled: busy || !nativeUser || !nativePass,
          onClick: () => finish(async () => {
            await runAction(host2, "activations.native", { connection_id: connectionId, username: nativeUser, password: nativePass }, false);
          }),
          children: "\u767B\u5F55\u5E76\u6FC0\u6D3B"
        }
      )
    ] }) : /* @__PURE__ */ jsxs("div", { children: [
      /* @__PURE__ */ jsx("input", { type: "password", placeholder: "\u4E2A\u4EBA\u8BBF\u95EE\u4EE4\u724C\uFF08\u4E0D\u56DE\u663E\uFF09", autoComplete: "off", value: pat, onChange: (e) => setPat(e.target.value), style: { display: "block", width: "100%", marginTop: 6 } }),
      /* @__PURE__ */ jsx(
        "button",
        {
          type: "button",
          style: btn(true, busy || pat.length < 8),
          disabled: busy || pat.length < 8,
          onClick: () => finish(async () => {
            await runAction(host2, "activations.pat", { connection_id: connectionId, access_token: pat }, false);
          }),
          children: "\u4FDD\u5B58\u4EE4\u724C\u5E76\u6FC0\u6D3B"
        }
      )
    ] })
  ] });
}

// src/receipt.ts
var SENSITIVE = /* @__PURE__ */ new Set([
  "password",
  "secret",
  "token",
  "access_token",
  "refresh_token",
  "client_secret",
  "ssn",
  "id_card",
  "bank_account"
]);
function object(value) {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}
function str(value, fallback = "") {
  return typeof value === "string" ? value : fallback;
}
function num(value, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}
function maskSensitive(value) {
  if (Array.isArray(value)) return value.map(maskSensitive);
  if (!object(value)) return value;
  const out = {};
  for (const [key, item] of Object.entries(value)) {
    const lower = key.toLowerCase();
    if (SENSITIVE.has(lower) || lower.endsWith("_secret") || lower.endsWith("_token")) {
      const text = String(item ?? "");
      out[key] = text.length <= 4 ? "****" : `${text.slice(0, 2)}****${text.slice(-2)}`;
    } else {
      out[key] = maskSensitive(item);
    }
  }
  return out;
}
function parseResult(raw) {
  if (!object(raw)) return null;
  const type = str(raw.type).toUpperCase();
  if (type !== "SUCCESS" && type !== "BUSINESS_REJECTED" && type !== "TECHNICAL_ERROR") return null;
  let status = str(raw.status).toUpperCase();
  if (type === "TECHNICAL_ERROR") {
    if (status !== "FAILED" && status !== "UNKNOWN") status = "UNKNOWN";
  } else {
    status = type;
  }
  const code = raw.code == null ? null : str(raw.code);
  const disclosable = raw.disclosable !== false && !(code && code.startsWith("INTERNAL_"));
  const message = disclosable && typeof raw.message === "string" ? raw.message.slice(0, 2e3) : null;
  const sideEffect = typeof raw.side_effect === "boolean" ? raw.side_effect : typeof raw.sideEffect === "boolean" ? raw.sideEffect : null;
  let safeRetry = Boolean(raw.safe_retry ?? raw.safeRetry);
  const idempotent = Boolean(raw.idempotent);
  if (type !== "TECHNICAL_ERROR" || status !== "FAILED" || sideEffect === true) safeRetry = false;
  safeRetry = Boolean(safeRetry && (idempotent || sideEffect === false));
  return {
    type,
    status,
    code,
    message,
    disclosable: Boolean(disclosable && message),
    safe_retry: safeRetry,
    idempotent,
    side_effect: sideEffect
  };
}
function normalizeActions(actions) {
  const out = [];
  const seen = /* @__PURE__ */ new Set();
  if (!Array.isArray(actions)) return out;
  for (const item of actions) {
    let name = str(item);
    if (name === "queryStatus") name = "query_status";
    if (name === "requestPermission") name = "request_permission";
    if (name === "view_detail") name = "view_document";
    if (!name || seen.has(name)) continue;
    seen.add(name);
    out.push(name);
  }
  return out;
}
function buttonsFor(state) {
  const result = state.result;
  const allowed = new Set(normalizeActions(state.allowedActions));
  const take = (...names) => names.filter((name) => allowed.has(name));
  if (!result) return take("edit", "save", "submit", "cancel", "close");
  if (result.type === "SUCCESS") {
    return [...state.recordId ? take("view_document") : [], ...take("continue", "close")];
  }
  if (result.type === "BUSINESS_REJECTED") {
    return [
      ...state.recordId ? take("view_document") : [],
      ...take("request_permission", "continue", "close")
    ];
  }
  if (result.status === "UNKNOWN") return take("query_status", "close");
  return [...result.safe_retry ? take("retry") : [], ...take("close")];
}
function eventFor(result, resolved = false) {
  if (!result) return null;
  if (resolved) return "BUSINESS_OPERATION_RESOLVED";
  if (result.type === "SUCCESS") return "BUSINESS_OPERATION_SUCCESS";
  if (result.type === "BUSINESS_REJECTED") return "BUSINESS_OPERATION_REJECTED";
  return "BUSINESS_OPERATION_ERROR";
}
function isStale(current, incoming) {
  if (incoming.recordVersion < current.recordVersion) return true;
  return incoming.recordVersion === current.recordVersion && incoming.receiptSequence < current.receiptSequence;
}
function pick(raw, camel, snake) {
  return raw[camel] ?? raw[snake];
}
function parseCardState(raw, fallback = {}) {
  const data = object(raw) ? raw : {};
  const result = parseResult(pick(data, "result", "result"));
  const recordIdValue = pick(data, "recordId", "record_id");
  const state = {
    documentType: str(pick(data, "documentType", "document_type"), fallback.documentType || "generic_request"),
    recordId: recordIdValue == null || recordIdValue === "" ? null : str(recordIdValue),
    formRef: str(pick(data, "formRef", "form_ref"), fallback.formRef || "generic.request.edit"),
    schemaVersion: str(pick(data, "schemaVersion", "schema_version"), fallback.schemaVersion || "1"),
    recordVersion: num(pick(data, "recordVersion", "record_version"), fallback.recordVersion || 0),
    allowedActions: normalizeActions(pick(data, "allowedActions", "allowed_actions") ?? fallback.allowedActions),
    interactionId: (() => {
      const value = pick(data, "interactionId", "interaction_id");
      return value ? str(value) : fallback.interactionId || null;
    })(),
    submissionStatus: str(
      pick(data, "submissionStatus", "submission_status"),
      fallback.submissionStatus || "unclaimed"
    ),
    approvalStatus: str(
      pick(data, "approvalStatus", "approval_status"),
      fallback.approvalStatus || "not_applicable"
    ),
    summary: maskSensitive(
      object(pick(data, "summary", "summary")) ? pick(data, "summary", "summary") : fallback.summary || {}
    ) || {},
    operationId: (() => {
      const value = pick(data, "operationId", "operation_id") ?? pick(data, "lastOperationId", "last_operation_id");
      return value ? str(value) : fallback.operationId || null;
    })(),
    result,
    navigation: object(pick(data, "navigation", "navigation")) ? pick(data, "navigation", "navigation") : fallback.navigation || null,
    event: str(pick(data, "event", "event")) || eventFor(result),
    receiptSequence: num(pick(data, "receiptSequence", "receipt_sequence"), fallback.receiptSequence || 0),
    claimRequired: Boolean(pick(data, "claimRequired", "claim_required") ?? fallback.claimRequired ?? true),
    connectionId: (() => {
      const value = pick(data, "connectionId", "connection_id");
      return value ? str(value) : fallback.connectionId || null;
    })(),
    lastError: pick(data, "lastError", "last_error") ? str(pick(data, "lastError", "last_error")) : null
  };
  if (result) state.allowedActions = buttonsFor(state);
  return state;
}
function applyEvent(state, event) {
  if (event === "DOCUMENT_VIEW_REQUESTED") return { ...state, event };
  return { ...state, event };
}
function shouldShowRecordId(state) {
  if (!state.recordId) return false;
  if (state.result?.type === "BUSINESS_REJECTED" && !state.recordId) return false;
  return true;
}

// src/BusinessReceiptCard.tsx
var LABELS = {
  view_document: "\u67E5\u770B\u6B63\u5F0F\u5355\u636E",
  continue: "\u7EE7\u7EED",
  request_permission: "\u7533\u8BF7\u6743\u9650",
  retry: "\u5B89\u5168\u91CD\u8BD5",
  query_status: "\u67E5\u8BE2\u72B6\u6001",
  close: "\u5173\u95ED"
};
function headline(state) {
  const type = state.result?.type;
  const status = state.result?.status;
  if (type === "SUCCESS") return { title: "\u5DF2\u6210\u529F", color: tone("ok") };
  if (type === "BUSINESS_REJECTED") return { title: "\u4E1A\u52A1\u5DF2\u62D2\u7EDD", color: tone("warn") };
  if (type === "TECHNICAL_ERROR" && status === "UNKNOWN") {
    return { title: "\u7ED3\u679C\u672A\u77E5\uFF08\u8BF7\u67E5\u8BE2\uFF0C\u52FF\u91CD\u590D\u63D0\u4EA4\uFF09", color: tone("warn") };
  }
  if (type === "TECHNICAL_ERROR") return { title: "\u6280\u672F\u5931\u8D25", color: tone("err") };
  return { title: "\u5904\u7406\u4E2D", color: tone("muted") };
}
function BusinessReceiptCard(props) {
  const { state, onAction, busy } = props;
  const [expanded, setExpanded] = useState(false);
  const head = headline(state);
  const message = state.result?.disclosable ? state.result?.message : null;
  const long = Boolean(message && message.length > 160);
  const shown = message && long && !expanded ? message.slice(0, 160) + "\u2026" : message;
  return /* @__PURE__ */ jsxs("div", { "data-business-receipt-card": "1", style: { marginTop: 10 }, children: [
    /* @__PURE__ */ jsx("div", { style: { fontWeight: 700, color: head.color }, children: head.title }),
    state.result?.code && state.result.disclosable ? /* @__PURE__ */ jsxs("div", { style: { fontSize: 12, marginTop: 4, color: tone("muted") }, children: [
      "\u539F\u56E0\u4EE3\u7801 ",
      state.result.code
    ] }) : null,
    shouldShowRecordId(state) ? /* @__PURE__ */ jsxs("div", { style: { fontSize: 12, marginTop: 4 }, children: [
      "\u5355\u53F7 ",
      state.recordId
    ] }) : null,
    state.operationId ? /* @__PURE__ */ jsxs("div", { style: { fontSize: 12, color: tone("muted") }, children: [
      "operationId ",
      state.operationId
    ] }) : null,
    shown ? /* @__PURE__ */ jsxs("div", { style: { fontSize: 12, marginTop: 8, whiteSpace: "pre-wrap" }, children: [
      shown,
      long ? /* @__PURE__ */ jsx("button", { type: "button", style: btn(false), onClick: () => setExpanded(!expanded), children: expanded ? "\u6536\u8D77" : "\u5C55\u5F00" }) : null
    ] }) : null,
    /* @__PURE__ */ jsx("div", { children: state.allowedActions.map(
      (name) => LABELS[name] ? /* @__PURE__ */ jsx(
        "button",
        {
          type: "button",
          "data-receipt-action": name,
          style: btn(name === "view_document" || name === "query_status" || name === "retry", busy),
          disabled: busy,
          onClick: () => onAction(name),
          children: LABELS[name]
        },
        name
      ) : null
    ) })
  ] });
}

// src/FormFrame.tsx
function FormFrame(props) {
  const { redeemUrl, ticket, nonce, origin, interactionId, onHint } = props;
  const iframeRef = useRef(null);
  const formRef = useRef(null);
  useEffect(() => {
    formRef.current?.submit();
  }, [ticket, redeemUrl]);
  useEffect(() => {
    function onMsg(ev) {
      if (ev.origin !== origin) return;
      if (!iframeRef.current || ev.source !== iframeRef.current.contentWindow) return;
      const data = ev.data || {};
      if (data.type !== "business-ui/hint") return;
      if (data.interactionId !== interactionId) return;
      if (data.nonce && data.nonce !== nonce) return;
      onHint(data);
    }
    window.addEventListener("message", onMsg);
    return () => window.removeEventListener("message", onMsg);
  }, [origin, interactionId, nonce, onHint]);
  return /* @__PURE__ */ jsxs("div", { style: { height: "100%", minHeight: 360, width: "100%" }, children: [
    /* @__PURE__ */ jsxs("form", { ref: formRef, method: "POST", action: redeemUrl, target: "bui-frame-" + interactionId, style: { display: "none" }, children: [
      /* @__PURE__ */ jsx("input", { type: "hidden", name: "ticket", value: ticket }),
      /* @__PURE__ */ jsx("input", { type: "hidden", name: "nonce", value: nonce })
    ] }),
    /* @__PURE__ */ jsx(
      "iframe",
      {
        ref: iframeRef,
        name: "bui-frame-" + interactionId,
        title: "Business form",
        sandbox: "allow-scripts allow-forms allow-same-origin",
        style: { width: "100%", height: 420, border: 0, background: "#fff" }
      }
    )
  ] });
}

// src/BusinessCard.tsx
function BusinessCard(props) {
  const dark = (props.host.getToolContext() || {}).theme === "dark";
  const data = props.data && typeof props.data === "object" ? props.data : {};
  const callId = props.callId || "";
  const host2 = props.host;
  const [state, setState] = useState(() => parseCardState(data));
  const [error, setError] = useState("");
  const [ticket, setTicket] = useState(null);
  const [embedAction, setEmbedAction] = useState(null);
  const [pageMode, setPageMode] = useState("edit");
  const [connections, setConnections] = useState([]);
  const [connectionId, setConnectionId] = useState(String(data.connectionId || data.connection_id || ""));
  const [busy, setBusy] = useState(false);
  const pollRef = useRef(null);
  const seqRef = useRef({ recordVersion: state.recordVersion, receiptSequence: state.receiptSequence });
  const selected = useMemo(
    () => connections.find((row) => row.connection_id === connectionId) || null,
    [connections, connectionId]
  );
  const activated = Boolean(selected && selected.activation_status === "active");
  const inSidePanel = props.presentation?.location === "side-panel" && props.presentation.active;
  const patchSafe = (next, extra = {}) => {
    if (!callId) return;
    try {
      host2.patchResult(callId, {
        ...data,
        ...extra,
        documentType: next.documentType,
        recordId: next.recordId,
        formRef: next.formRef,
        schemaVersion: next.schemaVersion,
        recordVersion: next.recordVersion,
        allowedActions: next.allowedActions,
        interactionId: next.interactionId,
        submissionStatus: next.submissionStatus,
        approvalStatus: next.approvalStatus,
        summary: next.summary,
        operationId: next.operationId,
        result: next.result,
        navigation: next.navigation,
        event: next.event,
        claimRequired: false
      });
    } catch {
    }
  };
  const applyRemote = useCallback(
    (raw) => {
      const next = parseCardState(raw, state);
      if (state.interactionId && next.interactionId === state.interactionId && isStale(seqRef.current, { recordVersion: next.recordVersion, receiptSequence: next.receiptSequence })) {
        return next;
      }
      seqRef.current = { recordVersion: next.recordVersion, receiptSequence: next.receiptSequence };
      setState(next);
      patchSafe(next);
      return next;
    },
    [state, callId]
  );
  const reloadConnections = useCallback(async () => {
    const res = await runAction(host2, "connections.list", {}, false);
    const rows = res.connections || [];
    setConnections(rows);
    return rows;
  }, [host2]);
  useEffect(() => {
    reloadConnections().then((rows) => {
      if (!connectionId && rows[0]) setConnectionId(String(rows[0].connection_id || ""));
    }).catch(() => {
    });
  }, [host2]);
  useEffect(() => {
    if (!callId) return;
    runAction(host2, "interactions.lookup", { call_id: callId }, true).then((raw) => applyRemote(raw)).catch(() => {
    });
  }, [callId, host2]);
  const stopPoll = () => {
    if (pollRef.current) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };
  const hydrate = async (interactionId) => {
    if (!interactionId || !callId) return null;
    try {
      const next = await runAction(host2, "interactions.get", { interaction_id: interactionId, call_id: callId }, true);
      return applyRemote(next);
    } catch (err) {
      setError(String(err?.message || err));
      return null;
    }
  };
  const openTicket = async (action, interactionId) => {
    const issued = await runAction(
      host2,
      "tickets.issue",
      { interaction_id: interactionId, call_id: callId, action },
      true
    );
    setTicket(issued);
    setPageMode(issued.page_mode === "readonly" ? "readonly" : "edit");
    setEmbedAction(action);
    host2.openSidePanel({ callId, title: action === "view_document" || action === "view_detail" ? "\u6B63\u5F0F\u5355\u636E" : "Business form" });
  };
  const claimAndOpen = async (action) => {
    setError("");
    if (!connectionId) {
      setError("Select an approved connection");
      return;
    }
    if (!activated) {
      setError("\u9700\u8981\u6FC0\u6D3B/\u91CD\u65B0\u6FC0\u6D3B");
      return;
    }
    try {
      const claimed = await runAction(
        host2,
        "interactions.claim",
        {
          call_id: callId,
          connection_id: connectionId,
          document_type: state.documentType,
          form_ref: state.formRef,
          schema_version: state.schemaVersion,
          record_id: state.recordId,
          record_version: state.recordVersion,
          summary: state.summary
        },
        true
      );
      const next = applyRemote(claimed);
      await openTicket(action, String(next.interactionId));
    } catch (err) {
      setError(String(err?.message || err));
    }
  };
  const onReceiptAction = async (name) => {
    if (!state.interactionId || !callId) return;
    setBusy(true);
    setError("");
    try {
      if (name === "view_document") {
        const next = applyEvent(state, "DOCUMENT_VIEW_REQUESTED");
        setState(next);
        patchSafe(next, { event: "DOCUMENT_VIEW_REQUESTED" });
        await openTicket("view_document", state.interactionId);
        return;
      }
      if (name === "query_status" && state.operationId) {
        const raw = await runAction(
          host2,
          "interactions.query_status",
          { interaction_id: state.interactionId, call_id: callId, operation_id: state.operationId },
          true
        );
        applyRemote(raw);
        return;
      }
      if (name === "retry") {
        const raw = await runAction(host2, "interactions.retry", { interaction_id: state.interactionId, call_id: callId }, true);
        applyRemote(raw);
        return;
      }
      if (name === "close") {
        host2.closeSidePanel(callId);
        return;
      }
      if (name === "continue" || name === "request_permission") {
        return;
      }
    } catch (err) {
      setError(String(err?.message || err));
    } finally {
      setBusy(false);
    }
  };
  const onHint = useCallback(
    (_hint) => {
      if (!state.interactionId) return;
      stopPoll();
      pollRef.current = window.setInterval(() => {
        hydrate(state.interactionId);
      }, 1500);
      hydrate(state.interactionId).then((next) => {
        if (!next?.result) return;
        stopPoll();
        if (next.result.type === "SUCCESS" && inSidePanel && pageMode === "edit" && next.recordId) {
          openTicket("view_document", next.interactionId).catch(() => {
          });
        }
      });
    },
    [state.interactionId, inSidePanel, pageMode]
  );
  useEffect(() => () => stopPoll(), []);
  const cancelled = state.submissionStatus === "cancelled";
  const showReceipt = Boolean(state.result);
  return /* @__PURE__ */ jsxs("div", { style: cardStyle(dark), "data-business-ui-card": "1", children: [
    /* @__PURE__ */ jsx("div", { style: { fontWeight: 700, fontSize: 16 }, children: String(state.summary.title || "\u4E1A\u52A1\u5355\u636E") }),
    /* @__PURE__ */ jsx("div", { style: { opacity: 0.8, marginTop: 6, fontSize: 13 }, children: String(state.summary.body || props.textFallback || "") }),
    error ? /* @__PURE__ */ jsx("div", { style: { color: tone("err"), fontSize: 12, marginTop: 8 }, children: error }) : null,
    showReceipt ? /* @__PURE__ */ jsx(BusinessReceiptCard, { state, dark, busy, onAction: onReceiptAction }) : null,
    !showReceipt && !cancelled ? /* @__PURE__ */ jsxs("div", { children: [
      /* @__PURE__ */ jsxs("select", { value: connectionId, onChange: (ev) => setConnectionId(ev.target.value), style: { marginTop: 8, padding: 4 }, children: [
        /* @__PURE__ */ jsx("option", { value: "", children: "\u9009\u62E9\u5DF2\u6279\u51C6\u8FDE\u63A5" }),
        connections.map((row) => /* @__PURE__ */ jsx("option", { value: String(row.connection_id), children: String(row.display_name) }, String(row.connection_id)))
      ] }),
      /* @__PURE__ */ jsx(ActivationPanel, { host: host2, connection: selected, onChanged: reloadConnections }),
      activated ? /* @__PURE__ */ jsx("button", { type: "button", style: btn(true), onClick: () => claimAndOpen("edit"), children: "\u6838\u5BF9\u5E76\u7F16\u8F91" }) : /* @__PURE__ */ jsx("div", { style: { color: tone("warn"), fontSize: 12, marginTop: 8 }, children: "\u9700\u8981\u6FC0\u6D3B/\u91CD\u65B0\u6FC0\u6D3B\u540E\u624D\u80FD\u6253\u5F00\u8868\u5355\u3002" }),
      /* @__PURE__ */ jsx(
        "button",
        {
          type: "button",
          style: btn(false),
          onClick: async () => {
            if (!state.interactionId) {
              const next = { ...state, submissionStatus: "cancelled", allowedActions: [] };
              setState(next);
              patchSafe(next);
              return;
            }
            const raw = await runAction(host2, "interactions.cancel", { interaction_id: state.interactionId, call_id: callId }, true);
            applyRemote(raw);
          },
          children: "\u53D6\u6D88"
        }
      )
    ] }) : null,
    ticket && state.interactionId ? /* @__PURE__ */ jsx(
      FormFrame,
      {
        redeemUrl: ticket.redeem_url,
        ticket: ticket.ticket,
        nonce: ticket.nonce,
        origin: ticket.form_origin,
        interactionId: state.interactionId,
        onHint
      }
    ) : null
  ] });
}

// src/ConfigCard.tsx
var emptyForm = {
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
  oauth_scopes: "openid profile"
};
function ConfigCard(props) {
  const dark = (props.host.getToolContext() || {}).theme === "dark";
  const host2 = props.host;
  const [rows, setRows] = useState([]);
  const [canManage, setCanManage] = useState(false);
  const [issuer, setIssuer] = useState("");
  const [error, setError] = useState("");
  const [test, setTest] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const reload = async () => {
    const res = await runAction(host2, "connections.list", {}, false);
    setRows(res.connections || []);
    setCanManage(!!res.can_manage);
    setIssuer(res.instance_issuer || "");
    setError(res.env_sync_error ? String(res.env_sync_error) : "");
  };
  useEffect(() => {
    reload().catch((err) => setError(String(err?.message || err)));
  }, [host2]);
  const save = async () => {
    setError("");
    const payload = {
      display_name: form.display_name,
      base_url: form.base_url,
      auth_method: form.auth_method,
      extra_origins: form.extra_origins ? form.extra_origins.split(/\s+/).filter(Boolean) : [],
      private_allow: form.private_allow ? form.private_allow.split(/\s+/).filter(Boolean) : [],
      instance_issuer: form.instance_issuer || void 0,
      enabled: form.enabled,
      user_auth_method: form.user_auth_method,
      oauth_discovery_url: form.oauth_discovery_url || void 0,
      oauth_authorize_url: form.oauth_authorize_url || void 0,
      oauth_token_url: form.oauth_token_url || void 0,
      oauth_revoke_url: form.oauth_revoke_url || void 0,
      oauth_client_id: form.oauth_client_id || void 0,
      oauth_scopes: form.oauth_scopes || void 0
    };
    if (form.secret) payload.secret = form.secret;
    if (form.tls_ca_pem) payload.tls_ca_pem = form.tls_ca_pem;
    if (form.oauth_client_secret) payload.oauth_client_secret = form.oauth_client_secret;
    try {
      await runAction(host2, "connections.save", payload, false);
      setForm((prev) => ({ ...prev, secret: "", oauth_client_secret: "" }));
      await reload();
    } catch (err) {
      setError(String(err?.message || err));
    }
  };
  return /* @__PURE__ */ jsxs("div", { style: cardStyle(dark), "data-business-ui-config": "1", children: [
    /* @__PURE__ */ jsx("div", { style: { fontWeight: 700 }, children: "Business UI \u8FDE\u63A5" }),
    /* @__PURE__ */ jsx("div", { style: { fontSize: 12, opacity: 0.8, marginTop: 4 }, children: "\u8FDE\u63A5\u5BC6\u94A5\u4E0E\u7528\u6237\u4EE4\u724C\u53EA\u7ECF\u5DF2\u8BA4\u8BC1 action \u5199\u5165 Host \u51ED\u636E\u3002\u6BCF\u4F4D\u7528\u6237\u5355\u72EC\u6FC0\u6D3B\u3002\u591A\u5B9E\u4F8B\u90E8\u7F72\u7528\u5168\u5C40 BUSINESS_UI_*\uFF08\u5BC6\u94A5\u53EA\u7528 *_FILE\uFF09\uFF0C\u4E0D\u5FC5\u5728\u804A\u5929\u91CC\u586B\uFF1B\u73AF\u5883\u53D8\u91CF\u9875\u6CA1\u6709 Test \u6309\u94AE\uFF0C\u8BF7\u7528 python -m business_ui test\u3002" }),
    issuer ? /* @__PURE__ */ jsxs("div", { style: { fontSize: 12, marginTop: 6 }, children: [
      "\u5B9E\u4F8B issuer\uFF1A",
      issuer
    ] }) : null,
    error ? /* @__PURE__ */ jsx("div", { style: { color: tone("err"), fontSize: 12 }, children: error }) : null,
    rows.map((row) => {
      const envManaged = row.managed_by === "env";
      return /* @__PURE__ */ jsxs("div", { style: { marginTop: 10, paddingTop: 8, borderTop: "1px solid var(--ant-color-border, #e2e8f0)", fontSize: 13 }, children: [
        /* @__PURE__ */ jsx("strong", { children: String(row.display_name) }),
        /* @__PURE__ */ jsxs("div", { children: [
          String(row.base_url),
          " \xB7 \u670D\u52A1\u8EAB\u4EFD ",
          String(row.auth_method),
          " \xB7 \u7528\u6237\u6388\u6743 ",
          methodLabel(String(row.user_auth_method)),
          row.enabled ? " \xB7 \u542F\u7528" : " \xB7 \u505C\u7528",
          envManaged ? " \xB7 \u73AF\u5883\u53D8\u91CF\u7BA1\u7406" : ""
        ] }),
        envManaged ? /* @__PURE__ */ jsx("div", { style: { fontSize: 12, marginTop: 4, opacity: 0.8 }, children: "\u7531\u5168\u5C40 BUSINESS_UI_* \u7BA1\u7406\uFF0C\u804A\u5929\u91CC\u4E0D\u80FD\u6539 URL/\u6388\u6743\u65B9\u5F0F\u3002\u6BCF\u4F4D\u7528\u6237\u4ECD\u9700\u5355\u72EC\u6FC0\u6D3B\u3002" }) : null,
        /* @__PURE__ */ jsx(ActivationPanel, { host: host2, connection: row, onChanged: reload }),
        canManage ? /* @__PURE__ */ jsxs("div", { children: [
          /* @__PURE__ */ jsx(
            "button",
            {
              type: "button",
              style: btn(false),
              onClick: async () => setTest(await runAction(host2, "connections.test", { connection_id: row.connection_id }, false)),
              children: "Test Connection"
            }
          ),
          envManaged ? null : /* @__PURE__ */ jsx(
            "button",
            {
              type: "button",
              style: btn(false),
              onClick: async () => {
                await runAction(host2, "connections.delete", { connection_id: row.connection_id }, false);
                await reload();
              },
              children: "\u5220\u9664"
            }
          )
        ] }) : null
      ] }, String(row.connection_id));
    }),
    canManage ? /* @__PURE__ */ jsxs("div", { style: { marginTop: 12 }, children: [
      /* @__PURE__ */ jsx("input", { placeholder: "\u663E\u793A\u540D", value: form.display_name, onChange: (e) => setForm({ ...form, display_name: e.target.value }), style: { display: "block", width: "100%", marginTop: 6 } }),
      /* @__PURE__ */ jsx("input", { placeholder: "HTTPS Adapter \u5730\u5740", value: form.base_url, onChange: (e) => setForm({ ...form, base_url: e.target.value }), style: { display: "block", width: "100%", marginTop: 6 } }),
      /* @__PURE__ */ jsx("input", { placeholder: "\u672C\u5B9E\u4F8B issuer https://octop.example.com", value: form.instance_issuer, onChange: (e) => setForm({ ...form, instance_issuer: e.target.value }), style: { display: "block", width: "100%", marginTop: 6 } }),
      /* @__PURE__ */ jsxs("select", { value: form.auth_method, onChange: (e) => setForm({ ...form, auth_method: e.target.value }), style: { marginTop: 6 }, children: [
        /* @__PURE__ */ jsx("option", { value: "api_token", children: "\u670D\u52A1\u8EAB\u4EFD\uFF1A\u53EF\u590D\u7528 API token" }),
        /* @__PURE__ */ jsx("option", { value: "authorization_code", children: "\u670D\u52A1\u8EAB\u4EFD\uFF1A\u4E00\u6B21\u6027\u6388\u6743\u7801" })
      ] }),
      /* @__PURE__ */ jsx("input", { type: "password", autoComplete: "new-password", placeholder: "\u670D\u52A1\u5BC6\u94A5 / \u6388\u6743\u7801\uFF08\u4E0D\u56DE\u663E\uFF09", value: form.secret, onChange: (e) => setForm({ ...form, secret: e.target.value }), style: { display: "block", width: "100%", marginTop: 6 } }),
      /* @__PURE__ */ jsxs("select", { value: form.user_auth_method, onChange: (e) => setForm({ ...form, user_auth_method: e.target.value }), style: { marginTop: 6, display: "block" }, children: [
        /* @__PURE__ */ jsx("option", { value: "oauth2", children: "\u7528\u6237\u6388\u6743\uFF1A\u6807\u51C6 OAuth2/OIDC + PKCE" }),
        /* @__PURE__ */ jsx("option", { value: "native_login", children: "\u7528\u6237\u6388\u6743\uFF1A\u4E1A\u52A1\u7CFB\u7EDF\u8D26\u53F7\u767B\u5F55" }),
        /* @__PURE__ */ jsx("option", { value: "personal_access_token", children: "\u7528\u6237\u6388\u6743\uFF1A\u4E2A\u4EBA\u8BBF\u95EE\u4EE4\u724C" })
      ] }),
      form.user_auth_method === "oauth2" ? /* @__PURE__ */ jsxs("div", { children: [
        /* @__PURE__ */ jsx("input", { placeholder: "OAuth discovery URL\uFF08\u53EF\u9009 RFC 8414\uFF09", value: form.oauth_discovery_url, onChange: (e) => setForm({ ...form, oauth_discovery_url: e.target.value }), style: { display: "block", width: "100%", marginTop: 6 } }),
        /* @__PURE__ */ jsx("input", { placeholder: "Authorize URL\uFF08\u65E0 discovery \u65F6\u5FC5\u586B\uFF09", value: form.oauth_authorize_url, onChange: (e) => setForm({ ...form, oauth_authorize_url: e.target.value }), style: { display: "block", width: "100%", marginTop: 6 } }),
        /* @__PURE__ */ jsx("input", { placeholder: "Token URL\uFF08\u65E0 discovery \u65F6\u5FC5\u586B\uFF09", value: form.oauth_token_url, onChange: (e) => setForm({ ...form, oauth_token_url: e.target.value }), style: { display: "block", width: "100%", marginTop: 6 } }),
        /* @__PURE__ */ jsx("input", { placeholder: "Revocation URL\uFF08\u53EF\u9009\uFF09", value: form.oauth_revoke_url, onChange: (e) => setForm({ ...form, oauth_revoke_url: e.target.value }), style: { display: "block", width: "100%", marginTop: 6 } }),
        /* @__PURE__ */ jsx("input", { placeholder: "OAuth client id", value: form.oauth_client_id, onChange: (e) => setForm({ ...form, oauth_client_id: e.target.value }), style: { display: "block", width: "100%", marginTop: 6 } }),
        /* @__PURE__ */ jsx("input", { type: "password", autoComplete: "new-password", placeholder: "OAuth client secret\uFF08\u4E0D\u56DE\u663E\uFF09", value: form.oauth_client_secret, onChange: (e) => setForm({ ...form, oauth_client_secret: e.target.value }), style: { display: "block", width: "100%", marginTop: 6 } }),
        /* @__PURE__ */ jsx("input", { placeholder: "scopes", value: form.oauth_scopes, onChange: (e) => setForm({ ...form, oauth_scopes: e.target.value }), style: { display: "block", width: "100%", marginTop: 6 } })
      ] }) : /* @__PURE__ */ jsx("div", { style: { fontSize: 12, marginTop: 6, opacity: 0.8 }, children: form.user_auth_method === "native_login" ? "\u7528\u6237\u5728\u63D2\u4EF6\u8868\u5355\u8F93\u5165\u4E1A\u52A1\u8D26\u53F7\uFF1B\u5BC6\u7801\u53EA\u7ECF action \u4EA4\u7ED9 Adapter\uFF0C\u63D2\u4EF6\u4E0D\u843D\u76D8\u3002" : "\u7528\u6237\u5728\u63D2\u4EF6\u8868\u5355\u7C98\u8D34\u4E2A\u4EBA\u8BBF\u95EE\u4EE4\u724C\uFF1B\u4EE4\u724C\u5199\u5165 Host \u51ED\u636E\uFF0C\u4E0D\u8FDB URL/\u804A\u5929\u3002" }),
      /* @__PURE__ */ jsx("textarea", { placeholder: "\u53EF\u9009\uFF1A\u5185\u7F51\u9002\u914D\u5668 TLS CA PEM", value: form.tls_ca_pem, onChange: (e) => setForm({ ...form, tls_ca_pem: e.target.value }), style: { display: "block", width: "100%", marginTop: 6, minHeight: 64 } }),
      /* @__PURE__ */ jsx("input", { placeholder: "\u989D\u5916 origin\uFF08\u7A7A\u683C\u5206\u9694\uFF09", value: form.extra_origins, onChange: (e) => setForm({ ...form, extra_origins: e.target.value }), style: { display: "block", width: "100%", marginTop: 6 } }),
      /* @__PURE__ */ jsx("input", { placeholder: "\u79C1\u6709\u7F51\u6BB5\u4F8B\u5916 CIDR/host", value: form.private_allow, onChange: (e) => setForm({ ...form, private_allow: e.target.value }), style: { display: "block", width: "100%", marginTop: 6 } }),
      /* @__PURE__ */ jsx("button", { type: "button", style: btn(true), onClick: () => save(), children: "\u4FDD\u5B58\u8FDE\u63A5" })
    ] }) : /* @__PURE__ */ jsx("div", { style: { fontSize: 12, marginTop: 8 }, children: "\u4EC5\u7BA1\u7406\u5458\u53EF\u65B0\u589E\u8FDE\u63A5\u3002\u89D2\u8272\u7531 Host JWT \u5224\u5B9A\u3002" }),
    test ? /* @__PURE__ */ jsxs("div", { style: { marginTop: 12, fontSize: 12 }, "data-connection-test": "1", children: [
      /* @__PURE__ */ jsxs("div", { children: [
        "Test ",
        test.ok ? "\u672A\u5B8C\u5168\u7B49\u540C\u6D4F\u89C8\u5668\u5D4C\u5165" : "\u5931\u8D25",
        " \xB7 ",
        String(test.unsupported_reason || test.protocol || "")
      ] }),
      Array.isArray(test.stages) ? test.stages.map((s) => /* @__PURE__ */ jsxs("div", { children: [
        s.ok ? "\u2713" : "\u2717",
        " ",
        s.name,
        " \u2014 ",
        s.detail
      ] }, s.name)) : null
    ] }) : null,
    /* @__PURE__ */ jsx("div", { style: { fontSize: 11, marginTop: 10, opacity: 0.7 }, children: "UNSUPPORTED\uFF1AOctop \u767B\u51FA\u4E0D\u4F1A\u7ACB\u5373\u4F5C\u5E9F\u5DF2\u5151\u4E1A\u52A1\u4F1A\u8BDD\u3002\u6D4F\u89C8\u5668\u7B2C\u4E09\u65B9\u5B58\u50A8\u9700\u5B9E\u6D4B\uFF0CPOST \u5151\u7968\u4E0D\u80FD\u4FDD\u8BC1 cookie\u3002" })
  ] });
}

// src/index.ts
function setup(host2) {
  host2.registerRenderer({
    id: "business_ui_card",
    tools: ["business_ui_draft"],
    component: BusinessCard
  });
  host2.registerRenderer({
    id: "business_ui_config",
    tools: ["business_ui_connections"],
    component: ConfigCard
  });
}
export {
  setup
};
