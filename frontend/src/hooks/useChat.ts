import { useCallback, useRef, useState } from "react";
import type { ChatMessage, PhaseInfo } from "../types";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

let _msgId = 0;
function nextId(): string {
  return `msg-${++_msgId}-${Date.now()}`;
}

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [phase, setPhase] = useState<PhaseInfo | null>(null);
  const [sessionId, setSessionId] = useState(() => {
    return `session-${Math.random().toString(36).slice(2, 8)}`;
  });

  const abortRef = useRef<AbortController | null>(null);

  /* ---------------------------------------------------------------- */
  /*  Send a message using SSE streaming                              */
  /* ---------------------------------------------------------------- */
  const sendMessage = useCallback(
    async (question: string) => {
      if (!question.trim() || isLoading) return;

      const userMsg: ChatMessage = {
        id: nextId(),
        role: "user",
        content: question.trim(),
      };

      const assistantId = nextId();
      const assistantMsg: ChatMessage = {
        id: assistantId,
        role: "assistant",
        content: "",
        isStreaming: true,
      };

      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      setIsLoading(true);
      setPhase(null);

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const resp = await fetch(`${API_URL}/chat/stream`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sessionId, question: question.trim() }),
          signal: controller.signal,
        });

        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          throw new Error(err?.detail || `Request failed (${resp.status})`);
        }

        const contentType = resp.headers.get("content-type") || "";

        if (contentType.includes("text/event-stream")) {
          /* ---------- SSE streaming path ---------- */
          await parseSSE(resp, assistantId);
        } else {
          /* ---------- JSON fallback (Q&A returned JSON instead of SSE) ---------- */
          const data = await resp.json();
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? {
                    ...m,
                    content: data.answer || data.formatted_report || "",
                    isStreaming: false,
                    meta: {
                      viewKey: data.view_key,
                      sql: data.sql,
                      isInsight: data.is_insight,
                    },
                  }
                : m,
            ),
          );
        }
      } catch (err: unknown) {
        if (err instanceof DOMException && err.name === "AbortError") return;
        const errorMsg = err instanceof Error ? err.message : "Unknown error";
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, content: `**Error:** ${errorMsg}`, isStreaming: false }
              : m,
          ),
        );
      } finally {
        setIsLoading(false);
        setPhase(null);
        abortRef.current = null;
      }
    },
    [isLoading, sessionId],
  );

  /* ---------------------------------------------------------------- */
  /*  Parse SSE event stream                                          */
  /* ---------------------------------------------------------------- */
  async function parseSSE(resp: Response, assistantId: string) {
    const reader = resp.body?.getReader();
    if (!reader) throw new Error("No readable stream");

    const decoder = new TextDecoder();
    let buffer = "";
    let accumulatedText = "";
    let meta: ChatMessage["meta"] = {};

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      let currentEvent = "";
      for (const line of lines) {
        if (line.startsWith("event: ")) {
          currentEvent = line.slice(7).trim();
        } else if (line.startsWith("data: ")) {
          const raw = line.slice(6);
          let data: Record<string, unknown>;
          try {
            data = JSON.parse(raw);
          } catch {
            continue;
          }

          switch (currentEvent) {
            case "phase":
              setPhase(data as unknown as PhaseInfo);
              break;

            case "meta":
              meta = {
                ...meta,
                viewKey: data.view_key as string | undefined,
                sql: data.sql as string | undefined,
                rowCount: data.row_count as number | undefined,
              };
              break;

            case "token": {
              const token = data.token as string;
              accumulatedText += token;
              const snapshot = accumulatedText;
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId ? { ...m, content: snapshot } : m,
                ),
              );
              break;
            }

            case "done": {
              const fullText = (data.full_text as string) || accumulatedText;
              const finalMeta: ChatMessage["meta"] = {
                ...meta,
                viewKey:
                  (data.view_key as string) ||
                  (data.report_key as string) ||
                  meta?.viewKey,
                sql: (data.sql as string) || meta?.sql,
                isInsight: !!(data.report_key as string),
                reportKey: data.report_key as string | undefined,
              };
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? { ...m, content: fullText, isStreaming: false, meta: finalMeta }
                    : m,
                ),
              );
              break;
            }

            case "error": {
              const errorText = data.error as string;
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? { ...m, content: `**Error:** ${errorText}`, isStreaming: false }
                    : m,
                ),
              );
              break;
            }
          }
        }
      }
    }

    /* If stream ended without a "done" event, finalize */
    setMessages((prev) =>
      prev.map((m) =>
        m.id === assistantId && m.isStreaming
          ? { ...m, isStreaming: false, meta }
          : m,
      ),
    );
  }

  /* ---------------------------------------------------------------- */
  /*  Utilities                                                       */
  /* ---------------------------------------------------------------- */
  const clearChat = useCallback(() => {
    setMessages([]);
    setPhase(null);
    setSessionId(`session-${Math.random().toString(36).slice(2, 8)}`);
  }, []);

  const stopStreaming = useCallback(() => {
    abortRef.current?.abort();
    setIsLoading(false);
    setPhase(null);
    setMessages((prev) =>
      prev.map((m) => (m.isStreaming ? { ...m, isStreaming: false } : m)),
    );
  }, []);

  return {
    messages,
    isLoading,
    phase,
    sessionId,
    setSessionId,
    sendMessage,
    clearChat,
    stopStreaming,
  };
}
