const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000/api";

// ── Auth helpers ──

function getAuthHeaders(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const token = localStorage.getItem("access_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

const AUTH_PUBLIC_PATHS = ["/auth/login", "/auth/register", "/auth/refresh"];
let refreshPromise: Promise<boolean> | null = null;

async function tryRefreshToken(): Promise<boolean> {
  if (refreshPromise) return refreshPromise;

  refreshPromise = (async () => {
    try {
      const refreshToken = localStorage.getItem("refresh_token");
      if (!refreshToken) return false;

      const res = await fetch(`${API_BASE}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });

      if (!res.ok) return false;

      const data = await res.json();
      localStorage.setItem("access_token", data.access_token);
      localStorage.setItem("refresh_token", data.refresh_token);
      return true;
    } catch {
      return false;
    } finally {
      refreshPromise = null;
    }
  })();

  return refreshPromise;
}

// ── Core request ──

async function request<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const buildHeaders = (): Record<string, string> => ({
    ...getAuthHeaders(),
    ...(options?.body instanceof FormData
      ? {}
      : { "Content-Type": "application/json" }),
    ...((options?.headers as Record<string, string>) || {}),
  });

  let res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: buildHeaders(),
  });

  if (res.status === 401 && !AUTH_PUBLIC_PATHS.includes(path)) {
    const refreshed = await tryRefreshToken();
    if (refreshed) {
      res = await fetch(`${API_BASE}${path}`, {
        ...options,
        headers: buildHeaders(),
      });
    }
    if (res.status === 401) {
      if (typeof window !== "undefined") {
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
        window.location.href = "/login";
      }
      throw new Error("Session expired");
    }
  }

  if (!res.ok) {
    const errorBody = await res.text();
    throw new Error(`API Error ${res.status}: ${errorBody}`);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

// ── Dashboard ──
export async function getDashboardStats() {
  return request<import("./types").DashboardStats>("/dashboard/stats");
}

// ── Products ──
export async function getProducts(params?: {
  search?: string;
  group?: string;
  skip?: number;
  limit?: number;
}) {
  const query = new URLSearchParams();
  if (params?.search) query.set("search", params.search);
  if (params?.group) query.set("group", params.group);
  if (params?.skip) query.set("skip", String(params.skip));
  if (params?.limit) query.set("limit", String(params.limit));
  const qs = query.toString();
  return request<import("./types").Product[]>(`/products/${qs ? `?${qs}` : ""}`);
}

export async function getProductCount() {
  return request<{ count: number }>("/products/count");
}

export async function getProductGroups() {
  return request<string[]>("/products/groups/list");
}

export async function createProduct(data: Partial<import("./types").Product>) {
  return request<import("./types").Product>("/products/", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateProduct(
  id: number,
  data: Partial<import("./types").Product>
) {
  return request<import("./types").Product>(`/products/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function deleteProduct(id: number) {
  return request<void>(`/products/${id}`, { method: "DELETE" });
}

export async function importProductsExcel(file: File, replaceAll = false) {
  const formData = new FormData();
  formData.append("file", file);
  const url = `/products/import-excel${replaceAll ? "?replace_all=true" : ""}`;
  return request<import("./types").ImportResult>(url, {
    method: "POST",
    body: formData,
  });
}

// ── Suppliers ──
export async function getSuppliers() {
  return request<import("./types").Supplier[]>("/suppliers/");
}

export async function createSupplier(
  data: Omit<import("./types").Supplier, "id" | "created_at">
) {
  return request<import("./types").Supplier>("/suppliers/", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateSupplier(
  id: number,
  data: Partial<import("./types").Supplier>
) {
  return request<import("./types").Supplier>(`/suppliers/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function deleteSupplier(id: number) {
  return request<void>(`/suppliers/${id}`, { method: "DELETE" });
}

// ── Invoices ──
export async function getInvoices(params?: {
  status?: string;
  supplier_id?: number;
  skip?: number;
  limit?: number;
}) {
  const query = new URLSearchParams();
  if (params?.status) query.set("status", params.status);
  if (params?.supplier_id) query.set("supplier_id", String(params.supplier_id));
  if (params?.skip) query.set("skip", String(params.skip));
  if (params?.limit) query.set("limit", String(params.limit));
  const qs = query.toString();
  return request<import("./types").Invoice[]>(`/invoices/${qs ? `?${qs}` : ""}`);
}

export async function getInvoice(id: number) {
  return request<import("./types").InvoiceDetail>(`/invoices/${id}`);
}

export async function deleteInvoice(id: number) {
  return request<void>(`/invoices/${id}`, { method: "DELETE" });
}

export async function uploadInvoice(files: File[]) {
  const formData = new FormData();
  files.forEach((f) => formData.append("files", f));
  return request<import("./types").Invoice>("/invoices/upload", {
    method: "POST",
    body: formData,
  });
}

export async function reprocessInvoice(id: number) {
  return request<import("./types").Invoice>(`/invoices/${id}/reprocess`, {
    method: "POST",
  });
}

export async function matchInvoice(id: number) {
  return request<import("./types").MatchSummary>(`/invoices/${id}/match`, {
    method: "POST",
  });
}

export async function manualMatchItem(
  invoiceId: number,
  itemId: number,
  productId: number
) {
  return request<import("./types").InvoiceItem>(
    `/invoices/${invoiceId}/items/${itemId}/match`,
    {
      method: "PUT",
      body: JSON.stringify({ product_id: productId }),
    }
  );
}

export async function getItemSuggestions(
  invoiceId: number,
  itemId: number
) {
  return request<import("./types").ProductSuggestion[]>(
    `/invoices/${invoiceId}/items/${itemId}/suggestions`
  );
}

export async function getInvoiceSuggestions(invoiceId: number) {
  return request<Record<string, import("./types").ProductSuggestion[]>>(
    `/invoices/${invoiceId}/suggestions`
  );
}

// ── Reports ──
export async function generateReport(invoiceId: number) {
  const res = await fetch(`${API_BASE}/reports/invoices/${invoiceId}/generate-report`, {
    method: "POST",
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error(`Failed to generate report: ${res.status}`);
  return res.blob();
}

export async function downloadReport(invoiceId: number) {
  const res = await fetch(`${API_BASE}/reports/invoices/${invoiceId}/download-report`, {
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error(`Failed to download report: ${res.status}`);
  return res.blob();
}

// ── Chat ──
export async function sendChatMessage(
  message: string,
  history: { role: string; text: string }[],
  sessionId?: number | null
) {
  return request<import("./types").ChatResponse>("/chat/", {
    method: "POST",
    body: JSON.stringify({ message, history, session_id: sessionId ?? null }),
  });
}

export async function sendChatWithImage(
  message: string,
  history: { role: string; text: string }[],
  files: File[],
  sessionId?: number | null
) {
  const formData = new FormData();
  formData.append("message", message);
  formData.append("history", JSON.stringify(history));
  if (sessionId != null) formData.append("session_id", String(sessionId));
  files.forEach((f) => formData.append("files", f));

  const res = await fetch(`${API_BASE}/chat/with-image`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: formData,
  });
  if (!res.ok) {
    const errorBody = await res.text();
    throw new Error(`API Error ${res.status}: ${errorBody}`);
  }
  return res.json() as Promise<import("./types").ChatResponse>;
}

export async function listChatSessions() {
  return request<import("./types").SessionSummary[]>("/chat/sessions");
}

export async function getChatSession(sessionId: number) {
  return request<import("./types").SessionDetail>(`/chat/sessions/${sessionId}`);
}

export async function deleteChatSession(sessionId: number) {
  return request<void>(`/chat/sessions/${sessionId}`, { method: "DELETE" });
}

// ── Auth ──

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface AuthUser {
  id: number;
  email: string;
  full_name: string;
  is_active: boolean;
}

export async function loginUser(email: string, password: string) {
  return request<TokenResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function registerUser(
  email: string,
  password: string,
  fullName: string,
  inviteCode: string
) {
  return request<AuthUser>("/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password, full_name: fullName, invite_code: inviteCode }),
  });
}

export async function getCurrentUser() {
  return request<AuthUser>("/auth/me");
}

