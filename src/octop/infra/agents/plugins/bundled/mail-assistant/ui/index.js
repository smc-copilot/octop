const React = window.__OCTOP_REACT__;
const { useState, useCallback } = React;
const { jsx: _jsx, jsxs: _jsxs } = window.__OCTOP_JSX__;

const PLUGIN_ID = "mail-assistant";

function btnStyle(dark, primary) {
  return {
    border: "none",
    borderRadius: 8,
    padding: "6px 12px",
    fontSize: 12,
    fontWeight: 600,
    cursor: "pointer",
    background: primary
      ? dark
        ? "#2563eb"
        : "#3b82f6"
      : dark
        ? "#3f3f46"
        : "#e2e8f0",
    color: primary ? "#fff" : dark ? "#f4f4f5" : "#0f172a",
  };
}

function cardShell(dark, children) {
  return _jsx("div", {
    "data-octop-plugin-ui": "mail-card",
    style: {
      margin: 0,
      maxWidth: 520,
      borderRadius: 16,
      overflow: "hidden",
      background: dark ? "#18181b" : "#fff",
      color: dark ? "#f8fafc" : "#0f172a",
      boxShadow: dark
        ? "0 10px 28px rgba(0,0,0,.4)"
        : "0 10px 24px rgba(15,23,42,.12)",
      border: dark ? "1px solid #27272a" : "1px solid #e2e8f0",
    },
    children,
  });
}

function sendPrefill(props, text) {
  const send =
    props.onSendMessage ||
    props.onAcpPermissionSelect ||
    (props.host && props.host.sendMessage);
  if (typeof send === "function") send(text);
}

async function runAction(host, name, payload) {
  const ctx = host.getToolContext() || {};
  const body = {
    api_version: 1,
    context: {
      agent_id: ctx.agentId || undefined,
      thread_id: ctx.threadId || undefined,
    },
    payload: payload || {},
  };
  const res = await host.request(`/plugins/${PLUGIN_ID}/actions/${name}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return res && res.result ? res.result : res;
}

function ListView(props) {
  const dark = props.dark;
  const d = props.data || {};
  const items = Array.isArray(d.items) ? d.items : [];
  const [fromFilter, setFromFilter] = useState("");
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(
    async (extra) => {
      setBusy(true);
      setError("");
      try {
        const result = await runAction(props.host, "mail.list", {
          unread: extra && extra.unread != null ? extra.unread : unreadOnly || undefined,
          from: (extra && extra.from != null ? extra.from : fromFilter) || undefined,
          limit: 20,
        });
        if (props.callId && result && result.data) {
          props.host.patchResult(props.callId, result.data);
        }
      } catch (err) {
        setError((err && err.message) || "Failed to refresh");
      } finally {
        setBusy(false);
      }
    },
    [props.host, props.callId, unreadOnly, fromFilter],
  );

  const openDetail = useCallback(
    async (uid) => {
      setBusy(true);
      setError("");
      try {
        const result = await runAction(props.host, "mail.detail", { uid });
        if (props.callId && result && result.data) {
          props.host.patchResult(props.callId, result.data);
        }
      } catch (err) {
        setError((err && err.message) || "Failed to open");
      } finally {
        setBusy(false);
      }
    },
    [props.host, props.callId],
  );

  return cardShell(
    dark,
    _jsxs("div", {
      style: { padding: 14 },
      children: [
        _jsxs("div", {
          style: {
            display: "flex",
            gap: 8,
            alignItems: "center",
            marginBottom: 10,
            flexWrap: "wrap",
          },
          children: [
            _jsx("strong", { style: { fontSize: 14 }, children: "Inbox" }),
            _jsxs("label", {
              style: { fontSize: 12, display: "flex", gap: 4, alignItems: "center" },
              children: [
                _jsx("input", {
                  type: "checkbox",
                  checked: unreadOnly,
                  onChange: (e) => setUnreadOnly(!!e.target.checked),
                }),
                "Unread",
              ],
            }),
            _jsx("input", {
              value: fromFilter,
              onChange: (e) => setFromFilter(e.target.value),
              placeholder: "From…",
              style: {
                flex: 1,
                minWidth: 120,
                fontSize: 12,
                padding: "4px 8px",
                borderRadius: 6,
                border: dark ? "1px solid #3f3f46" : "1px solid #cbd5e1",
                background: dark ? "#09090b" : "#fff",
                color: "inherit",
              },
            }),
            _jsx("button", {
              type: "button",
              style: btnStyle(dark, false),
              disabled: busy,
              onClick: () => refresh({}),
              children: busy ? "…" : "Refresh",
            }),
          ],
        }),
        error
          ? _jsx("div", {
              style: { color: "#ef4444", fontSize: 12, marginBottom: 8 },
              children: error,
            })
          : null,
        items.length === 0
          ? _jsx("div", {
              style: { fontSize: 13, opacity: 0.7 },
              children: "No messages",
            })
          : items.map((row) =>
              _jsxs(
                "button",
                {
                  type: "button",
                  onClick: () => openDetail(row.uid),
                  style: {
                    display: "block",
                    width: "100%",
                    textAlign: "left",
                    border: "none",
                    background: dark ? "#27272a" : "#f8fafc",
                    color: "inherit",
                    borderRadius: 10,
                    padding: "10px 12px",
                    marginBottom: 6,
                    cursor: "pointer",
                  },
                  children: [
                    _jsx("div", {
                      style: { fontSize: 12, opacity: 0.7 },
                      children: row.from || "(unknown)",
                    }),
                    _jsx("div", {
                      style: { fontSize: 13, fontWeight: 600 },
                      children: row.subject || "(no subject)",
                    }),
                    _jsx("div", {
                      style: { fontSize: 11, opacity: 0.55, marginTop: 2 },
                      children: row.date || "",
                    }),
                  ],
                },
                String(row.uid),
              ),
            ),
      ],
    }),
  );
}

function DetailView(props) {
  const dark = props.dark;
  const d = props.data || {};
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const backToList = useCallback(async () => {
    setBusy(true);
    setError("");
    try {
      const result = await runAction(props.host, "mail.list", { limit: 20 });
      if (props.callId && result && result.data) {
        props.host.patchResult(props.callId, result.data);
      }
    } catch (err) {
      setError((err && err.message) || "Failed");
    } finally {
      setBusy(false);
    }
  }, [props.host, props.callId]);

  const startReply = useCallback(async () => {
    setBusy(true);
    setError("");
    try {
      const result = await runAction(props.host, "mail.prepare_reply", {
        uid: d.uid,
      });
      if (props.callId && result && result.data) {
        props.host.patchResult(props.callId, result.data);
      }
    } catch (err) {
      setError((err && err.message) || "Failed");
    } finally {
      setBusy(false);
    }
  }, [props.host, props.callId, d.uid]);

  return cardShell(
    dark,
    _jsxs("div", {
      style: { padding: 14 },
      children: [
        _jsxs("div", {
          style: { display: "flex", gap: 8, marginBottom: 10, flexWrap: "wrap" },
          children: [
            _jsx("button", {
              type: "button",
              style: btnStyle(dark, false),
              disabled: busy,
              onClick: backToList,
              children: "← List",
            }),
            _jsx("button", {
              type: "button",
              style: btnStyle(dark, true),
              disabled: busy,
              onClick: () =>
                sendPrefill(
                  props,
                  `Please analyze this email (uid ${d.uid}) with the mail-analysis skill.`,
                ),
              children: "Analyze",
            }),
            _jsx("button", {
              type: "button",
              style: btnStyle(dark, true),
              disabled: busy,
              onClick: startReply,
              children: "Reply",
            }),
          ],
        }),
        error
          ? _jsx("div", {
              style: { color: "#ef4444", fontSize: 12, marginBottom: 8 },
              children: error,
            })
          : null,
        _jsx("div", {
          style: { fontSize: 12, opacity: 0.7 },
          children: d.from || "",
        }),
        _jsx("div", {
          style: { fontSize: 16, fontWeight: 700, margin: "4px 0" },
          children: d.subject || "(no subject)",
        }),
        _jsx("div", {
          style: { fontSize: 11, opacity: 0.55, marginBottom: 10 },
          children: d.date || "",
        }),
        Array.isArray(d.attachments) && d.attachments.length
          ? _jsx("div", {
              style: { fontSize: 11, opacity: 0.7, marginBottom: 8 },
              children: "Attachments: " + d.attachments.join(", "),
            })
          : null,
        _jsx("pre", {
          style: {
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            fontSize: 13,
            margin: 0,
            fontFamily: "inherit",
            background: dark ? "#09090b" : "#f8fafc",
            padding: 10,
            borderRadius: 8,
            maxHeight: 320,
            overflow: "auto",
          },
          children: d.body || "",
        }),
      ],
    }),
  );
}

function DraftView(props) {
  const dark = props.dark;
  const d = props.data || {};
  const summary = d.summary || {};
  const [body, setBody] = useState(
    typeof d.body === "string" ? d.body : summary.body_preview || "",
  );
  const to = d.to || summary.to || "";
  const subject = d.subject || summary.subject || "";
  const uid = d.uid || summary.uid || "";
  const confirmationRequired = !!d.confirmation_required;

  return cardShell(
    dark,
    _jsxs("div", {
      style: { padding: 14 },
      children: [
        _jsx("div", {
          style: { fontSize: 14, fontWeight: 700, marginBottom: 8 },
          children: confirmationRequired ? "Confirm send" : "Reply draft",
        }),
        _jsx("div", {
          style: { fontSize: 12, opacity: 0.75, marginBottom: 4 },
          children: `To: ${to}`,
        }),
        _jsx("div", {
          style: { fontSize: 12, opacity: 0.75, marginBottom: 8 },
          children: `Subject: ${subject}`,
        }),
        confirmationRequired
          ? _jsx("div", {
              style: {
                fontSize: 12,
                padding: 10,
                borderRadius: 8,
                background: dark ? "#1e3a5f" : "#eff6ff",
                marginBottom: 10,
              },
              children:
                "Approve the tool confirmation in chat to send. Reject to cancel.",
            })
          : _jsx("textarea", {
              value: body,
              onChange: (e) => setBody(e.target.value),
              rows: 8,
              style: {
                width: "100%",
                boxSizing: "border-box",
                fontSize: 13,
                padding: 10,
                borderRadius: 8,
                border: dark ? "1px solid #3f3f46" : "1px solid #cbd5e1",
                background: dark ? "#09090b" : "#fff",
                color: "inherit",
                resize: "vertical",
              },
            }),
        !confirmationRequired
          ? _jsxs("div", {
              style: { display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap" },
              children: [
                _jsx("button", {
                  type: "button",
                  style: btnStyle(dark, false),
                  onClick: () =>
                    sendPrefill(
                      props,
                      `Generate a reply template for email uid ${uid} using the reply-template skill.`,
                    ),
                  children: "Template",
                }),
                _jsx("button", {
                  type: "button",
                  style: btnStyle(dark, false),
                  onClick: () =>
                    sendPrefill(
                      props,
                      `Polish this reply draft with the reply-polish skill:\n\n${body}`,
                    ),
                  children: "Polish",
                }),
                _jsx("button", {
                  type: "button",
                  style: btnStyle(dark, true),
                  onClick: () =>
                    sendPrefill(
                      props,
                      uid
                        ? `Send a reply to email uid ${uid} with this body (use reply_email two-phase confirmation):\n\n${body}`
                        : `Send this email to ${to} with subject "${subject}" (use send_email two-phase confirmation):\n\n${body}`,
                    ),
                  children: "Send",
                }),
              ],
            })
          : null,
        d.quote
          ? _jsx("pre", {
              style: {
                marginTop: 12,
                whiteSpace: "pre-wrap",
                fontSize: 11,
                opacity: 0.6,
                fontFamily: "inherit",
              },
              children: d.quote,
            })
          : null,
      ],
    }),
  );
}

function MailCard(props) {
  const theme =
    (props.host && props.host.getToolContext && props.host.getToolContext().theme) ||
    "light";
  const dark = theme === "dark";
  const d = props.data && typeof props.data === "object" ? props.data : {};
  const view = d.view || (Array.isArray(d.items) ? "list" : "detail");
  const next = { ...props, data: d, dark };
  if (view === "list") return _jsx(ListView, next);
  if (view === "draft" || d.confirmation_required) return _jsx(DraftView, next);
  if (view === "sent") {
    return cardShell(
      dark,
      _jsxs("div", {
        style: { padding: 14, fontSize: 13 },
        children: [
          _jsx("strong", { children: "Sent" }),
          _jsx("div", {
            style: { marginTop: 6 },
            children: `To ${d.to || ""} · ${d.subject || ""}`,
          }),
        ],
      }),
    );
  }
  return _jsx(DetailView, next);
}

export function setup(host) {
  host.registerRenderer({
    id: "mail_card",
    tools: ["search_emails", "read_email", "send_email", "reply_email"],
    component: MailCard,
  });
}
