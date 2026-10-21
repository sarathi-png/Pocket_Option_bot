import { describe, expect, it } from "vitest";
import { apiErrorMessage, formatCountdown, formatPrice, secondsUntil } from "./format";

describe("format helpers", () => {
  it("formats prices with pair decimals", () => {
    expect(formatPrice(1.085423, 5)).toBe("1.08542");
    expect(formatPrice(155.4, 3)).toBe("155.400");
    expect(formatPrice(null, 5)).toBe("—");
  });

  it("formats countdowns", () => {
    expect(formatCountdown(125)).toBe("2:05");
    expect(formatCountdown(9)).toBe("0:09");
    expect(formatCountdown(-3)).toBe("expired");
  });

  it("computes seconds until expiry", () => {
    const now = new Date("2026-10-21T10:00:00Z");
    expect(secondsUntil("2026-10-21T10:02:00Z", now)).toBe(120);
  });

  it("extracts backend error messages without leaking internals", () => {
    expect(apiErrorMessage({ error: { code: "PAIR_NOT_FOUND", message: "Unknown pair" } })).toBe("Unknown pair");
    expect(apiErrorMessage(null)).toBe("Request failed. Please retry.");
    expect(apiErrorMessage("garbage")).toBe("Request failed. Please retry.");
  });
});
