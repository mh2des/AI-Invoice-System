"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { getInvoices, deleteInvoice, getSuppliers } from "@/lib/api";
import type { Invoice, Supplier } from "@/lib/types";

const STATUS_CHIP: Record<string, { label: string; bg: string; text: string }> = {
  pending: { label: "Pending", bg: "bg-yellow-100", text: "text-yellow-800" },
  processing: { label: "Processing", bg: "bg-blue-100", text: "text-blue-800" },
  done: { label: "Done", bg: "bg-green-100", text: "text-green-800" },
  failed: { label: "Failed", bg: "bg-red-100", text: "text-red-800" },
};

export default function InvoicesPage() {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("");
  const [supplierFilter, setSupplierFilter] = useState("");

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
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Invoices</h1>
          <p className="text-sm text-gray-500 mt-1">
            {invoices.length} invoice{invoices.length !== 1 ? "s" : ""}
          </p>
        </div>
        <Link
          href="/invoices/upload"
          className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
        >
          + Upload Invoice
        </Link>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-4">
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="">All Statuses</option>
          <option value="pending">Pending</option>
          <option value="processing">Processing</option>
          <option value="done">Done</option>
          <option value="failed">Failed</option>
        </select>
        <select
          value={supplierFilter}
          onChange={(e) => setSupplierFilter(e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="">All Suppliers</option>
          {suppliers.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
        <button
          onClick={fetchInvoices}
          className="text-sm text-blue-600 hover:text-blue-800 px-3 py-2"
        >
          Refresh
        </button>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-600">ID</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Invoice #</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Supplier</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Date</th>
                <th className="text-right px-4 py-3 font-medium text-gray-600">Total</th>
                <th className="text-center px-4 py-3 font-medium text-gray-600">Status</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Uploaded</th>
                <th className="text-center px-4 py-3 font-medium text-gray-600">Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={8} className="text-center py-8 text-gray-400">
                    Loading…
                  </td>
                </tr>
              ) : invoices.length === 0 ? (
                <tr>
                  <td colSpan={8} className="text-center py-8 text-gray-400">
                    No invoices found. Upload your first invoice to get started.
                  </td>
                </tr>
              ) : (
                invoices.map((inv) => {
                  const chip = STATUS_CHIP[inv.status] || STATUS_CHIP.pending;
                  return (
                    <tr
                      key={inv.id}
                      className="border-b border-gray-100 hover:bg-gray-50"
                    >
                      <td className="px-4 py-3 font-mono text-xs text-gray-500">
                        {inv.id}
                      </td>
                      <td className="px-4 py-3 text-gray-900 font-medium">
                        <Link
                          href={`/invoices/${inv.id}`}
                          className="hover:text-blue-600 hover:underline"
                        >
                          {inv.invoice_number || "—"}
                        </Link>
                      </td>
                      <td className="px-4 py-3 text-gray-600">
                        {supplierName(inv.supplier_id)}
                      </td>
                      <td className="px-4 py-3 text-gray-600">
                        {inv.invoice_date || "—"}
                      </td>
                      <td className="px-4 py-3 text-right text-gray-900">
                        {inv.grand_total != null
                          ? `${inv.currency} ${Number(inv.grand_total).toFixed(2)}`
                          : "—"}
                      </td>
                      <td className="px-4 py-3 text-center">
                        <span
                          className={`inline-block px-2.5 py-0.5 rounded-full text-xs font-medium ${chip.bg} ${chip.text}`}
                        >
                          {chip.label}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-gray-500 text-xs">
                        {new Date(inv.created_at).toLocaleDateString()}
                      </td>
                      <td className="px-4 py-3 text-center">
                        <div className="flex items-center justify-center gap-2">
                          <Link
                            href={`/invoices/${inv.id}`}
                            className="text-blue-600 hover:text-blue-800 text-xs"
                          >
                            View
                          </Link>
                          <button
                            onClick={() => handleDelete(inv.id)}
                            className="text-red-500 hover:text-red-700 text-xs"
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
