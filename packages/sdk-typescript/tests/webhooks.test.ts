/**
 * Verifying an inbound webhook.
 *
 * The expected digests are the same literals the platform's own suites
 * pin (`apps/api`, `apps/worker`) and the Python SDK repeats. If they
 * diverge, a customer using this SDK cannot verify a real delivery —
 * which looks, from their side, exactly like our signatures being broken.
 */

import { describe, expect, it } from "vitest";

import {
  DEFAULT_TOLERANCE_SECONDS,
  SignatureVerificationError,
  computeSignature,
  verifyWebhook,
} from "../src/webhooks.js";

const SECRET = "whsec_deadbeef";
const TIMESTAMP = 1_800_000_000;
const BODY = '{"id":"evt_1","type":"run.completed"}';

const EXPECTED_EMPTY_OBJECT = "bdbde3be09b48f018e8bfbaaaceadc664aaee6bbc7a1d2489d33f0f50c9e674c";
const EXPECTED_EVENT = "53e42645290d85bfbc1615823cb3bcb7a956c8b7c1ce9d2704a9de4337136e56";

function header(options: { secret?: string; timestamp?: number; body?: string } = {}): string {
  const timestamp = options.timestamp ?? TIMESTAMP;
  const digest = computeSignature({
    payload: options.body ?? BODY,
    secret: options.secret ?? SECRET,
    timestamp,
  });
  return `t=${String(timestamp)},v1=${digest}`;
}

describe("wire contract", () => {
  it("matches the platform's digest for an empty object", () => {
    expect(computeSignature({ payload: "{}", secret: SECRET, timestamp: TIMESTAMP })).toBe(
      EXPECTED_EMPTY_OBJECT,
    );
  });

  it("matches the platform's digest for a real event", () => {
    expect(computeSignature({ payload: BODY, secret: SECRET, timestamp: TIMESTAMP })).toBe(
      EXPECTED_EVENT,
    );
  });

  it("agrees between a string and the same bytes", () => {
    expect(
      computeSignature({
        payload: new TextEncoder().encode(BODY),
        secret: SECRET,
        timestamp: TIMESTAMP,
      }),
    ).toBe(EXPECTED_EVENT);
  });
});

describe("verification", () => {
  it("accepts a genuine delivery", () => {
    const event = verifyWebhook({
      payload: BODY,
      signatureHeader: header(),
      secret: SECRET,
      now: TIMESTAMP,
    });
    expect(event.type).toBe("run.completed");
    expect(event.id).toBe("evt_1");
  });

  it("rejects a forged signature", () => {
    expect(() =>
      verifyWebhook({
        payload: BODY,
        signatureHeader: `t=${String(TIMESTAMP)},v1=${"0".repeat(64)}`,
        secret: SECRET,
        now: TIMESTAMP,
      }),
    ).toThrow(SignatureVerificationError);
  });

  it("rejects a signature made with a different secret", () => {
    expect(() =>
      verifyWebhook({
        payload: BODY,
        signatureHeader: header({ secret: "whsec_someone_elses" }),
        secret: SECRET,
        now: TIMESTAMP,
      }),
    ).toThrow(SignatureVerificationError);
  });

  it("rejects a tampered body", () => {
    expect(() =>
      verifyWebhook({
        payload: BODY.replace("completed", "failed!!!"),
        signatureHeader: header(),
        secret: SECRET,
        now: TIMESTAMP,
      }),
    ).toThrow(SignatureVerificationError);
  });

  it("rejects a re-serialized body", () => {
    // The most common integration mistake, asserted so the docs are not
    // the only place it is stated: the signature is over bytes, and
    // `JSON.stringify(JSON.parse(x))` is not always `x`.
    const reserialized = JSON.stringify(JSON.parse(BODY) as unknown, null, 2);
    expect(reserialized).not.toBe(BODY);
    expect(() =>
      verifyWebhook({
        payload: reserialized,
        signatureHeader: header(),
        secret: SECRET,
        now: TIMESTAMP,
      }),
    ).toThrow(SignatureVerificationError);
  });

  it("rejects a signature of a different length without throwing from the comparison", () => {
    // `timingSafeEqual` throws on unequal lengths, which would surface as
    // a TypeError rather than a verification failure — and leak the
    // expected length.
    expect(() =>
      verifyWebhook({
        payload: BODY,
        signatureHeader: `t=${String(TIMESTAMP)},v1=short`,
        secret: SECRET,
        now: TIMESTAMP,
      }),
    ).toThrow(SignatureVerificationError);
  });
});

describe("replay window", () => {
  it("rejects a stale delivery", () => {
    expect(() =>
      verifyWebhook({
        payload: BODY,
        signatureHeader: header(),
        secret: SECRET,
        now: TIMESTAMP + DEFAULT_TOLERANCE_SECONDS + 1,
      }),
    ).toThrow(/tolerance/);
  });

  it("rejects a delivery from the future", () => {
    // A receiver whose clock runs fast would otherwise accept deliveries
    // stamped ahead of it forever.
    expect(() =>
      verifyWebhook({
        payload: BODY,
        signatureHeader: header(),
        secret: SECRET,
        now: TIMESTAMP - DEFAULT_TOLERANCE_SECONDS - 1,
      }),
    ).toThrow(/tolerance/);
  });

  it("accepts a delivery inside the window", () => {
    expect(
      verifyWebhook({
        payload: BODY,
        signatureHeader: header(),
        secret: SECRET,
        now: TIMESTAMP + DEFAULT_TOLERANCE_SECONDS - 1,
      }).type,
    ).toBe("run.completed");
  });

  it("checks the timestamp before the digest", () => {
    // A stale delivery should cost nothing to discard.
    expect(() =>
      verifyWebhook({
        payload: BODY,
        signatureHeader: `t=${String(TIMESTAMP)},v1=${"0".repeat(64)}`,
        secret: SECRET,
        now: TIMESTAMP + 10_000,
      }),
    ).toThrow(/tolerance/);
  });

  it("can be disabled deliberately", () => {
    expect(
      verifyWebhook({
        payload: BODY,
        signatureHeader: header(),
        secret: SECRET,
        toleranceSeconds: 0,
        now: Date.now() / 1000,
      }).id,
    ).toBe("evt_1");
  });
});

describe("header parsing", () => {
  it("rejects a header with no timestamp", () => {
    expect(() =>
      verifyWebhook({
        payload: BODY,
        signatureHeader: `v1=${"0".repeat(64)}`,
        secret: SECRET,
        now: TIMESTAMP,
      }),
    ).toThrow(SignatureVerificationError);
  });

  it("rejects a header with no digest", () => {
    expect(() =>
      verifyWebhook({
        payload: BODY,
        signatureHeader: `t=${String(TIMESTAMP)}`,
        secret: SECRET,
        now: TIMESTAMP,
      }),
    ).toThrow(SignatureVerificationError);
  });

  it("rejects a non-numeric timestamp", () => {
    expect(() =>
      verifyWebhook({
        payload: BODY,
        signatureHeader: `t=yesterday,v1=${"0".repeat(64)}`,
        secret: SECRET,
        now: TIMESTAMP,
      }),
    ).toThrow(SignatureVerificationError);
  });

  it("considers every digest, not just the first", () => {
    // The format allows several so a rotation can be signed under both.
    // A parser reading only the first would reject half the deliveries
    // during exactly the window rotation exists to make safe.
    const good = computeSignature({ payload: BODY, secret: SECRET, timestamp: TIMESTAMP });
    expect(
      verifyWebhook({
        payload: BODY,
        signatureHeader: `t=${String(TIMESTAMP)},v1=${"0".repeat(64)},v1=${good}`,
        secret: SECRET,
        now: TIMESTAMP,
      }).id,
    ).toBe("evt_1");
  });

  it("ignores an unknown version rather than trusting it", () => {
    expect(() =>
      verifyWebhook({
        payload: BODY,
        signatureHeader: `t=${String(TIMESTAMP)},v99=anything`,
        secret: SECRET,
        now: TIMESTAMP,
      }),
    ).toThrow(SignatureVerificationError);
  });
});

describe("parsed event", () => {
  it("exposes the envelope fields", () => {
    const body = JSON.stringify({
      id: "evt_abc",
      type: "run.completed",
      api_version: "v1",
      created_at: "2026-08-06T12:00:00+00:00",
      data: { run_id: "r1" },
    });
    const event = verifyWebhook({
      payload: body,
      signatureHeader: header({ body }),
      secret: SECRET,
      now: TIMESTAMP,
    });
    expect(event.api_version).toBe("v1");
    expect(event.data).toEqual({ run_id: "r1" });
  });

  it("turns a missing data object into an empty one", () => {
    // A receiver should not have to guard `event.data` for null.
    const event = verifyWebhook({
      payload: BODY,
      signatureHeader: header(),
      secret: SECRET,
      now: TIMESTAMP,
    });
    expect(event.data).toEqual({});
  });

  it("rejects a verified body that is not JSON", () => {
    const body = "not json at all";
    expect(() =>
      verifyWebhook({
        payload: body,
        signatureHeader: header({ body }),
        secret: SECRET,
        now: TIMESTAMP,
      }),
    ).toThrow(SignatureVerificationError);
  });

  it("rejects a verified body that is an array", () => {
    const body = "[1,2,3]";
    expect(() =>
      verifyWebhook({
        payload: body,
        signatureHeader: header({ body }),
        secret: SECRET,
        now: TIMESTAMP,
      }),
    ).toThrow(SignatureVerificationError);
  });
});
