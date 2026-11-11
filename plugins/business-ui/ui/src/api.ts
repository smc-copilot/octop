import type { PluginToolHost } from "./host";

const PLUGIN = "business-ui";

export function ctxOf(host: PluginToolHost) {
  const t = host.getToolContext() || { agentId: null, threadId: null, locale: "en", theme: "light" as const };
  const context: Record<string, string> = {};
  if (t.agentId) context.agent_id = t.agentId;
  if (t.threadId) context.thread_id = t.threadId;
  return Object.keys(context).length ? context : undefined;
}

export async function runAction<T = Record<string, unknown>>(
  host: PluginToolHost,
  name: string,
  payload: object,
  withScope: boolean,
): Promise<T> {
  const body: Record<string, unknown> = { api_version: 1, payload: payload || {} };
  if (withScope) {
    const context = ctxOf(host);
    if (context) body.context = context;
  }
  const res = await host.request<{ result?: T } & T>("/plugins/" + PLUGIN + "/actions/" + name, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (res && typeof res === "object" && "result" in res && res.result) return res.result;
  return res as T;
}
