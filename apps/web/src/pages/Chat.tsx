import { useEffect, useState, useCallback, useRef } from "react";
import { useParams } from "react-router-dom";
import { listChat, sendChat } from "../api/client";
import { usePollingRefresh } from "../hooks/useLiveRefresh";
import type { ChatMessage } from "../api/types";

const BASE = import.meta.env.VITE_API_URL ?? "";

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem("odp_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function clearChatApi(projectId: string): Promise<void> {
  await fetch(`${BASE}/projects/${projectId}/chat`, {
    method: "DELETE",
    headers: authHeaders(),
  });
}

export default function Chat() {
  const { projectId } = useParams<{ projectId: string }>();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [clearing, setClearing] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  // Whether we should auto-scroll on the next messages update.
  const shouldScrollRef = useRef(true);

  const isNearBottom = () => {
    const el = containerRef.current;
    if (!el) return true;
    return el.scrollHeight - el.scrollTop - el.clientHeight < 120;
  };

  const scrollToBottom = (smooth = true) => {
    bottomRef.current?.scrollIntoView({ behavior: smooth ? "smooth" : "instant" });
  };

  const refresh = useCallback(async () => {
    if (!projectId) return;
    const c = await listChat(projectId).catch(() => ({ messages: [] }));
    // API returns oldest-first; preserve that order.
    setMessages(c.messages ?? []);
  }, [projectId]);

  useEffect(() => {
    refresh().then(() => scrollToBottom(false));
  }, [refresh]);

  // Only auto-scroll on poll if already near bottom.
  useEffect(() => {
    if (shouldScrollRef.current || isNearBottom()) {
      scrollToBottom();
      shouldScrollRef.current = false;
    }
  }, [messages]);

  // Poll every 3s for new messages.
  usePollingRefresh(refresh, 3000);

  const handleSend = async () => {
    if (!input.trim() || !projectId || sending) return;
    const text = input.trim();
    setSending(true);
    shouldScrollRef.current = true;

    setMessages((prev) => [
      ...prev,
      {
        id: `optimistic-${Date.now()}`,
        project_id: projectId,
        task_id: null,
        actor: "user",
        text,
        created_at: new Date().toISOString(),
        compaction_of: null,
      },
    ]);
    setInput("");

    try {
      await sendChat(projectId, text);
      shouldScrollRef.current = true;
      await refresh();
    } catch {
      setMessages((prev) => prev.filter((m) => !m.id.startsWith("optimistic-")));
      setInput(text);
    } finally {
      setSending(false);
    }
  };

  const handleClear = async () => {
    if (!projectId || clearing) return;
    setClearing(true);
    try {
      await clearChatApi(projectId);
      setMessages([]);
    } finally {
      setClearing(false);
    }
  };

  return (
    <>
      <div className="page-header">
        <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
          <h2>Orchestrator Chat</h2>
          <span className="subtitle">Project: Orchestrated Dev Platform</span>
        </div>
        <button
          className="btn btn-secondary"
          onClick={handleClear}
          disabled={clearing || messages.length === 0}
          style={{ marginLeft: "auto" }}
        >
          {clearing ? "Clearing…" : "Clear Chat"}
        </button>
      </div>

      <div className="card chat-container">
        <div className="chat-messages" ref={containerRef}>
          {messages.length === 0 && (
            <p className="text-muted" style={{ textAlign: "center", marginTop: 40 }}>
              No messages yet. Start a conversation with the orchestrator.
            </p>
          )}
          {messages.map((m) => (
            <div key={m.id} className={`chat-bubble ${m.actor}`}>
              <div className="actor">
                {m.actor === "user" ? "You" : "Orchestrator"}
              </div>
              {m.text}
            </div>
          ))}
          <div ref={bottomRef} />
        </div>

        <div className="chat-input-row">
          <input
            placeholder="Type a message..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
            disabled={sending}
          />
          <button className="btn btn-primary" onClick={handleSend} disabled={sending}>
            {sending ? "…" : "Send"}
          </button>
        </div>
      </div>
    </>
  );
}
