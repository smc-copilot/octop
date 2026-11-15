import { useCallback, useEffect, useMemo, useRef, useState } from "./host";
import type { PluginToolProps } from "./host";
import { runAction } from "./api";
import { ActivationPanel } from "./ActivationPanel";
import { BusinessReceiptCard } from "./BusinessReceiptCard";
import { FormFrame } from "./FormFrame";
import { applyEvent, isStale, parseCardState, type CardState } from "./receipt";
import { btn, cardStyle, tone } from "./styles";

export function BusinessCard(props: PluginToolProps) {
  const dark = (props.host.getToolContext() || {}).theme === "dark";
  const data = props.data && typeof props.data === "object" ? (props.data as Record<string, unknown>) : {};
  const callId = props.callId || "";
  const host = props.host;
  const [state, setState] = useState<CardState>(() => parseCardState(data));
  const [error, setError] = useState("");
  const [ticket, setTicket] = useState<Record<string, string> | null>(null);
  const [embedAction, setEmbedAction] = useState<string | null>(null);
  const [pageMode, setPageMode] = useState<"edit" | "readonly">("edit");
  const [connections, setConnections] = useState<Record<string, unknown>[]>([]);
  const [connectionId, setConnectionId] = useState(String(data.connectionId || data.connection_id || ""));
  const [busy, setBusy] = useState(false);
  const pollRef = useRef<number | null>(null);
  const seqRef = useRef({ recordVersion: state.recordVersion, receiptSequence: state.receiptSequence });

  const selected = useMemo(
    () => connections.find((row) => row.connection_id === connectionId) || null,
    [connections, connectionId],
  );
  const activated = Boolean(selected && selected.activation_status === "active");
  const inSidePanel = props.presentation?.location === "side-panel" && props.presentation.active;

  const patchSafe = (next: CardState, extra: Record<string, unknown> = {}) => {
    if (!callId) return;
    try {
      host.patchResult(callId, {
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
        claimRequired: false,
      });
    } catch {
      /* card update must not affect backend */
    }
  };

  const applyRemote = useCallback(
    (raw: unknown) => {
      const next = parseCardState(raw, state);
      if (
        state.interactionId &&
        next.interactionId === state.interactionId &&
        isStale(seqRef.current, { recordVersion: next.recordVersion, receiptSequence: next.receiptSequence })
      ) {
        return next;
      }
      seqRef.current = { recordVersion: next.recordVersion, receiptSequence: next.receiptSequence };
      setState(next);
      patchSafe(next);
      return next;
    },
    [state, callId],
  );

  const reloadConnections = useCallback(async () => {
    const res = await runAction<{ connections?: Record<string, unknown>[] }>(host, "connections.list", {}, false);
    const rows = res.connections || [];
    setConnections(rows);
    return rows;
  }, [host]);

  useEffect(() => {
    reloadConnections()
      .then((rows) => {
        if (!connectionId && rows[0]) setConnectionId(String(rows[0].connection_id || ""));
      })
      .catch(() => {});
  }, [host]);

  useEffect(() => {
    if (!callId) return;
    runAction(host, "interactions.lookup", { call_id: callId }, true)
      .then((raw) => applyRemote(raw))
      .catch(() => {});
  }, [callId, host]);

  const stopPoll = () => {
    if (pollRef.current) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  const hydrate = async (interactionId: string) => {
    if (!interactionId || !callId) return null;
    try {
      const next = await runAction(host, "interactions.get", { interaction_id: interactionId, call_id: callId }, true);
      return applyRemote(next);
    } catch (err) {
      setError(String((err as Error)?.message || err));
      return null;
    }
  };

  const openTicket = async (action: string, interactionId: string) => {
    const issued = await runAction<Record<string, string>>(
      host,
      "tickets.issue",
      { interaction_id: interactionId, call_id: callId, action },
      true,
    );
    setTicket(issued);
    setPageMode(issued.page_mode === "readonly" ? "readonly" : "edit");
    setEmbedAction(action);
    host.openSidePanel({ callId, title: action === "view_document" || action === "view_detail" ? "正式单据" : "Business form" });
  };

  const claimAndOpen = async (action: string) => {
    setError("");
    if (!connectionId) {
      setError("Select an approved connection");
      return;
    }
    if (!activated) {
      setError("需要激活/重新激活");
      return;
    }
    try {
      const claimed = await runAction<Record<string, unknown>>(
        host,
        "interactions.claim",
        {
          call_id: callId,
          connection_id: connectionId,
          document_type: state.documentType,
          form_ref: state.formRef,
          schema_version: state.schemaVersion,
          record_id: state.recordId,
          record_version: state.recordVersion,
          summary: state.summary,
        },
        true,
      );
      const next = applyRemote(claimed);
      await openTicket(action, String(next.interactionId));
    } catch (err) {
      setError(String((err as Error)?.message || err));
    }
  };

  const onReceiptAction = async (name: string) => {
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
          host,
          "interactions.query_status",
          { interaction_id: state.interactionId, call_id: callId, operation_id: state.operationId },
          true,
        );
        applyRemote(raw);
        return;
      }
      if (name === "retry") {
        const raw = await runAction(host, "interactions.retry", { interaction_id: state.interactionId, call_id: callId }, true);
        applyRemote(raw);
        return;
      }
      if (name === "close") {
        host.closeSidePanel(callId);
        return;
      }
      if (name === "continue" || name === "request_permission") {
        return;
      }
    } catch (err) {
      setError(String((err as Error)?.message || err));
    } finally {
      setBusy(false);
    }
  };

  const onHint = useCallback(
    (_hint: Record<string, unknown>) => {
      if (!state.interactionId) return;
      stopPoll();
      pollRef.current = window.setInterval(() => {
        hydrate(state.interactionId as string);
      }, 1500);
      hydrate(state.interactionId).then((next) => {
        if (!next?.result) return;
        stopPoll();
        if (next.result.type === "SUCCESS" && inSidePanel && pageMode === "edit" && next.recordId) {
          openTicket("view_document", next.interactionId as string).catch(() => {});
        }
      });
    },
    [state.interactionId, inSidePanel, pageMode],
  );

  useEffect(() => () => stopPoll(), []);

  const cancelled = state.submissionStatus === "cancelled";
  const showReceipt = Boolean(state.result);

  return (
    <div style={cardStyle(dark)} data-business-ui-card="1">
      <div style={{ fontWeight: 700, fontSize: 16 }}>{String(state.summary.title || "业务单据")}</div>
      <div style={{ opacity: 0.8, marginTop: 6, fontSize: 13 }}>{String(state.summary.body || props.textFallback || "")}</div>
      {error ? <div style={{ color: tone("err"), fontSize: 12, marginTop: 8 }}>{error}</div> : null}
      {showReceipt ? <BusinessReceiptCard state={state} dark={dark} busy={busy} onAction={onReceiptAction} /> : null}
      {!showReceipt && !cancelled ? (
        <div>
          <select value={connectionId} onChange={(ev) => setConnectionId(ev.target.value)} style={{ marginTop: 8, padding: 4 }}>
            <option value="">选择已批准连接</option>
            {connections.map((row) => (
              <option key={String(row.connection_id)} value={String(row.connection_id)}>
                {String(row.display_name)}
              </option>
            ))}
          </select>
          <ActivationPanel host={host} connection={selected} onChanged={reloadConnections} />
          {activated ? (
            <button type="button" style={btn(true)} onClick={() => claimAndOpen("edit")}>
              核对并编辑
            </button>
          ) : (
            <div style={{ color: tone("warn"), fontSize: 12, marginTop: 8 }}>需要激活/重新激活后才能打开表单。</div>
          )}
          <button
            type="button"
            style={btn(false)}
            onClick={async () => {
              if (!state.interactionId) {
                const next = { ...state, submissionStatus: "cancelled", allowedActions: [] };
                setState(next);
                patchSafe(next);
                return;
              }
              const raw = await runAction(host, "interactions.cancel", { interaction_id: state.interactionId, call_id: callId }, true);
              applyRemote(raw);
            }}
          >
            取消
          </button>
        </div>
      ) : null}
      {ticket && state.interactionId ? (
        <FormFrame
          redeemUrl={ticket.redeem_url}
          ticket={ticket.ticket}
          nonce={ticket.nonce}
          origin={ticket.form_origin}
          interactionId={state.interactionId}
          onHint={onHint}
        />
      ) : null}
    </div>
  );
}
