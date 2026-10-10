"""
Punto de entrada principal del Servicio de Inventario Inteligente.

Ejecutar con:
    uvicorn main:app --reload --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import create_all_tables

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s — %(message)s",
)


# ── Lifespan ───────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa y cierra recursos con el ciclo de vida de la app."""
    # 1. Crear tablas (idempotente — no hace nada si ya existen)
    try:
        await create_all_tables()
    except Exception as exc:
        logger.warning("No se pudieron crear/verificar las tablas: %s", exc)

    # 2. Kafka producer
    from app.services.kafka_producer import start_producer, stop_producer
    try:
        await start_producer()
    except Exception as exc:
        logger.warning("Kafka producer no disponible al arrancar: %s", exc)

    # 3. Kafka consumer (en background — no bloquea el arranque)
    from app.services.kafka_consumer import start_consumer, stop_consumer
    try:
        await start_consumer()
    except Exception as exc:
        logger.warning("Kafka consumer no disponible al arrancar: %s", exc)

    logger.info("Servicio de Inventario listo (env=%s)", settings.APP_ENV)

    yield  # ── aplicación corriendo ──────────────────────────────────────────

    # Shutdown
    try:
        await stop_consumer()
    except Exception as exc:
        logger.warning("Error al detener el consumer: %s", exc)
    try:
        await stop_producer()
    except Exception as exc:
        logger.warning("Error al detener el producer: %s", exc)

    logger.info("Servicio de Inventario detenido.")


# ── Aplicación FastAPI ─────────────────────────────────────────────────────────

app = FastAPI(
    title="Servicio de Inventario Inteligente del Taller",
    description=(
        "API REST para gestión de inventario de husillos y motores industriales. "
        "Consume eventos de Redpanda (shop.*) y publica en inventory.events."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── CORS ───────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "*",              # permite cualquier origen (hackathon)
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────────────

from app.api.parts import router as parts_router
from app.api.work_orders import router as work_orders_router
from app.api.inventory import router as inventory_router
from app.api.locations import router as locations_router

app.include_router(parts_router)
app.include_router(work_orders_router)
app.include_router(inventory_router)
app.include_router(locations_router)


# ── Health check ───────────────────────────────────────────────────────────────

@app.get("/health", tags=["ops"], summary="Health check")
async def health_check():
    return {
        "status": "ok",
        "service": "inventory",
        "version": "1.0.0",
        "env": settings.APP_ENV,
    }
