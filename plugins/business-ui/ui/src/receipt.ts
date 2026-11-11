export type ResultType = "SUCCESS" | "BUSINESS_REJECTED" | "TECHNICAL_ERROR";
export type ResultStatus = "SUCCESS" | "BUSINESS_REJECTED" | "FAILED" | "UNKNOWN";
export type ReceiptEvent =
  | "BUSINESS_OPERATION_SUCCESS"
  | "BUSINESS_OPERATION_REJECTED"
  | "BUSINESS_OPERATION_ERROR"
  | "BUSINESS_OPERATION_RESOLVED"
  | "DOCUMENT_VIEW_REQUESTED";

export interface OperationResult {
  type: ResultType;
  status: ResultStatus | null;
  code: string | null;
  message: string | null;
  disclosable: boolean;
  safe_retry: boolean;
  idempotent: boolean;
  side_effect: boolean | null;
}

export interface CardState {
  documentType: string;
  recordId: string | null;
  formRef: string;
  schemaVersion: string;
  recordVersion: number;
  allowedActions: string[];
  interactionId: string | null;
  submissionStatus: string;
  approvalStatus: string;
  summary: Record<string, unknown>;
  operationId: string | null;
  result: OperationResult | null;
  navigation: Record<string, unknown> | null;
  event: ReceiptEvent | null;
  receiptSequence: number;
  claimRequired: boolean;
  connectionId: string | null;
  lastError: string | null;
}

const SENSITIVE = new Set([
  "password",
  "secret",
  "token",
  "access_token",
  "refresh_token",
  "client_secret",
  "ssn",
  "id_card",
  "bank_account",
]);

function object(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function str(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function num(value: unknown, fallback = 0): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

export function maskSensitive(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(maskSensitive);
  if (!object(value)) return value;
  const out: Record<string, unknown> = {};
  for (const [key, item] of Object.entries(value)) {
    const lower = key.toLowerCase();
    if (SENSITIVE.has(lower) || lower.endsWith("_secret") || lower.endsWith("_token")) {
      const text = String(item ?? "");
      out[key] = text.length <= 4 ? "****" : `${text.slice(0, 2)}****${text.slice(-2)}`;
    } else {
      out[key] = maskSensitive(item);
    }
  }
  return out;
}

export function parseResult(raw: unknown): OperationResult | null {
  if (!object(raw)) return null;
  const type = str(raw.type).toUpperCase();
  if (type !== "SUCCESS" && type !== "BUSINESS_REJECTED" && type !== "TECHNICAL_ERROR") return null;
  let status = str(raw.status).toUpperCase();
  if (type === "TECHNICAL_ERROR") {
    if (status !== "FAILED" && status !== "UNKNOWN") status = "UNKNOWN";
  } else {
    status = type;
  }
  const code = raw.code == null ? null : str(raw.code);
  const disclosable = raw.disclosable !== false && !(code && code.startsWith("INTERNAL_"));
  const message = disclosable && typeof raw.message === "string" ? raw.message.slice(0, 2000) : null;
  const sideEffect =
    typeof raw.side_effect === "boolean"
      ? raw.side_effect
      : typeof raw.sideEffect === "boolean"
        ? raw.sideEffect
        : null;
  let safeRetry = Boolean(raw.safe_retry ?? raw.safeRetry);
  const idempotent = Boolean(raw.idempotent);
  if (type !== "TECHNICAL_ERROR" || status !== "FAILED" || sideEffect === true) safeRetry = false;
  safeRetry = Boolean(safeRetry && (idempotent || sideEffect === false));
  return {
    type: type as ResultType,
    status: status as ResultStatus,
    code,
    message,
    disclosable: Boolean(disclosable && message),
    safe_retry: safeRetry,
    idempotent,
    side_effect: sideEffect,
  };
}

export function normalizeActions(actions: unknown): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  if (!Array.isArray(actions)) return out;
  for (const item of actions) {
    let name = str(item);
    if (name === "queryStatus") name = "query_status";
    if (name === "requestPermission") name = "request_permission";
    if (name === "view_detail") name = "view_document";
    if (!name || seen.has(name)) continue;
    seen.add(name);
    out.push(name);
  }
  return out;
}

export function buttonsFor(state: Pick<CardState, "result" | "recordId" | "allowedActions">): string[] {
  const result = state.result;
  const allowed = new Set(normalizeActions(state.allowedActions));
  const take = (...names: string[]) => names.filter((name) => allowed.has(name));
  if (!result) return take("edit", "save", "submit", "cancel", "close");
  if (result.type === "SUCCESS") {
    return [...(state.recordId ? take("view_document") : []), ...take("continue", "close")];
  }
  if (result.type === "BUSINESS_REJECTED") {
    return [
      ...(state.recordId ? take("view_document") : []),
      ...take("request_permission", "continue", "close"),
    ];
  }
  if (result.status === "UNKNOWN") return take("query_status", "close");
  return [...(result.safe_retry ? take("retry") : []), ...take("close")];
}

export function eventFor(result: OperationResult | null, resolved = false): ReceiptEvent | null {
  if (!result) return null;
  if (resolved) return "BUSINESS_OPERATION_RESOLVED";
  if (result.type === "SUCCESS") return "BUSINESS_OPERATION_SUCCESS";
  if (result.type === "BUSINESS_REJECTED") return "BUSINESS_OPERATION_REJECTED";
  return "BUSINESS_OPERATION_ERROR";
}

export function isStale(
  current: { recordVersion: number; receiptSequence: number },
  incoming: { recordVersion: number; receiptSequence: number },
): boolean {
  if (incoming.recordVersion < current.recordVersion) return true;
  return incoming.recordVersion === current.recordVersion && incoming.receiptSequence < current.receiptSequence;
}

function pick(raw: Record<string, unknown>, camel: string, snake: string): unknown {
  return raw[camel] ?? raw[snake];
}

export function parseCardState(raw: unknown, fallback: Partial<CardState> = {}): CardState {
  const data = object(raw) ? raw : {};
  const result = parseResult(pick(data, "result", "result"));
  const recordIdValue = pick(data, "recordId", "record_id");
  const state: CardState = {
    documentType: str(pick(data, "documentType", "document_type"), fallback.documentType || "generic_request"),
    recordId: recordIdValue == null || recordIdValue === "" ? null : str(recordIdValue),
    formRef: str(pick(data, "formRef", "form_ref"), fallback.formRef || "generic.request.edit"),
    schemaVersion: str(pick(data, "schemaVersion", "schema_version"), fallback.schemaVersion || "1"),
    recordVersion: num(pick(data, "recordVersion", "record_version"), fallback.recordVersion || 0),
    allowedActions: normalizeActions(pick(data, "allowedActions", "allowed_actions") ?? fallback.allowedActions),
    interactionId: (() => {
      const value = pick(data, "interactionId", "interaction_id");
      return value ? str(value) : fallback.interactionId || null;
    })(),
    submissionStatus: str(
      pick(data, "submissionStatus", "submission_status"),
      fallback.submissionStatus || "unclaimed",
    ),
    approvalStatus: str(
      pick(data, "approvalStatus", "approval_status"),
      fallback.approvalStatus || "not_applicable",
    ),
    summary: (maskSensitive(
      object(pick(data, "summary", "summary")) ? pick(data, "summary", "summary") : fallback.summary || {},
    ) || {}) as Record<string, unknown>,
    operationId: (() => {
      const value = pick(data, "operationId", "operation_id") ?? pick(data, "lastOperationId", "last_operation_id");
      return value ? str(value) : fallback.operationId || null;
    })(),
    result,
    navigation: object(pick(data, "navigation", "navigation"))
      ? (pick(data, "navigation", "navigation") as Record<string, unknown>)
      : fallback.navigation || null,
    event: (str(pick(data, "event", "event")) as ReceiptEvent) || eventFor(result),
    receiptSequence: num(pick(data, "receiptSequence", "receipt_sequence"), fallback.receiptSequence || 0),
    claimRequired: Boolean(pick(data, "claimRequired", "claim_required") ?? fallback.claimRequired ?? true),
    connectionId: (() => {
      const value = pick(data, "connectionId", "connection_id");
      return value ? str(value) : fallback.connectionId || null;
    })(),
    lastError: pick(data, "lastError", "last_error") ? str(pick(data, "lastError", "last_error")) : null,
  };
  if (result) state.allowedActions = buttonsFor(state);
  return state;
}

export function applyEvent(state: CardState, event: ReceiptEvent): CardState {
  if (event === "DOCUMENT_VIEW_REQUESTED") return { ...state, event };
  return { ...state, event };
}

export function shouldShowRecordId(state: CardState): boolean {
  if (!state.recordId) return false;
  if (state.result?.type === "BUSINESS_REJECTED" && !state.recordId) return false;
  return true;
}
