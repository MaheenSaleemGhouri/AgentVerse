"use client";

import { CornerDownLeft, Loader2, Sparkles } from "lucide-react";
import * as React from "react";

import {
  listAssistantMessagesAction,
  openAssistantSessionAction,
} from "@/lib/api/actions";
import { MAX_QUESTION_LENGTH, type AssistantMessage } from "@/lib/assistant/types";
import { useAssistantAnswer } from "@/lib/hooks/useAssistantAnswer";

import { AssistantAnswer } from "@/components/assistant/assistant-answer";
import { AgentVerseMascot } from "@/components/brand/agentverse-mascot";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Textarea } from "@/components/ui/textarea";

const SUGGESTIONS = [
  "How do I publish an agent version?",
  "Where do I see why a run failed?",
  "What can a viewer do?",
] as const;

/**
 * The conversation.
 *
 * One session per panel opening rather than a persistent thread list:
 * help conversations are short and topical, and a sidebar of past
 * questions is a filing system for something nobody files. The sessions
 * are still persisted and listable — the API supports the history — this
 * surface just does not lead with it.
 */
export function AssistantPanel({ workspaceId }: { workspaceId: string }): React.JSX.Element {
  const [sessionId, setSessionId] = React.useState<string | null>(null);
  const [messages, setMessages] = React.useState<AssistantMessage[]>([]);
  const [draft, setDraft] = React.useState("");
  const [opening, setOpening] = React.useState(false);
  const [openError, setOpenError] = React.useState<string | null>(null);

  const { text, status, error, ask } = useAssistantAnswer(workspaceId);
  const bottomRef = React.useRef<HTMLDivElement>(null);

  const busy = opening || status === "streaming";

  // Follow the answer as it streams, the way a chat surface is expected
  // to. `smooth` is deliberately not used: at flush frequency it lags
  // behind the text it is chasing.
  React.useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [messages, text]);

  const send = React.useCallback(
    async (question: string) => {
      const trimmed = question.trim();
      if (trimmed === "" || busy) return;

      setDraft("");
      setOpenError(null);

      let activeSession = sessionId;
      if (activeSession === null) {
        setOpening(true);
        try {
          activeSession = (await openAssistantSessionAction(workspaceId, trimmed)).id;
          setSessionId(activeSession);
        } catch {
          setOpenError("Could not start a conversation. Check your connection and try again.");
          setDraft(trimmed);
          return;
        } finally {
          setOpening(false);
        }
      }

      // Shown optimistically. The API has already persisted it by the
      // time the first token arrives, and re-fetching to display the
      // user's own words would add a round trip to show them something
      // they just typed.
      setMessages((current) => [
        ...current,
        {
          id: `local-${current.length}`,
          role: "user",
          content: trimmed,
          created_at: new Date().toISOString(),
        },
      ]);

      await ask(activeSession, trimmed);

      // Reconcile against the server once the answer is complete, so the
      // transcript that persists is the one the API stored — including
      // the case where it stored nothing because the turn failed.
      try {
        setMessages(await listAssistantMessagesAction(workspaceId, activeSession));
      } catch {
        // The answer is already on screen; a failed reconcile is not
        // worth an error state over.
      }
    },
    [ask, busy, sessionId, workspaceId]
  );

  return (
    <div className="flex h-full flex-col">
      <ScrollArea className="flex-1 px-4">
        <div className="space-y-4 py-4">
          {messages.length === 0 && status === "idle" && (
            <div className="space-y-3">
              <AgentVerseMascot pose="thinking" className="h-20 w-auto" />
              <p className="text-sm text-muted-foreground">
                Ask about anything in AgentVerse. Answers come from the documentation and link
                back to it, so you can check them.
              </p>
              <div className="flex flex-col items-start gap-2">
                {SUGGESTIONS.map((suggestion) => (
                  <Button
                    key={suggestion}
                    variant="outline"
                    size="sm"
                    className="h-auto py-1.5 text-left whitespace-normal"
                    onClick={() => void send(suggestion)}
                  >
                    {suggestion}
                  </Button>
                ))}
              </div>
            </div>
          )}

          {messages.map((message) =>
            message.role === "user" ? (
              <p
                key={message.id}
                className="ml-auto w-fit max-w-[85%] rounded-lg bg-accent px-3 py-2 text-sm text-accent-foreground"
              >
                {message.content}
              </p>
            ) : (
              <AssistantAnswer key={message.id} markdown={message.content} />
            )
          )}

          {/* The streaming answer is rendered outside `messages` until
              the reconcile replaces it, so it never appears twice. */}
          {status === "streaming" && (
            <div aria-live="polite" aria-busy="true">
              {text === "" ? (
                <p className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                  Reading the documentation…
                </p>
              ) : (
                <AssistantAnswer markdown={text} />
              )}
            </div>
          )}

          {(error ?? openError) !== null && (
            <p role="alert" className="text-sm text-destructive">
              {openError ?? error}
            </p>
          )}

          <div ref={bottomRef} />
        </div>
      </ScrollArea>

      <form
        className="border-t border-border p-3"
        onSubmit={(event) => {
          event.preventDefault();
          void send(draft);
        }}
      >
        <label htmlFor="assistant-question" className="sr-only">
          Ask the AgentVerse assistant
        </label>
        <Textarea
          id="assistant-question"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            // Enter sends, Shift+Enter breaks a line — the convention
            // for this shape of input, and the one a developer's hands
            // already expect.
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void send(draft);
            }
          }}
          placeholder="Ask a question…"
          maxLength={MAX_QUESTION_LENGTH}
          rows={2}
          className="resize-none"
          disabled={busy}
        />
        <div className="mt-2 flex items-center justify-between">
          <p className="text-xs text-muted-foreground">
            <CornerDownLeft className="mr-1 inline size-3" aria-hidden="true" />
            Enter to send
          </p>
          <Button type="submit" size="sm" disabled={busy || draft.trim() === ""}>
            {busy ? (
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
            ) : (
              <Sparkles className="size-4" aria-hidden="true" />
            )}
            Ask
          </Button>
        </div>
      </form>
    </div>
  );
}
