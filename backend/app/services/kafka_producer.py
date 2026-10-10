"""
Productor Kafka para publicar eventos en inventory.events.

Uso:
    await producer.publish("stock.received", data={...}, key="part_id:42")
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from aiokafka import AIOKafkaProducer

from app.core.config import settings

logger = logging.getLogger(__name__)

_producer: Optional[AIOKafkaProducer] = None


async def start_producer() -> None:
    """Inicia el producer Kafka. Llamar en el lifespan de FastAPI."""
    global _producer
    _producer = AIOKafkaProducer(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8") if k else None,
        acks="all",           # máxima durabilidad
        enable_idempotence=True,
    )
    await _producer.start()
    logger.info("Kafka producer iniciado → %s", settings.KAFKA_BOOTSTRAP_SERVERS)


async def stop_producer() -> None:
    """Cierra el producer Kafka. Llamar en el shutdown del lifespan."""
    global _producer
    if _producer:
        await _producer.stop()
        _producer = None
        logger.info("Kafka producer detenido.")


def _envelope(event_type: str, data: dict[str, Any]) -> dict[str, Any]:
    """Construye el sobre estándar de eventos de inventario."""
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "event_version": 1,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "source": "inventory",
        "key": event_type,
        "data": data,
    }


async def publish(event_type: str, data: dict[str, Any], key: Optional[str] = None) -> None:
    """
    Publica un evento en inventory.events.
    Si el producer no está disponible, solo loguea una advertencia (fail-soft).
    """
    if _producer is None:
        logger.warning("Producer no disponible; evento descartado: %s", event_type)
        return

    message = _envelope(event_type, data)
    try:
        await _producer.send_and_wait(
            settings.KAFKA_TOPIC_INVENTORY_EVENTS,
            value=message,
            key=key or event_type,
        )
        logger.debug("Evento publicado: %s", event_type)
    except Exception as exc:
        logger.error("Error publicando evento %s: %s", event_type, exc)
