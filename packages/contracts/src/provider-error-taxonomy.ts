/**
 * AgentVerse's internal provider-error taxonomy (CLAUDE.md §9 Provider
 * abstraction). The Python side
 * (`apps/api/.../orchestration_service/domain/provider_errors.py`) is
 * authoritative — every `code` value here is a hand-kept mirror of that
 * module's `ProviderError` subclasses, not generated, because this
 * internal route deliberately isn't part of the public OpenAPI surface
 * that `generated.ts` is built from.
 *
 * Kept here (not re-declared per consuming component) per CLAUDE.md
 * Rule 3: one source of truth for API/error codes shared across a
 * service boundary.
 */

export const PROVIDER_ERROR_CODES = [
  "provider_error",
  "rate_limited",
  "context_length_exceeded",
  "content_filtered",
  "provider_auth_failed",
  "invalid_request",
  "provider_unavailable",
] as const;

export type ProviderErrorCode = (typeof PROVIDER_ERROR_CODES)[number];

export interface ProviderErrorEvent {
  type: "error";
  code: ProviderErrorCode;
  message: string;
  retry_after_seconds: number | null;
}
