from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import EmailVerification, Role, User
from app.security import hash_password


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override():
        with Session() as db:
            yield db

    app.dependency_overrides[get_db] = override
    with Session() as db:
        # Created directly (bypasses the email-code flow), like the real ensure_admin() does.
        db.add(User(email="admin@test.io", password_hash=hash_password("adminpass1"),
                    role=Role.admin, email_verified=True))
        db.commit()
    tc = TestClient(app)  # no `with`: skips lifespan, so the app's real DB is untouched
    tc.Session = Session
    yield tc
    app.dependency_overrides.clear()


def login(client, email, password):
    r = client.post("/auth/login", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def latest_code(client, email):
    with client.Session() as db:
        user = db.scalar(select(User).where(User.email == email))
        record = db.scalar(select(EmailVerification).where(EmailVerification.user_id == user.id))
        return record.code


def customer(client, email="bob@test.io"):
    r = client.post("/auth/register", json={"email": email, "password": "password123"})
    assert r.status_code == 201, r.text
    v = client.post("/auth/verify-email", json={"email": email, "code": latest_code(client, email)})
    assert v.status_code == 200, v.text
    return {"Authorization": f"Bearer {v.json()['access_token']}"}


def make_product(client, admin, **kw):
    body = {"name": "Apple", "price": "2.50", "unit": "kg", "stock": 10, **kw}
    r = client.post("/admin/products", json=body, headers=admin)
    assert r.status_code == 201, r.text
    return r.json()


def test_auth_flow_and_duplicates(client):
    h = customer(client)
    assert client.get("/users/me", headers=h).json()["email"] == "bob@test.io"
    dup = client.post("/auth/register", json={"email": "BOB@test.io", "password": "password123"})
    assert dup.status_code == 409
    bad = client.post("/auth/login", data={"username": "bob@test.io", "password": "wrong"})
    assert bad.status_code == 401


def test_login_blocked_until_email_verified(client):
    email = "carol@test.io"
    assert client.post("/auth/register", json={"email": email, "password": "password123"}).status_code == 201

    blocked = client.post("/auth/login", data={"username": email, "password": "password123"})
    assert blocked.status_code == 403

    wrong_code = client.post("/auth/verify-email", json={"email": email, "code": "000000"})
    assert wrong_code.status_code == 400

    ok = client.post("/auth/verify-email", json={"email": email, "code": latest_code(client, email)})
    assert ok.status_code == 200 and "access_token" in ok.json()
    assert client.post("/auth/login", data={"username": email, "password": "password123"}).status_code == 200


def test_resend_code_issues_a_new_one(client):
    email = "dave@test.io"
    client.post("/auth/register", json={"email": email, "password": "password123"})
    old_code = latest_code(client, email)

    assert client.post("/auth/resend-code", json={"email": email}).status_code == 204
    new_code = latest_code(client, email)

    assert client.post("/auth/verify-email", json={"email": email, "code": old_code}).status_code == 400
    assert client.post("/auth/verify-email", json={"email": email, "code": new_code}).status_code == 200
    # Resending for an unknown/already-verified email doesn't leak that info via an error.
    assert client.post("/auth/resend-code", json={"email": "nobody@test.io"}).status_code == 204


def test_admin_only(client):
    h = customer(client)
    assert client.post("/admin/products", json={"name": "x", "price": "1"}, headers=h).status_code == 403
    assert client.get("/admin/stats").status_code == 401


def test_catalog_search_filter_pagination(client):
    admin = login(client, "admin@test.io", "adminpass1")
    cat = client.post("/admin/categories", json={"name": "Fruit"}, headers=admin).json()
    sub = client.post("/admin/categories", json={"name": "Citrus", "parent_id": cat["id"]}, headers=admin).json()
    make_product(client, admin, name="Apple", category_id=cat["id"])
    make_product(client, admin, name="Orange", price="4.00", category_id=sub["id"])
    make_product(client, admin, name="Empty", stock=0)

    assert client.get("/products?q=app").json()["total"] == 1
    assert client.get(f"/products?category_id={cat['id']}").json()["total"] == 2  # includes subcategory
    assert client.get("/products?in_stock=true").json()["total"] == 2
    assert client.get("/products?min_price=3").json()["items"][0]["name"] == "Orange"
    page = client.get("/products?size=1&page=2&sort=price_desc").json()
    assert page["total"] == 3 and len(page["items"]) == 1


def test_cart_stock_limit(client):
    admin = login(client, "admin@test.io", "adminpass1")
    p = make_product(client, admin, stock=3)
    h = customer(client)
    assert client.post("/cart/items", json={"product_id": p["id"], "quantity": 2}, headers=h).status_code == 200
    r = client.post("/cart/items", json={"product_id": p["id"], "quantity": 2}, headers=h)
    assert r.status_code == 409
    cart = client.patch(f"/cart/items/{p['id']}", json={"quantity": 3}, headers=h).json()
    assert Decimal(cart["total"]) == Decimal("7.50")


def test_order_payment_and_cancel_restores_stock(client):
    admin = login(client, "admin@test.io", "adminpass1")
    p = make_product(client, admin, stock=5)
    h = customer(client)
    addr = {"address": "Main street 1", "phone": "+123456"}

    assert client.post("/orders", json=addr, headers=h).status_code == 400  # empty cart

    client.post("/cart/items", json={"product_id": p["id"], "quantity": 4}, headers=h)
    order = client.post("/orders", json=addr, headers=h)
    assert order.status_code == 201
    order = order.json()
    assert Decimal(order["total"]) == Decimal("10.00")
    assert client.get("/cart", headers=h).json()["items"] == []
    assert client.get(f"/products/{p['id']}").json()["stock"] == 1

    declined = client.post(f"/orders/{order['id']}/pay", json={"payment_token": "tok_fail"}, headers=h)
    assert declined.status_code == 402
    paid = client.post(f"/orders/{order['id']}/pay", json={"payment_token": "tok_ok"}, headers=h)
    assert paid.status_code == 200 and paid.json()["status"] == "paid"
    assert len(paid.json()["payments"]) == 2

    # paid orders can't be cancelled by the customer, but admin can (stock returns)
    assert client.post(f"/orders/{order['id']}/cancel", headers=h).status_code == 409
    r = client.patch(f"/admin/orders/{order['id']}/status", json={"status": "cancelled"}, headers=admin)
    assert r.status_code == 200
    assert client.get(f"/products/{p['id']}").json()["stock"] == 5


def test_orders_are_private_and_no_oversell(client):
    admin = login(client, "admin@test.io", "adminpass1")
    p = make_product(client, admin, stock=1)
    a, b = customer(client, "a@test.io"), customer(client, "b@test.io")
    for h in (a, b):
        client.post("/cart/items", json={"product_id": p["id"], "quantity": 1}, headers=h)
    addr = {"address": "Main street 1", "phone": "+123456"}
    first = client.post("/orders", json=addr, headers=a)
    second = client.post("/orders", json=addr, headers=b)
    assert first.status_code == 201 and second.status_code == 409
    assert client.get(f"/orders/{first.json()['id']}", headers=b).status_code == 404


def test_admin_stats(client):
    admin = login(client, "admin@test.io", "adminpass1")
    assert client.get("/admin/stats", headers=admin).json()["orders"] == 0


def test_admin_users_list_shows_registered_customers(client):
    admin = login(client, "admin@test.io", "adminpass1")
    h = customer(client)
    p = make_product(client, admin, stock=5)
    client.post("/cart/items", json={"product_id": p["id"], "quantity": 1}, headers=h)
    client.post("/orders", json={"address": "Main street 1", "phone": "+123456"}, headers=h)

    users = client.get("/admin/users", headers=admin).json()
    assert client.get("/admin/users", headers=h).status_code == 403  # customers can't see the list
    by_email = {u["email"]: u for u in users}
    assert by_email["bob@test.io"]["orders_count"] == 1
    assert by_email["admin@test.io"]["role"] == "admin"
    assert by_email["bob@test.io"]["is_active"] is True


def test_admin_can_block_and_unblock_a_customer(client):
    admin = login(client, "admin@test.io", "adminpass1")
    customer(client)
    bob_id = next(u["id"] for u in client.get("/admin/users", headers=admin).json() if u["email"] == "bob@test.io")

    blocked = client.patch(f"/admin/users/{bob_id}/status", json={"is_active": False}, headers=admin)
    assert blocked.status_code == 200 and blocked.json()["is_active"] is False
    assert client.post("/auth/login", data={"username": "bob@test.io", "password": "password123"}).status_code == 401

    unblocked = client.patch(f"/admin/users/{bob_id}/status", json={"is_active": True}, headers=admin)
    assert unblocked.status_code == 200 and unblocked.json()["is_active"] is True
    assert client.post("/auth/login", data={"username": "bob@test.io", "password": "password123"}).status_code == 200


def test_admin_cannot_block_self(client):
    admin_id = 1  # the fixture creates the admin user first, so id=1
    admin = login(client, "admin@test.io", "adminpass1")
    r = client.patch(f"/admin/users/{admin_id}/status", json={"is_active": False}, headers=admin)
    assert r.status_code == 400
