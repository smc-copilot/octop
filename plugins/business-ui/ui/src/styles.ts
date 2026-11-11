export function cardStyle(dark: boolean): Record<string, string | number> {
  return {
    fontFamily: "ui-sans-serif, system-ui, sans-serif",
    width: "100%",
    maxWidth: "100%",
    boxSizing: "border-box",
    border: "1px solid var(--ant-color-border, " + (dark ? "#334155" : "#e2e8f0") + ")",
    borderRadius: 12,
    padding: 16,
    background: "var(--ant-color-bg-container, " + (dark ? "#0f172a" : "#fff") + ")",
    color: "var(--ant-color-text, " + (dark ? "#e2e8f0" : "#0f172a") + ")",
  };
}

export function btn(primary: boolean, disabled = false): Record<string, string | number> {
  return {
    marginRight: 8,
    marginTop: 8,
    padding: "6px 12px",
    borderRadius: 8,
    border: "1px solid var(--ant-color-primary, " + (primary ? "#2563eb" : "#94a3b8") + ")",
    background: primary ? "var(--ant-color-primary, #2563eb)" : "transparent",
    color: primary ? "var(--ant-color-text-light-solid, #fff)" : "inherit",
    cursor: disabled ? "not-allowed" : "pointer",
    opacity: disabled ? 0.55 : 1,
  };
}

export function tone(kind: "ok" | "warn" | "err" | "muted"): string {
  if (kind === "ok") return "var(--ant-color-success, #15803d)";
  if (kind === "warn") return "var(--ant-color-warning, #b45309)";
  if (kind === "err") return "var(--ant-color-error, #b91c1c)";
  return "var(--ant-color-text-secondary, #64748b)";
}
