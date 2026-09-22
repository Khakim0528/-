from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from .config import settings
from .database import Base, SessionLocal, engine, run_light_migrations
from .models import Role, User
from .routers import admin, auth, cart, catalog, orders
from .security import hash_password


def ensure_admin():
    if not (settings.admin_email and settings.admin_password):
        return
    with SessionLocal() as db:
        email = settings.admin_email.lower()
        if not db.scalar(select(User).where(User.email == email)):
            # Created directly, so it skips the email-code flow new signups go through.
            db.add(User(email=email, password_hash=hash_password(settings.admin_password),
                        full_name="Administrator", role=Role.admin, email_verified=True))
            db.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)  # use Alembic migrations in production
    run_light_migrations()
    ensure_admin()
    yield


app = FastAPI(title="Grocery Shop API", version="1.0.0", lifespan=lifespan)

app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

for module in (auth, catalog, cart, orders, admin):
    app.include_router(module.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}


# Frontend is mounted last so that API routes and /docs take priority.
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
