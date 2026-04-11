export interface Supplier {
  id: number;
  name: string;
  address: string | null;
  phone: string | null;
  bank_name: string | null;
  bank_account: string | null;
  notes: string | null;
  created_at: string;
}

export interface Product {
  id: number;
  stock_id: string | null;
  barcode: string;
  description: string;
  uom: string;
  cost: number;
  price: number;
  brand: string | null;
  group_name: string | null;
  category: string | null;
  balance_qty: number;
  tax_code: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ImportResult {
  inserted: number;
  updated: number;
  skipped: number;
  errors: string[];
}

export interface DashboardStats {
  total_invoices: number;
  total_products: number;
  total_suppliers: number;
  invoices_done: number;
  invoices_pending: number;
  invoices_failed: number;
  match_rate: number;
}

// ── Invoice types ──

export interface Invoice {
  id: number;
  invoice_number: string | null;
  supplier_id: number | null;
  invoice_date: string | null;
  payment_terms: string | null;
  currency: string;
  uploaded_by: string | null;
  image_urls: string[] | null;
  status: "pending" | "processing" | "done" | "failed";
  subtotal: number | null;
  discount_total: number | null;
  grand_total: number | null;
  excel_file_url: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface InvoiceItem {
  id: number;
  invoice_id: number;
  product_id: number | null;
  line_number: number | null;
  extracted_name: string | null;
  extracted_barcode: string | null;
  extracted_qty: number | null;
  extracted_uom: string | null;
  extracted_unit_price: number | null;
  extracted_discount: number | null;
  extracted_total: number | null;
  matched: boolean;
  match_confidence: number | null;
  match_method: string | null;
  created_at: string;
}

export interface InvoiceDetail extends Invoice {
  items: InvoiceItem[];
  supplier_name: string | null;
}

export interface MatchItemResult {
  item_id: number;
  line_number: number | null;
  extracted_name: string | null;
  product_id: number | null;
  product_name: string | null;
  matched: boolean;
  confidence: number | null;
  method: string | null;
  uom_mismatch: boolean;
}

export interface MatchSummary {
  total: number;
  matched: number;
  unmatched: number;
  match_rate: number;
  items: MatchItemResult[];
}

// ── Chat types ──

export interface ChatMessage {
  role: "user" | "assistant";
  text: string;
  images?: string[]; // data URLs for display
}

export interface ChatResponse {
  reply: string;
}
