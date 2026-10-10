"""
Consumer Kafka (aiokafka) para todos los tópicos de entrada.

Se suscribe a:
  - shop.catalog
  - shop.work_orders
  - shop.inspections
  - shop.purchasing

Cada mensaje se deserializa al sobre KafkaEventEnvelope y se despacha
al event_processor central, que garantiza idempotencia y persistencia.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaConnectionError

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.schemas import KafkaEventEnvelope
from app.services import event_processor

logger = logging.getLogger(__name__)

_consumer: Optional[AIOKafkaConsumer] = None
_consumer_task: Optional[asyncio.Task] = None


# ── Ciclo de vida ──────────────────────────────────────────────────────────────

async def start_consumer() -> None:
    """Inicia el consumer y lanza la tarea de consumo en background."""
    global _consumer, _consumer_task

    topics = [
        settings.KAFKA_TOPIC_CATALOG,
        settings.KAFKA_TOPIC_WORK_ORDERS,
        settings.KAFKA_TOPIC_INSPECTIONS,
        settings.KAFKA_TOPIC_PURCHASING,
    ]

    _consumer = AIOKafkaConsumer(
        *topics,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id=settings.KAFKA_CONSUMER_GROUP_ID,
        auto_offset_reset="earliest",
        enable_auto_commit=False,          # commit manual tras procesamiento exitoso
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        session_timeout_ms=30_000,
        heartbeat_interval_ms=10_000,
        max_poll_interval_ms=300_000,
    )

    try:
        await _consumer.start()
        logger.info(
            "Kafka consumer iniciado — tópicos: %s — broker: %s",
            topics, settings.KAFKA_BOOTSTRAP_SERVERS,
        )
    except KafkaConnectionError as exc:
        logger.warning(
            "No se pudo conectar al broker Kafka (%s). "
            "El servicio arrancará sin consumer; reinténtalo cuando el broker esté disponible.",
            exc,
        )
        _consumer = None
        return

    _consumer_task = asyncio.create_task(_consume_loop(), name="kafka-consumer")


async def stop_consumer() -> None:
    """Detiene el consumer y cancela la tarea de consumo."""
    global _consumer, _consumer_task

    if _consumer_task and not _consumer_task.done():
        _consumer_task.cancel()
        try:
            await _consumer_task
        except asyncio.CancelledError:
            pass
        _consumer_task = None

    if _consumer:
        await _consumer.stop()
        _consumer = None
        logger.info("Kafka consumer detenido.")


# ── Loop principal de consumo ──────────────────────────────────────────────────

async def _consume_loop() -> None:
    """
    Itera mensajes del broker indefinidamente.
    Estrategia de error: reintento con backoff exponencial hasta MAX_RETRIES,
    luego descarta el mensaje y continúa (Dead Letter implícito via log).
    """
    MAX_RETRIES = 3

    if _consumer is None:
        return

    async for msg in _consumer:
        raw = msg.value
        topic = msg.topic
        partition = msg.partition
        offset = msg.offset

        try:
            envelope = KafkaEventEnvelope(**raw)
        except Exception as parse_err:
            logger.error(
                "Mensaje malformado en %s[%d]@%d — descartado: %s",
                topic, partition, offset, parse_err,
            )
            await _consumer.commit()
            continue

        retries = 0
        while retries < MAX_RETRIES:
            try:
                async with AsyncSessionLocal() as db:
                    await event_processor.process_event(envelope, db)
                break  # éxito
            except Exception as proc_err:
                retries += 1
                wait = 2 ** retries
                logger.warning(
                    "Error procesando %s (intento %d/%d), reintentando en %ds: %s",
                    envelope.event_type, retries, MAX_RETRIES, wait, proc_err,
                )
                if retries < MAX_RETRIES:
                    await asyncio.sleep(wait)
                else:
                    logger.error(
                        "Evento descartado tras %d intentos: %s | id=%s",
                        MAX_RETRIES, envelope.event_type, envelope.event_id,
                    )

        # Commit manual después de procesar (o descartar) el mensaje
        await _consumer.commit()
