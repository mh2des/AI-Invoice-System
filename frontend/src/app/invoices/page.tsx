"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { getInvoices, deleteInvoice, getSuppliers, uploadInvoice } from "@/lib/api";
import type { Invoice, Supplier } from "@/lib/types";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Plus, Eye, Trash2, RefreshCw, Loader2 } from "lucide-react";

const STATUS_VARIANT: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  pending: "outline",
  processing: "secondary",
  done: "default",
  failed: "destructive",
};

const STATUS_LABEL: Record<string, string> = {
  pending: "Pending",
  processing: "Processing",
  done: "Done",
  failed: "Failed",
};

export default function InvoicesPage() {
  const router = useRouter();
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("");
  const [supplierFilter, setSupplierFilter] = useState("");
  const [pasteUploading, setPasteUploading] = useState(false);
  const [pasteError, setPasteError] = useState<string | null>(null);

  // Paste-to-upload: Cmd+V / Ctrl+V with clipboard images → instant upload
  useEffect(() => {
    const handlePaste = async (e: ClipboardEvent) => {
      const items = e.clipboardData?.items;
      if (!items) return;

      const imageFiles: File[] = [];
      for (const item of Array.from(items)) {
        if (item.kind === "file" && item.type.startsWith("image/")) {
          const file = item.getAsFile();
          if (file) {
            const timestamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
            const ext = file.type.split("/")[1] || "png";
            const named = new File([file], `pasted-invoice-${timestamp}.${ext}`, {
              type: file.type,
            });
            imageFiles.push(named);
          }
        }
      }

      if (imageFiles.length === 0) return;
      e.preventDefault();
      setPasteUploading(true);
      setPasteError(null);
      try {
        const invoice = await uploadInvoice(imageFiles);
        router.push(`/invoices/${invoice.id}`);
      } catch (err) {
        console.error(err);
        setPasteError(err instanceof Error ? err.message : "Paste upload failed");
        setPasteUploading(false);
      }
    };

    window.addEventListener("paste", handlePaste);
    return () => window.removeEventListener("paste", handlePaste);
  }, [router]);

  const fetchInvoices = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getInvoices({
        status: statusFilter || undefined,
        supplier_id: supplierFilter ? Number(supplierFilter) : undefined,
        limit: 100,
      });
      setInvoices(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [statusFilter, supplierFilter]);

  useEffect(() => {
    getSuppliers().then(setSuppliers).catch(console.error);
  }, []);

  useEffect(() => {
    fetchInvoices();
  }, [fetchInvoices]);

  const handleDelete = async (id: number) => {
    if (!confirm(`Delete invoice #${id}? This cannot be undone.`)) return;
    try {
      await deleteInvoice(id);
      setInvoices((prev) => prev.filter((inv) => inv.id !== id));
    } catch (err) {
      console.error(err);
      alert("Delete failed.");
    }
  };

  const supplierName = (id: number | null) => {
    if (!id) return "—";
    return suppliers.find((s) => s.id === id)?.name || `#${id}`;
  };

  return (
    <div className="p-4 md:p-8">
      {pasteUploading && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm">
          <div className="flex flex-col items-center gap-3 p-8 rounded-xl bg-card border shadow-lg">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
            <p className="text-base font-medium">Uploading pasted invoice…</p>
            <p className="text-sm text-muted-foreground">AI extraction will start automatically</p>
          </div>
        </div>
      )}

      {pasteError && (
        <Alert variant="destructive" className="mb-4">
          <AlertDescription>{pasteError}</AlertDescription>
        </Alert>
      )}

      <PageHeader
        title="Invoices"
        description={`${invoices.length} invoice${invoices.length !== 1 ? "s" : ""}`}
      >
        <Button nativeButton={false} render={<Link href="/invoices/upload" />}>
          <Plus className="h-4 w-4 mr-2" />
          Upload Invoice
        </Button>
      </PageHeader>

      <div className="flex flex-wrap gap-3 mb-4">
        <Select value={statusFilter} onValueChange={(v) => setStatusFilter(v ?? "__all__")}>
          <SelectTrigger className="w-[160px]">
            <SelectValue placeholder="All Statuses" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All Statuses</SelectItem>
            <SelectItem value="pending">Pending</SelectItem>
            <SelectItem value="processing">Processing</SelectItem>
            <SelectItem value="done">Done</SelectItem>
            <SelectItem value="failed">Failed</SelectItem>
          </SelectContent>
        </Select>
        <Select value={supplierFilter} onValueChange={(v) => setSupplierFilter(v ?? "__all__")}>
          <SelectTrigger className="w-[200px]">
            <SelectValue placeholder="All Suppliers" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All Suppliers</SelectItem>
            {suppliers.map((s) => (
              <SelectItem key={s.id} value={String(s.id)}>
                {s.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button variant="ghost" size="sm" onClick={fetchInvoices}>
          <RefreshCw className="h-4 w-4 mr-1" />
          Refresh
        </Button>
      </div>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>ID</TableHead>
                <TableHead>Invoice #</TableHead>
                <TableHead>Supplier</TableHead>
                <TableHead>Date</TableHead>
                <TableHead className="text-right">Total</TableHead>
                <TableHead className="text-center">Status</TableHead>
                <TableHead>Uploaded</TableHead>
                <TableHead className="text-center">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <TableRow key={i}>
                    {Array.from({ length: 8 }).map((_, j) => (
                      <TableCell key={j}>
                        <Skeleton className="h-4 w-full" />
                      </TableCell>
                    ))}
                  </TableRow>
                ))
              ) : invoices.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={8} className="text-center py-8 text-muted-foreground">
                    No invoices found. Upload your first invoice to get started.
                  </TableCell>
                </TableRow>
              ) : (
                invoices.map((inv) => (
                  <TableRow key={inv.id}>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {inv.id}
                    </TableCell>
                    <TableCell className="font-medium">
                      <Link
                        href={`/invoices/${inv.id}`}
                        className="hover:underline"
                      >
                        {inv.invoice_number || "—"}
                      </Link>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {supplierName(inv.supplier_id)}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {inv.invoice_date || "—"}
                    </TableCell>
                    <TableCell className="text-right">
                      {inv.grand_total != null
                        ? `${inv.currency} ${Number(inv.grand_total).toFixed(2)}`
                        : "—"}
                    </TableCell>
                    <TableCell className="text-center">
                      <Badge variant={STATUS_VARIANT[inv.status] || "outline"}>
                        {STATUS_LABEL[inv.status] || inv.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-muted-foreground text-xs">
                      {new Date(inv.created_at).toLocaleDateString()}
                    </TableCell>
                    <TableCell className="text-center">
                      <div className="flex items-center justify-center gap-1">
                        <Button nativeButton={false} variant="ghost" size="sm" render={<Link href={`/invoices/${inv.id}`} />}>
                          <Eye className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleDelete(inv.id)}
                          className="text-destructive hover:text-destructive"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
