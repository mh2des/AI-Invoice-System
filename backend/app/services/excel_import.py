from decimal import Decimal, InvalidOperation
from io import BytesIO

from openpyxl import load_workbook
from sqlalchemy import delete, select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invoice import InvoiceItem
from app.models.product import Product
from app.schemas.product import ProductImportResult

# Column mapping from POS Excel export to our product fields.
# Maps header names to our DB column names.
COLUMN_MAP = {
    "Stock ID": "stock_id",
    "Barcode": "barcode",
    "Description 1": "description",
    "UOM ID": "uom",
    "Cost": "cost",
    "Price 1": "price",
    "Balance Quantity (UOM)": "balance_qty",
    "Brand Description": "brand",
    "Group Description": "group_name",
    "Category Description": "category",
    "Supply Tax Code (SST)": "tax_code",
}


def _safe_decimal(value) -> Decimal:
    """Convert a value to Decimal, defaulting to 0."""
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _safe_str(value, max_len: int = 500) -> str:
    """Convert a value to a trimmed string."""
    if value is None:
        return ""
    return str(value).strip()[:max_len]


async def import_products_from_excel(
    file_content: bytes,
    db: AsyncSession,
    replace_all: bool = False,
) -> ProductImportResult:
    """
    Import products from a POS Excel export.
    - If replace_all=True: deletes ALL existing products atomically, then inserts
      everything from the file (full database replacement). Invoice items that
      referenced old products have their product_id set to NULL first so the FK
      constraint is not violated.
    - If replace_all=False (default): upserts — updates existing by barcode,
      inserts new ones.
    - Skips rows with empty/missing barcode or description.
    - The entire operation runs in one DB transaction; any error triggers a full
      rollback so the database is never left in a partial state.
    """
    wb = load_workbook(filename=BytesIO(file_content), read_only=True)
    ws = wb.active

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return ProductImportResult(inserted=0, updated=0, skipped=0, errors=["Empty file"])

    # Build column index map from header row
    header_row = rows[0]
    col_index = {}
    for i, header in enumerate(header_row):
        if header and str(header).strip() in COLUMN_MAP:
            col_index[COLUMN_MAP[str(header).strip()]] = i

    # Validate required columns exist
    if "barcode" not in col_index:
        return ProductImportResult(
            inserted=0, updated=0, skipped=0,
            errors=["Missing required column: 'Barcode'"]
        )
    if "description" not in col_index:
        return ProductImportResult(
            inserted=0, updated=0, skipped=0,
            errors=["Missing required column: 'Description 1'"]
        )

    inserted = 0
    updated = 0
    skipped = 0
    deleted = 0
    errors = []

    data_rows = rows[1:]

    # ── REPLACE ALL MODE ──────────────────────────────────────────────────────
    # Parse ALL rows first (before touching the DB), so that if the Excel is
    # malformed we abort without deleting anything.
    if replace_all:
        # Build the full list of valid product dicts from the file
        new_products: list[dict] = []
        for row_num, row in enumerate(data_rows, start=2):
            try:
                barcode = _safe_str(row[col_index["barcode"]])
                description = _safe_str(row[col_index["description"]])
                if not barcode or not description:
                    skipped += 1
                    continue
                if barcode == "00" or description == "00":
                    skipped += 1
                    continue
                product_data = {
                    "barcode": barcode,
                    "description": description,
                    "stock_id": _safe_str(row[col_index["stock_id"]]) if "stock_id" in col_index else None,
                    "uom": _safe_str(row[col_index["uom"]], 20) if "uom" in col_index else "PCS",
                    "cost": _safe_decimal(row[col_index["cost"]]) if "cost" in col_index else Decimal("0"),
                    "price": _safe_decimal(row[col_index["price"]]) if "price" in col_index else Decimal("0"),
                    "balance_qty": _safe_decimal(row[col_index["balance_qty"]]) if "balance_qty" in col_index else Decimal("0"),
                    "brand": _safe_str(row[col_index["brand"]], 100) if "brand" in col_index else None,
                    "group_name": _safe_str(row[col_index["group_name"]], 100) if "group_name" in col_index else None,
                    "category": _safe_str(row[col_index["category"]], 100) if "category" in col_index else None,
                    "tax_code": _safe_str(row[col_index["tax_code"]], 20) if "tax_code" in col_index else None,
                }
                for key in ("brand", "group_name", "category", "stock_id"):
                    if product_data.get(key) == "NA":
                        product_data[key] = None
                new_products.append(product_data)
            except Exception as e:
                errors.append(f"Row {row_num}: {str(e)}")
                skipped += 1

        if not new_products:
            wb.close()
            return ProductImportResult(inserted=0, updated=0, skipped=skipped, deleted=0, errors=errors or ["No valid products found in file"])

        # Count existing products before deletion
        count_result = await db.execute(select(func.count(Product.id)))
        deleted = count_result.scalar() or 0

        # Step 1: Null out all product_id FKs on invoice items to avoid constraint violation
        await db.execute(update(InvoiceItem).values(product_id=None))

        # Step 2: Delete all products
        await db.execute(delete(Product))

        # Step 3: Insert all new products in bulk
        db.add_all([Product(**p) for p in new_products])
        inserted = len(new_products)

        await db.commit()
        wb.close()
        return ProductImportResult(inserted=inserted, updated=0, skipped=skipped, deleted=deleted, errors=errors[:50])

    # ── UPSERT MODE (default) ─────────────────────────────────────────────────
    result = await db.execute(select(Product.barcode, Product.id))
    existing_barcodes: dict[str, int] = {row[0]: row[1] for row in result.all()}

    for row_num, row in enumerate(data_rows, start=2):
        try:
            barcode = _safe_str(row[col_index["barcode"]])
            description = _safe_str(row[col_index["description"]])

            # Skip rows without barcode or description
            if not barcode or not description:
                skipped += 1
                continue

            # Skip placeholder/test rows (e.g., barcode "00")
            if barcode == "00" or description == "00":
                skipped += 1
                continue

            # Build product data
            product_data = {
                "barcode": barcode,
                "description": description,
                "stock_id": _safe_str(row[col_index["stock_id"]]) if "stock_id" in col_index else None,
                "uom": _safe_str(row[col_index["uom"]], 20) if "uom" in col_index else "PCS",
                "cost": _safe_decimal(row[col_index["cost"]]) if "cost" in col_index else Decimal("0"),
                "price": _safe_decimal(row[col_index["price"]]) if "price" in col_index else Decimal("0"),
                "balance_qty": _safe_decimal(row[col_index["balance_qty"]]) if "balance_qty" in col_index else Decimal("0"),
                "brand": _safe_str(row[col_index["brand"]], 100) if "brand" in col_index else None,
                "group_name": _safe_str(row[col_index["group_name"]], 100) if "group_name" in col_index else None,
                "category": _safe_str(row[col_index["category"]], 100) if "category" in col_index else None,
                "tax_code": _safe_str(row[col_index["tax_code"]], 20) if "tax_code" in col_index else None,
            }

            # Clean up "NA" placeholder values
            for key in ("brand", "group_name", "category", "stock_id"):
                if product_data.get(key) == "NA":
                    product_data[key] = None

            if barcode in existing_barcodes:
                # Update existing product
                product = await db.get(Product, existing_barcodes[barcode])
                if product:
                    for field, value in product_data.items():
                        setattr(product, field, value)
                    updated += 1
            else:
                # Insert new product
                product = Product(**product_data)
                db.add(product)
                existing_barcodes[barcode] = -1  # Mark as seen
                inserted += 1

        except Exception as e:
            errors.append(f"Row {row_num}: {str(e)}")
            skipped += 1

    await db.commit()
    wb.close()

    return ProductImportResult(
        inserted=inserted,
        updated=updated,
        skipped=skipped,
        deleted=deleted,
        errors=errors[:50],  # Cap error list
    )
