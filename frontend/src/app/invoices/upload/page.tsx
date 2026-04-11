"use client";

import { useState, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import { uploadInvoice } from "@/lib/api";

export default function UploadInvoicePage() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);

  const ALLOWED_TYPES = [
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "image/tiff",
    "application/pdf",
  ];

  const addFiles = useCallback(
    (newFiles: FileList | File[]) => {
      const valid: File[] = [];
      for (const f of Array.from(newFiles)) {
        if (!ALLOWED_TYPES.includes(f.type)) {
          setError(`Unsupported file type: ${f.name}. Use images or PDF.`);
          return;
        }
        if (f.size > 20 * 1024 * 1024) {
          setError(`File too large: ${f.name}. Maximum 20MB.`);
          return;
        }
        valid.push(f);
      }
      setError(null);
      setFiles((prev) => [...prev, ...valid]);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      if (e.dataTransfer.files.length) {
        addFiles(e.dataTransfer.files);
      }
    },
    [addFiles]
  );

  const handleUpload = async () => {
    if (files.length === 0) return;
    setUploading(true);
    setError(null);
    try {
      const invoice = await uploadInvoice(files);
      router.push(`/invoices/${invoice.id}`);
    } catch (err) {
      console.error(err);
      setError(err instanceof Error ? err.message : "Upload failed");
      setUploading(false);
    }
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="p-4 md:p-8 max-w-2xl">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Upload Invoice</h1>
        <p className="text-sm text-gray-500 mt-1">
          Upload invoice images or PDF. AI will extract items automatically.
        </p>
      </div>

      {/* Drop zone */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-colors ${
          dragOver
            ? "border-blue-500 bg-blue-50"
            : "border-gray-300 hover:border-gray-400 bg-white"
        }`}
      >
        <div className="text-4xl mb-3">📤</div>
        <p className="text-sm font-medium text-gray-700">
          Drag & drop files here, or click to browse
        </p>
        <p className="text-xs text-gray-400 mt-1">
          JPEG, PNG, WebP, GIF, TIFF, or PDF — max 20MB each
        </p>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*,application/pdf"
          multiple
          onChange={(e) => {
            if (e.target.files) addFiles(e.target.files);
            e.target.value = "";
          }}
          className="hidden"
        />
      </div>

      {/* File list */}
      {files.length > 0 && (
        <div className="mt-4 space-y-2">
          {files.map((f, i) => (
            <div
              key={`${f.name}-${i}`}
              className="flex items-center justify-between bg-white border border-gray-200 rounded-lg px-4 py-2"
            >
              <div className="flex items-center gap-3 min-w-0">
                <span className="text-lg">
                  {f.type === "application/pdf" ? "📄" : "🖼️"}
                </span>
                <div className="min-w-0">
                  <p className="text-sm text-gray-900 truncate">{f.name}</p>
                  <p className="text-xs text-gray-400">{formatSize(f.size)}</p>
                </div>
              </div>
              <button
                onClick={() => removeFile(i)}
                className="text-gray-400 hover:text-red-500 text-sm ml-2"
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Actions */}
      <div className="mt-6 flex gap-3">
        <button
          onClick={handleUpload}
          disabled={files.length === 0 || uploading}
          className="bg-blue-600 text-white px-6 py-2.5 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {uploading ? "Uploading & Processing…" : `Upload ${files.length} file${files.length !== 1 ? "s" : ""}`}
        </button>
        <button
          onClick={() => router.push("/invoices")}
          className="text-gray-600 hover:text-gray-900 px-4 py-2.5 text-sm transition-colors"
        >
          Cancel
        </button>
      </div>

      {uploading && (
        <div className="mt-4 p-4 bg-blue-50 border border-blue-200 rounded-lg">
          <div className="flex items-center gap-3">
            <div className="animate-spin h-5 w-5 border-2 border-blue-600 border-t-transparent rounded-full" />
            <div>
              <p className="text-sm font-medium text-blue-800">
                Processing invoice…
              </p>
              <p className="text-xs text-blue-600 mt-0.5">
                AI extraction runs in the background. You&apos;ll be redirected to the invoice detail page.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
