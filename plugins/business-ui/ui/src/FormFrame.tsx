import { useEffect, useRef } from "./host";

export function FormFrame(props: {
  redeemUrl: string;
  ticket: string;
  nonce: string;
  origin: string;
  interactionId: string;
  onHint: (hint: Record<string, unknown>) => void;
}) {
  const { redeemUrl, ticket, nonce, origin, interactionId, onHint } = props;
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const formRef = useRef<HTMLFormElement | null>(null);
  useEffect(() => {
    formRef.current?.submit();
  }, [ticket, redeemUrl]);
  useEffect(() => {
    function onMsg(ev: MessageEvent) {
      if (ev.origin !== origin) return;
      if (!iframeRef.current || ev.source !== iframeRef.current.contentWindow) return;
      const data = (ev.data || {}) as Record<string, unknown>;
      if (data.type !== "business-ui/hint") return;
      if (data.interactionId !== interactionId) return;
      if (data.nonce && data.nonce !== nonce) return;
      onHint(data);
    }
    window.addEventListener("message", onMsg);
    return () => window.removeEventListener("message", onMsg);
  }, [origin, interactionId, nonce, onHint]);
  return (
    <div style={{ height: "100%", minHeight: 360, width: "100%" }}>
      <form ref={formRef} method="POST" action={redeemUrl} target={"bui-frame-" + interactionId} style={{ display: "none" }}>
        <input type="hidden" name="ticket" value={ticket} />
        <input type="hidden" name="nonce" value={nonce} />
      </form>
      <iframe
        ref={iframeRef}
        name={"bui-frame-" + interactionId}
        title="Business form"
        sandbox="allow-scripts allow-forms allow-same-origin"
        style={{ width: "100%", height: 420, border: 0, background: "#fff" }}
      />
    </div>
  );
}
