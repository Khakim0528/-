from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .models import OrderStatus, PaymentStatus, Role


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- auth / users ----
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(default="", max_length=255)
    phone: str | None = Field(default=None, max_length=32)


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)


class UserOut(ORM):
    id: int
    email: EmailStr
    full_name: str
    phone: str | None
    role: Role
    created_at: datetime


class AdminUserOut(UserOut):
    orders_count: int = 0


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---- catalog ----
class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    parent_id: int | None = None


class CategoryOut(ORM):
    id: int
    name: str
    parent_id: int | None


class ProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    price: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    unit: str = Field(default="pcs", max_length=16)
    stock: int = Field(default=0, ge=0)
    image_url: str | None = None
    is_active: bool = True
    category_id: int | None = None


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    price: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    unit: str | None = Field(default=None, max_length=16)
    stock: int | None = Field(default=None, ge=0)
    image_url: str | None = None
    is_active: bool | None = None
    category_id: int | None = None


class ProductOut(ORM):
    id: int
    name: str
    description: str
    price: Decimal
    unit: str
    stock: int
    image_url: str | None
    is_active: bool
    category_id: int | None


class ProductPage(BaseModel):
    items: list[ProductOut]
    total: int
    page: int
    size: int


# ---- cart ----
class CartItemIn(BaseModel):
    product_id: int
    quantity: int = Field(default=1, ge=1, le=999)


class CartItemUpdate(BaseModel):
    quantity: int = Field(ge=1, le=999)


class CartItemOut(ORM):
    product: ProductOut
    quantity: int
    line_total: Decimal


class CartOut(BaseModel):
    items: list[CartItemOut]
    total: Decimal


# ---- orders / payments ----
class OrderCreate(BaseModel):
    address: str = Field(min_length=5, max_length=512)
    phone: str = Field(min_length=5, max_length=32)
    comment: str | None = Field(default=None, max_length=1000)


class OrderItemOut(ORM):
    product_id: int | None
    product_name: str
    unit_price: Decimal
    quantity: int


class PaymentOut(ORM):
    id: int
    amount: Decimal
    status: PaymentStatus
    provider_ref: str
    created_at: datetime


class OrderOut(ORM):
    id: int
    user_id: int
    status: OrderStatus
    total: Decimal
    address: str
    phone: str
    comment: str | None
    created_at: datetime
    items: list[OrderItemOut]
    payments: list[PaymentOut]


class PayIn(BaseModel):
    # Mock gateway: token "tok_fail" is declined, anything else succeeds.
    # Replace with a real provider token (Stripe, YooKassa, ...) in production.
    payment_token: str = Field(min_length=1, max_length=128)


class StatusUpdate(BaseModel):
    status: OrderStatus


class StatsOut(BaseModel):
    users: int
    products: int
    orders: int
    revenue: Decimal
    orders_by_status: dict[str, int]
