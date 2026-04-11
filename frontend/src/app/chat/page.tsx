"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { sendChatMessage, sendChatWithImage } from "@/lib/api";
import type { ChatMessage } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { ImageIcon, Send, X } from "lucide-react";

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: "assistant",
      text: "Hello! I'm your AI accounting assistant. You can:\n\n• **Send me a receipt/invoice image** and I'll analyze it\n• **Ask questions** about your invoices, products, or suppliers\n• **Request summaries** like \"What did I spend this week?\"\n\nHow can I help you today?",
    },
  ]);
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

  const handleSend = async () => {
    const text = input.trim();
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

  return (
    <div className="flex flex-col h-[calc(100vh-3.5rem)]">
      <div className="border-b px-4 md:px-6 py-4">
        <h1 className="text-lg font-bold">AI Assistant</h1>
        <p className="text-xs text-muted-foreground">
          Chat about invoices, send receipts for analysis
        </p>
      </div>

      <div className="flex-1 overflow-y-auto px-4 md:px-6 py-4 space-y-4">
        {messages.map((msg, i) => (
          <div
            key={i}
            className={cn(
              "flex",
              msg.role === "user" ? "justify-end" : "justify-start"
            )}
          >
            <div
              className={cn(
                "max-w-[85%] md:max-w-[70%] rounded-2xl px-4 py-3",
                msg.role === "user"
                  ? "bg-primary text-primary-foreground"
                  : "bg-card border text-card-foreground"
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
              <div
                className={cn(
                  "text-sm whitespace-pre-wrap break-words",
                  msg.role === "assistant" && "prose prose-sm max-w-none"
                )}
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
          <div className="flex justify-start">
            <div className="bg-card border rounded-2xl px-4 py-3">
              <div className="flex items-center gap-1">
                <div className="w-2 h-2 bg-muted-foreground rounded-full animate-bounce [animation-delay:-0.3s]" />
                <div className="w-2 h-2 bg-muted-foreground rounded-full animate-bounce [animation-delay:-0.15s]" />
                <div className="w-2 h-2 bg-muted-foreground rounded-full animate-bounce" />
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {files.length > 0 && (
        <div className="px-4 md:px-6 py-2 border-t bg-muted/50">
          <div className="flex flex-wrap gap-2">
            {files.map((f, i) => (
              <div
                key={i}
                className="flex items-center gap-2 bg-card border rounded-lg px-3 py-1.5"
              >
                <ImageIcon className="h-4 w-4 text-muted-foreground" />
                <span className="text-xs truncate max-w-[120px]">{f.name}</span>
                <span className="text-xs text-muted-foreground">
                  {formatSize(f.size)}
                </span>
                <button
                  onClick={() => removeFile(i)}
                  className="text-muted-foreground hover:text-destructive ml-1"
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="border-t px-4 md:px-6 py-3">
        <div className="flex items-end gap-2">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => fileInputRef.current?.click()}
            disabled={sending}
            className="flex-shrink-0"
          >
            <ImageIcon className="h-5 w-5" />
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
            placeholder="Ask about invoices, or send a receipt image…"
            rows={1}
            disabled={sending}
            className="flex-1 resize-none min-h-[42px] max-h-32 rounded-xl"
            onInput={(e) => {
              const target = e.target as HTMLTextAreaElement;
              target.style.height = "auto";
              target.style.height = Math.min(target.scrollHeight, 128) + "px";
            }}
          />

          <Button
            size="icon"
            onClick={handleSend}
            disabled={sending || (!input.trim() && files.length === 0)}
            className="flex-shrink-0 rounded-xl"
          >
            <Send className="h-5 w-5" />
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
      '<code class="bg-muted px-1 py-0.5 rounded text-xs font-mono">$1</code>'
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
