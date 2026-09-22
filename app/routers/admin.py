from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import func, select

from ..deps import DB, AdminUser
from ..models import CartItem, Category, EmailVerification, Order, OrderItem, OrderStatus, Product, User
from ..schemas import (AdminUserOut, CategoryIn, CategoryOut, OrderOut, ProductIn, ProductOut,
                       ProductUpdate, StatsOut, StatusUpdate, UserStatusUpdate)
from .orders import cancel_order

router = APIRouter(prefix="/admin", tags=["admin"])


def _check_category(db, category_id: int | None):
    if category_id is not None and not db.get(Category, category_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Category does not exist")


# ---- categories ----
@router.post("/categories", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(data: CategoryIn, _: AdminUser, db: DB):
    _check_category(db, data.parent_id)
    if db.scalar(select(Category).where(Category.name == data.name)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Category already exists")
    category = Category(**data.model_dump())
    db.add(category)
    db.commit()
    return category


@router.put("/categories/{category_id}", response_model=CategoryOut)
def update_category(category_id: int, data: CategoryIn, _: AdminUser, db: DB):
    category = db.get(Category, category_id)
    if not category:
        raise HTTPException(404, "Category not found")
    if data.parent_id == category_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Category cannot be its own parent")
    _check_category(db, data.parent_id)
    category.name, category.parent_id = data.name, data.parent_id
    db.commit()
    return category


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: int, _: AdminUser, db: DB):
    category = db.get(Category, category_id)
    if not category:
        raise HTTPException(404, "Category not found")
    if db.scalar(select(Category.id).where(Category.parent_id == category_id).limit(1)) or \
       db.scalar(select(Product.id).where(Product.category_id == category_id).limit(1)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Category is not empty")
    db.delete(category)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---- products ----
@router.get("/products", response_model=list[ProductOut])
def list_all_products(_: AdminUser, db: DB, skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200)):
    """Includes deactivated products."""
    return db.scalars(select(Product).order_by(Product.id).offset(skip).limit(limit)).all()


@router.post("/products", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(data: ProductIn, _: AdminUser, db: DB):
    _check_category(db, data.category_id)
    product = Product(**data.model_dump())
    db.add(product)
    db.commit()
    return product


@router.patch("/products/{product_id}", response_model=ProductOut)
def update_product(product_id: int, data: ProductUpdate, _: AdminUser, db: DB):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    changes = data.model_dump(exclude_unset=True)
    if "category_id" in changes:
        _check_category(db, changes["category_id"])
    for field, value in changes.items():
        setattr(product, field, value)
    db.commit()
    return product


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_product(product_id: int, _: AdminUser, db: DB):
    """Soft delete: keeps order history intact."""
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    product.is_active = False
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---- orders ----
@router.get("/orders", response_model=list[OrderOut])
def all_orders(_: AdminUser, db: DB, status_filter: OrderStatus | None = Query(None, alias="status"),
               skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200)):
    stmt = select(Order).order_by(Order.id.desc()).offset(skip).limit(limit)
    if status_filter:
        stmt = stmt.where(Order.status == status_filter)
    return db.scalars(stmt).all()


ALLOWED_TRANSITIONS = {
    OrderStatus.pending_payment: {OrderStatus.cancelled},
    OrderStatus.paid: {OrderStatus.processing, OrderStatus.cancelled},
    OrderStatus.processing: {OrderStatus.delivering, OrderStatus.cancelled},
    OrderStatus.delivering: {OrderStatus.completed, OrderStatus.cancelled},
    OrderStatus.completed: set(),
    OrderStatus.cancelled: set(),
}


@router.patch("/orders/{order_id}/status", response_model=OrderOut)
def set_order_status(order_id: int, data: StatusUpdate, _: AdminUser, db: DB):
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    if data.status not in ALLOWED_TRANSITIONS[order.status]:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Cannot move order from {order.status.value} to {data.status.value}")
    if data.status == OrderStatus.cancelled:
        cancel_order(db, order)
    else:
        order.status = data.status
    db.commit()
    return order


# ---- users ----
@router.get("/users", response_model=list[AdminUserOut])
def list_users(_: AdminUser, db: DB, skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=200)):
    order_counts = (select(Order.user_id, func.count(Order.id).label("cnt"))
                    .group_by(Order.user_id).subquery())
    stmt = (select(User, func.coalesce(order_counts.c.cnt, 0))
            .outerjoin(order_counts, order_counts.c.user_id == User.id)
            .order_by(User.id.desc()).offset(skip).limit(limit))
    return [AdminUserOut.model_validate(user).model_copy(update={"orders_count": count})
            for user, count in db.execute(stmt).all()]


@router.patch("/users/{user_id}/status", response_model=AdminUserOut)
def set_user_status(user_id: int, data: UserStatusUpdate, admin: AdminUser, db: DB):
    """Block/unblock a customer. Blocked users can't log in; their order history is kept."""
    if user_id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot block your own account")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    user.is_active = data.is_active
    db.commit()
    order_count = db.scalar(select(func.count(Order.id)).where(Order.user_id == user.id)) or 0
    return AdminUserOut.model_validate(user).model_copy(update={"orders_count": order_count})


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, admin: AdminUser, db: DB):
    """Permanently remove a customer who never placed an order. Once they have
    order history, deleting them would break those records — block them instead."""
    if user_id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot delete your own account")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    if db.scalar(select(Order.id).where(Order.user_id == user.id).limit(1)):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "У клиента есть заказы — удалить нельзя, история заказов сломается. Заблокируйте вместо этого.")
    for item in db.scalars(select(CartItem).where(CartItem.user_id == user.id)):
        db.delete(item)
    record = db.scalar(select(EmailVerification).where(EmailVerification.user_id == user.id))
    if record:
        db.delete(record)
    db.delete(user)
    db.commit()


# ---- stats ----
@router.get("/stats", response_model=StatsOut)
def stats(_: AdminUser, db: DB):
    paid = [OrderStatus.paid, OrderStatus.processing, OrderStatus.delivering, OrderStatus.completed]
    revenue = db.scalar(select(func.coalesce(func.sum(Order.total), 0)).where(Order.status.in_(paid)))
    by_status = dict(db.execute(select(Order.status, func.count()).group_by(Order.status)).all())
    return StatsOut(
        users=db.scalar(select(func.count(User.id))) or 0,
        products=db.scalar(select(func.count(Product.id))) or 0,
        orders=db.scalar(select(func.count(Order.id))) or 0,
        revenue=Decimal(revenue),
        orders_by_status={s.value: n for s, n in by_status.items()},
    )
