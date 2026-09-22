from decimal import Decimal

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from ..deps import DB, CurrentUser
from ..models import CartItem, Product
from ..schemas import CartItemIn, CartItemOut, CartItemUpdate, CartOut

router = APIRouter(prefix="/cart", tags=["cart"])


def build_cart(db, user_id: int) -> CartOut:
    rows = db.scalars(select(CartItem).where(CartItem.user_id == user_id).order_by(CartItem.id)).all()
    items = [CartItemOut(product=r.product, quantity=r.quantity, line_total=r.product.price * r.quantity)
             for r in rows]
    return CartOut(items=items, total=sum((i.line_total for i in items), Decimal("0")))


def _active_product(db, product_id: int) -> Product:
    product = db.get(Product, product_id)
    if not product or not product.is_active:
        raise HTTPException(404, "Product not found")
    return product


def _check_stock(product: Product, quantity: int):
    if quantity > product.stock:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Only {product.stock} in stock for '{product.name}'")


def _find_item(db, user_id: int, product_id: int) -> CartItem | None:
    return db.scalar(select(CartItem).where(CartItem.user_id == user_id, CartItem.product_id == product_id))


@router.get("", response_model=CartOut)
def get_cart(user: CurrentUser, db: DB):
    return build_cart(db, user.id)


@router.post("/items", response_model=CartOut)
def add_item(data: CartItemIn, user: CurrentUser, db: DB):
    product = _active_product(db, data.product_id)
    item = _find_item(db, user.id, product.id)
    new_qty = data.quantity + (item.quantity if item else 0)
    _check_stock(product, new_qty)
    if item:
        item.quantity = new_qty
    else:
        db.add(CartItem(user_id=user.id, product_id=product.id, quantity=new_qty))
    db.commit()
    return build_cart(db, user.id)


@router.patch("/items/{product_id}", response_model=CartOut)
def set_quantity(product_id: int, data: CartItemUpdate, user: CurrentUser, db: DB):
    item = _find_item(db, user.id, product_id)
    if not item:
        raise HTTPException(404, "Item not in cart")
    _check_stock(item.product, data.quantity)
    item.quantity = data.quantity
    db.commit()
    return build_cart(db, user.id)


@router.delete("/items/{product_id}", response_model=CartOut)
def remove_item(product_id: int, user: CurrentUser, db: DB):
    item = _find_item(db, user.id, product_id)
    if item:
        db.delete(item)
        db.commit()
    return build_cart(db, user.id)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def clear_cart(user: CurrentUser, db: DB):
    for item in db.scalars(select(CartItem).where(CartItem.user_id == user.id)):
        db.delete(item)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
