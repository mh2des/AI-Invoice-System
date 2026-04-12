"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { sendChatMessage, sendChatWithImage } from "@/lib/api";
import type { ChatMessage } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { ImageIcon, Send, X, Bot, Sparkles, FileText, HelpCircle } from "lucide-react";

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [sending, setSending] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  const handleSend = async (prefill?: string) => {
    const text = (prefill || input).trim();
    if (!text && files.length === 0) return;

    const imageUrls: string[] = [];
    for (const f of files) {
      const url = URL.createObjectURL(f);
      imageUrls.push(url);
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
      if (currentFiles.length > 0) {
        const res = await sendChatWithImage(
          text || "Please analyze this receipt/invoice.",
          history,
          currentFiles
        );
        reply = res.reply;
      } else {
        const res = await sendChatMessage(text, history);
        reply = res.reply;
      }

      setMessages((prev) => [...prev, { role: "assistant", text: reply }]);
    } catch (err) {
      console.error(err);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: "Sorry, something went wrong. Please try again.",
        },
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

  return (
    <div className="flex flex-col h-[calc(100vh-3.5rem)]">
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
                  {msg.role === "assistant" && i === 0 + (messages[0]?.role === "user" ? 1 : 0) && (
                    <p className="text-xs font-semibold text-primary mb-1.5">Imam</p>
                  )}
                  <div
                    className="text-[15px] leading-relaxed whitespace-pre-wrap break-words"
                    dangerouslySetInnerHTML={{
                      __html:
                        msg.role === "assistant"
                          ? formatMarkdown(msg.text)
                          : escapeHtml(msg.text),
                    }}
                  />
                </div>
              </div>
            ))}

            {sending && (
              <div className="flex gap-3 justify-start">
                <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center mt-0.5">
                  <Bot className="h-4 w-4 text-primary" />
                </div>
                <div className="bg-muted/60 rounded-2xl px-4 py-3">
                  <p className="text-xs font-semibold text-primary mb-1.5">Imam</p>
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
                <span className="text-xs text-muted-foreground">
                  {formatSize(f.size)}
                </span>
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
  );
}

function formatMarkdown(text: string): string {
  return escapeHtml(text)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(
      /`(.+?)`/g,
      '<code class="bg-muted px-1.5 py-0.5 rounded text-sm font-mono">$1</code>'
    )
    .replace(/^• /gm, "• ")
    .replace(/\n/g, "<br/>");
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
