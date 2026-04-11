# Gemini API Monthly Cost Report

## System Overview

| Component | Model | Temperature | Purpose |
|-----------|-------|-------------|---------|
| Invoice Extraction | `gemini-2.5-flash` | 0.1 | Extract structured JSON from receipt/invoice images |
| AI Chat Assistant | `gemini-2.5-flash` | 0.7 | Conversational AI with database context injection |

---

## Gemini 2.5 Flash Pricing (Paid Tier)

> Source: [Google AI Pricing](https://ai.google.dev/gemini-api/docs/pricing) — Last updated April 2025

| Token Type | Price per 1M Tokens |
|------------|---------------------|
| **Input** (text / image / video) | **$0.30** |
| **Output** (including thinking tokens) | **$2.50** |

**Important:** Gemini 2.5 Flash is a *thinking model*. Internal reasoning ("thinking") tokens are charged as output tokens. These invisible tokens can be 2–5x the visible response length.

---

## Free Tier Option

Google offers a **free Standard tier** with generous rate limits:

| Limit | Value |
|-------|-------|
| Requests per minute | 15 RPM |
| Requests per day | 1,500 RPD |
| Tokens per minute | 1,000,000 TPM |

**Trade-off:** Content on the free tier may be used by Google to improve their products.

For a small accounting business processing **< 1,500 invoices/day + chat messages**, the free tier may be sufficient at **$0.00/month**.

---

## Per-Operation Cost Breakdown

### 1. Invoice Extraction

Each extraction call sends the invoice image(s) plus a structured prompt (~350 tokens) and expects a JSON response.

| Component | Token Estimate | Notes |
|-----------|---------------|-------|
| **Input: Prompt** | ~350 tokens | Structured JSON schema + rules |
| **Input: Image** | ~258–800 tokens/image | Varies by resolution; typical receipt = ~500 tokens |
| **Output: JSON response** | ~400–800 tokens | Invoice data with items array |
| **Output: Thinking tokens** | ~500–2,000 tokens | Internal reasoning (charged as output) |

**Estimated totals per extraction:**

| | Conservative | Typical | High |
|--|-------------|---------|------|
| Input tokens | 600 | 850 | 1,200 |
| Output tokens (incl. thinking) | 900 | 1,500 | 2,800 |
| **Input cost** | $0.00018 | $0.00026 | $0.00036 |
| **Output cost** | $0.00225 | $0.00375 | $0.00700 |
| **Total per extraction** | **$0.00243** | **$0.00401** | **$0.00736** |

**Retry factor:** System retries up to 3 times on failure (exponential backoff). Assuming ~5% retry rate, multiply by **1.05x**.

**Adjusted cost per extraction: ~$0.0042** (typical)

---

### 2. Chat Message (Text Only)

Each chat call includes a system prompt with injected database context, full conversation history, and the current message.

| Component | Token Estimate | Notes |
|-----------|---------------|-------|
| **Input: System prompt** | ~150 tokens | Template instructions |
| **Input: DB context** | ~200–600 tokens | Injected stats, recent invoices, suppliers, products |
| **Input: Conversation history** | ~0–3,000 tokens | Grows with conversation length |
| **Input: Current message** | ~50–200 tokens | User's question |
| **Output: Response** | ~200–500 tokens | AI answer |
| **Output: Thinking tokens** | ~300–1,500 tokens | Internal reasoning |

**Estimated totals per chat message (mid-conversation):**

| | Short Chat | Typical | Long Conversation |
|--|-----------|---------|-------------------|
| Input tokens | 500 | 1,600 | 4,000 |
| Output tokens (incl. thinking) | 500 | 1,000 | 2,000 |
| **Input cost** | $0.00015 | $0.00048 | $0.00120 |
| **Output cost** | $0.00125 | $0.00250 | $0.00500 |
| **Total per message** | **$0.00140** | **$0.00298** | **$0.00620** |

---

### 3. Chat Message (With Image Attachment)

Same as text chat, plus an uploaded receipt/invoice image for analysis.

| | Typical | With Large Image |
|--|---------|-----------------|
| Input tokens | 1,900 | 2,800 |
| Output tokens (incl. thinking) | 1,500 | 2,500 |
| **Input cost** | $0.00057 | $0.00084 |
| **Output cost** | $0.00375 | $0.00625 |
| **Total per message** | **$0.00432** | **$0.00709** |

---

## Monthly Cost Scenarios

### Assumptions

| Parameter | Small Business | Medium Business | Busy Practice |
|-----------|---------------|-----------------|---------------|
| Invoices processed/month | 100 | 500 | 2,000 |
| Chat messages (text)/month | 50 | 200 | 800 |
| Chat messages (with image)/month | 10 | 30 | 100 |

---

### Scenario 1: Small Business (100 invoices/month)

| Operation | Volume | Unit Cost | Monthly Cost |
|-----------|--------|-----------|--------------|
| Invoice extraction | 100 | $0.0042 | $0.42 |
| Chat (text) | 50 | $0.0030 | $0.15 |
| Chat (image) | 10 | $0.0043 | $0.04 |
| **Total** | | | **$0.61** |

---

### Scenario 2: Medium Business (500 invoices/month)

| Operation | Volume | Unit Cost | Monthly Cost |
|-----------|--------|-----------|--------------|
| Invoice extraction | 500 | $0.0042 | $2.10 |
| Chat (text) | 200 | $0.0030 | $0.60 |
| Chat (image) | 30 | $0.0043 | $0.13 |
| **Total** | | | **$2.83** |

---

### Scenario 3: Busy Practice (2,000 invoices/month)

| Operation | Volume | Unit Cost | Monthly Cost |
|-----------|--------|-----------|--------------|
| Invoice extraction | 2,000 | $0.0042 | $8.40 |
| Chat (text) | 800 | $0.0030 | $2.40 |
| Chat (image) | 100 | $0.0043 | $0.43 |
| **Total** | | | **$11.23** |

---

## Summary Table

| Scenario | Invoices/mo | Chat/mo | **Monthly Cost** |
|----------|-------------|---------|------------------|
| Free Tier (< 1,500 RPD total) | Any | Any | **$0.00** |
| Small Business | 100 | 60 | **~$0.61** |
| Medium Business | 500 | 230 | **~$2.83** |
| Busy Practice | 2,000 | 900 | **~$11.23** |

---

## Key Observations

1. **Extremely affordable.** Even at 2,000 invoices/month, the cost is under $12/month.

2. **Free tier is viable.** For a small accounting practice (< 50 invoices/day), the free tier's 1,500 RPD limit is more than sufficient.

3. **Output tokens dominate costs.** At $2.50/M vs $0.30/M for input, output (including thinking) accounts for ~85% of total cost. The thinking tokens are the main cost driver.

4. **Extraction costs more than chat.** Due to the structured JSON output and image processing, each extraction costs ~40% more than a text chat message.

5. **Retry impact is minimal.** With only ~5% retry rate (exponential backoff), retries add ~$0.02–$0.50/month depending on volume.

6. **Images are cheap.** Image input tokens are charged at the same $0.30/M rate as text. A receipt image adds only ~$0.00015 to the input cost.

---

## Cost Optimization Tips

| Strategy | Potential Savings |
|----------|------------------|
| Use **free tier** for low volume | 100% — $0/month |
| Set `thinking_budget` to limit thinking tokens | 20–40% output savings |
| Use **Batch API** (50% cost reduction) for bulk processing | 50% on batch extractions |
| Cache system prompt with **Context Caching** ($0.03/M input) | 90% reduction on repeated system prompts |
| Downgrade to `gemini-2.5-flash-lite` ($0.10 input / $0.40 output) | ~70% cheaper per token |

---

*Report generated for the LLM Accounting Invoice Processing System.*
*Pricing data from Google AI Developer API (April 2025). Prices subject to change.*
