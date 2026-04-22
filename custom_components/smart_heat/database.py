"""SQLite database for Smart Heat decision logs and analytics snapshots.

Uses aiosqlite for async-safe access. Stores:
- Hourly analytics snapshots per zone
- Optimizer decision log entries
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import aiosqlite

_LOGGER = logging.getLogger(__name__)

SCHEMA_VERSION = 1


class SmartHeatDatabase:
    """Async SQLite database for Smart Heat."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def async_setup(self) -> None:
        """Open database and create tables if needed."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self._db_path))
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._create_tables()
        _LOGGER.info("Smart Heat database opened at %s", self._db_path)

    async def _create_tables(self) -> None:
        assert self._db is not None
        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY
            );

            CREATE TABLE IF NOT EXISTS analytics_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                zone_name TEXT NOT NULL,
                indoor_temp REAL,
                outdoor_temp REAL,
                energy_kwh REAL,
                delta_t REAL,
                heat_loss_score REAL,
                heat_loss_confidence REAL,
                effectiveness_score REAL,
                effectiveness_confidence REAL
            );

            CREATE INDEX IF NOT EXISTS idx_snapshots_zone_time
                ON analytics_snapshots(zone_name, timestamp);

            CREATE TABLE IF NOT EXISTS optimizer_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                zone_name TEXT NOT NULL,
                control_mode TEXT NOT NULL,
                action TEXT NOT NULL,
                reason TEXT,
                current_temp REAL,
                target_temp REAL,
                outdoor_temp REAL,
                heat_loss_score REAL,
                applied INTEGER DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_decisions_zone_time
                ON optimizer_decisions(zone_name, timestamp);
        """)
        await self._db.commit()

    # ── Analytics snapshots ─────────────────────────────────────────

    async def insert_snapshot(
        self,
        zone_name: str,
        indoor_temp: float | None,
        outdoor_temp: float | None,
        energy_kwh: float | None,
        delta_t: float | None,
        heat_loss_score: float | None,
        heat_loss_confidence: float | None,
        effectiveness_score: float | None,
        effectiveness_confidence: float | None,
    ) -> None:
        """Insert an hourly analytics snapshot."""
        assert self._db is not None
        await self._db.execute(
            """INSERT INTO analytics_snapshots
               (timestamp, zone_name, indoor_temp, outdoor_temp, energy_kwh,
                delta_t, heat_loss_score, heat_loss_confidence,
                effectiveness_score, effectiveness_confidence)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.utcnow().isoformat(),
                zone_name,
                indoor_temp,
                outdoor_temp,
                energy_kwh,
                delta_t,
                heat_loss_score,
                heat_loss_confidence,
                effectiveness_score,
                effectiveness_confidence,
            ),
        )
        await self._db.commit()

    async def get_recent_snapshots(
        self, zone_name: str, hours: int = 24
    ) -> list[dict[str, Any]]:
        """Retrieve recent snapshots for a zone."""
        assert self._db is not None
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        cursor = await self._db.execute(
            """SELECT * FROM analytics_snapshots
               WHERE zone_name = ? AND timestamp >= ?
               ORDER BY timestamp ASC""",
            (zone_name, cutoff),
        )
        columns = [d[0] for d in cursor.description]
        rows = await cursor.fetchall()
        return [dict(zip(columns, row)) for row in rows]

    # ── Optimizer decisions ─────────────────────────────────────────

    async def log_decision(
        self,
        zone_name: str,
        control_mode: str,
        action: str,
        reason: str,
        current_temp: float | None = None,
        target_temp: float | None = None,
        outdoor_temp: float | None = None,
        heat_loss_score: float | None = None,
        applied: bool = False,
    ) -> None:
        """Log an optimizer decision."""
        assert self._db is not None
        await self._db.execute(
            """INSERT INTO optimizer_decisions
               (timestamp, zone_name, control_mode, action, reason,
                current_temp, target_temp, outdoor_temp, heat_loss_score, applied)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.utcnow().isoformat(),
                zone_name,
                control_mode,
                action,
                reason,
                current_temp,
                target_temp,
                outdoor_temp,
                heat_loss_score,
                int(applied),
            ),
        )
        await self._db.commit()

    # ── Cleanup ─────────────────────────────────────────────────────

    async def prune_old_data(self, retention_days: int = 90) -> None:
        """Remove data older than retention period."""
        assert self._db is not None
        cutoff = (datetime.utcnow() - timedelta(days=retention_days)).isoformat()
        await self._db.execute(
            "DELETE FROM analytics_snapshots WHERE timestamp < ?", (cutoff,)
        )
        await self._db.execute(
            "DELETE FROM optimizer_decisions WHERE timestamp < ?", (cutoff,)
        )
        await self._db.commit()

    async def async_close(self) -> None:
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None
            _LOGGER.debug("Smart Heat database closed")
