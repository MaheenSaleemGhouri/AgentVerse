"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { AssistantStreamEvent } from "@/lib/assistant/types";

export type AnswerStatus = "idle" | "streaming" | "done" | "error";

interface UseAssistantAnswerResult {
  /** The answer so far. Grows during streaming. */
  readonly text: string;
  readonly status: AnswerStatus;
  readonly error: string | null;
  readonly ask: (sessionId: string, question: string) => Promise<void>;
  readonly reset: () => void;
}

const FLUSH_INTERVAL_MS = 80;

/**
 * Streams one answer from the BFF route.
 *
 * `fetch` rather than `EventSource`, because the question is a request
 * body and `EventSource` is GET-only.
 *
 * Deltas are buffered in a ref and flushed on an interval rather than
 * calling `setState` per event (CLAUDE.md §6): a token-per-render
 * assistant re-renders the whole panel dozens of times a second, and on
 * a page that already has a dashboard under it that is visible jank.
 *
 * An in-flight request is aborted on unmount and when a new question
 * starts — a stream still writing into state after the panel closes is
 * the leak this hook is responsible for not creating.
 */
export function useAssistantAnswer(workspaceId: string): UseAssistantAnswerResult {
  const [text, setText] = useState("");
  const [status, setStatus] = useState<AnswerStatus>("idle");
  const [error, setError] = useState<string | null>(null);

  const bufferRef = useRef("");
  const controllerRef = useRef<AbortController | null>(null);

  useEffect(
    () => () => {
      controllerRef.current?.abort();
    },
    []
  );

  const reset = useCallback(() => {
    controllerRef.current?.abort();
    bufferRef.current = "";
    setText("");
    setError(null);
    setStatus("idle");
  }, []);

  const ask = useCallback(
    async (sessionId: string, question: string) => {
      controllerRef.current?.abort();
      const controller = new AbortController();
      controllerRef.current = controller;

      bufferRef.current = "";
      setText("");
      setError(null);
      setStatus("streaming");

      const flush = (): void => {
        if (bufferRef.current === "") return;
        const batch = bufferRef.current;
        bufferRef.current = "";
        setText((previous) => previous + batch);
      };
      const intervalId = window.setInterval(flush, FLUSH_INTERVAL_MS);

      try {
        const response = await fetch(
          `/api/assistant/${sessionId}?workspaceId=${encodeURIComponent(workspaceId)}`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question }),
            signal: controller.signal,
          }
        );

        if (!response.ok || response.body === null) {
          throw new Error("The assistant is unavailable right now.");
        }

        const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
        // SSE frames are separated by a blank line, and a chunk can end
        // mid-frame — so the tail is carried forward rather than parsed.
        let pending = "";

        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;

          pending += value;
          const frames = pending.split("\n\n");
          pending = frames.pop() ?? "";

          for (const frame of frames) {
            const line = frame.trim();
            if (!line.startsWith("data:")) continue;

            const event = JSON.parse(line.slice(5).trim()) as AssistantStreamEvent;
            if (event.type === "delta") {
              bufferRef.current += event.text;
            } else if (event.type === "error") {
              throw new Error(event.message);
            }
          }
        }

        flush();
        setStatus("done");
      } catch (caught) {
        if (controller.signal.aborted) return;
        flush();
        setError(caught instanceof Error ? caught.message : "Something went wrong.");
        setStatus("error");
      } finally {
        window.clearInterval(intervalId);
      }
    },
    [workspaceId]
  );

  return { text, status, error, ask, reset };
}
