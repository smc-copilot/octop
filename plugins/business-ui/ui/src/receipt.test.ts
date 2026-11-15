import { describe, expect, it } from "vitest";
import {
  buttonsFor,
  eventFor,
  isStale,
  maskSensitive,
  parseCardState,
  parseResult,
} from "./receipt";

describe("receipt parser", () => {
  it("parses SUCCESS / REJECTED / TECHNICAL_ERROR", () => {
    expect(parseResult({ type: "SUCCESS" })?.type).toBe("SUCCESS");
    expect(parseResult({ type: "BUSINESS_REJECTED", code: "PERMISSION_DENIED" })?.type).toBe(
      "BUSINESS_REJECTED",
    );
    expect(parseResult({ type: "TECHNICAL_ERROR" })?.status).toBe("UNKNOWN");
    expect(
      parseResult({
        type: "TECHNICAL_ERROR",
        status: "FAILED",
        safe_retry: true,
        idempotent: true,
        side_effect: false,
      })?.safe_retry,
    ).toBe(true);
    expect(
      parseResult({
        type: "TECHNICAL_ERROR",
        status: "FAILED",
        safe_retry: true,
        side_effect: true,
      })?.safe_retry,
    ).toBe(false);
    expect(parseResult({ type: "NOPE" })).toBeNull();
  });

  it("masks secrets and hides internal codes", () => {
    const masked = maskSensitive({ title: "ok", password: "supersecret" }) as { password: string };
    expect(masked.password).not.toContain("supersecret");
    expect(parseResult({ type: "SUCCESS", code: "INTERNAL_TRACE", message: "stack", disclosable: true })?.message).toBeNull();
  });

  it("generates buttons from allowedActions + result", () => {
    expect(
      buttonsFor({
        result: { type: "SUCCESS", status: "SUCCESS", code: null, message: null, disclosable: true, safe_retry: false, idempotent: true, side_effect: true },
        recordId: "REQ-1",
        allowedActions: ["view_detail", "edit", "submit", "close"],
      }),
    ).toEqual(["view_document", "close"]);
    expect(
      buttonsFor({
        result: { type: "BUSINESS_REJECTED", status: "BUSINESS_REJECTED", code: "PERMISSION_DENIED", message: "no", disclosable: true, safe_retry: false, idempotent: true, side_effect: false },
        recordId: null,
        allowedActions: ["edit", "view_document", "request_permission", "close"],
      }),
    ).toEqual(["request_permission", "close"]);
    expect(
      buttonsFor({
        result: { type: "TECHNICAL_ERROR", status: "UNKNOWN", code: "X", message: "?", disclosable: true, safe_retry: false, idempotent: false, side_effect: null },
        recordId: null,
        allowedActions: ["query_status", "retry", "submit", "close"],
      }),
    ).toEqual(["query_status", "close"]);
  });

  it("orders receipts by recordVersion then sequence", () => {
    expect(isStale({ recordVersion: 4, receiptSequence: 8 }, { recordVersion: 3, receiptSequence: 99 })).toBe(true);
    expect(isStale({ recordVersion: 4, receiptSequence: 8 }, { recordVersion: 4, receiptSequence: 7 })).toBe(true);
    expect(isStale({ recordVersion: 4, receiptSequence: 8 }, { recordVersion: 5, receiptSequence: 1 })).toBe(false);
  });

  it("parses mixed camel/snake card payloads", () => {
    const state = parseCardState({
      interaction_id: "int-abc",
      record_id: "REQ-1",
      form_ref: "generic.request.edit",
      record_version: 2,
      allowed_actions: ["view_detail", "close"],
      result: { type: "SUCCESS" },
      event: "BUSINESS_OPERATION_SUCCESS",
    });
    expect(state.interactionId).toBe("int-abc");
    expect(state.recordId).toBe("REQ-1");
    expect(state.allowedActions).toContain("view_document");
    expect(eventFor(state.result)).toBe("BUSINESS_OPERATION_SUCCESS");
  });
});
