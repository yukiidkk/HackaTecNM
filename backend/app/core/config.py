"""
Configuración central de la aplicación.
Las variables se leen desde el entorno o un archivo .env en la raíz del backend.
"""

from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Kafka / Redpanda ──────────────────────────────────────────────────────
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:19092"
    KAFKA_CONSUMER_GROUP_ID: str = "inventory-service"

    # Tópicos de entrada oficiales del taller
    KAFKA_TOPIC_CATALOG: str = "shop.catalog"
    KAFKA_TOPIC_WORK_ORDERS: str = "shop.work_orders"
    KAFKA_TOPIC_INSPECTIONS: str = "shop.inspections"
    KAFKA_TOPIC_PURCHASING: str = "shop.purchasing"

    # Tópico de salida oficial
    KAFKA_TOPIC_INVENTORY_EVENTS: str = "inventory.events"

    # ── Base de Datos (Supabase / PostgreSQL vía Pooler IPv4) ─────────────────
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres"

    # ── Variables auxiliares / opcionales ──────────────────────────────────────
    SUPABASE_URL: Optional[str] = None
    SUPABASE_KEY: Optional[str] = None
    DEFAULT_STOCK_LOCATION_ID: int = 100

    # ── Google Gemini AI ───────────────────────────────────────────────────────
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-1.5-flash"

    # ── Aplicación ────────────────────────────────────────────────────────────
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    # Permite variables extra en el .env sin arrojar error
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


# Instancia singleton importable desde cualquier módulo
settings = Settings()