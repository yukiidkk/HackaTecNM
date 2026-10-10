"""
Configuración central de la aplicación.
Las variables se leen desde el entorno o un archivo .env en la raíz del backend.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Kafka / Redpanda ──────────────────────────────────────────────────────
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_CONSUMER_GROUP_ID: str = "inventory-service"

    # Tópicos de entrada
    KAFKA_TOPIC_CATALOG: str = "shop.catalog"
    KAFKA_TOPIC_WORK_ORDERS: str = "shop.work_orders"
    KAFKA_TOPIC_INSPECTIONS: str = "shop.inspections"
    KAFKA_TOPIC_PURCHASING: str = "shop.purchasing"

    # Tópico de salida
    KAFKA_TOPIC_INVENTORY_EVENTS: str = "inventory.events"

    # ── Base de Datos (Supabase / PostgreSQL) ─────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/inventory"

    # ── Supabase (cliente Python supabase-py) ─────────────────────────────────
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""  # service_role key (nunca la anon key en backend)

    # ── Inventario — ubicación por defecto para recepciones de restock ─────────
    DEFAULT_STOCK_LOCATION_ID: int = 100  # código U-100

    # ── Google Gemini ─────────────────────────────────────────────────────────
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-1.5-flash"

    # ── Aplicación ────────────────────────────────────────────────────────────
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


# Instancia singleton importable desde cualquier módulo
settings = Settings()
