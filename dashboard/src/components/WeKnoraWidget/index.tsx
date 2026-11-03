import { useEffect } from "react";

/**
 * WeKnora floating chat launcher. Mount only under AuthGuard so the
 * widget never appears on /login, /setup, or /invite.
 */

const SCRIPT_ID = "weknora-widget-sdk";
const STYLE_ID = "weknora-widget-offset";
const SCRIPT_SRC = "http://weknora.superic.com:18080/weknora-widget.js";
const BASE_URL = "http://weknora.superic.com:18080";
const CHANNEL = "5f44f925-5304-47bb-930e-408bc8ac4886";
const TOKEN = "em_PBugOUedW6jZGgiN4kuOxIRjlPVqZtqRanWMHko2_Nk";
const TITLE = "芯助手";
const PRIMARY_COLOR = "#07c05f";

type WeKnoraApi = {
  init: (opts: Record<string, unknown>) => unknown;
  destroy: () => void;
};

declare global {
  interface Window {
    WeKnora?: WeKnoraApi;
  }
}

function ensureOffsetCss(): void {
  if (document.getElementById(STYLE_ID)) return;
  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
button[aria-label="${TITLE}"] {
  bottom: 200px !important;
}
body > div:has(> iframe[src*="weknora.superic.com"]) {
  bottom: 264px !important;
}
`;
  document.head.appendChild(style);
}

function loadSdk(): Promise<WeKnoraApi> {
  const existing = window.WeKnora;
  if (existing) return Promise.resolve(existing);

  const prior = document.getElementById(SCRIPT_ID) as HTMLScriptElement | null;
  if (prior) {
    return new Promise((resolve, reject) => {
      prior.addEventListener("load", () => {
        if (window.WeKnora) resolve(window.WeKnora);
        else reject(new Error("WeKnora global missing after load"));
      });
      prior.addEventListener("error", () =>
        reject(new Error("WeKnora script failed")),
      );
    });
  }

  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.id = SCRIPT_ID;
    script.src = SCRIPT_SRC;
    script.async = true;
    script.onload = () => {
      if (window.WeKnora) resolve(window.WeKnora);
      else reject(new Error("WeKnora global missing"));
    };
    script.onerror = () => reject(new Error("WeKnora script failed"));
    document.body.appendChild(script);
  });
}

export default function WeKnoraWidget() {
  useEffect(() => {
    let cancelled = false;

    void (async () => {
      try {
        const api = await loadSdk();
        if (cancelled) return;
        ensureOffsetCss();
        api.init({
          channel: CHANNEL,
          token: TOKEN,
          position: "bottom-right",
          primaryColor: PRIMARY_COLOR,
          title: TITLE,
          baseUrl: BASE_URL,
        });
      } catch (err) {
        console.warn("[WeKnoraWidget]", err);
      }
    })();

    return () => {
      cancelled = true;
      window.WeKnora?.destroy();
    };
  }, []);

  return null;
}
