from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, or_, select

from ..deps import DB
from ..layout import layout_variants
from ..models import Category, Product
from ..schemas import CategoryOut, ProductOut, ProductPage

router = APIRouter(tags=["catalog"])

SORTS = {
    "name": Product.name.asc(),
    "price_asc": Product.price.asc(),
    "price_desc": Product.price.desc(),
    "newest": Product.created_at.desc(),
}


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(db: DB):
    return db.scalars(select(Category).order_by(Category.name)).all()


def _category_ids(db, root_id: int) -> list[int]:
    """The category and all its descendants."""
    ids, frontier = [root_id], [root_id]
    while frontier:
        frontier = list(db.scalars(select(Category.id).where(Category.parent_id.in_(frontier))))
        ids.extend(frontier)
    return ids


@router.get("/products", response_model=ProductPage)
def list_products(
    db: DB,
    q: Annotated[str | None, Query(description="Search in name and description")] = None,
    category_id: int | None = None,
    min_price: Decimal | None = Query(default=None, ge=0),
    max_price: Decimal | None = Query(default=None, ge=0),
    in_stock: bool = False,
    sort: Literal["name", "price_asc", "price_desc", "newest"] = "name",
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    stmt = select(Product).where(Product.is_active.is_(True))
    if q and q.strip():
        # Also try the query re-typed on the other keyboard layout, so a search
        # like "djlf" (Russian "вода" typed with an English layout) still matches.
        conditions = []
        for variant in layout_variants(q.strip()):
            like = f"%{variant}%"
            conditions += [Product.name.ilike(like), Product.description.ilike(like)]
        stmt = stmt.where(or_(*conditions))
    if category_id is not None:
        stmt = stmt.where(Product.category_id.in_(_category_ids(db, category_id)))
    if min_price is not None:
        stmt = stmt.where(Product.price >= min_price)
    if max_price is not None:
        stmt = stmt.where(Product.price <= max_price)
    if in_stock:
        stmt = stmt.where(Product.stock > 0)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = db.scalars(stmt.order_by(SORTS[sort], Product.id).offset((page - 1) * size).limit(size)).all()
    return ProductPage(items=items, total=total, page=page, size=size)


@router.get("/products/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: DB):
    product = db.get(Product, product_id)
    if not product or not product.is_active:
        raise HTTPException(404, "Product not found")
    return product
