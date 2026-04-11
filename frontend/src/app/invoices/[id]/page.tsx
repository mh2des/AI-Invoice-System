"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  getInvoice,
  reprocessInvoice,
  matchInvoice,
  manualMatchItem,
  generateReport,
  getProducts,
} from "@/lib/api";
import type { InvoiceDetail, Product } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import {
  ArrowLeft,
  RefreshCw,
  Download,
  Target,
  Loader2,
  AlertCircle,
  AlertTriangle,
  Link2,
} from "lucide-react";

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

const MATCH_VARIANT: Record<string, "default" | "secondary" | "outline"> = {
  barcode: "default",
  exact_name: "default",
  fuzzy: "secondary",
  manual: "outline",
};

const MATCH_LABEL: Record<string, string> = {
  barcode: "Barcode",
  exact_name: "Exact",
  fuzzy: "Fuzzy",
  manual: "Manual",
};

export default function InvoiceDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [invoice, setInvoice] = useState<InvoiceDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [manualMatchItemId, setManualMatchItemId] = useState<number | null>(null);
  const [selectedProductId, setSelectedProductId] = useState<string>("");

  const fetchInvoice = useCallback(async () => {
    try {
      const data = await getInvoice(Number(id));
      setInvoice(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchInvoice();
    getProducts({ limit: 5000 }).then(setProducts).catch(console.error);
  }, [fetchInvoice]);

  useEffect(() => {
    if (!invoice || !["pending", "processing"].includes(invoice.status)) return;
    const interval = setInterval(fetchInvoice, 3000);
    return () => clearInterval(interval);
  }, [invoice, fetchInvoice]);

  const handleReprocess = async () => {
    setActionLoading("reprocess");
    try {
      await reprocessInvoice(Number(id));
      await fetchInvoice();
    } catch (err) {
      console.error(err);
      alert("Reprocess failed.");
    } finally {
      setActionLoading(null);
    }
  };

  const handleMatch = async () => {
    setActionLoading("match");
    try {
      await matchInvoice(Number(id));
      await fetchInvoice();
    } catch (err) {
      console.error(err);
      alert("Match failed.");
    } finally {
      setActionLoading(null);
    }
  };

  const handleGenerateReport = async () => {
    setActionLoading("report");
    try {
      const blob = await generateReport(Number(id));
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `report-invoice-${id}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error(err);
      alert("Report generation failed.");
    } finally {
      setActionLoading(null);
    }
  };

  const handleManualMatch = async () => {
    if (!manualMatchItemId || !selectedProductId) return;
    setActionLoading("manual");
    try {
      await manualMatchItem(Number(id), manualMatchItemId, Number(selectedProductId));
      setManualMatchItemId(null);
      setSelectedProductId("");
      await fetchInvoice();
    } catch (err) {
      console.error(err);
      alert("Manual match failed.");
    } finally {
      setActionLoading(null);
    }
  };

  if (loading) {
    return (
      <div className="p-4 md:p-8 space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-4 w-72" />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
      </div>
    );
  }

  if (!invoice) {
    return (
      <div className="p-4 md:p-8">
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>Invoice not found.</AlertDescription>
        </Alert>
        <Button
          variant="link"
          onClick={() => router.push("/invoices")}
          className="mt-4 p-0"
        >
          <ArrowLeft className="h-4 w-4 mr-1" />
          Back to Invoices
        </Button>
      </div>
    );
  }

  const matchedCount = invoice.items.filter((i) => i.matched).length;
  const totalItems = invoice.items.length;

  return (
    <div className="p-4 md:p-8">
      <Button
        variant="ghost"
        size="sm"
        onClick={() => router.push("/invoices")}
        className="mb-4 -ml-2"
      >
        <ArrowLeft className="h-4 w-4 mr-1" />
        Back to Invoices
      </Button>

      <div className="flex flex-col md:flex-row md:items-start justify-between gap-4 mb-6">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight">
              Invoice {invoice.invoice_number || `#${invoice.id}`}
            </h1>
            <Badge variant={STATUS_VARIANT[invoice.status] || "outline"}>
              {STATUS_LABEL[invoice.status] || invoice.status}
            </Badge>
          </div>
          <div className="flex flex-wrap items-center gap-2 md:gap-4 mt-1 text-sm text-muted-foreground">
            {invoice.supplier_name && <span>Supplier: {invoice.supplier_name}</span>}
            {invoice.invoice_date && <span>Date: {invoice.invoice_date}</span>}
            {invoice.currency && invoice.grand_total != null && (
              <span className="font-medium text-foreground">
                Total: {invoice.currency} {Number(invoice.grand_total).toFixed(2)}
              </span>
            )}
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          {invoice.status === "done" && (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={handleMatch}
                disabled={actionLoading !== null}
              >
                {actionLoading === "match" ? (
                  <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                ) : (
                  <Target className="h-4 w-4 mr-1" />
                )}
                Re-match
              </Button>
              <Button
                size="sm"
                onClick={handleGenerateReport}
                disabled={actionLoading !== null}
                className="bg-green-600 hover:bg-green-700"
              >
                {actionLoading === "report" ? (
                  <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                ) : (
                  <Download className="h-4 w-4 mr-1" />
                )}
                Download Report
              </Button>
            </>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={handleReprocess}
            disabled={actionLoading !== null}
          >
            {actionLoading === "reprocess" ? (
              <Loader2 className="h-4 w-4 mr-1 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4 mr-1" />
            )}
            Reprocess
          </Button>
        </div>
      </div>

      {["pending", "processing"].includes(invoice.status) && (
        <Alert className="mb-6 border-blue-200 bg-blue-50">
          <Loader2 className="h-4 w-4 animate-spin text-blue-600" />
          <AlertDescription className="text-blue-800">
            <span className="font-medium">
              {invoice.status === "pending"
                ? "Queued for processing…"
                : "AI extraction in progress…"}
            </span>
            <br />
            <span className="text-xs text-blue-600">
              This page auto-refreshes every 3 seconds.
            </span>
          </AlertDescription>
        </Alert>
      )}

      {invoice.status === "failed" && invoice.error_message && (
        <Alert variant="destructive" className="mb-6">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            <span className="font-medium">Extraction failed</span>
            <br />
            <span className="text-xs">{invoice.error_message}</span>
          </AlertDescription>
        </Alert>
      )}

      {invoice.status === "done" && invoice.error_message && (
        <Alert className="mb-6 border-amber-200 bg-amber-50">
          <AlertTriangle className="h-4 w-4 text-amber-600" />
          <AlertDescription className="text-amber-800">
            <span className="font-medium">Warning</span>
            <br />
            <span className="text-xs text-amber-700">{invoice.error_message}</span>
          </AlertDescription>
        </Alert>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <Card>
          <CardContent className="p-4">
            <p className="text-xs text-muted-foreground">Items Extracted</p>
            <p className="text-2xl font-bold">{totalItems}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <p className="text-xs text-muted-foreground">Matched</p>
            <p className="text-2xl font-bold text-green-600">{matchedCount}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <p className="text-xs text-muted-foreground">Unmatched</p>
            <p className="text-2xl font-bold text-red-600">
              {totalItems - matchedCount}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <p className="text-xs text-muted-foreground">Match Rate</p>
            <p className="text-2xl font-bold text-purple-600">
              {totalItems > 0
                ? `${Math.round((matchedCount / totalItems) * 100)}%`
                : "—"}
            </p>
          </CardContent>
        </Card>
      </div>

      {totalItems > 0 && (
        <Card className="mb-6">
          <CardHeader className="py-3">
            <CardTitle className="text-sm">Extracted Items</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>#</TableHead>
                  <TableHead>Name</TableHead>
                  <TableHead>Barcode</TableHead>
                  <TableHead className="text-right">Qty</TableHead>
                  <TableHead>UOM</TableHead>
                  <TableHead className="text-right">Unit Price</TableHead>
                  <TableHead className="text-right">Disc %</TableHead>
                  <TableHead className="text-right">Total</TableHead>
                  <TableHead className="text-center">Match</TableHead>
                  <TableHead className="text-center">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {invoice.items
                  .sort((a, b) => (a.line_number || 0) - (b.line_number || 0))
                  .map((item) => (
                    <TableRow
                      key={item.id}
                      className={
                        item.matched ? "bg-green-50/30" : "bg-red-50/30"
                      }
                    >
                      <TableCell className="text-muted-foreground">
                        {item.line_number || "—"}
                      </TableCell>
                      <TableCell className="max-w-[200px] truncate">
                        {item.extracted_name || "—"}
                      </TableCell>
                      <TableCell className="font-mono text-xs text-muted-foreground">
                        {item.extracted_barcode || "—"}
                      </TableCell>
                      <TableCell className="text-right">
                        {item.extracted_qty != null
                          ? Number(item.extracted_qty)
                          : "—"}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {item.extracted_uom || "—"}
                      </TableCell>
                      <TableCell className="text-right">
                        {item.extracted_unit_price != null
                          ? Number(item.extracted_unit_price).toFixed(2)
                          : "—"}
                      </TableCell>
                      <TableCell className="text-right text-muted-foreground">
                        {item.extracted_discount != null
                          ? `${Number(item.extracted_discount)}%`
                          : "—"}
                      </TableCell>
                      <TableCell className="text-right font-medium">
                        {item.extracted_total != null
                          ? Number(item.extracted_total).toFixed(2)
                          : "—"}
                      </TableCell>
                      <TableCell className="text-center">
                        {item.matched ? (
                          <Badge
                            variant={
                              item.match_method
                                ? MATCH_VARIANT[item.match_method] || "default"
                                : "default"
                            }
                          >
                            {item.match_method
                              ? MATCH_LABEL[item.match_method] || "Matched"
                              : "Matched"}{" "}
                            {item.match_confidence != null &&
                              `${Math.round(Number(item.match_confidence) * 100)}%`}
                          </Badge>
                        ) : (
                          <Badge variant="destructive">No Match</Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-center">
                        {!item.matched && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => {
                              setManualMatchItemId(item.id);
                              setSelectedProductId("");
                            }}
                          >
                            <Link2 className="h-4 w-4" />
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      <Dialog
        open={manualMatchItemId !== null}
        onOpenChange={(open) => {
          if (!open) {
            setManualMatchItemId(null);
            setSelectedProductId("");
          }
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Manual Product Match</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground mb-3">
            Select a product to match this item to:
          </p>
          <Select
            value={selectedProductId}
            onValueChange={(val) => setSelectedProductId(val ?? "")}
          >
            <SelectTrigger>
              <SelectValue placeholder="— Select Product —" />
            </SelectTrigger>
            <SelectContent>
              {products.map((p) => (
                <SelectItem key={p.id} value={String(p.id)}>
                  {p.barcode} — {p.description} ({p.uom})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setManualMatchItemId(null);
                setSelectedProductId("");
              }}
            >
              Cancel
            </Button>
            <Button
              onClick={handleManualMatch}
              disabled={!selectedProductId || actionLoading === "manual"}
            >
              {actionLoading === "manual" ? (
                <>
                  <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                  Matching…
                </>
              ) : (
                "Confirm Match"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Card>
        <CardHeader className="py-3">
          <CardTitle className="text-sm">Details</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <div>
              <span className="text-muted-foreground">Payment Terms:</span>{" "}
              <span>{invoice.payment_terms || "—"}</span>
            </div>
            <div>
              <span className="text-muted-foreground">Currency:</span>{" "}
              <span>{invoice.currency}</span>
            </div>
            <div>
              <span className="text-muted-foreground">Subtotal:</span>{" "}
              <span>
                {invoice.subtotal != null
                  ? Number(invoice.subtotal).toFixed(2)
                  : "—"}
              </span>
            </div>
            <div>
              <span className="text-muted-foreground">Discount:</span>{" "}
              <span>
                {invoice.discount_total != null
                  ? Number(invoice.discount_total).toFixed(2)
                  : "—"}
              </span>
            </div>
            <div>
              <span className="text-muted-foreground">Created:</span>{" "}
              <span>{new Date(invoice.created_at).toLocaleString()}</span>
            </div>
            <div>
              <span className="text-muted-foreground">Updated:</span>{" "}
              <span>{new Date(invoice.updated_at).toLocaleString()}</span>
            </div>
            <div>
              <span className="text-muted-foreground">Files:</span>{" "}
              <span>{invoice.image_urls?.length || 0} file(s)</span>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
