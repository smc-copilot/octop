export type PluginJson =
  | null
  | boolean
  | number
  | string
  | readonly PluginJson[]
  | { readonly [key: string]: PluginJson };

export interface PluginToolContext {
  agentId: string | null;
  threadId: string | null;
  locale: string;
  theme: "light" | "dark";
}

export interface PluginToolHost {
  request<T = unknown>(path: string, init?: RequestInit): Promise<T>;
  getToolContext(): PluginToolContext;
  patchResult(callId: string, nextData: unknown): void;
  openSidePanel(options: { callId: string; title?: string; toolName?: string }): void;
  closeSidePanel(callId: string): void;
}

export interface PluginToolProps {
  pluginId: string;
  toolName: string;
  displayName?: string;
  callId?: string;
  status: "running" | "done" | "error";
  args: unknown;
  data: unknown;
  textFallback?: string;
  host: PluginToolHost;
  presentation?: {
    location: "inline" | "side-panel";
    active: boolean;
    state?: PluginJson;
  };
  output?: string;
  isStreaming: boolean;
}

export interface PluginSetupHost {
  registerRenderer(registration: {
    id: string;
    tools: string[];
    component: (props: PluginToolProps) => unknown;
  }): void;
}

type ReactHost = {
  Fragment: unknown;
  createElement: (...args: any[]) => any;
  useCallback: (...args: any[]) => any;
  useEffect: (...args: any[]) => any;
  useMemo: (...args: any[]) => any;
  useRef: (...args: any[]) => any;
  useState: (...args: any[]) => any;
};
type JsxHost = {
  Fragment: unknown;
  jsx: (...args: any[]) => any;
  jsxs: (...args: any[]) => any;
};

function react(): ReactHost {
  return (window as unknown as { __OCTOP_REACT__: ReactHost }).__OCTOP_REACT__;
}
function jsxHost(): JsxHost {
  return (window as unknown as { __OCTOP_JSX__: JsxHost }).__OCTOP_JSX__;
}

export const Fragment = Symbol.for("react.fragment");
export const jsx = (...args: any[]) => jsxHost().jsx(...args);
export const jsxs = (...args: any[]) => jsxHost().jsxs(...args);
export const createElement = (...args: any[]) => react().createElement(...args);
export function useCallback<T extends (...args: any[]) => any>(callback: T, deps: unknown[]): T {
  return react().useCallback(callback, deps);
}
export function useEffect(effect: () => void | (() => void), deps?: unknown[]): void {
  react().useEffect(effect, deps);
}
export function useMemo<T>(factory: () => T, deps: unknown[]): T {
  return react().useMemo(factory, deps);
}
export function useRef<T>(initial: T): { current: T } {
  return react().useRef(initial);
}
export function useState<T>(
  initial: T | (() => T),
): [T, (value: T | ((previous: T) => T) ) => void] {
  return react().useState(initial);
}
