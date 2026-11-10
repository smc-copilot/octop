const React = window.__OCTOP_REACT__;
const { jsx: _jsx, jsxs: _jsxs } = window.__OCTOP_JSX__;
const { useCallback, useEffect, useMemo, useRef, useState } = React;

const PLUGIN = "business-ui";

function ctxOf(host) {
  const t = host.getToolContext() || {};
  const context = {};
  if (t.agentId) context.agent_id = t.agentId;
  if (t.threadId) context.thread_id = t.threadId;
  return Object.keys(context).length ? context : undefined;
}

async function runAction(host, name, payload, withScope) {
  const body = { api_version: 1, payload: payload || {} };
  if (withScope) {
    const context = ctxOf(host);
    if (context) body.context = context;
  }
  const res = await host.request("/plugins/" + PLUGIN + "/actions/" + name, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (res && res.result) return res.result;
  return res;
}

function cardStyle(dark) {
  return {
    fontFamily: "ui-sans-serif, system-ui, sans-serif",
    maxWidth: 560,
    border: "1px solid " + (dark ? "#334155" : "#e2e8f0"),
    borderRadius: 12,
    padding: 16,
    background: dark ? "#0f172a" : "#fff",
    color: dark ? "#e2e8f0" : "#0f172a",
  };
}

function btn(primary) {
  return {
    marginRight: 8,
    marginTop: 8,
    padding: "6px 12px",
    borderRadius: 8,
    border: "1px solid " + (primary ? "#2563eb" : "#94a3b8"),
    background: primary ? "#2563eb" : "transparent",
    color: primary ? "#fff" : "inherit",
    cursor: "pointer",
  };
}

function FormFrame(props) {
  const { redeemUrl, ticket, nonce, origin, interactionId, onHint } = props;
  const iframeRef = useRef(null);
  const formRef = useRef(null);
  useEffect(() => {
    if (formRef.current) formRef.current.submit();
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
  return _jsxs("div", {
    style: { height: "100%", minHeight: 360 },
    children: [
      _jsxs("form", {
        ref: formRef,
        method: "POST",
        action: redeemUrl,
        target: "bui-frame-" + interactionId,
        style: { display: "none" },
        children: [
          _jsx("input", { type: "hidden", name: "ticket", value: ticket }),
          _jsx("input", { type: "hidden", name: "nonce", value: nonce }),
        ],
      }),
      _jsx("iframe", {
        ref: iframeRef,
        name: "bui-frame-" + interactionId,
        title: "Business form",
        sandbox: "allow-scripts allow-forms allow-same-origin",
        style: { width: "100%", height: 420, border: "0", background: "#fff" },
      }),
    ],
  });
}

function BusinessCard(props) {
  const dark = (props.host.getToolContext() || {}).theme === "dark";
  const data = props.data && typeof props.data === "object" ? props.data : {};
  const callId = props.callId || "";
  const host = props.host;
  const [state, setState] = useState(data);
  const [error, setError] = useState("");
  const [ticket, setTicket] = useState(null);
  const [embedAction, setEmbedAction] = useState(data.embedAction || null);
  const [connections, setConnections] = useState([]);
  const [connectionId, setConnectionId] = useState(data.connectionId || "");
  const pollRef = useRef(null);

  const hydrate = useCallback(
    async (interactionId) => {
      if (!interactionId || !callId) return;
      try {
        const next = await runAction(
          host,
          "interactions.get",
          { interaction_id: interactionId, call_id: callId },
          true,
        );
        setState((prev) => ({ ...prev, ...next, interactionId: next.interaction_id }));
        host.patchResult(callId, {
          ...data,
          ...next,
          interactionId: next.interaction_id,
          submissionStatus: next.submission_status,
          approvalStatus: next.approval_status,
          claimRequired: false,
        });
        return next;
      } catch (err) {
        setError(String(err && err.message ? err.message : err));
        return null;
      }
    },
    [host, callId, data],
  );

  useEffect(() => {
    runAction(host, "connections.list", {}, false)
      .then((res) => {
        const rows = (res && res.connections) || [];
        setConnections(rows);
        if (!connectionId && rows[0]) setConnectionId(rows[0].connection_id);
      })
      .catch(() => {});
  }, [host]);

  useEffect(() => {
    if (state.interactionId || data.interactionId) {
      hydrate(state.interactionId || data.interactionId);
    }
  }, []);

  const stopPoll = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  const startPoll = (interactionId) => {
    stopPoll();
    pollRef.current = setInterval(() => {
      hydrate(interactionId);
    }, 1500);
  };

  useEffect(() => () => stopPoll(), []);

  useEffect(() => {
    const action = embedAction || data.embedAction;
    const interactionId = state.interactionId || data.interactionId;
    if (!interactionId || !action || ticket || !callId) return undefined;
    let cancelled = false;
    const timer = setTimeout(async () => {
      try {
        const issued = await runAction(
          host,
          "tickets.issue",
          { interaction_id: interactionId, call_id: callId, action },
          true,
        );
        if (!cancelled) setTicket(issued);
      } catch (err) {
        if (!cancelled) setError(String(err && err.message ? err.message : err));
      }
    }, 80);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [embedAction, data.embedAction, state.interactionId, data.interactionId, ticket, callId, host]);

  const claimAndOpen = async (action) => {
    setError("");
    if (!connectionId) {
      setError("Select an approved connection");
      return;
    }
    try {
      const claimed = await runAction(
        host,
        "interactions.claim",
        {
          call_id: callId,
          connection_id: connectionId,
          document_type: state.documentType || data.documentType || "generic_request",
          form_ref: state.formRef || data.formRef || "generic.request.edit",
          schema_version: state.schemaVersion || data.schemaVersion || "1",
          record_id: state.recordId || data.recordId || null,
          record_version: state.recordVersion || 0,
          summary: state.summary || data.summary || {},
        },
        true,
      );
      setState((prev) => ({ ...prev, ...claimed, interactionId: claimed.interaction_id }));
      setEmbedAction(action);
      setTicket(null);
      host.patchResult(callId, {
        ...data,
        ...claimed,
        interactionId: claimed.interaction_id,
        submissionStatus: claimed.submission_status,
        approvalStatus: claimed.approval_status,
        claimRequired: false,
        embedAction: action,
      });
      host.openSidePanel({ callId, title: "Business form" });
    } catch (err) {
      setError(String(err && err.message ? err.message : err));
    }
  };

  const cancel = async () => {
    try {
      if (!state.interactionId) {
        host.patchResult(callId, { ...data, submissionStatus: "cancelled", allowedActions: [] });
        setState((prev) => ({ ...prev, submissionStatus: "cancelled" }));
        return;
      }
      const next = await runAction(
        host,
        "interactions.cancel",
        { interaction_id: state.interactionId, call_id: callId },
        true,
      );
      setState((prev) => ({ ...prev, ...next }));
      host.patchResult(callId, { ...data, submissionStatus: "cancelled" });
    } catch (err) {
      setError(String(err && err.message ? err.message : err));
    }
  };

  const onHint = useCallback(
    (hint) => {
      if (!state.interactionId) return;
      startPoll(state.interactionId);
      hydrate(state.interactionId).then((next) => {
        if (next && next.submission_status === "submitted") {
          stopPoll();
          if (next.last_error) return;
          claimAndOpen("view_detail").catch(() => {});
        }
      });
    },
    [state.interactionId],
  );

  const submitted = (state.submissionStatus || state.submission_status) === "submitted";
  const cancelled = (state.submissionStatus || state.submission_status) === "cancelled";
  const statusLabel = submitted
    ? "已提交"
    : cancelled
      ? "已取消"
      : "草稿（未授权）";

  return _jsxs("div", {
    style: cardStyle(dark),
    "data-business-ui-card": "1",
    children: [
      _jsx("div", { style: { fontWeight: 700, fontSize: 16 }, children: (state.summary && state.summary.title) || "业务单据草稿" }),
      _jsx("div", { style: { opacity: 0.8, marginTop: 6, fontSize: 13 }, children: (state.summary && state.summary.body) || data.textFallback || "" }),
      _jsxs("div", { style: { marginTop: 10, fontSize: 12 }, children: ["状态：", statusLabel, " · 审批：", state.approvalStatus || state.approval_status || "not_applicable"] }),
      state.recordId || state.record_id
        ? _jsxs("div", { style: { fontSize: 12 }, children: ["单号 ", state.recordId || state.record_id] })
        : null,
      submitted && (state.last_error || state.lastError)
        ? _jsxs("div", { style: { color: "#b45309", fontSize: 12, marginTop: 8 }, children: ["详情加载失败，单据仍为已提交。",
            _jsx("button", { type: "button", style: btn(false), onClick: () => claimAndOpen("view_detail"), children: "重试加载正式单据" })] })
        : null,
      error ? _jsx("div", { style: { color: "#b91c1c", fontSize: 12, marginTop: 8 }, children: error }) : null,
      !submitted && !cancelled
        ? _jsxs("div", {
            children: [
              _jsx("select", {
                value: connectionId,
                onChange: (ev) => setConnectionId(ev.target.value),
                style: { marginTop: 8, padding: 4 },
                children: [_jsx("option", { value: "", children: "选择已批准连接" }), ...connections.map((c) => _jsx("option", { value: c.connection_id, children: c.display_name }, c.connection_id))],
              }),
              _jsx("button", { type: "button", style: btn(true), onClick: () => claimAndOpen("edit"), children: "核对并编辑" }),
              _jsx("button", { type: "button", style: btn(false), onClick: cancel, children: "取消" }),
            ],
          })
        : null,
      submitted
        ? _jsx("button", { type: "button", style: btn(true), onClick: () => claimAndOpen("view_detail"), children: "查看正式单据" })
        : null,
      ticket
        ? _jsx(FormFrame, {
            redeemUrl: ticket.redeem_url,
            ticket: ticket.ticket,
            nonce: ticket.nonce,
            origin: ticket.form_origin,
            interactionId: state.interactionId,
            onHint,
          })
        : null,
    ],
  });
}

function ConfigCard(props) {
  const dark = (props.host.getToolContext() || {}).theme === "dark";
  const host = props.host;
  const [rows, setRows] = useState([]);
  const [canManage, setCanManage] = useState(false);
  const [issuer, setIssuer] = useState("");
  const [error, setError] = useState("");
  const [test, setTest] = useState(null);
  const [form, setForm] = useState({
    display_name: "",
    base_url: "",
    auth_method: "api_token",
    secret: "",
    extra_origins: "",
    private_allow: "127.0.0.1/32",
    tls_ca_pem: "",
    instance_issuer: "",
    enabled: true,
  });

  const reload = async () => {
    const res = await runAction(host, "connections.list", {}, false);
    setRows(res.connections || []);
    setCanManage(!!res.can_manage);
    setIssuer(res.instance_issuer || "");
  };

  useEffect(() => {
    reload().catch((err) => setError(String(err && err.message ? err.message : err)));
  }, [host]);

  const save = async (connectionId) => {
    setError("");
    const payload = {
      connection_id: connectionId || undefined,
      display_name: form.display_name,
      base_url: form.base_url,
      auth_method: form.auth_method,
      extra_origins: form.extra_origins ? form.extra_origins.split(/\s+/).filter(Boolean) : [],
      private_allow: form.private_allow ? form.private_allow.split(/\s+/).filter(Boolean) : [],
      instance_issuer: form.instance_issuer || undefined,
      enabled: form.enabled,
    };
    if (form.secret) payload.secret = form.secret;
      if (form.tls_ca_pem) payload.tls_ca_pem = form.tls_ca_pem;
    try {
      await runAction(host, "connections.save", payload, false);
      setForm((prev) => ({ ...prev, secret: "" }));
      await reload();
    } catch (err) {
      setError(String(err && err.message ? err.message : err));
    }
  };

  const remove = async (id) => {
    await runAction(host, "connections.delete", { connection_id: id }, false);
    await reload();
  };

  const probe = async (id) => {
    const res = await runAction(host, "connections.test", { connection_id: id }, false);
    setTest(res);
  };

  return _jsxs("div", {
    style: cardStyle(dark),
    "data-business-ui-config": "1",
    children: [
      _jsx("div", { style: { fontWeight: 700 }, children: "Business UI 连接" }),
      _jsx("div", { style: { fontSize: 12, opacity: 0.8, marginTop: 4 }, children: "密钥只出现在本表单并经已认证 action 写入 Host 凭据，不会进聊天或 plugin_records。" }),
      issuer ? _jsxs("div", { style: { fontSize: 12, marginTop: 6 }, children: ["实例 issuer：", issuer] }) : null,
      error ? _jsx("div", { style: { color: "#b91c1c", fontSize: 12 }, children: error }) : null,
      rows.map((row) =>
        _jsxs("div", {
          style: { marginTop: 10, paddingTop: 8, borderTop: "1px solid #e2e8f0", fontSize: 13 },
          children: [
            _jsx("strong", { children: row.display_name }),
            _jsxs("div", { children: [row.base_url, " · ", row.auth_method, row.enabled ? " · 启用" : " · 停用"] }),
            canManage
              ? _jsxs("div", {
                  children: [
                    _jsx("button", { type: "button", style: btn(false), onClick: () => probe(row.connection_id), children: "Test Connection" }),
                    _jsx("button", { type: "button", style: btn(false), onClick: () => remove(row.connection_id), children: "删除" }),
                  ],
                })
              : null,
          ],
        }, row.connection_id),
      ),
      canManage
        ? _jsxs("div", {
            style: { marginTop: 12 },
            children: [
              _jsx("input", { placeholder: "显示名", value: form.display_name, onChange: (e) => setForm({ ...form, display_name: e.target.value }), style: { display: "block", width: "100%", marginTop: 6 } }),
              _jsx("input", { placeholder: "HTTPS Adapter 地址", value: form.base_url, onChange: (e) => setForm({ ...form, base_url: e.target.value }), style: { display: "block", width: "100%", marginTop: 6 } }),
              _jsx("input", { placeholder: "本实例 issuer https://octop.example.com", value: form.instance_issuer, onChange: (e) => setForm({ ...form, instance_issuer: e.target.value }), style: { display: "block", width: "100%", marginTop: 6 } }),
              _jsxs("select", { value: form.auth_method, onChange: (e) => setForm({ ...form, auth_method: e.target.value }), style: { marginTop: 6 }, children: [_jsx("option", { value: "api_token", children: "可复用 API token" }), _jsx("option", { value: "authorization_code", children: "一次性授权码" })] }),
              _jsx("input", { type: "password", autoComplete: "new-password", placeholder: "密钥 / 授权码（不回显）", value: form.secret, onChange: (e) => setForm({ ...form, secret: e.target.value }), style: { display: "block", width: "100%", marginTop: 6 } }),
              _jsx("textarea", { placeholder: "可选：内网适配器 TLS CA PEM", value: form.tls_ca_pem, onChange: (e) => setForm({ ...form, tls_ca_pem: e.target.value }), style: { display: "block", width: "100%", marginTop: 6, minHeight: 64 } }),
              _jsx("input", { placeholder: "额外 origin（空格分隔）", value: form.extra_origins, onChange: (e) => setForm({ ...form, extra_origins: e.target.value }), style: { display: "block", width: "100%", marginTop: 6 } }),
              _jsx("input", { placeholder: "私有网段例外 CIDR/host", value: form.private_allow, onChange: (e) => setForm({ ...form, private_allow: e.target.value }), style: { display: "block", width: "100%", marginTop: 6 } }),
              _jsx("button", { type: "button", style: btn(true), onClick: () => save(""), children: "保存连接" }),
            ],
          })
        : _jsx("div", { style: { fontSize: 12, marginTop: 8 }, children: "仅管理员可新增连接。角色由 Host JWT 判定。" }),
      test
        ? _jsxs("div", {
            style: { marginTop: 12, fontSize: 12 },
            "data-connection-test": "1",
            children: [
              _jsxs("div", { children: ["Test ", test.ok ? "未完全等同浏览器嵌入" : "失败", " · ", test.unsupported_reason || test.protocol || ""] }),
              ...(test.stages || []).map((s) =>
                _jsxs("div", { children: [s.ok ? "✓" : "✗", " ", s.name, " — ", s.detail] }, s.name),
              ),
            ],
          })
        : null,
      _jsx("div", { style: { fontSize: 11, marginTop: 10, opacity: 0.7 }, children: "UNSUPPORTED：Octop 登出不会立即作废已兑业务会话。浏览器第三方存储需实测，POST 兑票不能保证 cookie。" }),
    ],
  });
}

export function setup(host) {
  host.registerRenderer({ id: "business_ui_card", tools: ["business_ui_draft"], component: BusinessCard });
  host.registerRenderer({ id: "business_ui_config", tools: ["business_ui_connections"], component: ConfigCard });
}
