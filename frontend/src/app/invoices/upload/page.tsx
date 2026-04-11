"use client";

import { useState, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import { uploadInvoice } from "@/lib/api";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Upload, FileText, Image, X, Loader2 } from "lucide-react";

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
      <PageHeader
        title="Upload Invoice"
        description="Upload invoice images or PDF. AI will extract items automatically."
      />

      <Card
        className={`cursor-pointer transition-colors ${
          dragOver ? "border-primary bg-primary/5" : ""
        }`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
      >
        <CardContent className="flex flex-col items-center justify-center py-12">
          <Upload className="h-10 w-10 text-muted-foreground mb-3" />
          <p className="text-sm font-medium">
            Drag & drop files here, or click to browse
          </p>
          <p className="text-xs text-muted-foreground mt-1">
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
        </CardContent>
      </Card>

      {files.length > 0 && (
        <div className="mt-4 space-y-2">
          {files.map((f, i) => (
            <div
              key={`${f.name}-${i}`}
              className="flex items-center justify-between border rounded-lg px-4 py-2"
            >
              <div className="flex items-center gap-3 min-w-0">
                {f.type === "application/pdf" ? (
                  <FileText className="h-5 w-5 text-muted-foreground flex-shrink-0" />
                ) : (
                  <Image className="h-5 w-5 text-muted-foreground flex-shrink-0" />
                )}
                <div className="min-w-0">
                  <p className="text-sm truncate">{f.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {formatSize(f.size)}
                  </p>
                </div>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={(e) => {
                  e.stopPropagation();
                  removeFile(i);
                }}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          ))}
        </div>
      )}

      {error && (
        <Alert variant="destructive" className="mt-4">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <div className="mt-6 flex gap-3">
        <Button
          onClick={handleUpload}
          disabled={files.length === 0 || uploading}
        >
          {uploading ? (
            <>
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              Uploading & Processing…
            </>
          ) : (
            `Upload ${files.length} file${files.length !== 1 ? "s" : ""}`
          )}
        </Button>
        <Button variant="ghost" onClick={() => router.push("/invoices")}>
          Cancel
        </Button>
      </div>

      {uploading && (
        <Alert className="mt-4 border-blue-200 bg-blue-50">
          <Loader2 className="h-4 w-4 animate-spin text-blue-600" />
          <AlertDescription className="text-blue-800">
            <span className="font-medium">Processing invoice…</span>
            <br />
            <span className="text-xs text-blue-600">
              AI extraction runs in the background. You&apos;ll be redirected to
              the invoice detail page.
            </span>
          </AlertDescription>
        </Alert>
      )}
    </div>
  );
}
