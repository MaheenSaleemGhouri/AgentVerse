/**
 * Client-safe assistant types and constants.
 *
 * Separate from `lib/api/assistant.ts` because that module is
 * `server-only`: a Client Component importing a *value* from it drags
 * `next/headers` into the browser bundle and fails the production build.
 * `lib/server-only-boundary.test.ts` is the gate that catches it.
 */

export interface AssistantSession {
  id: string;
  title: string;
  created_at: string;
  last_message_at: string;
}

export interface AssistantMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

/** Matches `MAX_QUESTION_LENGTH` in the API's domain entities. The cap
 * is enforced server-side; this one only keeps the textarea from letting
 * someone paste past a limit they cannot see. */
export const MAX_QUESTION_LENGTH = 2000;

/** One frame of the SSE answer stream, matching the API's `_serialize`. */
export type AssistantStreamEvent =
  | { type: "delta"; text: string }
  | { type: "done"; finish_reason: string }
  | { type: "error"; code: string; message: string };
