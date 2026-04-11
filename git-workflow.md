# Git Workflow Guide

This project follows a **feature-based branching** strategy. Every change — whether a new feature, bug fix, or improvement — lives on its own branch and merges into `main` through a clean, documented history.

---

## Branch Naming Convention

| Branch Type | Pattern | Example |
|-------------|---------|---------|
| **Feature** | `feature/<short-description>` | `feature/batch-upload` |
| **Bug Fix** | `fix/<short-description>` | `fix/extraction-retry` |
| **Improvement** | `improve/<short-description>` | `improve/matching-speed` |
| **Refactor** | `refactor/<short-description>` | `refactor/api-structure` |
| **Docs** | `docs/<short-description>` | `docs/api-reference` |
| **Chore** | `chore/<short-description>` | `chore/update-deps` |

**Rules:**
- Use lowercase and hyphens (no spaces or underscores)
- Keep it short but descriptive (2–4 words)
- Never commit directly to `main`

---

## Commit Message Convention

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short description>
```

### Types

| Type | When to Use |
|------|-------------|
| `feat` | New feature or capability |
| `fix` | Bug fix |
| `improve` | Enhancement to existing feature |
| `refactor` | Code restructure (no behavior change) |
| `docs` | Documentation changes |
| `style` | Formatting, linting (no logic change) |
| `chore` | Dependencies, config, tooling |
| `test` | Adding or updating tests |

### Scopes

| Scope | Area |
|-------|------|
| `extraction` | Gemini extraction pipeline |
| `matching` | Product matching engine |
| `chat` | AI chat assistant |
| `invoices` | Invoice CRUD & processing |
| `products` | Product management |
| `suppliers` | Supplier management |
| `reports` | Excel report generation |
| `dashboard` | Dashboard & stats |
| `ui` | Frontend components & layout |
| `api` | Backend API endpoints |
| `db` | Database models & migrations |
| `config` | Configuration & environment |
| `auth` | Authentication & security |

### Examples

```bash
feat(extraction): add PDF multi-page support
fix(matching): handle empty barcode in fuzzy search
improve(ui): add loading skeleton to invoice list
refactor(api): split invoice router into sub-modules
chore(config): upgrade google-genai to 2.0
docs: update API reference with chat endpoints
```

---

## Workflow: Adding a New Feature

### Step 1 — Create a feature branch

```bash
# Make sure you're on main and up to date
git checkout main
git pull origin main

# Create your feature branch
git checkout -b feature/your-feature-name
```

### Step 2 — Develop on your branch

Make your changes. Commit frequently with meaningful messages:

```bash
git add .
git commit -m "feat(invoices): add batch upload endpoint"
```

If the feature involves multiple logical steps, make multiple commits:

```bash
git commit -m "feat(invoices): add batch upload API endpoint"
git commit -m "feat(ui): add batch upload drag-and-drop UI"
git commit -m "test(invoices): add batch upload validation tests"
```

### Step 3 — Push your branch

```bash
git push origin feature/your-feature-name
```

### Step 4 — Create a Pull Request (optional for solo dev)

If working solo, you can merge locally:

```bash
git checkout main
git merge feature/your-feature-name
git push origin main
```

If collaborating, create a PR on GitHub and request review.

### Step 5 — Clean up

```bash
# Delete the local feature branch
git branch -d feature/your-feature-name

# Delete the remote feature branch
git push origin --delete feature/your-feature-name
```

---

## Workflow: Quick Bug Fix

```bash
git checkout main
git pull origin main
git checkout -b fix/invoice-date-parsing

# Fix the bug
git add .
git commit -m "fix(extraction): handle null date from Gemini response"

# Merge back
git checkout main
git merge fix/invoice-date-parsing
git push origin main

# Clean up
git branch -d fix/invoice-date-parsing
```

---

## Keeping Your Branch Up to Date

If `main` has moved forward while you're working on a feature:

```bash
# On your feature branch
git fetch origin
git rebase origin/main

# Resolve any conflicts, then continue
git rebase --continue
```

---

## Release Tags

When a significant milestone is reached, tag it:

```bash
git tag -a v1.0.0 -m "Release: Full invoice processing pipeline"
git push origin v1.0.0
```

### Versioning

| Version | Meaning |
|---------|---------|
| `v1.0.0` | First production-ready release |
| `v1.1.0` | New feature added |
| `v1.0.1` | Bug fix release |
| `v2.0.0` | Breaking changes |

---

## Current Feature History

The initial `main` branch includes these completed features:

| Feature | Description |
|---------|-------------|
| Foundation | FastAPI + Next.js + PostgreSQL project setup |
| Product Management | CRUD + Excel bulk import + search |
| Supplier Management | CRUD with product linking |
| Gemini Extraction | Invoice image/PDF → structured JSON |
| Matching Engine | 4-tier cascade (barcode → exact → fuzzy → manual) |
| Excel Reports | Professional Excel report generation |
| Invoice UI | List, upload, detail pages with status tracking |
| Dashboard | Stats cards + recent activity |
| Mobile Responsive | Hamburger menu, slide-out sidebar |
| Error Handling | Retry with backoff, duplicate detection, warnings |
| AI Chat Assistant | Conversational AI with DB context + image support |
| Model Fallback | Gemini 3.1 Flash-Lite primary → 2.5 Flash fallback |

---

## Example: Next Features to Branch

Here are some features you might add next, with their proper branch names:

```bash
# User authentication
git checkout -b feature/user-auth

# Multi-page PDF processing
git checkout -b feature/pdf-multipage

# Supplier auto-detection from invoice
git checkout -b feature/supplier-autodetect

# Invoice search and filtering
git checkout -b feature/invoice-search

# Dark mode
git checkout -b feature/dark-mode

# Export all invoices to CSV
git checkout -b feature/csv-export

# Cloudflare R2 image storage
git checkout -b feature/r2-storage

# Google Docs report output
git checkout -b feature/google-docs-reports
```

---

## Quick Reference

```bash
# See all branches
git branch -a

# See commit history (compact)
git log --oneline --graph --all

# Undo last commit (keep changes)
git reset --soft HEAD~1

# Stash work in progress
git stash
git stash pop

# See what changed
git diff --stat
```
