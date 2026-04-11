"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { sendChatMessage, sendChatWithImage } from "@/lib/api";
import type { ChatMessage } from "@/lib/types";

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

    // Build user message with image previews
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
      // Build history (exclude images, only text)
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

      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: reply },
      ]);
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
    <div className="flex flex-col h-[calc(100vh-3.5rem)] md:h-screen">
      {/* Header */}
      <div className="border-b border-gray-200 bg-white px-4 md:px-6 py-4">
        <h1 className="text-lg font-bold text-gray-900">AI Assistant</h1>
        <p className="text-xs text-gray-500">
          Chat about invoices, send receipts for analysis
        </p>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 md:px-6 py-4 space-y-4">
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[85%] md:max-w-[70%] rounded-2xl px-4 py-3 ${
                msg.role === "user"
                  ? "bg-blue-600 text-white"
                  : "bg-white border border-gray-200 text-gray-900"
              }`}
            >
              {/* Images */}
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
              {/* Text with markdown-like formatting */}
              <div
                className={`text-sm whitespace-pre-wrap break-words ${
                  msg.role === "user" ? "" : "prose prose-sm max-w-none"
                }`}
                dangerouslySetInnerHTML={{
                  __html: msg.role === "assistant"
                    ? formatMarkdown(msg.text)
                    : escapeHtml(msg.text),
                }}
              />
            </div>
          </div>
        ))}

        {/* Typing indicator */}
        {sending && (
          <div className="flex justify-start">
            <div className="bg-white border border-gray-200 rounded-2xl px-4 py-3">
              <div className="flex items-center gap-1">
                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:-0.3s]" />
                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:-0.15s]" />
                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" />
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* File preview */}
      {files.length > 0 && (
        <div className="px-4 md:px-6 py-2 border-t border-gray-100 bg-gray-50">
          <div className="flex flex-wrap gap-2">
            {files.map((f, i) => (
              <div
                key={i}
                className="flex items-center gap-2 bg-white border border-gray-200 rounded-lg px-3 py-1.5"
              >
                <span className="text-sm">🖼️</span>
                <span className="text-xs text-gray-700 truncate max-w-[120px]">
                  {f.name}
                </span>
                <span className="text-xs text-gray-400">
                  {formatSize(f.size)}
                </span>
                <button
                  onClick={() => removeFile(i)}
                  className="text-gray-400 hover:text-red-500 text-xs ml-1"
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Input */}
      <div className="border-t border-gray-200 bg-white px-4 md:px-6 py-3">
        <div className="flex items-end gap-2">
          {/* Image upload button */}
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={sending}
            className="text-gray-400 hover:text-gray-600 p-2 rounded-lg hover:bg-gray-100 transition-colors disabled:opacity-50 flex-shrink-0"
            title="Attach image"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
              />
            </svg>
          </button>
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

          {/* Text input */}
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about invoices, or send a receipt image…"
            rows={1}
            disabled={sending}
            className="flex-1 resize-none border border-gray-300 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 max-h-32"
            style={{ minHeight: "42px" }}
            onInput={(e) => {
              const target = e.target as HTMLTextAreaElement;
              target.style.height = "auto";
              target.style.height = Math.min(target.scrollHeight, 128) + "px";
            }}
          />

          {/* Send button */}
          <button
            onClick={handleSend}
            disabled={sending || (!input.trim() && files.length === 0)}
            className="bg-blue-600 text-white p-2.5 rounded-xl hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex-shrink-0"
            title="Send"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"
              />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}

/** Simple markdown-to-HTML for assistant messages. */
function formatMarkdown(text: string): string {
  return escapeHtml(text)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/`(.+?)`/g, '<code class="bg-gray-100 px-1 py-0.5 rounded text-xs font-mono">$1</code>')
    .replace(/^• /gm, "• ")
    .replace(/\n/g, "<br/>");
}

/** Escape HTML entities. */
function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
