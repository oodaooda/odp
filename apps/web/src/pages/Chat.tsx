import { useEffect, useState, useCallback, useRef } from "react";
import { useParams } from "react-router-dom";
import { listChat, sendChat } from "../api/client";
import { usePollingRefresh } from "../hooks/useLiveRefresh";
import type { ChatMessage } from "../api/types";

export default function Chat() {
  const { projectId } = useParams<{ projectId: string }>();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const refresh = useCallback(async () => {
    if (!projectId) return;
    const c = await listChat(projectId).catch(() => ({ messages: [] }));
    setMessages(c.messages ?? []);
  }, [projectId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Poll every 3s for new messages (chat doesn't have a task-specific WS)
  usePollingRefresh(refresh, 3000);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || !projectId || sending) return;
    const text = input.trim();
    setSending(true);

    // Optimistic: show message immediately
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
      // Refresh to get the real message with server ID
      await refresh();
    } catch {
      // Remove optimistic message on failure
      setMessages((prev) => prev.filter((m) => !m.id.startsWith("optimistic-")));
      setInput(text);
    } finally {
      setSending(false);
    }
  };

  return (
    <>
      <div className="page-header">
        <div style={{ display: "flex", alignItems: "baseline" }}>
          <h2>Orchestrator Chat</h2>
          <span className="subtitle">Project: Orchestrated Dev Platform</span>
        </div>
      </div>

      <div className="card chat-container">
        <div className="chat-messages">
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
            {sending ? "..." : "Send"}
          </button>
        </div>
      </div>
    </>
  );
}
