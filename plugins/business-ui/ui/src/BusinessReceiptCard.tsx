import { useState } from "./host";
import type { CardState } from "./receipt";
import { shouldShowRecordId } from "./receipt";
import { btn, tone } from "./styles";

const LABELS: Record<string, string> = {
  view_document: "查看正式单据",
  continue: "继续",
  request_permission: "申请权限",
  retry: "安全重试",
  query_status: "查询状态",
  close: "关闭",
};

function headline(state: CardState): { title: string; color: string } {
  const type = state.result?.type;
  const status = state.result?.status;
  if (type === "SUCCESS") return { title: "已成功", color: tone("ok") };
  if (type === "BUSINESS_REJECTED") return { title: "业务已拒绝", color: tone("warn") };
  if (type === "TECHNICAL_ERROR" && status === "UNKNOWN") {
    return { title: "结果未知（请查询，勿重复提交）", color: tone("warn") };
  }
  if (type === "TECHNICAL_ERROR") return { title: "技术失败", color: tone("err") };
  return { title: "处理中", color: tone("muted") };
}

export function BusinessReceiptCard(props: {
  state: CardState;
  dark: boolean;
  busy?: boolean;
  onAction: (name: string) => void;
}) {
  const { state, onAction, busy } = props;
  const [expanded, setExpanded] = useState(false);
  const head = headline(state);
  const message = state.result?.disclosable ? state.result?.message : null;
  const long = Boolean(message && message.length > 160);
  const shown = message && long && !expanded ? message.slice(0, 160) + "…" : message;
  return (
    <div data-business-receipt-card="1" style={{ marginTop: 10 }}>
      <div style={{ fontWeight: 700, color: head.color }}>{head.title}</div>
      {state.result?.code && state.result.disclosable ? (
        <div style={{ fontSize: 12, marginTop: 4, color: tone("muted") }}>原因代码 {state.result.code}</div>
      ) : null}
      {shouldShowRecordId(state) ? (
        <div style={{ fontSize: 12, marginTop: 4 }}>单号 {state.recordId}</div>
      ) : null}
      {state.operationId ? (
        <div style={{ fontSize: 12, color: tone("muted") }}>operationId {state.operationId}</div>
      ) : null}
      {shown ? (
        <div style={{ fontSize: 12, marginTop: 8, whiteSpace: "pre-wrap" }}>
          {shown}
          {long ? (
            <button type="button" style={btn(false)} onClick={() => setExpanded(!expanded)}>
              {expanded ? "收起" : "展开"}
            </button>
          ) : null}
        </div>
      ) : null}
      <div>
        {state.allowedActions.map((name) =>
          LABELS[name] ? (
            <button
              key={name}
              type="button"
              data-receipt-action={name}
              style={btn(name === "view_document" || name === "query_status" || name === "retry", busy)}
              disabled={busy}
              onClick={() => onAction(name)}
            >
              {LABELS[name]}
            </button>
          ) : null,
        )}
      </div>
    </div>
  );
}
