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

const STATUS_CHIP: Record<string, { label: string; bg: string; text: string }> = {
  pending: { label: "Pending", bg: "bg-yellow-100", text: "text-yellow-800" },
  processing: { label: "Processing", bg: "bg-blue-100", text: "text-blue-800" },
  done: { label: "Done", bg: "bg-green-100", text: "text-green-800" },
  failed: { label: "Failed", bg: "bg-red-100", text: "text-red-800" },
};

const MATCH_BADGE: Record<string, { label: string; color: string }> = {
  barcode: { label: "Barcode", color: "text-green-700 bg-green-50" },
  exact_name: { label: "Exact", color: "text-green-600 bg-green-50" },
  fuzzy: { label: "Fuzzy", color: "text-amber-700 bg-amber-50" },
  manual: { label: "Manual", color: "text-blue-700 bg-blue-50" },
};

export default function InvoiceDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [invoice, setInvoice] = useState<InvoiceDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [manualMatchItemId, setManualMatchItemId] = useState<number | null>(null);
  const [selectedProductId, setSelectedProductId] = useState<number | null>(null);

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

  // Auto-refresh while pending/processing
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
      await manualMatchItem(Number(id), manualMatchItemId, selectedProductId);
      setManualMatchItemId(null);
      setSelectedProductId(null);
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
      <div className="p-8 text-gray-400">Loading invoice…</div>
    );
  }

  if (!invoice) {
    return (
      <div className="p-8">
        <p className="text-red-600">Invoice not found.</p>
        <button
          onClick={() => router.push("/invoices")}
          className="mt-4 text-blue-600 hover:underline text-sm"
        >
          ← Back to Invoices
        </button>
      </div>
    );
  }

  const chip = STATUS_CHIP[invoice.status] || STATUS_CHIP.pending;
  const matchedCount = invoice.items.filter((i) => i.matched).length;
  const totalItems = invoice.items.length;

  return (
    <div className="p-4 md:p-8">
      {/* Back link */}
      <button
        onClick={() => router.push("/invoices")}
        className="text-sm text-gray-500 hover:text-gray-700 mb-4 inline-block"
      >
        ← Back to Invoices
      </button>

      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-start justify-between gap-4 mb-6">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-gray-900">
              Invoice {invoice.invoice_number || `#${invoice.id}`}
            </h1>
            <span
              className={`inline-block px-2.5 py-0.5 rounded-full text-xs font-medium ${chip.bg} ${chip.text}`}
            >
              {chip.label}
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-2 md:gap-4 mt-1 text-sm text-gray-500">
            {invoice.supplier_name && <span>Supplier: {invoice.supplier_name}</span>}
            {invoice.invoice_date && <span>Date: {invoice.invoice_date}</span>}
            {invoice.currency && invoice.grand_total != null && (
              <span className="font-medium text-gray-900">
                Total: {invoice.currency} {Number(invoice.grand_total).toFixed(2)}
              </span>
            )}
          </div>
        </div>

        {/* Action buttons */}
        <div className="flex flex-wrap gap-2">
          {invoice.status === "done" && (
            <>
              <button
                onClick={handleMatch}
                disabled={actionLoading !== null}
                className="px-3 py-2 text-sm border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 transition-colors"
              >
                {actionLoading === "match" ? "Matching…" : "Re-match"}
              </button>
              <button
                onClick={handleGenerateReport}
                disabled={actionLoading !== null}
                className="px-3 py-2 text-sm bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 transition-colors"
              >
                {actionLoading === "report" ? "Generating…" : "Download Report"}
              </button>
            </>
          )}
          <button
            onClick={handleReprocess}
            disabled={actionLoading !== null}
            className="px-3 py-2 text-sm border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 transition-colors"
          >
            {actionLoading === "reprocess" ? "Reprocessing…" : "Reprocess"}
          </button>
        </div>
      </div>

      {/* Processing indicator */}
      {["pending", "processing"].includes(invoice.status) && (
        <div className="mb-6 p-4 bg-blue-50 border border-blue-200 rounded-lg flex items-center gap-3">
          <div className="animate-spin h-5 w-5 border-2 border-blue-600 border-t-transparent rounded-full" />
          <div>
            <p className="text-sm font-medium text-blue-800">
              {invoice.status === "pending" ? "Queued for processing…" : "AI extraction in progress…"}
            </p>
            <p className="text-xs text-blue-600">This page auto-refreshes every 3 seconds.</p>
          </div>
        </div>
      )}

      {/* Error message */}
      {invoice.status === "failed" && invoice.error_message && (
        <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg">
          <p className="text-sm font-medium text-red-800">Extraction failed</p>
          <p className="text-xs text-red-600 mt-1">{invoice.error_message}</p>
        </div>
      )}

      {/* Warning message (e.g. duplicate invoice number) */}
      {invoice.status === "done" && invoice.error_message && (
        <div className="mb-6 p-4 bg-amber-50 border border-amber-200 rounded-lg">
          <p className="text-sm font-medium text-amber-800">Warning</p>
          <p className="text-xs text-amber-700 mt-1">{invoice.error_message}</p>
        </div>
      )}

      {/* Invoice details cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <p className="text-xs text-gray-500">Items Extracted</p>
          <p className="text-2xl font-bold text-gray-900">{totalItems}</p>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <p className="text-xs text-gray-500">Matched</p>
          <p className="text-2xl font-bold text-green-600">{matchedCount}</p>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <p className="text-xs text-gray-500">Unmatched</p>
          <p className="text-2xl font-bold text-red-600">{totalItems - matchedCount}</p>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <p className="text-xs text-gray-500">Match Rate</p>
          <p className="text-2xl font-bold text-purple-600">
            {totalItems > 0 ? `${Math.round((matchedCount / totalItems) * 100)}%` : "—"}
          </p>
        </div>
      </div>

      {/* Items table */}
      {totalItems > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-200 bg-gray-50">
            <h2 className="text-sm font-semibold text-gray-700">Extracted Items</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="text-left px-4 py-2 font-medium text-gray-600">#</th>
                  <th className="text-left px-4 py-2 font-medium text-gray-600">Name</th>
                  <th className="text-left px-4 py-2 font-medium text-gray-600">Barcode</th>
                  <th className="text-right px-4 py-2 font-medium text-gray-600">Qty</th>
                  <th className="text-left px-4 py-2 font-medium text-gray-600">UOM</th>
                  <th className="text-right px-4 py-2 font-medium text-gray-600">Unit Price</th>
                  <th className="text-right px-4 py-2 font-medium text-gray-600">Disc %</th>
                  <th className="text-right px-4 py-2 font-medium text-gray-600">Total</th>
                  <th className="text-center px-4 py-2 font-medium text-gray-600">Match</th>
                  <th className="text-center px-4 py-2 font-medium text-gray-600">Actions</th>
                </tr>
              </thead>
              <tbody>
                {invoice.items
                  .sort((a, b) => (a.line_number || 0) - (b.line_number || 0))
                  .map((item) => {
                    const badge = item.match_method
                      ? MATCH_BADGE[item.match_method]
                      : null;
                    return (
                      <tr
                        key={item.id}
                        className={`border-b border-gray-100 ${
                          item.matched
                            ? "bg-green-50/30"
                            : "bg-red-50/30"
                        }`}
                      >
                        <td className="px-4 py-2 text-gray-500">
                          {item.line_number || "—"}
                        </td>
                        <td className="px-4 py-2 text-gray-900 max-w-[200px] truncate">
                          {item.extracted_name || "—"}
                        </td>
                        <td className="px-4 py-2 font-mono text-xs text-gray-600">
                          {item.extracted_barcode || "—"}
                        </td>
                        <td className="px-4 py-2 text-right text-gray-900">
                          {item.extracted_qty != null ? Number(item.extracted_qty) : "—"}
                        </td>
                        <td className="px-4 py-2 text-gray-600">
                          {item.extracted_uom || "—"}
                        </td>
                        <td className="px-4 py-2 text-right text-gray-900">
                          {item.extracted_unit_price != null
                            ? Number(item.extracted_unit_price).toFixed(2)
                            : "—"}
                        </td>
                        <td className="px-4 py-2 text-right text-gray-600">
                          {item.extracted_discount != null
                            ? `${Number(item.extracted_discount)}%`
                            : "—"}
                        </td>
                        <td className="px-4 py-2 text-right font-medium text-gray-900">
                          {item.extracted_total != null
                            ? Number(item.extracted_total).toFixed(2)
                            : "—"}
                        </td>
                        <td className="px-4 py-2 text-center">
                          {item.matched ? (
                            <span
                              className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                                badge?.color || "text-green-700 bg-green-50"
                              }`}
                            >
                              {badge?.label || "Matched"}{" "}
                              {item.match_confidence != null &&
                                `${Math.round(Number(item.match_confidence) * 100)}%`}
                            </span>
                          ) : (
                            <span className="inline-block px-2 py-0.5 rounded text-xs font-medium text-red-700 bg-red-50">
                              No Match
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-2 text-center">
                          {!item.matched && (
                            <button
                              onClick={() => {
                                setManualMatchItemId(item.id);
                                setSelectedProductId(null);
                              }}
                              className="text-xs text-blue-600 hover:text-blue-800"
                            >
                              Match
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Manual match dialog */}
      {manualMatchItemId && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-md mx-4">
            <h3 className="text-lg font-semibold mb-4 text-gray-900">
              Manual Product Match
            </h3>
            <p className="text-sm text-gray-500 mb-3">
              Select a product to match this item to:
            </p>
            <select
              value={selectedProductId ?? ""}
              onChange={(e) =>
                setSelectedProductId(e.target.value ? Number(e.target.value) : null)
              }
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 mb-4"
            >
              <option value="">— Select Product —</option>
              {products.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.barcode} — {p.description} ({p.uom})
                </option>
              ))}
            </select>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => {
                  setManualMatchItemId(null);
                  setSelectedProductId(null);
                }}
                className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900"
              >
                Cancel
              </button>
              <button
                onClick={handleManualMatch}
                disabled={!selectedProductId || actionLoading === "manual"}
                className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
              >
                {actionLoading === "manual" ? "Matching…" : "Confirm Match"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Invoice metadata */}
      <div className="mt-6 bg-white rounded-xl border border-gray-200 p-4">
        <h2 className="text-sm font-semibold text-gray-700 mb-3">Details</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <span className="text-gray-500">Payment Terms:</span>{" "}
            <span className="text-gray-900">{invoice.payment_terms || "—"}</span>
          </div>
          <div>
            <span className="text-gray-500">Currency:</span>{" "}
            <span className="text-gray-900">{invoice.currency}</span>
          </div>
          <div>
            <span className="text-gray-500">Subtotal:</span>{" "}
            <span className="text-gray-900">
              {invoice.subtotal != null ? Number(invoice.subtotal).toFixed(2) : "—"}
            </span>
          </div>
          <div>
            <span className="text-gray-500">Discount:</span>{" "}
            <span className="text-gray-900">
              {invoice.discount_total != null ? Number(invoice.discount_total).toFixed(2) : "—"}
            </span>
          </div>
          <div>
            <span className="text-gray-500">Created:</span>{" "}
            <span className="text-gray-900">
              {new Date(invoice.created_at).toLocaleString()}
            </span>
          </div>
          <div>
            <span className="text-gray-500">Updated:</span>{" "}
            <span className="text-gray-900">
              {new Date(invoice.updated_at).toLocaleString()}
            </span>
          </div>
          <div>
            <span className="text-gray-500">Files:</span>{" "}
            <span className="text-gray-900">
              {invoice.image_urls?.length || 0} file(s)
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
