import uuid
from decimal import Decimal

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select, update

from ..deps import DB, CurrentUser
from ..models import (CartItem, Order, OrderItem, OrderStatus, Payment,
                      PaymentStatus, Product)
from ..schemas import OrderCreate, OrderOut, PayIn

router = APIRouter(prefix="/orders", tags=["orders"])


def restore_stock(db, order: Order):
    for item in order.items:
        if item.product_id:
            db.execute(update(Product).where(Product.id == item.product_id)
                       .values(stock=Product.stock + item.quantity))


def cancel_order(db, order: Order):
    """Cancel and return reserved goods to stock (idempotent)."""
    if order.status != OrderStatus.cancelled:
        restore_stock(db, order)
        order.status = OrderStatus.cancelled


def _own_order(db, user_id: int, order_id: int) -> Order:
    order = db.get(Order, order_id)
    if not order or order.user_id != user_id:
        raise HTTPException(404, "Order not found")
    return order


@router.post("", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
def create_order(data: OrderCreate, user: CurrentUser, db: DB):
    cart = db.scalars(select(CartItem).where(CartItem.user_id == user.id)).all()
    if not cart:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cart is empty")

    order = Order(user_id=user.id, total=Decimal("0"), address=data.address,
                  phone=data.phone, comment=data.comment)
    try:
        for row in cart:
            product = row.product
            if not product.is_active:
                raise HTTPException(status.HTTP_409_CONFLICT, f"'{product.name}' is no longer available")
            # Atomic reservation: succeeds only if enough stock remains (no oversell under concurrency).
            res = db.execute(update(Product)
                             .where(Product.id == product.id, Product.stock >= row.quantity)
                             .values(stock=Product.stock - row.quantity))
            if res.rowcount != 1:
                raise HTTPException(status.HTTP_409_CONFLICT, f"Not enough stock for '{product.name}'")
            order.items.append(OrderItem(product_id=product.id, product_name=product.name,
                                         unit_price=product.price, quantity=row.quantity))
            order.total += product.price * row.quantity
            db.delete(row)
        db.add(order)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return order


@router.get("", response_model=list[OrderOut])
def my_orders(user: CurrentUser, db: DB):
    return db.scalars(select(Order).where(Order.user_id == user.id).order_by(Order.id.desc())).all()


@router.get("/{order_id}", response_model=OrderOut)
def get_order(order_id: int, user: CurrentUser, db: DB):
    return _own_order(db, user.id, order_id)


@router.post("/{order_id}/cancel", response_model=OrderOut)
def cancel(order_id: int, user: CurrentUser, db: DB):
    order = _own_order(db, user.id, order_id)
    if order.status != OrderStatus.pending_payment:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only unpaid orders can be cancelled; contact support")
    cancel_order(db, order)
    db.commit()
    return order


@router.post("/{order_id}/pay", response_model=OrderOut)
def pay(order_id: int, data: PayIn, user: CurrentUser, db: DB):
    """Mock payment gateway. Swap the `charge` stub for a real provider call."""
    order = _own_order(db, user.id, order_id)
    if order.status != OrderStatus.pending_payment:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Order is {order.status.value}, cannot pay")

    ok = data.payment_token != "tok_fail"
    order.payments.append(Payment(amount=order.total,
                                  status=PaymentStatus.succeeded if ok else PaymentStatus.failed,
                                  provider_ref=f"mock_{uuid.uuid4().hex[:16]}"))
    if ok:
        order.status = OrderStatus.paid
    db.commit()
    if not ok:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, "Payment declined")
    return order
