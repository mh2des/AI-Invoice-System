"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  getInvoice,
  reprocessInvoice,
  matchInvoice,
  manualMatchItem,
  getItemSuggestions,
  generateReport,
  getProducts,
} from "@/lib/api";
import type { InvoiceDetail, Product, ProductSuggestion } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
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
  Search,
  Sparkles,
  Check,
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
  barcode_partial: "default",
  exact_name: "default",
  exact_name_normalized: "default",
  fuzzy: "secondary",
  manual: "outline",
};

const MATCH_LABEL: Record<string, string> = {
  barcode: "Barcode",
  barcode_partial: "Barcode~",
  exact_name: "Exact",
  exact_name_normalized: "Exact",
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
  const [suggestions, setSuggestions] = useState<Record<number, ProductSuggestion[]>>({});
  const [loadingSuggestions, setLoadingSuggestions] = useState<Record<number, boolean>>({});
  const [productSearch, setProductSearch] = useState("");

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

  // Auto-load suggestions for unmatched items
  useEffect(() => {
    if (!invoice || invoice.status !== "done") return;
    const unmatchedItems = invoice.items.filter(
      (i) => !i.matched && i.extracted_name && !suggestions[i.id] && !loadingSuggestions[i.id]
    );
    if (unmatchedItems.length === 0) return;

    for (const item of unmatchedItems) {
      setLoadingSuggestions((prev) => ({ ...prev, [item.id]: true }));
      getItemSuggestions(Number(id), item.id)
        .then((data) => {
          setSuggestions((prev) => ({ ...prev, [item.id]: data }));
        })
        .catch(console.error)
        .finally(() => {
          setLoadingSuggestions((prev) => ({ ...prev, [item.id]: false }));
        });
    }
  }, [invoice, id]); // eslint-disable-line react-hooks/exhaustive-deps

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
      setProductSearch("");
      await fetchInvoice();
    } catch (err) {
      console.error(err);
      alert("Manual match failed.");
    } finally {
      setActionLoading(null);
    }
  };

  const handleQuickMatch = async (itemId: number, productId: number) => {
    setActionLoading(`quick-${itemId}`);
    try {
      await manualMatchItem(Number(id), itemId, productId);
      await fetchInvoice();
    } catch (err) {
      console.error(err);
      alert("Match failed.");
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
                  .map((item) => {
                    const itemSuggestions = suggestions[item.id] || [];
                    const hasLowConfidenceMatch = !item.matched && item.product_id;
                    return (
                      <TableRow
                        key={item.id}
                        className={
                          item.matched
                            ? "bg-green-50/30 dark:bg-green-950/10"
                            : "bg-red-50/30 dark:bg-red-950/10"
                        }
                      >
                        <TableCell className="text-muted-foreground">
                          {item.line_number || "—"}
                        </TableCell>
                        <TableCell className="max-w-[260px]">
                          <div className="truncate">{item.extracted_name || "—"}</div>
                          {/* Show matched product name */}
                          {item.matched && item.product_id && (
                            <div className="text-xs text-muted-foreground mt-0.5 truncate flex items-center gap-1">
                              <Check className="h-3 w-3 text-green-600 shrink-0" />
                              {products.find((p) => p.id === item.product_id)?.description || `Product #${item.product_id}`}
                            </div>
                          )}
                          {/* Show suggestions for unmatched items */}
                          {!item.matched && (
                            <div className="mt-1.5 space-y-1">
                              {loadingSuggestions[item.id] && (
                                <div className="flex items-center gap-1 text-xs text-muted-foreground">
                                  <Loader2 className="h-3 w-3 animate-spin" />
                                  Finding similar products…
                                </div>
                              )}
                              {itemSuggestions.length > 0 && (
                                <div className="space-y-1">
                                  <span className="text-xs text-muted-foreground flex items-center gap-1">
                                    <Sparkles className="h-3 w-3" />
                                    Suggestions:
                                  </span>
                                  <div className="flex flex-wrap gap-1">
                                    {itemSuggestions.slice(0, 5).map((s) => (
                                      <button
                                        key={s.product_id}
                                        className="inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-md border bg-background hover:bg-accent hover:text-accent-foreground transition-colors disabled:opacity-50"
                                        title={`${s.product_name} (${Math.round(s.confidence * 100)}% confidence)\n${s.barcode || "No barcode"} · ${s.uom || "—"}`}
                                        disabled={actionLoading === `quick-${item.id}`}
                                        onClick={() => handleQuickMatch(item.id, s.product_id)}
                                      >
                                        <span className="max-w-[150px] truncate">{s.product_name}</span>
                                        <Badge variant="outline" className="ml-0.5 px-1 py-0 text-[10px] leading-tight">
                                          {Math.round(s.confidence * 100)}%
                                        </Badge>
                                      </button>
                                    ))}
                                  </div>
                                </div>
                              )}
                              {!loadingSuggestions[item.id] && itemSuggestions.length === 0 && hasLowConfidenceMatch && (
                                <span className="text-xs text-amber-600">
                                  Low confidence match — verify manually
                                </span>
                              )}
                            </div>
                          )}
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
                              title="Search all products"
                              onClick={() => {
                                setManualMatchItemId(item.id);
                                setSelectedProductId("");
                                setProductSearch("");
                              }}
                            >
                              <Link2 className="h-4 w-4" />
                            </Button>
                          )}
                        </TableCell>
                      </TableRow>
                    );
                  })}
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
            setProductSearch("");
          }
        }}
      >
        <DialogContent className="sm:max-w-lg max-h-[80vh] flex flex-col">
          <DialogHeader>
            <DialogTitle>Manual Product Match</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Search and select a product to match this item to:
          </p>

          {/* Suggestions section */}
          {manualMatchItemId && suggestions[manualMatchItemId]?.length > 0 && (
            <div className="space-y-1.5">
              <span className="text-xs font-medium text-muted-foreground flex items-center gap-1">
                <Sparkles className="h-3 w-3" />
                AI Suggestions
              </span>
              <div className="flex flex-col gap-1 max-h-32 overflow-y-auto">
                {suggestions[manualMatchItemId].map((s) => (
                  <button
                    key={s.product_id}
                    className={`flex items-center justify-between px-3 py-1.5 text-sm rounded-md border transition-colors ${
                      selectedProductId === String(s.product_id)
                        ? "border-primary bg-primary/10"
                        : "hover:bg-accent"
                    }`}
                    onClick={() => setSelectedProductId(String(s.product_id))}
                  >
                    <span className="truncate text-left">{s.product_name}</span>
                    <Badge variant="outline" className="ml-2 shrink-0 text-xs">
                      {Math.round(s.confidence * 100)}%
                    </Badge>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Search */}
          <div className="relative">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search by name or barcode…"
              value={productSearch}
              onChange={(e) => setProductSearch(e.target.value)}
              className="pl-8"
            />
          </div>

          {/* Product list */}
          <div className="flex-1 overflow-y-auto border rounded-md min-h-[150px] max-h-[300px]">
            {products
              .filter((p) => {
                if (!productSearch) return true;
                const q = productSearch.toLowerCase();
                return (
                  p.description.toLowerCase().includes(q) ||
                  p.barcode.toLowerCase().includes(q) ||
                  (p.brand && p.brand.toLowerCase().includes(q))
                );
              })
              .slice(0, 100)
              .map((p) => (
                <button
                  key={p.id}
                  className={`w-full flex items-center gap-2 px-3 py-2 text-sm text-left border-b last:border-b-0 transition-colors ${
                    selectedProductId === String(p.id)
                      ? "bg-primary/10 text-primary"
                      : "hover:bg-accent"
                  }`}
                  onClick={() => setSelectedProductId(String(p.id))}
                >
                  <span className="font-mono text-xs text-muted-foreground w-28 shrink-0 truncate">
                    {p.barcode}
                  </span>
                  <span className="truncate flex-1">{p.description}</span>
                  <span className="text-xs text-muted-foreground shrink-0">{p.uom}</span>
                </button>
              ))}
            {products.filter((p) => {
              if (!productSearch) return true;
              const q = productSearch.toLowerCase();
              return (
                p.description.toLowerCase().includes(q) ||
                p.barcode.toLowerCase().includes(q) ||
                (p.brand && p.brand.toLowerCase().includes(q))
              );
            }).length === 0 && (
              <div className="p-4 text-center text-sm text-muted-foreground">
                No products found
              </div>
            )}
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setManualMatchItemId(null);
                setSelectedProductId("");
                setProductSearch("");
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
