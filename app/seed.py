"""Fill the database with demo categories and products: python -m app.seed"""
from decimal import Decimal

from sqlalchemy import select

from .database import Base, SessionLocal, engine
from .models import Category, Product


def img(photo_id: str) -> str:
    return f"https://images.unsplash.com/photo-{photo_id}?auto=format&fit=crop&w=400&q=80"


DATA = {
    "Овощи и фрукты": [
        ("Яблоки", "1.99", "kg", 120, img("1560806887-1e4cd0b6cbd6")),
        ("Бананы", "1.49", "kg", 90, img("1571771894821-ce9b6c11b08e")),
        ("Помидоры", "3.20", "kg", 60, img("1546094096-0df4bcaaa337")),
        ("Картофель", "0.89", "kg", 300, img("1518977676601-b53f82aba655")),
    ],
    "Молочные продукты": [
        ("Молоко 3.2%", "1.10", "l", 80, img("1550583724-b2692b85b150")),
        ("Кефир", "1.05", "l", 50, img("1563636619-e9143da7973b")),
        ("Сыр Гауда", "7.50", "kg", 25, img("1618164436241-4473940d1f5c")),
        ("Йогурт натуральный", "0.75", "pcs", 100, img("1488477181946-6428a0291777")),
    ],
    "Хлеб и выпечка": [
        ("Хлеб пшеничный", "0.95", "pcs", 70, img("1509440159596-0249088772ff")),
        ("Багет", "1.20", "pcs", 40, img("1608198093002-ad4e005484ec")),
    ],
    "Мясо и рыба": [
        ("Куриное филе", "5.90", "kg", 45, img("1587593810167-a84920ea0781")),
        ("Лосось", "14.00", "kg", 15, img("1519708227418-c8fd9a32b7a2")),
    ],
    "Напитки": [
        ("Вода минеральная", "0.60", "l", 200, img("1560023907-5f339617ea30")),
        ("Сок апельсиновый", "2.10", "l", 60, img("1600271886742-f049cd451bba")),
    ],
}


def run():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        existing = {p.name: p for p in db.scalars(select(Product))}
        for cat_name, products in DATA.items():
            cat = db.scalar(select(Category).where(Category.name == cat_name))
            if not cat:
                cat = Category(name=cat_name)
                db.add(cat)
                db.flush()
            for name, price, unit, stock, image_url in products:
                if name in existing:
                    existing[name].image_url = image_url  # backfill photos for already-seeded rows
                else:
                    db.add(Product(name=name, price=Decimal(price), unit=unit, stock=stock,
                                   category_id=cat.id, image_url=image_url))
        db.commit()
        print("Seeded demo data (existing products got photos added).")


if __name__ == "__main__":
    run()
