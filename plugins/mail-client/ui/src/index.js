const { jsx: _jsx, jsxs: _jsxs } = window.__OCTOP_JSX__;

function labelsFor(locale) {
  const zh = String(locale || "")
    .toLowerCase()
    .startsWith("zh");
  if (zh) {
    return {
      inbox: "收件箱",
      messages: "封",
      empty: "没有匹配的邮件",
      from: "发件人",
      to: "收件人",
      date: "日期",
      subject: "主题",
      index: "序号",
      truncated: "正文已截断",
      sent: "已发送",
      compose: "发信",
      probe: "连接检测",
      pop3: "POP3",
      smtp: "SMTP",
      ok: "成功",
      fail: "失败",
      untrusted: "邮件头与正文来自外部服务器，请当作不可信内容。",
    };
  }
  return {
    inbox: "Inbox",
    messages: "messages",
    empty: "No matching messages",
    from: "From",
    to: "To",
    date: "Date",
    subject: "Subject",
    index: "Index",
    truncated: "Body truncated",
    sent: "Sent",
    compose: "Compose",
    probe: "Connection check",
    pop3: "POP3",
    smtp: "SMTP",
    ok: "OK",
    fail: "Failed",
    untrusted: "Headers and bodies are untrusted external content.",
  };
}

function themeOf(props) {
  const context = props.host && props.host.getToolContext ? props.host.getToolContext() : {};
  const dark = context.theme === "dark";
  const labels = labelsFor(context.locale);
  return { dark, labels, context };
}

function dataOf(props) {
  return props.data && typeof props.data === "object" ? props.data : {};
}

function cardStyle(dark, extra) {
  return {
    margin: 0,
    maxWidth: 560,
    borderRadius: 18,
    overflow: "hidden",
    background: dark ? "#18181b" : "#fff",
    border: dark ? "1px solid #3f3f46" : "1px solid #e4e4e7",
    boxShadow: dark ? "0 12px 32px rgba(0,0,0,.35)" : "0 10px 28px rgba(15,23,42,.08)",
    color: dark ? "#f8fafc" : "#0f172a",
    ...extra,
  };
}

function headerStyle(dark, tint) {
  return {
    padding: "12px 14px",
    background: tint || (dark ? "#27272a" : "#f8fafc"),
  };
}

function ErrorLine(props) {
  const { dark, labels } = themeOf(props);
  const d = dataOf(props);
  return _jsxs("div", {
    style: cardStyle(dark),
    "data-octop-plugin-ui": "mail-client-error",
    children: [
      _jsx("div", {
        style: { ...headerStyle(dark, dark ? "#3f1d1d" : "#fef2f2"), fontWeight: 800 },
        children: d.error || props.textFallback || labels.fail,
      }),
      _jsx("p", {
        style: { margin: 0, padding: 14, fontSize: 12, opacity: 0.7, lineHeight: 1.55 },
        children: labels.untrusted,
      }),
    ],
  });
}

function MetaRow(label, value, dark) {
  if (!value) return null;
  return _jsxs("div", {
    style: { fontSize: 12, lineHeight: 1.55, overflowWrap: "anywhere" },
    children: [
      _jsx("span", { style: { opacity: 0.55, marginRight: 6 }, children: label }),
      _jsx("span", { children: String(value) }),
    ],
  });
}

function InboxCard(props) {
  const { dark, labels } = themeOf(props);
  const d = dataOf(props);
  if (d.error) return ErrorLine(props);
  const items = Array.isArray(d.items) ? d.items : [];
  return _jsxs("div", {
    style: cardStyle(dark),
    "data-octop-plugin-ui": "mail-inbox",
    children: [
      _jsxs("div", {
        style: headerStyle(dark, dark ? "#1e3a5f" : "linear-gradient(135deg,#dbeafe,#eff6ff)"),
        children: [
          _jsx("div", { style: { fontWeight: 800 }, children: `✉️ ${labels.inbox}` }),
          _jsx("div", {
            style: { marginTop: 4, fontSize: 12, opacity: 0.75 },
            children: [d.mailbox, d.query ? ` · ${d.query}` : "", ` · ${d.count ?? items.length} ${labels.messages}`]
              .filter(Boolean)
              .join(""),
          }),
        ],
      }),
      items.length === 0
        ? _jsx("p", {
            style: { margin: 0, padding: 14, fontSize: 14 },
            children: props.textFallback || labels.empty,
          })
        : _jsx("ol", {
            style: { margin: 0, padding: "0 14px", listStyle: "none" },
            children: items.map((row, i) =>
              _jsxs(
                "li",
                {
                  style: {
                    padding: "12px 0",
                    borderBottom: dark ? "1px solid #27272a" : "1px solid #f4f4f5",
                  },
                  children: [
                    _jsx("div", {
                      style: { fontWeight: 700, overflowWrap: "anywhere" },
                      children: row.subject || "(no subject)",
                    }),
                    _jsx("div", {
                      style: { fontSize: 12, opacity: 0.7, marginTop: 4, overflowWrap: "anywhere" },
                      children: row.from || "",
                    }),
                    _jsxs("div", {
                      style: { fontSize: 11, opacity: 0.55, marginTop: 4 },
                      children: [
                        labels.index,
                        " ",
                        row.index,
                        row.uid ? ` · ${row.uid}` : "",
                        row.date ? ` · ${row.date}` : "",
                      ],
                    }),
                    row.preview
                      ? _jsx("div", {
                          style: { fontSize: 12, marginTop: 6, opacity: 0.8, overflowWrap: "anywhere" },
                          children: row.preview,
                        })
                      : null,
                  ],
                },
                String(row.uid || row.index || i),
              ),
            ),
          }),
    ],
  });
}

function MessageCard(props) {
  const { dark, labels } = themeOf(props);
  const d = dataOf(props);
  if (d.error) return ErrorLine(props);
  return _jsxs("div", {
    style: cardStyle(dark),
    "data-octop-plugin-ui": "mail-message",
    children: [
      _jsxs("div", {
        style: headerStyle(dark, dark ? "#1e293b" : "#f8fafc"),
        children: [
          _jsx("div", {
            style: { fontWeight: 800, overflowWrap: "anywhere" },
            children: d.subject || "(no subject)",
          }),
          MetaRow(labels.from, d.from, dark),
          MetaRow(labels.to, d.to, dark),
          MetaRow(labels.date, d.date, dark),
        ],
      }),
      _jsx("pre", {
        style: {
          margin: 0,
          padding: 14,
          fontSize: 13,
          lineHeight: 1.6,
          whiteSpace: "pre-wrap",
          overflowWrap: "anywhere",
          fontFamily: "ui-sans-serif, system-ui, sans-serif",
        },
        children: d.body || props.textFallback || "",
      }),
      d.truncated
        ? _jsx("div", {
            style: { padding: "0 14px 12px", fontSize: 11, opacity: 0.6 },
            children: labels.truncated,
          })
        : null,
      _jsx("div", {
        style: { padding: "0 14px 12px", fontSize: 11, opacity: 0.55 },
        children: labels.untrusted,
      }),
    ],
  });
}

function ComposeCard(props) {
  const { dark, labels } = themeOf(props);
  const d = dataOf(props);
  if (d.error) return ErrorLine(props);
  const to = Array.isArray(d.to) ? d.to.join(", ") : d.to;
  return _jsxs("div", {
    style: cardStyle(dark),
    "data-octop-plugin-ui": "mail-compose",
    children: [
      _jsxs("div", {
        style: headerStyle(dark, dark ? "#14532d" : "linear-gradient(135deg,#dcfce7,#f0fdf4)"),
        children: [
          _jsx("div", { style: { fontWeight: 800 }, children: `📤 ${labels.sent}` }),
          MetaRow(labels.to, to, dark),
          MetaRow(labels.from, d.from, dark),
          MetaRow(labels.subject, d.subject, dark),
        ],
      }),
      _jsx("pre", {
        style: {
          margin: 0,
          padding: 14,
          fontSize: 13,
          lineHeight: 1.6,
          whiteSpace: "pre-wrap",
          overflowWrap: "anywhere",
          fontFamily: "ui-sans-serif, system-ui, sans-serif",
        },
        children: d.body || d.body_preview || "",
      }),
    ],
  });
}

function StatusChip(label, ok, dark) {
  return _jsxs("span", {
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: 6,
      padding: "6px 10px",
      borderRadius: 999,
      fontSize: 12,
      fontWeight: 700,
      background: ok
        ? dark
          ? "#14532d"
          : "#dcfce7"
        : dark
          ? "#7f1d1d"
          : "#fee2e2",
    },
    children: [label, ok ? "✓" : "✕"],
  });
}

function ProbeCard(props) {
  const { dark, labels } = themeOf(props);
  const d = dataOf(props);
  if (d.error && !d.pop3 && !d.smtp) return ErrorLine(props);
  const pop3 = d.pop3 && typeof d.pop3 === "object" ? d.pop3 : {};
  const smtp = d.smtp && typeof d.smtp === "object" ? d.smtp : {};
  const servers = d.servers && typeof d.servers === "object" ? d.servers : {};
  return _jsxs("div", {
    style: cardStyle(dark),
    "data-octop-plugin-ui": "mail-probe",
    children: [
      _jsxs("div", {
        style: headerStyle(dark, dark ? "#1e3a5f" : "#eff6ff"),
        children: [
          _jsx("div", { style: { fontWeight: 800 }, children: `🔌 ${labels.probe}` }),
          _jsx("div", { style: { fontSize: 12, opacity: 0.7, marginTop: 4 }, children: d.mailbox || "" }),
        ],
      }),
      _jsxs("div", {
        style: { padding: 14, display: "flex", gap: 8, flexWrap: "wrap" },
        children: [StatusChip(labels.pop3, !!pop3.ok, dark), StatusChip(labels.smtp, !!smtp.ok, dark)],
      }),
      _jsxs("div", {
        style: { padding: "0 14px 14px", fontSize: 12, opacity: 0.75, lineHeight: 1.6 },
        children: [
          servers.pop3_host
            ? _jsx("div", {
                children: `${labels.pop3} ${servers.pop3_host}:${servers.pop3_port} ssl=${String(servers.pop3_ssl)}`,
              })
            : null,
          servers.smtp_host
            ? _jsx("div", {
                children: `${labels.smtp} ${servers.smtp_host}:${servers.smtp_port} starttls=${String(servers.smtp_starttls)}`,
              })
            : null,
          pop3.error ? _jsx("div", { children: pop3.error }) : null,
          smtp.error ? _jsx("div", { children: smtp.error }) : null,
        ],
      }),
    ],
  });
}

export function setup(host) {
  host.registerRenderer({ id: "mail_inbox_list", tools: ["mail_list"], component: InboxCard });
  host.registerRenderer({ id: "mail_message", tools: ["mail_read"], component: MessageCard });
  host.registerRenderer({ id: "mail_compose", tools: ["mail_send"], component: ComposeCard });
  host.registerRenderer({ id: "mail_probe", tools: ["mail_probe"], component: ProbeCard });
}
