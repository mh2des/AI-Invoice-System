<div align="center">

# AI Invoice Processing System

**Intelligent receipt & invoice processing powered by Google Gemini**

[![FastAPI](https://img.shields.io/badge/FastAPI-0.135-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-16.2-000000?logo=nextdotjs&logoColor=white)](https://nextjs.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org)
[![Gemini](https://img.shields.io/badge/Gemini_3.1_Flash_Lite-Preview-4285F4?logo=google&logoColor=white)](https://ai.google.dev)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

[Features](#features) · [Architecture](#architecture) · [Quick Start](#quick-start) · [API Reference](#api-reference) · [Contributing](#contributing)

</div>

---

## Overview

A production-ready web application that automates supplier invoice processing for small-to-medium accounting practices. Users upload receipt images or PDFs, and the system uses Google Gemini's multimodal AI to extract line items, automatically match them against a product database, and generate structured Excel reports — all in seconds.

## Features

### Core Processing Pipeline
- **AI-Powered Extraction** — Gemini 3.1 Flash-Lite extracts structured data from receipt images and PDFs with automatic fallback to Gemini 2.5 Flash
- **Multilingual Support** — Handles invoices in English, Arabic, Chinese, and Malay with automatic translation
- **Smart Matching Engine** — 4-tier cascade: barcode exact match → name exact match → fuzzy match (rapidfuzz) → manual assignment
- **Excel Report Generation** — One-click professional Excel reports with match status, confidence scores, and financial summaries

### AI Chat Assistant
- **Conversational AI** — Built-in chat assistant with full database context awareness
- **Image Analysis** — Attach receipt images to chat for instant analysis
- **Business Insights** — Ask questions about invoices, spending patterns, suppliers, and product data

### User Interface
- **Modern Dashboard** — Real-time stats: total invoices, match rates, recent activity
- **Drag & Drop Upload** — Multi-file upload with progress tracking and validation
- **Invoice Detail View** — Line-item table with match badges, manual match modal, and auto-refresh
- **Mobile Responsive** — Hamburger menu, slide-out drawer, full touch support
- **Duplicate Detection** — Warning banners for duplicate invoice numbers

### Resilience
- **Model Fallback** — Primary model (3.1 Flash-Lite) → Fallback (2.5 Flash) automatic cascade
- **Retry with Backoff** — Exponential backoff (3 attempts) on API failures
- **Graceful Degradation** — Meaningful error messages for blurry images, empty extractions, API failures

---

## Architecture

```
┌─────────────────────┐     ┌──────────────────────────────────┐
│   Next.js Frontend  │────▸│         FastAPI Backend           │
│   (React 19 + TW)   │◂────│                                  │
└─────────────────────┘     │  ┌──────────┐  ┌──────────────┐  │
                            │  │ Gemini   │  │ PostgreSQL   │  │
                            │  │ 3.1 Lite │  │ (Products,   │  │
                            │  │ ───────  │  │  Invoices,   │  │
                            │  │ 2.5 Flash│  │  Suppliers)  │  │
                            │  │(Fallback)│  │              │  │
                            │  └──────────┘  └──────────────┘  │
                            │  ┌──────────┐  ┌──────────────┐  │
                            │  │ Matching │  │ Excel Export  │  │
                            │  │ Engine   │  │ (openpyxl)   │  │
                            │  └──────────┘  └──────────────┘  │
                            └──────────────────────────────────┘
```

### Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| **Frontend** | Next.js (App Router) + React + Tailwind CSS | 16.2 / 19.2 / 3.4 |
| **Backend** | FastAPI + SQLAlchemy 2.0 (async) | 0.135 / 2.0 |
| **Database** | PostgreSQL + asyncpg | 17 |
| **AI** | Google Gemini (3.1 Flash-Lite + 2.5 Flash fallback) | google-genai 1.72 |
| **Matching** | rapidfuzz | 3.14 |
| **Reports** | openpyxl | 3.1 |
| **Migrations** | Alembic | 1.18 |

---

## Project Structure

```
.
├── backend/
│   ├── app/
│   │   ├── api/                    # Route handlers
│   │   │   ├── chat.py             #   Chat endpoints
│   │   │   ├── dashboard.py        #   Dashboard stats
│   │   │   ├── invoices.py         #   Invoice CRUD + upload
│   │   │   ├── products.py         #   Product CRUD + Excel import
│   │   │   ├── reports.py          #   Excel report generation
│   │   │   └── suppliers.py        #   Supplier CRUD
│   │   ├── core/
│   │   │   ├── config.py           #   Settings (env-based)
│   │   │   └── security.py         #   JWT auth utilities
│   │   ├── db/
│   │   │   ├── base.py             #   SQLAlchemy base model
│   │   │   └── session.py          #   Async session factory
│   │   ├── models/                 # SQLAlchemy ORM models
│   │   │   ├── invoice.py
│   │   │   ├── invoice_item.py
│   │   │   ├── product.py
│   │   │   └── supplier.py
│   │   ├── schemas/                # Pydantic request/response schemas
│   │   │   ├── invoice.py
│   │   │   ├── product.py
│   │   │   └── supplier.py
│   │   ├── services/               # Business logic
│   │   │   ├── chat.py             #   Gemini chat with DB context
│   │   │   ├── excel_export.py     #   Report generation
│   │   │   ├── excel_import.py     #   Product bulk import
│   │   │   ├── extraction.py       #   Gemini invoice extraction
│   │   │   ├── matching.py         #   4-tier matching engine
│   │   │   └── storage.py          #   File storage (R2/local)
│   │   └── main.py                 # FastAPI app entry point
│   ├── alembic/                    # Database migrations
│   ├── .env.example                # Environment template
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── app/                    # Next.js App Router pages
│   │   │   ├── chat/               #   AI assistant page
│   │   │   ├── invoices/           #   List + upload + detail
│   │   │   ├── products/           #   Product management
│   │   │   ├── suppliers/          #   Supplier management
│   │   │   ├── layout.tsx          #   Root layout + sidebar
│   │   │   └── page.tsx            #   Dashboard
│   │   ├── components/
│   │   │   └── Sidebar.tsx         #   Responsive navigation
│   │   └── lib/
│   │       ├── api.ts              #   API client (23 functions)
│   │       └── types.ts            #   TypeScript interfaces
│   ├── package.json
│   └── tailwind.config.ts
│
├── Receipt images exampls/         # Sample invoice images for testing
├── .gitignore
├── git-workflow.md                 # Git branching & workflow guide
├── GEMINI_COST_REPORT.md           # API cost analysis
└── README.md
```

---

## Quick Start

### Prerequisites

- **Python** 3.11+
- **Node.js** 18+
- **PostgreSQL** 15+
- **Google Gemini API Key** — [Get one free](https://aistudio.google.com/apikey)

### 1. Clone the repository

```bash
git clone https://github.com/mh2des/AI-Invoice-System.git
cd AI-Invoice-System
```

### 2. Backend setup

```bash
cd backend

# Create virtual environment
python -m venv .venv
source .venv/bin/activate        # Linux/Mac
# .venv\Scripts\activate         # Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your values:
#   DATABASE_URL=postgresql+asyncpg://postgres:yourpass@127.0.0.1:5432/invoice_system
#   GEMINI_API_KEY=your_actual_key
```

### 3. Database setup

```bash
# Create the database
createdb invoice_system

# Run migrations
alembic upgrade head
```

### 4. Frontend setup

```bash
cd ../frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

### 5. Start the backend

```bash
cd ../backend
source .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

### 6. Open the application

- **Frontend**: http://localhost:3000
- **Backend API docs**: http://127.0.0.1:8001/docs

---

## API Reference

### Invoices

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/invoices/` | List all invoices with optional filters |
| `GET` | `/api/invoices/{id}` | Get invoice detail with items |
| `POST` | `/api/invoices/upload` | Upload receipt image(s) for processing |
| `POST` | `/api/invoices/{id}/reprocess` | Re-run Gemini extraction |
| `POST` | `/api/invoices/{id}/match` | Run matching engine on invoice items |
| `PUT` | `/api/invoices/{id}/items/{item_id}/match` | Manual product match |
| `DELETE` | `/api/invoices/{id}` | Delete invoice and its items |

### Products

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/products/` | List all products (paginated, searchable) |
| `GET` | `/api/products/{id}` | Get product by ID |
| `POST` | `/api/products/` | Create a product |
| `PUT` | `/api/products/{id}` | Update a product |
| `DELETE` | `/api/products/{id}` | Delete a product |
| `POST` | `/api/products/import-excel` | Bulk import from Excel |
| `GET` | `/api/products/template` | Download Excel import template |

### Suppliers

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/suppliers/` | List all suppliers |
| `POST` | `/api/suppliers/` | Create a supplier |
| `PUT` | `/api/suppliers/{id}` | Update a supplier |
| `DELETE` | `/api/suppliers/{id}` | Delete a supplier |

### Reports

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/reports/{invoice_id}/generate` | Generate Excel report |
| `GET` | `/api/reports/{invoice_id}/download` | Download Excel report |

### Chat

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/chat/` | Send text message to AI assistant |
| `POST` | `/api/chat/with-image` | Send message with image attachment |

### Dashboard

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/dashboard/stats` | Get system statistics |

---

## Matching Engine

The matching engine runs a 4-tier cascade for each extracted line item:

```
1. Barcode Exact Match     → confidence: 1.00
         ↓ (no match)
2. Name Exact Match        → confidence: 0.95
         ↓ (no match)
3. Fuzzy Name Match        → confidence: from rapidfuzz (0.00–1.00)
         ↓ (below 0.75 threshold)
4. Unmatched               → flagged for manual review
```

Items with confidence below **0.75** are highlighted in the UI for manual assignment.

---

## AI Model Configuration

The system uses a **primary + fallback** model strategy:

| Role | Model | Use Case |
|------|-------|----------|
| **Primary** | `gemini-3.1-flash-lite-preview` | Fastest, most cost-efficient |
| **Fallback** | `gemini-2.5-flash` | Stable, reliable backup |

Models are configurable via environment variables:

```env
GEMINI_PRIMARY_MODEL=gemini-3.1-flash-lite-preview
GEMINI_FALLBACK_MODEL=gemini-2.5-flash
```

See [GEMINI_COST_REPORT.md](GEMINI_COST_REPORT.md) for detailed cost analysis.

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | — | PostgreSQL async connection string |
| `GEMINI_API_KEY` | Yes | — | Google Gemini API key |
| `GEMINI_PRIMARY_MODEL` | No | `gemini-3.1-flash-lite-preview` | Primary AI model |
| `GEMINI_FALLBACK_MODEL` | No | `gemini-2.5-flash` | Fallback AI model |
| `R2_ENDPOINT_URL` | No | — | Cloudflare R2 endpoint |
| `R2_ACCESS_KEY_ID` | No | — | R2 access key |
| `R2_SECRET_ACCESS_KEY` | No | — | R2 secret key |
| `R2_BUCKET_NAME` | No | `invoice-images` | R2 bucket name |
| `JWT_SECRET_KEY` | No | — | JWT signing secret |

---

## Contributing

This project uses a **feature-based branching** workflow. See [git-workflow.md](git-workflow.md) for the complete guide.

```bash
# Create a feature branch
git checkout -b feature/your-feature-name

# Make changes, commit with conventional commits
git commit -m "feat: add batch invoice upload"

# Push and create a PR
git push origin feature/your-feature-name
```

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

<div align="center">

**Built with FastAPI + Next.js + Google Gemini**

</div>
