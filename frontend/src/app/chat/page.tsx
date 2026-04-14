"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import {
  sendChatMessage,
  sendChatWithImage,
  listChatSessions,
  getChatSession,
  deleteChatSession,
} from "@/lib/api";
import type { ChatMessage, SessionSummary } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import {
  ImageIcon,
  Send,
  X,
  Bot,
  Sparkles,
  FileText,
  HelpCircle,
  History,
  Plus,
  Trash2,
  ChevronLeft,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [sending, setSending] = useState(false);
  const [sessionId, setSessionId] = useState<number | null>(null);

  // History sidebar state
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  const loadSessions = useCallback(async () => {
    setLoadingSessions(true);
    try {
      const data = await listChatSessions();
      setSessions(data);
    } catch {
      // silent
    } finally {
      setLoadingSessions(false);
    }
  }, []);

  const openSidebar = () => {
    setSidebarOpen(true);
    loadSessions();
  };

  const loadSession = async (id: number) => {
    try {
      const detail = await getChatSession(id);
      const msgs: ChatMessage[] = detail.messages.map((m) => ({
        role: m.role as "user" | "assistant",
        text: m.text,
      }));
      setMessages(msgs);
      setSessionId(detail.id);
      setSidebarOpen(false);
    } catch {
      // silent
    }
  };

  const handleDeleteSession = async (e: React.MouseEvent, id: number) => {
    e.stopPropagation();
    try {
      await deleteChatSession(id);
      setSessions((prev) => prev.filter((s) => s.id !== id));
      if (sessionId === id) {
        setMessages([]);
        setSessionId(null);
      }
    } catch {
      // silent
    }
  };

  const startNewChat = () => {
    setMessages([]);
    setSessionId(null);
    setSidebarOpen(false);
  };

  const handleSend = async (prefill?: string) => {
    const text = (prefill || input).trim();
    if (!text && files.length === 0) return;

    const imageUrls: string[] = [];
    for (const f of files) {
      imageUrls.push(URL.createObjectURL(f));
    }

    const userMsg: ChatMessage = {
      role: "user",
      text: text || "(image attached)",
      images: imageUrls.length > 0 ? imageUrls : undefined,
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    const currentFiles = [...files];
    setFiles([]);
    setSending(true);

    try {
      const history = messages
        .filter((m) => m.text)
        .map((m) => ({ role: m.role, text: m.text }));

      let reply: string;
      let newSessionId: number;

      if (currentFiles.length > 0) {
        const res = await sendChatWithImage(text || "Please analyze this receipt/invoice.", history, currentFiles, sessionId);
        reply = res.reply;
        newSessionId = res.session_id;
      } else {
        const res = await sendChatMessage(text, history, sessionId);
        reply = res.reply;
        newSessionId = res.session_id;
      }

      setSessionId(newSessionId);
      setMessages((prev) => [...prev, { role: "assistant", text: reply }]);
    } catch (err) {
      console.error(err);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: "Sorry, something went wrong. Please try again." },
      ]);
    } finally {
      setSending(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const suggestions = [
    { icon: FileText, label: "Analyze a receipt", prompt: "I want to analyze a receipt" },
    { icon: HelpCircle, label: "What did I spend this week?", prompt: "What did I spend this week?" },
    { icon: Sparkles, label: "Summarize my invoices", prompt: "Summarize all my invoices" },
  ];

  const showWelcome = messages.length === 0;

  // Group sessions by date label
  const groupedSessions = groupByDate(sessions);

  return (
    <div className="flex h-[calc(100vh-3.5rem)] overflow-hidden">
      {/* ── History Sidebar ── */}
      {sidebarOpen && (
        <div className="w-72 border-r bg-muted/30 flex flex-col flex-shrink-0 overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b">
            <span className="font-semibold text-[15px]">Chat History</span>
            <button
              onClick={() => setSidebarOpen(false)}
              className="text-muted-foreground hover:text-foreground transition-colors"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
          </div>

          <div className="px-3 py-2 border-b">
            <button
              onClick={startNewChat}
              className="flex items-center gap-2 w-full rounded-lg px-3 py-2 text-sm font-medium hover:bg-primary/10 text-primary transition-colors"
            >
              <Plus className="h-4 w-4" />
              New Chat
            </button>
          </div>

          <div className="flex-1 overflow-y-auto px-2 py-2">
            {loadingSessions && (
              <p className="text-xs text-muted-foreground px-2 py-4 text-center">Loading…</p>
            )}
            {!loadingSessions && sessions.length === 0 && (
              <p className="text-xs text-muted-foreground px-2 py-4 text-center">No saved chats yet</p>
            )}
            {Object.entries(groupedSessions).map(([label, group]) => (
              <div key={label} className="mb-3">
                <p className="text-[11px] font-semibold uppercase text-muted-foreground px-2 mb-1 tracking-wide">
                  {label}
                </p>
                {group.map((s) => (
                  <button
                    key={s.id}
                    onClick={() => loadSession(s.id)}
                    className={cn(
                      "group w-full text-left rounded-lg px-3 py-2 mb-0.5 transition-colors hover:bg-muted",
                      sessionId === s.id && "bg-muted"
                    )}
                  >
                    <p className="text-sm font-medium truncate leading-tight">
                      {s.title || "Untitled"}
                    </p>
                    {s.last_message && (
                      <p className="text-xs text-muted-foreground truncate mt-0.5">
                        {s.last_message}
                      </p>
                    )}
                    <div className="flex items-center justify-between mt-1">
                      <span className="text-[11px] text-muted-foreground">
                        {s.message_count / 2 | 0} exchanges
                      </span>
                      <button
                        onClick={(e) => handleDeleteSession(e, s.id)}
                        className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive transition-all"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </button>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Main Chat Area ── */}
      <div className="flex flex-col flex-1 min-w-0">
        {/* Toolbar */}
        <div className="flex items-center gap-2 px-4 py-2 border-b bg-background">
          <button
            onClick={openSidebar}
            className={cn(
              "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted hover:text-foreground transition-colors",
              sidebarOpen && "bg-muted text-foreground"
            )}
          >
            <History className="h-4 w-4" />
            History
          </button>
          {sessionId && (
            <button
              onClick={startNewChat}
              className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
            >
              <Plus className="h-4 w-4" />
              New Chat
            </button>
          )}
          {sessionId && (
            <span className="ml-auto text-xs text-muted-foreground">
              Session #{sessionId} — auto-saved
            </span>
          )}
        </div>

        {/* Messages or Welcome */}
        <div className="flex-1 overflow-y-auto">
          {showWelcome ? (
            <div className="flex flex-col items-center justify-center h-full px-4">
              <div className="flex items-center justify-center w-16 h-16 rounded-2xl bg-primary/10 mb-5">
                <Bot className="h-8 w-8 text-primary" />
              </div>
              <h1 className="text-2xl font-bold tracking-tight mb-1">Imam</h1>
              <p className="text-muted-foreground text-base mb-8">
                Your AI accounting assistant
              </p>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 w-full max-w-xl">
                {suggestions.map((s) => (
                  <button
                    key={s.label}
                    onClick={() => handleSend(s.prompt)}
                    className="group flex flex-col items-center gap-2 rounded-xl border bg-card p-4 text-center transition-all hover:border-primary/40 hover:shadow-sm"
                  >
                    <s.icon className="h-5 w-5 text-muted-foreground transition-transform duration-200 group-hover:scale-110" />
                    <span className="text-sm font-medium">{s.label}</span>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="px-4 md:px-6 py-4 space-y-5 max-w-3xl mx-auto">
              {messages.map((msg, i) => (
                <div
                  key={i}
                  className={cn(
                    "flex gap-3",
                    msg.role === "user" ? "justify-end" : "justify-start"
                  )}
                >
                  {msg.role === "assistant" && (
                    <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center mt-0.5">
                      <Bot className="h-4 w-4 text-primary" />
                    </div>
                  )}
                  <div
                    className={cn(
                      "max-w-[80%] md:max-w-[70%] rounded-2xl px-4 py-3",
                      msg.role === "user"
                        ? "bg-primary text-primary-foreground"
                        : "bg-muted/60 text-foreground"
                    )}
                  >
                    {msg.images && msg.images.length > 0 && (
                      <div className="flex flex-wrap gap-2 mb-2">
                        {msg.images.map((url, j) => (
                          <img
                            key={j}
                            src={url}
                            alt="Attached"
                            className="max-w-[200px] max-h-[200px] rounded-lg object-cover"
                          />
                        ))}
                      </div>
                    )}
                    {msg.role === "assistant" ? (
                      <div className="chat-markdown">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {msg.text}
                        </ReactMarkdown>
                      </div>
                    ) : (
                      <div className="text-[15px] leading-relaxed whitespace-pre-wrap break-words">
                        {msg.text}
                      </div>
                    )}
                  </div>
                </div>
              ))}

              {sending && (
                <div className="flex gap-3 justify-start">
                  <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center mt-0.5">
                    <Bot className="h-4 w-4 text-primary" />
                  </div>
                  <div className="bg-muted/60 rounded-2xl px-4 py-3">
                    <div className="flex items-center gap-1.5">
                      <div className="w-2 h-2 bg-muted-foreground/60 rounded-full animate-bounce [animation-delay:-0.3s]" />
                      <div className="w-2 h-2 bg-muted-foreground/60 rounded-full animate-bounce [animation-delay:-0.15s]" />
                      <div className="w-2 h-2 bg-muted-foreground/60 rounded-full animate-bounce" />
                    </div>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* File preview bar */}
        {files.length > 0 && (
          <div className="px-4 md:px-6 py-2 border-t bg-muted/30">
            <div className="flex flex-wrap gap-2 max-w-3xl mx-auto">
              {files.map((f, i) => (
                <div
                  key={i}
                  className="flex items-center gap-2 bg-card border rounded-lg px-3 py-1.5"
                >
                  <ImageIcon className="h-4 w-4 text-muted-foreground" />
                  <span className="text-sm truncate max-w-[120px]">{f.name}</span>
                  <span className="text-xs text-muted-foreground">{formatSize(f.size)}</span>
                  <button
                    onClick={() => removeFile(i)}
                    className="text-muted-foreground hover:text-destructive ml-1 transition-colors"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Input bar */}
        <div className="border-t px-4 md:px-6 py-3 bg-background">
          <div className="flex items-end gap-2 max-w-3xl mx-auto">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => fileInputRef.current?.click()}
              disabled={sending}
              className="flex-shrink-0 group"
            >
              <ImageIcon className="h-5 w-5 transition-transform duration-200 group-hover:scale-110" />
            </Button>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*,application/pdf"
              multiple
              onChange={(e) => {
                if (e.target.files) {
                  setFiles((prev) => [...prev, ...Array.from(e.target.files!)]);
                }
                e.target.value = "";
              }}
              className="hidden"
            />

            <Textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask Imam about invoices, or send a receipt…"
              rows={1}
              disabled={sending}
              className="flex-1 resize-none min-h-[44px] max-h-32 rounded-xl text-[15px]"
              onInput={(e) => {
                const target = e.target as HTMLTextAreaElement;
                target.style.height = "auto";
                target.style.height = Math.min(target.scrollHeight, 128) + "px";
              }}
            />

            <Button
              size="icon"
              onClick={() => handleSend()}
              disabled={sending || (!input.trim() && files.length === 0)}
              className="flex-shrink-0 rounded-xl group"
            >
              <Send className="h-5 w-5 transition-transform duration-200 group-hover:scale-110" />
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

function groupByDate(sessions: SessionSummary[]): Record<string, SessionSummary[]> {
  const now = new Date();
  const result: Record<string, SessionSummary[]> = {};

  for (const s of sessions) {
    const d = new Date(s.updated_at);
    const diffDays = Math.floor((now.getTime() - d.getTime()) / (1000 * 60 * 60 * 24));
    let label: string;
    if (diffDays === 0) label = "Today";
    else if (diffDays === 1) label = "Yesterday";
    else if (diffDays < 7) label = "This Week";
    else if (diffDays < 30) label = "This Month";
    else label = "Older";

    if (!result[label]) result[label] = [];
    result[label].push(s);
  }
  return result;
}
