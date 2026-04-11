"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import {
  getProducts,
  getProductGroups,
  importProductsExcel,
  deleteProduct,
} from "@/lib/api";
import type { Product, ImportResult } from "@/lib/types";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { Upload, Trash2, CheckCircle2 } from "lucide-react";

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
    <div className="p-4 md:p-8">
      <PageHeader
        title="Products"
        description={`${products.length} product${products.length !== 1 ? "s" : ""} loaded`}
      >
        <input
          ref={fileRef}
          type="file"
          accept=".xlsx,.xls"
          onChange={handleImport}
          className="hidden"
          id="excel-upload"
        />
        <Button
          onClick={() => fileRef.current?.click()}
          disabled={importing}
        >
          <Upload className="h-4 w-4 mr-2" />
          {importing ? "Importing…" : "Import Excel"}
        </Button>
      </PageHeader>

      {importResult && (
        <Alert className="mb-4 border-green-200 bg-green-50">
          <CheckCircle2 className="h-4 w-4 text-green-600" />
          <AlertTitle className="text-green-800">Import Complete</AlertTitle>
          <AlertDescription className="text-green-700">
            {importResult.inserted} inserted, {importResult.updated} updated,{" "}
            {importResult.skipped} skipped
            {importResult.errors.length > 0 && (
              <span className="text-destructive">
                , {importResult.errors.length} error(s)
              </span>
            )}
            {importResult.errors.length > 0 && (
              <ul className="mt-2 text-destructive list-disc list-inside">
                {importResult.errors.slice(0, 5).map((e, i) => (
                  <li key={i}>{e}</li>
                ))}
              </ul>
            )}
            <button
              onClick={() => setImportResult(null)}
              className="block mt-2 text-xs text-green-600 underline"
            >
              Dismiss
            </button>
          </AlertDescription>
        </Alert>
      )}

      <div className="flex gap-3 mb-4">
        <Input
          type="text"
          placeholder="Search by name or barcode…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1"
        />
        <Select value={group} onValueChange={(v) => setGroup(v ?? "")}>
          <SelectTrigger className="w-[200px]">
            <SelectValue placeholder="All Groups" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All Groups</SelectItem>
            {groups.map((g) => (
              <SelectItem key={g} value={g}>
                {g}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Barcode</TableHead>
                <TableHead>Description</TableHead>
                <TableHead>UOM</TableHead>
                <TableHead className="text-right">Cost</TableHead>
                <TableHead className="text-right">Price</TableHead>
                <TableHead>Group</TableHead>
                <TableHead className="text-right">Qty</TableHead>
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
              ) : products.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={8} className="text-center py-8 text-muted-foreground">
                    No products found. Import an Excel file to get started.
                  </TableCell>
                </TableRow>
              ) : (
                products.map((p) => (
                  <TableRow key={p.id}>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {p.barcode}
                    </TableCell>
                    <TableCell>{p.description}</TableCell>
                    <TableCell className="text-muted-foreground">{p.uom}</TableCell>
                    <TableCell className="text-right">
                      {Number(p.cost).toFixed(2)}
                    </TableCell>
                    <TableCell className="text-right">
                      {Number(p.price).toFixed(2)}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {p.group_name || "—"}
                    </TableCell>
                    <TableCell className="text-right text-muted-foreground">
                      {p.balance_qty}
                    </TableCell>
                    <TableCell className="text-center">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDelete(p.id, p.description)}
                        className="text-destructive hover:text-destructive"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
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
