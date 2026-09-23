"""Rollback-only integration checks; run explicitly inside the ingestion container."""

import os
import unittest
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from weather_common.db import SqlFileLoader
from weather_common.settings import Settings
from weather_ingest.forecast_insights import InsightWriter, utc


@unittest.skipUnless(
    os.getenv("WEATHER_RUN_INSIGHT_DB_TESTS") == "1", "Explicit database opt-in required"
)
class InsightDatabaseTests(unittest.TestCase):
    def test_revisions_prepared_queries_and_station_corrections(self):
        settings = Settings.from_environment()
        now = datetime.now(UTC)
        area = "test-" + uuid4().hex
        station_id = "IT" + uuid4().hex[:12]
        region = {"id": area, "issuedAt": utc(now), "latitude": 44.65, "longitude": -63.57}
        with psycopg.connect(settings.database_url, row_factory=dict_row) as connection:  # noqa: SIM117
            with connection.transaction(force_rollback=True):
                writer = InsightWriter(connection, SqlFileLoader(settings.sql_root))
                writer.revision(region, "bulletin")
                writer.revision(region, "bulletin")
                self.assertEqual(
                    len(
                        writer.query(
                            "revisions", {"area_id": area, "source": "bulletin"}
                        ).fetchall()
                    ),
                    1,
                )
                writer.publish(area, "changes", {"groups": []}, now, now + timedelta(hours=1))
                self.assertEqual(
                    writer.query("prepared", {"area_id": area, "kind": "changes"}).fetchone()[
                        "payload"
                    ],
                    {"groups": []},
                )
                writer.query(
                    "upsert_station",
                    {
                        "id": station_id,
                        "longitude": -63.57,
                        "latitude": 44.65,
                        "metadata": Jsonb({"id": station_id, "name": "Integration only"}),
                        "observed_at": now,
                    },
                )
                for observed, correction, value in [
                    (now, 0, 10),
                    (now, 1, 11),
                    (now - timedelta(hours=1), 2, 9),
                ]:
                    payload = {
                        "values": {"temperatureC": value},
                        "expiresAt": utc(observed + timedelta(hours=2)),
                    }
                    params = {
                        "id": station_id,
                        "observed_at": observed,
                        "correction": correction,
                        "report_type": "AUTO",
                        "version": uuid4().hex,
                        "payload": Jsonb(payload),
                    }
                    writer.query("insert_observation", params)
                    writer.query("insert_observation", params)
                params = {
                    "id": station_id,
                    "now": now,
                    "longitude": -63.57,
                    "latitude": 44.65,
                    "radius": 100,
                    "west": -64,
                    "east": -63,
                    "south": 44,
                    "north": 45,
                    "field": "temperatureC",
                    "limit": 5,
                    "offset": 0,
                }
                rows = writer.query("stations", params).fetchall()
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["payload"]["values"]["temperatureC"], 11)
                self.assertFalse(rows[0]["stale"])
                self.assertAlmostEqual(rows[0]["distance_km"], 0)
                params.update(west=170, east=-170)
                self.assertEqual(writer.query("stations", params).fetchall(), [])
                history = writer.query(
                    "station_history",
                    {"id": station_id, "start": now - timedelta(hours=2), "end": now},
                ).fetchall()
                self.assertEqual(len(history), 2)
                self.assertEqual(history[-1]["payload"]["values"]["temperatureC"], 11)
                # Feature API readers have no insert/update grants.
                permissions = connection.execute(
                    "SELECT has_table_privilege('weather_api', 'catalogue.forecast_revision', "
                    "'INSERT') AS writes, has_table_privilege('weather_api', "
                    "'catalogue.weather_observation', 'SELECT') AS reads"
                ).fetchone()
                self.assertFalse(permissions["writes"])
                self.assertTrue(permissions["reads"])


if __name__ == "__main__":
    unittest.main()
