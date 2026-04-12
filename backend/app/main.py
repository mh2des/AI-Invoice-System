from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import products, invoices, suppliers, reports, dashboard, chat
from app.core.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    yield
    # Shutdown


app = FastAPI(
    title="AI Invoice Processing System",
    description="Upload supplier invoices, extract line items with AI, match against product database, generate Excel reports.",
    version="1.0.0",
    lifespan=lifespan,
)

# Build allowed origins list: always allow localhost, add FRONTEND_URL if set
_settings = get_settings()
_allowed_origins = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:3002",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
]
if _settings.FRONTEND_URL:
    _allowed_origins.append(_settings.FRONTEND_URL.rstrip("/"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(dashboard.router, prefix="/api")
app.include_router(suppliers.router, prefix="/api")
app.include_router(products.router, prefix="/api")
app.include_router(invoices.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(chat.router, prefix="/api")


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "AI Invoice Processing System"}
