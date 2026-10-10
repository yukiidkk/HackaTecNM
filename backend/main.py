"""
Punto de entrada principal del Servicio de Inventario Inteligente.

Ejecutar con:
    uvicorn main:app --reload --port 8000
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings


# ── Lifespan (startup / shutdown) ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestiona recursos que requieren ciclo de vida (Kafka, DB pool, etc.)."""
    # TODO: inicializar consumer Kafka y pool de base de datos
    yield
    # TODO: cerrar consumer Kafka y pool de base de datos


# ── Instancia de la aplicación ────────────────────────────────────────────────
app = FastAPI(
    title="Servicio de Inventario Inteligente del Taller",
    description=(
        "API REST para gestión de inventario de husillos y motores industriales. "
        "Consume eventos de Redpanda y publica en inventory.events."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Next.js dev server
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Routers ───────────────────────────────────────────────────────────────────
from app.api.inventory import router as inventory_router
app.include_router(inventory_router)


# ── Endpoints base ────────────────────────────────────────────────────────────
@app.get("/health", tags=["ops"], summary="Health check")
async def health_check():
    """Verifica que el servicio está levantado y accesible."""
    return {
        "status": "ok",
        "service": "inventory",
        "env": settings.APP_ENV,
    }
