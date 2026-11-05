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
      width: "100%",
      maxWidth: 720,
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

/** Compact ``MM-DD HH:mm`` from RFC2822 / ISO date strings. */
function formatMailTime(raw) {
  const text = String(raw || "").trim();
  if (!text) return "—";
  const d = new Date(text);
  if (Number.isNaN(d.getTime())) {
    return text.length > 16 ? text.slice(0, 16) : text;
  }
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  const mi = String(d.getMinutes()).padStart(2, "0");
  return mm + "-" + dd + " " + hh + ":" + mi;
}

/** Prefer display name from ``Name <addr@x>``. */
function formatSender(from) {
  const s = String(from || "").trim();
  if (!s) return "(未知)";
  const m = s.match(/^"?([^"<]+?)"?\s*</);
  if (m && m[1].trim()) return m[1].trim();
  return s;
}

function ellipsisStyle(flex) {
  return {
    flex: flex,
    minWidth: 0,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  };
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
  const [fromFilter, setFromFilter] = useState(d.from || "");
  const [unreadOnly, setUnreadOnly] = useState(!!d.unread);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const pageSize = Number(d.limit) > 0 ? Number(d.limit) : 20;
  const offset = Number(d.offset) > 0 ? Number(d.offset) : 0;
  const total = Number(d.total) >= 0 ? Number(d.total) : items.length;
  const hasMore = d.has_more === true || offset + items.length < total;
  const page = Math.floor(offset / pageSize) + 1;
  const pages = Math.max(1, Math.ceil((total || 0) / pageSize));

  const refresh = useCallback(
    async (extra) => {
      setBusy(true);
      setError("");
      try {
        const result = await runAction(props.host, "mail.list", {
          unread: extra && extra.unread != null ? extra.unread : unreadOnly || undefined,
          from: (extra && extra.from != null ? extra.from : fromFilter) || undefined,
          since_days: d.since_days,
          query: d.query,
          offset: extra && extra.offset != null ? extra.offset : 0,
          limit: pageSize,
        });
        if (props.callId && result && result.data) {
          props.host.patchResult(props.callId, result.data);
        }
      } catch (err) {
        setError((err && err.message) || "刷新失败");
      } finally {
        setBusy(false);
      }
    },
    [props.host, props.callId, unreadOnly, fromFilter, d.since_days, d.query, pageSize],
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
        setError((err && err.message) || "打开失败");
      } finally {
        setBusy(false);
      }
    },
    [props.host, props.callId],
  );

  return cardShell(
    dark,
    _jsxs("div", {
      style: { padding: 12 },
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
            _jsx("strong", { style: { fontSize: 14 }, children: "收件箱" }),
            _jsxs("label", {
              style: { fontSize: 12, display: "flex", gap: 4, alignItems: "center" },
              children: [
                _jsx("input", {
                  type: "checkbox",
                  checked: unreadOnly,
                  onChange: (e) => setUnreadOnly(!!e.target.checked),
                }),
                "未读",
              ],
            }),
            _jsx("input", {
              value: fromFilter,
              onChange: (e) => setFromFilter(e.target.value),
              placeholder: "发件人…",
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
              onClick: () => refresh({ offset: 0 }),
              children: busy ? "…" : "刷新",
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
              children: "暂无邮件",
            })
          : _jsxs("div", {
              style: {
                display: "flex",
                flexDirection: "column",
                gap: 2,
                borderRadius: 10,
                overflow: "hidden",
                border: dark ? "1px solid #27272a" : "1px solid #e2e8f0",
              },
              children: [
                _jsxs("div", {
                  style: {
                    display: "flex",
                    gap: 10,
                    padding: "6px 10px",
                    fontSize: 11,
                    fontWeight: 600,
                    opacity: 0.55,
                    background: dark ? "#09090b" : "#f8fafc",
                  },
                  children: [
                    _jsx("span", { style: { flex: "0 0 88px" }, children: "时间" }),
                    _jsx("span", { style: { flex: "0 0 128px" }, children: "发件人" }),
                    _jsx("span", { style: { flex: 1 }, children: "主题" }),
                  ],
                }),
                items.map((row, idx) =>
                  _jsxs(
                    "button",
                    {
                      type: "button",
                      title: "点击查看正文",
                      onClick: () => openDetail(row.uid),
                      disabled: busy,
                      style: {
                        display: "flex",
                        alignItems: "center",
                        gap: 10,
                        width: "100%",
                        textAlign: "left",
                        border: "none",
                        borderTop:
                          idx === 0
                            ? "none"
                            : dark
                              ? "1px solid #27272a"
                              : "1px solid #f1f5f9",
                        background: "transparent",
                        color: "inherit",
                        padding: "8px 10px",
                        cursor: busy ? "wait" : "pointer",
                        fontSize: 12,
                        lineHeight: 1.35,
                      },
                      onMouseEnter: (e) => {
                        e.currentTarget.style.background = dark ? "#27272a" : "#f1f5f9";
                      },
                      onMouseLeave: (e) => {
                        e.currentTarget.style.background = "transparent";
                      },
                      children: [
                        _jsx("span", {
                          style: {
                            ...ellipsisStyle("0 0 88px"),
                            fontVariantNumeric: "tabular-nums",
                            opacity: 0.72,
                          },
                          children: formatMailTime(row.date),
                        }),
                        _jsx("span", {
                          style: ellipsisStyle("0 0 128px"),
                          title: row.from || "",
                          children: formatSender(row.from),
                        }),
                        _jsx("span", {
                          style: {
                            ...ellipsisStyle("1 1 auto"),
                            fontWeight: 600,
                          },
                          title: row.subject || "",
                          children: row.subject || "(无主题)",
                        }),
                      ],
                    },
                    String(row.uid),
                  ),
                ),
              ],
            }),
        total > pageSize || offset > 0
          ? _jsxs("div", {
              style: {
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 8,
                marginTop: 10,
              },
              children: [
                _jsx("button", {
                  type: "button",
                  style: btnStyle(dark, false),
                  disabled: busy || offset <= 0,
                  onClick: () => refresh({ offset: Math.max(0, offset - pageSize) }),
                  children: "上一页",
                }),
                _jsx("span", {
                  style: { fontSize: 12, opacity: 0.7 },
                  children: "第 " + page + " / " + pages + " 页 · 共 " + total + " 封",
                }),
                _jsx("button", {
                  type: "button",
                  style: btnStyle(dark, false),
                  disabled: busy || !hasMore,
                  onClick: () => refresh({ offset: offset + pageSize }),
                  children: "下一页",
                }),
              ],
            })
          : null,
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
      setError((err && err.message) || "返回失败");
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
      setError((err && err.message) || "准备回复失败");
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
              children: "← 列表",
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
              children: "分析",
            }),
            _jsx("button", {
              type: "button",
              style: btnStyle(dark, true),
              disabled: busy,
              onClick: startReply,
              children: "回复",
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
          children: d.subject || "(无主题)",
        }),
        _jsx("div", {
          style: { fontSize: 11, opacity: 0.55, marginBottom: 10 },
          children: d.date || "",
        }),
        Array.isArray(d.attachments) && d.attachments.length
          ? _jsx("div", {
              style: { fontSize: 11, opacity: 0.7, marginBottom: 8 },
              children: "附件: " + d.attachments.join(", "),
            })
          : null,
        d.body_html
          ? _jsx("div", {
              style: {
                fontSize: 14,
                lineHeight: 1.6,
                wordBreak: "break-word",
                background: dark ? "#09090b" : "#f8fafc",
                padding: 12,
                borderRadius: 8,
                maxHeight: 480,
                overflow: "auto",
              },
              dangerouslySetInnerHTML: { __html: d.body_html },
            })
          : _jsx("pre", {
              style: {
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                fontSize: 13,
                margin: 0,
                fontFamily: "inherit",
                background: dark ? "#09090b" : "#f8fafc",
                padding: 10,
                borderRadius: 8,
                maxHeight: 480,
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
          children: confirmationRequired ? "确认发送" : "回复草稿",
        }),
        _jsx("div", {
          style: { fontSize: 12, opacity: 0.75, marginBottom: 4 },
          children: `收件人: ${to}`,
        }),
        _jsx("div", {
          style: { fontSize: 12, opacity: 0.75, marginBottom: 8 },
          children: `主题: ${subject}`,
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
              children: "请在聊天中批准工具确认以发送；拒绝即取消。",
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
                  children: "模板",
                }),
                _jsx("button", {
                  type: "button",
                  style: btnStyle(dark, false),
                  onClick: () =>
                    sendPrefill(
                      props,
                      `Polish this reply draft with the reply-polish skill:\n\n${body}`,
                    ),
                  children: "润色",
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
                  children: "发送",
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
          _jsx("strong", { children: "已发送" }),
          _jsx("div", {
            style: { marginTop: 6 },
            children: `收件人 ${d.to || ""} · ${d.subject || ""}`,
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
