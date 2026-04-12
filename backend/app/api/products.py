from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.product import Product
from app.schemas.product import ProductCreate, ProductImportResult, ProductResponse, ProductUpdate
from app.services.excel_import import import_products_from_excel

router = APIRouter(prefix="/products", tags=["Products"])


@router.get("/", response_model=list[ProductResponse])
async def list_products(
    search: str | None = Query(None, description="Search by description or barcode"),
    group: str | None = Query(None, description="Filter by group"),
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    query = select(Product).where(Product.is_active == True)  # noqa: E712

    if search:
        search_filter = f"%{search}%"
        query = query.where(
            (Product.description.ilike(search_filter))
            | (Product.barcode.ilike(search_filter))
        )

    if group:
        query = query.where(Product.group_name == group)

    query = query.order_by(Product.description).offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/count")
async def count_products(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(func.count(Product.id)))
    return {"count": result.scalar()}


@router.post("/import-excel", response_model=ProductImportResult)
async def import_products_excel(
    file: UploadFile = File(..., description="POS Excel export file (.xlsx)"),
    replace_all: bool = Query(False, description="If true, delete all existing products and replace with this file"),
    db: AsyncSession = Depends(get_db),
):
    if not file.filename or not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Only .xlsx/.xls files are accepted")

    content = await file.read()
    if len(content) > 20 * 1024 * 1024:  # 20MB limit
        raise HTTPException(status_code=400, detail="File too large (max 20MB)")

    result = await import_products_from_excel(content, db, replace_all=replace_all)
    return result


@router.get("/barcode/{barcode}", response_model=ProductResponse)
async def get_product_by_barcode(barcode: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product).where(Product.barcode == barcode))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.get("/groups/list")
async def list_product_groups(db: AsyncSession = Depends(get_db)):
    """Return distinct product groups for filter dropdowns."""
    result = await db.execute(
        select(Product.group_name)
        .where(Product.group_name.isnot(None))
        .distinct()
        .order_by(Product.group_name)
    )
    return [row[0] for row in result.all()]


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(product_id: int, db: AsyncSession = Depends(get_db)):
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.post("/", response_model=ProductResponse, status_code=201)
async def create_product(data: ProductCreate, db: AsyncSession = Depends(get_db)):
    # Check barcode uniqueness
    existing = await db.execute(select(Product).where(Product.barcode == data.barcode))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Product with this barcode already exists")

    product = Product(**data.model_dump())
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


@router.patch("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: int, data: ProductUpdate, db: AsyncSession = Depends(get_db)
):
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    await db.commit()
    await db.refresh(product)
    return product


@router.delete("/{product_id}", status_code=204)
async def delete_product(product_id: int, db: AsyncSession = Depends(get_db)):
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    await db.delete(product)
    await db.commit()
