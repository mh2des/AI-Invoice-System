# AI Invoice Processing System — Final Professional Plan

> **Revised after thorough review of:** project-idea.md, accounting-system-plan.pdf, data-example.xlsx (actual product DB export with 46 columns), and 4 sample invoice images (Al Buraq International, Tarim Trading, Alhabeeb Sunnah, handwritten cash invoice).

---

## Critical Changes from Original Plan

| # | Original Plan | Revised | Why |
|---|---------------|---------|-----|
| 1 | Called "receipts" | **Invoices** (supplier invoices) | These are B2B purchase invoices, not retail receipts. Professional terminology matters. |
| 2 | Google Docs output | **Excel export (primary) + Google Sheets (optional)** | Accountants work in spreadsheets. Google Docs is wrong for tabular data. Also eliminates Google Docs API + Drive API complexity. |
| 3 | Process page 1 only | **Process ALL pages** | Tarim Trading invoice is 4 pages. Losing 75% of line items is unacceptable. |
| 4 | Simple 8-column products table | **Schema matches real POS export** | The actual data has barcode, UOM, brand, group, category, cost, price, tax code — all needed for matching. |
| 5 | Extract: name, barcode, qty, price, total | **Also extract: invoice #, supplier, date, terms, UOM, discount** | All visible on real invoices. Essential for accounting. |
| 6 | No product DB import | **Excel import for product database** | Your friend already has the data in Excel. Manual re-entry of thousands of products is not viable. |
| 7 | English-only prompt | **Multilingual prompt (EN/AR/ZH/MS)** | Real invoices contain Arabic, Chinese, and Malay text. |
| 8 | Gemini 1.5 Flash | **Gemini 2.5 Flash** | Latest model, better multilingual OCR, better structured output. |
| 9 | No supplier tracking | **Suppliers table added** | Every invoice comes from a supplier. Track them. |
| 10 | No discount handling | **Discount per line item** | Al Buraq invoice shows 10% discount on item 3. Real invoices have discounts. |

---

## 1. What We're Building

A web-based system where an accountant uploads supplier invoice images (photos/PDFs), Gemini Vision extracts all line items across all pages, the system matches them against the existing product database, and outputs a structured Excel report — eliminating manual data entry and reducing errors.

### Architecture Flow

```
User (Accountant)
    ↓ upload invoice photo/PDF
Next.js Frontend
    ↓ API call
FastAPI Backend
    ├── Save image → Cloudflare R2
    ├── Send to Gemini 2.5 Flash (vision) → structured JSON
    ├── Match items → PostgreSQL product DB
    ├── Generate Excel report (openpyxl)
    └── Return results + downloadable Excel
    ↓
User reviews matches, corrects if needed, downloads report
```

---

## 2. Tech Stack

| Layer | Choice | Why |
|-------|--------|-----|
| Frontend | **Next.js 14 (App Router)** | Your stack, clean SSR/CSR |
| Backend | **FastAPI** | Your stack, async-first, fast |
| Database | **PostgreSQL + SQLAlchemy 2.0** | Your stack, JSONB support for raw extraction |
| AI/OCR | **Gemini 2.5 Flash (vision)** | Latest model — better multilingual OCR, structured JSON output, fast, cheap |
| Report Output | **Excel via openpyxl** | What accountants actually use. No extra API keys needed. Zero external dependencies. |
| Report Output (optional) | **Google Sheets API** | For shareable live spreadsheets. Phase 2 feature if needed. |
| File Storage | **Cloudflare R2** | Your infra, S3-compatible |
| Auth | **JWT (access + refresh)** | Standard, matches your backend pattern |
| Hosting | **Google Cloud Run (API) + Vercel (frontend)** | Your existing setup |

### What Was Removed
- **Google Docs API** — Wrong tool for tabular accounting data. Replaced with Excel export.
- **Google Drive API** — No longer needed (was only for Docs sharing permissions).
- **google-api-python-client** — Eliminated. One less dependency, one less API to authenticate.
- **pdf2image + Poppler** — Gemini 2.5 Flash accepts PDFs natively. No conversion needed.

### What Was Added
- **openpyxl** — Excel generation. Zero external API dependencies, accountant-friendly output.
- **Product DB Excel import** — Essential for initial setup with existing data.

---

## 3. APIs & Integrations

### Gemini 2.5 Flash — Primary AI

- **Model:** `gemini-2.5-flash` (vision capable, multilingual, structured output)
- **Usage:** Send invoice image(s) → receive structured JSON
- **SDK:** `google-generativeai` Python package
- **Multi-page handling:** Send all pages as multiple images in a single request. Gemini handles multi-image context natively.
- **PDF handling:** Gemini 2.5 Flash accepts PDF files directly — no conversion needed.

### Gemini Prompt (revised for real invoices)

```
You are a professional invoice data extraction assistant.
Extract all data from this supplier invoice image(s).

The invoice may contain text in English, Arabic (العربية), Chinese (中文), or Malay.
Translate all product names to English in the output.

Return ONLY valid JSON, no markdown, no preamble.

{
  "invoice_number": "string or null",
  "supplier_name": "string or null",
  "date": "YYYY-MM-DD or null",
  "payment_terms": "string or null",
  "currency": "MYR",
  "items": [
    {
      "item_name": "string",
      "barcode": "string or null",
      "quantity": number,
      "uom": "string (e.g. CTN, BOX, PCS, UNIT, PAKET)",
      "unit_price": number,
      "discount_percent": number or null,
      "total": number
    }
  ],
  "subtotal": number or null,
  "discount_total": number or null,
  "grand_total": number
}

Rules:
- If multiple pages, combine ALL items into one array.
- If a field is not visible or illegible, use null.
- For handwritten invoices, do your best — mark uncertain values with a trailing "?" in item_name.
- UOM must be extracted exactly as shown (CTN, BOX, PCS, etc.)
- Discount: if a line item shows a discount percentage, capture it.
- Grand total: the final amount after all discounts.
```

### Cloudflare R2 — File Storage
- Store uploaded invoice images/PDFs
- S3-compatible via boto3
- Presigned URLs for frontend image display

---

## 4. Database Schema (Revised)

Based on the actual `data-example.xlsx` export, the schema is aligned with the real product data structure.

```sql
-- ============================================
-- SUPPLIERS (NEW — tracks invoice sources)
-- ============================================
CREATE TABLE suppliers (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(255) NOT NULL,        -- "AL BURAQ INTERNATIONAL SDN BHD"
    address         TEXT,
    phone           VARCHAR(50),
    bank_name       VARCHAR(100),
    bank_account    VARCHAR(50),
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- PRODUCTS (revised to match real POS data)
-- ============================================
CREATE TABLE products (
    id              SERIAL PRIMARY KEY,
    stock_id        VARCHAR(50),                  -- internal stock code
    barcode         VARCHAR(50) UNIQUE NOT NULL,   -- "9555289101531"
    description     VARCHAR(500) NOT NULL,         -- "1*50 NYC LIGHTER TRANSPARENT AL505"
    uom             VARCHAR(20) DEFAULT 'PCS',     -- PCS, UNIT, CTN, BOX, etc.
    cost            DECIMAL(12,2) DEFAULT 0,       -- purchase cost
    price           DECIMAL(12,2) DEFAULT 0,       -- selling price
    brand           VARCHAR(100),
    group_name      VARCHAR(100),                  -- "JUICE&DRINKS"
    category        VARCHAR(100),
    balance_qty     DECIMAL(12,2) DEFAULT 0,       -- current stock balance
    tax_code        VARCHAR(20),                   -- "SV0", "EP-NA"
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_products_barcode ON products(barcode);
CREATE INDEX idx_products_description ON products(description);
CREATE INDEX idx_products_group ON products(group_name);

-- ============================================
-- INVOICES (renamed from receipts)
-- ============================================
CREATE TABLE invoices (
    id              SERIAL PRIMARY KEY,
    invoice_number  VARCHAR(100),                  -- "INV10839", "CS-0002306"
    supplier_id     INTEGER REFERENCES suppliers(id),
    uploaded_by     VARCHAR(100),
    image_urls      TEXT[],                        -- array of R2 URLs (multi-page)
    status          VARCHAR(20) DEFAULT 'pending'
                    CHECK (status IN ('pending', 'processing', 'done', 'failed')),
    invoice_date    DATE,
    payment_terms   VARCHAR(100),                  -- "C.O.D.", "60 DAYS"
    currency        VARCHAR(10) DEFAULT 'MYR',
    subtotal        DECIMAL(12,2),
    discount_total  DECIMAL(12,2),
    grand_total     DECIMAL(12,2),
    raw_extraction  JSONB,                         -- full Gemini JSON response
    excel_file_url  VARCHAR(500),                  -- generated report URL
    error_message   TEXT,                           -- if status = 'failed'
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- INVOICE ITEMS (renamed from receipt_items)
-- ============================================
CREATE TABLE invoice_items (
    id                  SERIAL PRIMARY KEY,
    invoice_id          INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    product_id          INTEGER REFERENCES products(id),  -- NULL if unmatched
    line_number         INTEGER,                           -- order on invoice
    extracted_name      VARCHAR(500),                      -- raw name from Gemini
    extracted_barcode   VARCHAR(50),
    extracted_qty       DECIMAL(12,2),
    extracted_uom       VARCHAR(20),                       -- CTN, BOX, PCS
    extracted_unit_price DECIMAL(12,2),
    extracted_discount  DECIMAL(5,2),                      -- discount percentage
    extracted_total     DECIMAL(12,2),
    matched             BOOLEAN DEFAULT FALSE,
    match_confidence    DECIMAL(4,2),                      -- 0.00 to 1.00
    match_method        VARCHAR(20),                       -- 'barcode', 'exact_name', 'fuzzy', 'manual'
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_invoice_items_invoice ON invoice_items(invoice_id);
CREATE INDEX idx_invoice_items_product ON invoice_items(product_id);
```

### What Changed from Original Schema
- **`suppliers` table added** — every invoice comes from a supplier
- **`products` expanded** — UOM, cost, brand, group, category, tax_code, balance_qty (mirrors real POS data)
- **`receipts` → `invoices`** — correct terminology + added invoice_number, supplier_id, payment_terms, discount_total, error_message
- **`receipt_items` → `invoice_items`** — added line_number, extracted_uom, extracted_discount, match_method
- **`image_urls` is now an array** — supports multi-page invoices (multiple photos/pages)

---

## 5. Backend Structure

```
app/
├── api/
│   ├── products.py         # CRUD + Excel bulk import
│   ├── invoices.py         # Upload, status, results, items
│   ├── suppliers.py        # CRUD for suppliers
│   └── reports.py          # Generate + download Excel report
├── services/
│   ├── extraction.py       # Gemini Vision call + JSON parse
│   ├── matching.py         # Barcode → exact name → fuzzy match
│   ├── excel_import.py     # Import products from Excel file
│   └── excel_export.py     # Generate Excel report (openpyxl)
├── models/
│   ├── product.py
│   ├── invoice.py
│   ├── invoice_item.py
│   └── supplier.py
├── schemas/
│   ├── product.py
│   ├── invoice.py
│   └── supplier.py
├── db/
│   ├── session.py
│   └── base.py
└── core/
    ├── config.py           # API keys, DB URL, R2 config
    └── security.py         # JWT auth
```

### Key additions from original:
- `excel_import.py` — Parse the POS export Excel and bulk-insert products
- `excel_export.py` — Generate professional Excel reports (replaces Google Docs)
- `suppliers.py` — CRUD for supplier management
- Split models into individual files for clarity

---

## 6. Matching Engine (Revised)

Same priority cascade, but now **UOM-aware**:

| Priority | Strategy | Confidence | Notes |
|----------|----------|------------|-------|
| 1 | Exact barcode match | 1.00 | Most reliable when barcode is visible |
| 2 | Exact description match (case-insensitive, trimmed) | 0.95 | Direct text match |
| 3 | Fuzzy description match (rapidfuzz) | Library score | Token sort ratio works best for reordered words |
| 4 | No match — flagged for review | < 0.75 | User picks correct product from dropdown |

**UOM handling:** When matched, compare extracted UOM with product UOM. If different (e.g., invoice says "CTN" but product UOM is "PCS"), flag with a note: "UOM mismatch — verify quantity."

**Threshold:** Items below **0.75 confidence** = "Unmatched — needs review" (highlighted in UI).

**Manual match:** When user manually matches an item, store `match_method = 'manual'` and `match_confidence = 1.00`. This builds training data for future improvement.

---

## 7. Excel Report Format (Replaces Google Docs)

Generated using **openpyxl** with professional formatting:

```
┌─────────────────────────────────────────────────────────────┐
│  INVOICE PROCESSING REPORT                                   │
│  Invoice #: INV10839                                         │
│  Supplier: AL BURAQ INTERNATIONAL SDN BHD                    │
│  Date: 04 Apr 2026         Processed: 11 Apr 2026           │
│  Terms: C.O.D.             Currency: MYR                     │
├─────┬──────────────┬──────────────┬─────┬─────┬────┬────────┤
│  #  │ Product Name │   Barcode    │ Qty │ UOM │U/P │ Total  │ Disc │ Match  │
├─────┼──────────────┼──────────────┼─────┼─────┼────┼────────┤
│  1  │ ALHARAMAIN.. │ 9555XXXXXXX  │ 5   │ BOX │ 38 │ 190.00 │  -   │ ✓ 1.00 │
│  2  │ ALHARAMAIN.. │ 9555XXXXXXX  │ 5   │ BOX │ 52 │ 260.00 │  -   │ ✓ 0.95 │
│  3  │ ROYAL ARM ..│              │ 1   │ CTN │ 72 │  64.80 │ 10%  │ ✗ 0.60 │
├─────┴──────────────┴──────────────┴─────┴─────┴────┴────────┤
│  Subtotal: MYR 522.00                                        │
│  Discount: MYR 7.20                                          │
│  GRAND TOTAL: MYR 514.80                                     │
├──────────────────────────────────────────────────────────────┤
│  Summary: 3 items │ 2 matched │ 1 needs review               │
│  Generated by AI Invoice Processing System                   │
└──────────────────────────────────────────────────────────────┘
```

**Features:**
- Professional header with supplier info and invoice metadata
- Color-coded match status (green = matched, amber = low confidence, red = unmatched)
- Discount column only shown when discounts exist
- Summary row with totals and match statistics
- Downloaded as `.xlsx` file — importable into any accounting software
- File stored in R2 for re-download

---

## 8. Product Database Import (NEW)

The accountant already has thousands of products in their POS system. Manual entry is not viable.

**Import flow:**
1. User uploads their Excel export (like `data-example.xlsx`)
2. Backend reads with openpyxl
3. Maps columns: `Stock ID → stock_id`, `Barcode → barcode`, `Description 1 → description`, `UOM ID → uom`, `Cost → cost`, `Price 1 → price`, `Brand Description → brand`, `Group Description → group_name`, `Category Description → category`
4. Bulk upsert into `products` table (update existing barcodes, insert new)
5. Return summary: X inserted, Y updated, Z skipped (invalid)

**Endpoint:** `POST /api/products/import-excel`

This is a **Day 2 deliverable** — before anything else can work, the product database must be populated.

---

## 9. Multi-Page Invoice Handling (Revised)

The original plan said "process page 1 only" — this is **unacceptable** for real invoices.

**Strategy:**
- **Photo uploads:** User uploads multiple photos (one per page). All are sent to Gemini as a multi-image request.
- **PDF uploads:** Gemini 2.5 Flash accepts PDFs natively with all pages. No conversion needed.
- **Gemini processes all pages in a single request** and returns one combined JSON array of all items.
- Frontend allows selecting/uploading multiple images for a single invoice.

This eliminates pdf2image + Poppler dependencies entirely.

---

## 10. Python Dependencies (Revised)

```
# Core
fastapi
uvicorn[standard]
sqlalchemy[asyncio]
alembic
asyncpg
pydantic-settings
python-multipart

# AI
google-generativeai          # Gemini 2.5 Flash

# Storage
boto3                        # Cloudflare R2 (S3-compatible)

# Processing
rapidfuzz                    # Fuzzy product name matching
openpyxl                     # Excel import AND export
pillow                       # Image handling (resize before upload if needed)

# Auth
python-jose[cryptography]    # JWT tokens
passlib[bcrypt]              # Password hashing
```

### Removed from original:
- `google-api-python-client` — No longer using Google Docs/Drive API
- `google-auth` — No longer need service account auth
- `pdf2image` — Gemini 2.5 Flash handles PDFs natively

### Added:
- `python-jose` + `passlib` — Proper JWT auth (was listed as a feature but not in dependencies)

**Total external API dependencies: 2** (was 4)
- Gemini API (extraction)
- Cloudflare R2 (storage)

---

## 11. Frontend Pages

| Page | Purpose |
|------|---------|
| **Login** | Simple JWT login |
| **Dashboard** | Stats: total invoices, match rate %, recent activity, quick upload button |
| **Upload Invoice** | Drag-and-drop zone for multiple images/PDF, supplier selector, progress indicator |
| **Invoices List** | Table with status chips (pending/processing/done/failed), date, supplier, total |
| **Invoice Detail** | Extracted items table, match status badges, manual match dropdown, download Excel button |
| **Products** | Searchable product list, Excel import button, add/edit product |
| **Suppliers** | Supplier list, add/edit supplier |

---

## 12. Revised 8-Day Execution Plan

### Day 1 — Foundation & Infrastructure
- Init FastAPI project with clean architecture
- Init Next.js 14 project with App Router
- PostgreSQL setup + Alembic migrations for all 4 tables (suppliers, products, invoices, invoice_items)
- Configure `.env`: Gemini API key, DB URL, R2 credentials, JWT secret
- Set up Cloudflare R2 bucket
- Git repo + basic CI

**Deliverable:** Both projects boot, DB migrations run, R2 connected.

---

### Day 2 — Product Database & Import
- Products CRUD endpoints (POST, GET list with search/filter, GET by barcode, PATCH, DELETE)
- **Excel import endpoint** — upload POS export → bulk insert products
- Suppliers CRUD endpoints (POST, GET, PATCH)
- Pydantic schemas for products and suppliers
- Seed script OR import from `data-example.xlsx`
- Frontend: Products page (list + search + import button) and Suppliers page

**Deliverable:** Product DB populated from Excel import. CRUD working via API and UI.

---

### Day 3 — Gemini Extraction Pipeline
- Invoice upload endpoint → save images to R2 → create invoice row
- `extraction.py` service:
  - Download images from R2
  - Send to Gemini 2.5 Flash with the multilingual structured prompt
  - Parse JSON response into `InvoiceExtraction` model
  - Handle multi-page: send all images in single Gemini request
  - Handle PDF: send directly (Gemini accepts PDF natively)
- Store raw Gemini JSON in `invoices.raw_extraction`
- Auto-detect supplier from extracted text, link to `suppliers` table if exists
- Status tracking: pending → processing → done / failed
- Background processing via FastAPI `BackgroundTasks` (don't block upload response)

**Deliverable:** Upload invoice → Gemini extracts all items → stored in DB.

---

### Day 4 — Matching Engine
- `matching.py` service:
  - Priority cascade: barcode → exact name → fuzzy (rapidfuzz)
  - UOM comparison and mismatch flagging
  - Store match method and confidence per item
- Save `invoice_items` rows with match results
- Flag items below 0.75 confidence as unmatched
- Endpoint: `GET /invoices/{id}/items` returns matched + unmatched
- Frontend: Invoice detail page with match badges (green/amber/red)
- Manual match UI: dropdown to pick correct product for unmatched items

**Deliverable:** Full extraction-to-match pipeline working E2E.

---

### Day 5 — Excel Report Generation
- `excel_export.py` service using openpyxl:
  - Professional header (supplier info, invoice metadata)
  - Items table with all columns
  - Color-coded match status
  - Summary section (totals, match statistics)
  - Styled with borders, fonts, column widths
- `POST /invoices/{id}/generate-report` → creates Excel → stores in R2
- `GET /invoices/{id}/download-report` → returns Excel file
- Test with all 4 sample invoices

**Deliverable:** Click button → download professional Excel report.

---

### Day 6 — Frontend Core UI
- Layout: sidebar nav (Dashboard, Invoices, Products, Suppliers)
- Dashboard: stats cards (total invoices, match rate, recent activity)
- Invoices list page: status chips, supplier name, date, total
- Invoice upload page: drag-and-drop for multiple files, supplier dropdown, progress
- JWT login page

**Deliverable:** Clean functional UI, upload flow works.

---

### Day 7 — Frontend: Results & Polish
- Invoice detail page:
  - Extracted items table with match status
  - Unmatched items highlighted amber/red
  - Manual match dropdown per unmatched item
  - "Download Report" button
  - "Re-process" button (retry Gemini extraction)
- Product import UI: Excel file upload with progress and result summary
- Mobile-responsive layout (receipts are often photographed on phones)

**Deliverable:** Full user journey works start to finish.

---

### Day 8 — Error Handling, Testing & Deploy
- Backend: proper error handling, structured logging, Gemini retry with exponential backoff
- Edge cases:
  - Blurry/unreadable images → status = 'failed' with helpful error message
  - Empty extraction → prompt user to re-upload better photo
  - Gemini returns invalid JSON → retry once with stricter prompt
  - Duplicate invoice number warning
- Deploy FastAPI to Google Cloud Run
- Deploy Next.js to Vercel
- Final smoke test with all 4 real invoices + additional test cases
- Write brief user guide for the accountant

**Deliverable:** Live, deployed, tested system.

---

## 13. API Endpoints Summary

```
AUTH
  POST   /api/auth/login              # JWT login
  POST   /api/auth/refresh             # Refresh token

SUPPLIERS
  GET    /api/suppliers                # List all
  POST   /api/suppliers                # Create
  PATCH  /api/suppliers/{id}           # Update
  DELETE /api/suppliers/{id}           # Delete

PRODUCTS
  GET    /api/products                 # List (search, filter by group)
  GET    /api/products/{barcode}       # Get by barcode
  POST   /api/products                 # Create single
  PATCH  /api/products/{id}            # Update
  DELETE /api/products/{id}            # Delete
  POST   /api/products/import-excel    # Bulk import from Excel

INVOICES
  GET    /api/invoices                 # List (filter by status, supplier, date)
  POST   /api/invoices/upload          # Upload images/PDF → start processing
  GET    /api/invoices/{id}            # Get invoice details
  GET    /api/invoices/{id}/items      # Get extracted & matched items
  PATCH  /api/invoices/{id}/items/{item_id}/match   # Manual match
  POST   /api/invoices/{id}/reprocess  # Re-run Gemini extraction
  DELETE /api/invoices/{id}            # Delete invoice

REPORTS
  POST   /api/invoices/{id}/generate-report   # Generate Excel
  GET    /api/invoices/{id}/download-report    # Download Excel file

DASHBOARD
  GET    /api/dashboard/stats          # Summary statistics
```

---

## 14. Key Risks & Mitigations (Revised)

| Risk | Mitigation |
|------|-----------|
| **Handwritten invoices** (images 3 & 4) | Gemini handles handwriting reasonably well. Flag low-confidence items. Show original image alongside extraction for manual verification. |
| **Arabic/Chinese text misread** | Prompt explicitly lists supported languages. Translate to English in output. Test with real samples during Day 3. |
| **Multi-page photo uploads out of order** | Let user reorder images before submitting. Number pages in UI. |
| **Gemini returns invalid JSON** | Wrap in try/catch, retry once with stricter prompt. If second attempt fails, mark as 'failed' with error message. |
| **Product DB has thousands of items → slow fuzzy matching** | Pre-filter by group/category if available. Use rapidfuzz `process.extractOne` with score cutoff — already optimized in C. |
| **UOM mismatches** (invoice says CTN, product DB says PCS) | Flag mismatch in UI, don't auto-calculate. Let accountant resolve. |
| **Duplicate invoice upload** | Warn if invoice_number + supplier already exists. Allow override. |
| **Blurry phone photos** | Show image quality warning if file size < 100KB. Recommend good lighting in user guide. |

---

## 15. Day-by-Day Summary

| Day | Focus | Key Milestone |
|-----|-------|---------------|
| 1 | Foundation & Infrastructure | Both projects boot, DB ready, R2 connected |
| 2 | Product DB & Import | Products imported from Excel, CRUD working |
| 3 | Gemini Pipeline | Invoice upload → AI extraction → stored in DB |
| 4 | Matching Engine | Items matched against product DB with confidence scores |
| 5 | Excel Reports | Professional Excel report generated and downloadable |
| 6 | Frontend Core | Upload flow, invoices list, dashboard |
| 7 | Frontend Results & Polish | Full user journey, manual matching, mobile-ready |
| 8 | Testing & Deploy | Live system, tested with real invoices |

---

## 16. Environment Variables

```env
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/invoice_system

# Gemini AI
GEMINI_API_KEY=your_gemini_api_key

# Cloudflare R2
R2_ENDPOINT_URL=https://your-account.r2.cloudflarestorage.com
R2_ACCESS_KEY_ID=your_access_key
R2_SECRET_ACCESS_KEY=your_secret_key
R2_BUCKET_NAME=invoice-images

# JWT Auth
JWT_SECRET_KEY=your-secure-random-key
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7
```

**Eliminated from original:** Google Service Account JSON, Google Docs credentials, Google Drive credentials. The move from Google Docs to Excel export removed 3 environment configuration steps.

---

*This plan is designed for a solo developer, prioritizing professional quality without unnecessary complexity. It reflects the actual invoice types, product data structure, and accounting workflow observed from the real samples provided.*
