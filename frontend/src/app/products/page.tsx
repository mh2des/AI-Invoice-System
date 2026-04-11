"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import {
  getProducts,
  getProductGroups,
  importProductsExcel,
  deleteProduct,
} from "@/lib/api";
import type { Product, ImportResult } from "@/lib/types";

export default function ProductsPage() {
  const [products, setProducts] = useState<Product[]>([]);
  const [groups, setGroups] = useState<string[]>([]);
  const [search, setSearch] = useState("");
  const [group, setGroup] = useState("");
  const [loading, setLoading] = useState(true);
  const [importResult, setImportResult] = useState<ImportResult | null>(null);
  const [importing, setImporting] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const fetchProducts = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getProducts({
        search: search || undefined,
        group: group || undefined,
        limit: 100,
      });
      setProducts(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [search, group]);

  useEffect(() => {
    getProductGroups().then(setGroups).catch(console.error);
  }, []);

  useEffect(() => {
    const timer = setTimeout(fetchProducts, 300);
    return () => clearTimeout(timer);
  }, [fetchProducts]);

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    setImportResult(null);
    try {
      const result = await importProductsExcel(file);
      setImportResult(result);
      fetchProducts();
    } catch (err) {
      console.error(err);
      alert("Import failed. Check console for details.");
    } finally {
      setImporting(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const handleDelete = async (id: number, desc: string) => {
    if (!confirm(`Delete product "${desc}"?`)) return;
    try {
      await deleteProduct(id);
      setProducts((prev) => prev.filter((p) => p.id !== id));
    } catch (err) {
      console.error(err);
      alert("Delete failed.");
    }
  };

  return (
    <div className="p-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Products</h1>
          <p className="text-sm text-gray-500 mt-1">
            {products.length} product{products.length !== 1 ? "s" : ""} loaded
          </p>
        </div>
        <div>
          <input
            ref={fileRef}
            type="file"
            accept=".xlsx,.xls"
            onChange={handleImport}
            className="hidden"
            id="excel-upload"
          />
          <button
            onClick={() => fileRef.current?.click()}
            disabled={importing}
            className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {importing ? "Importing…" : "Import Excel"}
          </button>
        </div>
      </div>

      {/* Import Result Banner */}
      {importResult && (
        <div className="mb-4 p-4 bg-green-50 border border-green-200 rounded-lg text-sm">
          <p className="font-medium text-green-800">Import Complete</p>
          <p className="text-green-700 mt-1">
            {importResult.inserted} inserted, {importResult.updated} updated,{" "}
            {importResult.skipped} skipped
            {importResult.errors.length > 0 && (
              <span className="text-red-600">
                , {importResult.errors.length} error(s)
              </span>
            )}
          </p>
          {importResult.errors.length > 0 && (
            <ul className="mt-2 text-red-600 list-disc list-inside">
              {importResult.errors.slice(0, 5).map((e, i) => (
                <li key={i}>{e}</li>
              ))}
            </ul>
          )}
          <button
            onClick={() => setImportResult(null)}
            className="mt-2 text-xs text-green-600 underline"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Filters */}
      <div className="flex gap-3 mb-4">
        <input
          type="text"
          placeholder="Search by name or barcode…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <select
          value={group}
          onChange={(e) => setGroup(e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="">All Groups</option>
          {groups.map((g) => (
            <option key={g} value={g}>
              {g}
            </option>
          ))}
        </select>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-600">
                  Barcode
                </th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">
                  Description
                </th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">
                  UOM
                </th>
                <th className="text-right px-4 py-3 font-medium text-gray-600">
                  Cost
                </th>
                <th className="text-right px-4 py-3 font-medium text-gray-600">
                  Price
                </th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">
                  Group
                </th>
                <th className="text-right px-4 py-3 font-medium text-gray-600">
                  Qty
                </th>
                <th className="text-center px-4 py-3 font-medium text-gray-600">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={8} className="text-center py-8 text-gray-400">
                    Loading…
                  </td>
                </tr>
              ) : products.length === 0 ? (
                <tr>
                  <td colSpan={8} className="text-center py-8 text-gray-400">
                    No products found. Import an Excel file to get started.
                  </td>
                </tr>
              ) : (
                products.map((p) => (
                  <tr
                    key={p.id}
                    className="border-b border-gray-100 hover:bg-gray-50"
                  >
                    <td className="px-4 py-3 font-mono text-xs text-gray-600">
                      {p.barcode}
                    </td>
                    <td className="px-4 py-3 text-gray-900">{p.description}</td>
                    <td className="px-4 py-3 text-gray-600">{p.uom}</td>
                    <td className="px-4 py-3 text-right text-gray-900">
                      {Number(p.cost).toFixed(2)}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-900">
                      {Number(p.price).toFixed(2)}
                    </td>
                    <td className="px-4 py-3 text-gray-600">
                      {p.group_name || "—"}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-600">
                      {p.balance_qty}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <button
                        onClick={() => handleDelete(p.id, p.description)}
                        className="text-red-500 hover:text-red-700 text-xs"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
