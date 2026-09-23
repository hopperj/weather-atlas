from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest
from weather_common.db import Database, SqlFileLoader
from weather_ingest.config import load_product_config

TEST_DATABASE_URL = os.getenv("WEATHER_TEST_DATABASE_URL")
EXPECTED_MIGRATION_COUNT = len(
    list((Path(__file__).parents[1] / "database" / "migrations").glob("*.sql"))
)
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="WEATHER_TEST_DATABASE_URL is not configured for PostgreSQL integration tests",
)


def _fetch_scalar(connection: psycopg.Connection[tuple[object, ...]], sql: str) -> object:
    with connection.cursor() as cursor:
        cursor.execute(sql)
        row = cursor.fetchone()
    assert row is not None
    return row[0]


def test_phase_one_schema_and_seed_data_are_present() -> None:
    assert TEST_DATABASE_URL is not None
    with psycopg.connect(TEST_DATABASE_URL) as connection:
        migration_count = _fetch_scalar(
            connection,
            "SELECT count(*) FROM app.schema_migration;",
        )
        product_count = _fetch_scalar(
            connection,
            "SELECT count(*) FROM catalogue.product WHERE provider_id = "
            "(SELECT id FROM catalogue.provider WHERE code = 'eccc');",
        )
        surface_level_count = _fetch_scalar(
            connection,
            "SELECT count(*) FROM catalogue.vertical_level WHERE code = 'surface';",
        )

    assert migration_count == EXPECTED_MIGRATION_COUNT
    assert product_count == 7
    assert surface_level_count == 1


@pytest.mark.parametrize(
    "role,table_name,privilege,expected",
    [
        ("weather_api", "catalogue.product", "SELECT", True),
        ("weather_api", "catalogue.product", "INSERT", False),
        ("weather_tiles", "catalogue.asset", "SELECT", True),
        ("weather_tiles", "catalogue.asset", "UPDATE", False),
        ("weather_ingest", "catalogue.asset", "INSERT", True),
        ("weather_ingest", "catalogue.asset", "DELETE", False),
        ("weather_ingest", "ingestion.source_object", "UPDATE", True),
        ("weather_api", "ingestion.source_object", "SELECT", False),
    ],
)
def test_service_role_table_boundaries(
    role: str,
    table_name: str,
    privilege: str,
    expected: bool,
) -> None:
    assert TEST_DATABASE_URL is not None
    with psycopg.connect(TEST_DATABASE_URL) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT has_table_privilege(%s, %s, %s);",
            (role, table_name, privilege),
        )
        row = cursor.fetchone()

    assert row == (expected,)


def test_migrator_cannot_create_roles() -> None:
    assert TEST_DATABASE_URL is not None
    with psycopg.connect(TEST_DATABASE_URL) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT rolsuper, rolcreaterole, rolcreatedb "
            "FROM pg_catalog.pg_roles WHERE rolname = 'weather_migrator';"
        )
        row = cursor.fetchone()

    assert row == (False, False, False)


def test_async_sql_file_executor_reads_catalogue() -> None:
    assert TEST_DATABASE_URL is not None

    async def read_products() -> list[dict[str, object]]:
        async with (
            Database(TEST_DATABASE_URL, min_size=1, max_size=1) as database,
            database.transaction() as executor,
        ):
            return await executor.fetch_all("catalogue/list_products.sql")

    rows = asyncio.run(read_products())

    assert len(rows) == 7
    assert rows[0]["code"] == "hrdps"


def test_configured_weather_fields_match_reviewed_yaml() -> None:
    assert TEST_DATABASE_URL is not None
    config_root = Path(__file__).parents[1] / "config"
    expected: dict[tuple[str, str], tuple[object, ...]] = {}
    for product_code in ("hrdps", "raqdps", "rdps", "gdps"):
        product = load_product_config(config_root, product_code)
        for field in product.fields:
            expected[(product_code, field.code)] = (
                field.canonical_variable,
                field.level_code,
                field.source.producer,
                field.source.parameter,
                field.source.level,
                field.source.expected_unit,
                field.canonical_unit,
                field.conversion_key,
                field.display_enabled,
                field.download_enabled,
                field.processing_enabled,
                field.output_data_type,
                field.nodata_value,
                field.resampling,
                field.default_style,
                field.display_name,
                field.availability.start_forecast_hour,
                field.availability.end_forecast_hour,
                field.availability.forecast_hour_step,
            )

    with psycopg.connect(TEST_DATABASE_URL) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                product.code,
                product_field.metadata ->> 'field_code',
                variable.code,
                vertical_level.code,
                product_field.source_producer,
                product_field.source_parameter,
                product_field.metadata ->> 'source_level',
                product_field.source_unit,
                variable.canonical_unit,
                product_field.conversion_key,
                product_field.displayable,
                product_field.download_enabled,
                product_field.processing_enabled,
                product_field.metadata ->> 'output_data_type',
                (product_field.metadata ->> 'nodata_value')::double precision,
                product_field.metadata ->> 'resampling',
                product_field.metadata ->> 'default_style',
                product_field.metadata ->> 'display_name',
                (product_field.metadata #>> '{availability,start_forecast_hour}')::integer,
                (product_field.metadata #>> '{availability,end_forecast_hour}')::integer,
                COALESCE(
                    (product_field.metadata #>> '{availability,forecast_hour_step}')::integer,
                    1
                )
            FROM catalogue.product_field
            JOIN catalogue.product ON product.id = product_field.product_id
            JOIN catalogue.variable ON variable.id = product_field.variable_id
            JOIN catalogue.vertical_level
                ON vertical_level.id = product_field.vertical_level_id
            WHERE product.code IN ('hrdps', 'raqdps', 'rdps', 'gdps')
            ORDER BY product.code, product_field.metadata ->> 'field_code';
            """
        )
        actual_rows = cursor.fetchall()

    actual = {
        (str(row[0]), str(row[1])): tuple(row[2:])
        for row in actual_rows
    }
    assert actual == expected


def test_every_configured_field_has_its_configured_default_style() -> None:
    assert TEST_DATABASE_URL is not None
    with psycopg.connect(TEST_DATABASE_URL) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT count(*), count(variable_style.id)
            FROM catalogue.product_field
            JOIN catalogue.product ON product.id = product_field.product_id
            LEFT JOIN display.variable_style
                ON variable_style.product_field_id = product_field.id
                AND variable_style.variable_id = product_field.variable_id
                AND variable_style.code = 'default'
                AND variable_style.revision = 1
                AND variable_style.enabled
            LEFT JOIN display.palette ON palette.id = variable_style.palette_id
            WHERE product.code IN ('hrdps', 'raqdps', 'rdps', 'gdps')
              AND (
                  variable_style.id IS NULL
                  OR palette.code = product_field.metadata ->> 'default_style'
              );
            """
        )
        row = cursor.fetchone()

    assert row == (37, 37)


def test_configured_domains_are_present() -> None:
    assert TEST_DATABASE_URL is not None
    with psycopg.connect(TEST_DATABASE_URL) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT product.code, domain.code, domain.native_crs,
                domain.grid_width, domain.grid_height
            FROM catalogue.domain
            JOIN catalogue.product ON product.id = domain.product_id
            WHERE product.code IN ('hrdps', 'raqdps', 'rdps', 'gdps')
            ORDER BY product.code;
            """
        )
        rows = cursor.fetchall()

    assert rows == [
        ("gdps", "global", "LatLon0.15", 2400, 1201),
        ("hrdps", "continental", "RLatLon0.0225", 2540, 1290),
        ("raqdps", "north_america", "RLatLon0.09", 729, 599),
        ("rdps", "north_america", "RLatLon0.09", 1140, 1045),
    ]


def test_precipitation_analysis_catalogue_retains_complete_historical_cycles() -> None:
    assert TEST_DATABASE_URL is not None
    with psycopg.connect(TEST_DATABASE_URL) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                product.code,
                domain.code,
                domain.grid_width,
                domain.grid_height,
                count(product_field.id),
                count(product_field.id) FILTER (WHERE product_field.download_enabled),
                count(product_field.id) FILTER (WHERE product_field.processing_enabled),
                count(product_field.id) FILTER (WHERE product_field.displayable),
                bool_and(product_field.source_producer =
                    product_field.metadata ->> 'source_producer'),
                bool_and((product_field.metadata ->> 'source_band')::integer = 1),
                bool_and(product_field.metadata ->> 'retention_policy' =
                    'historical_archive'),
                bool_and((product.retention_config ->> 'retain_forever')::boolean)
            FROM catalogue.product
            JOIN catalogue.domain ON domain.product_id = product.id
            JOIN catalogue.product_field ON product_field.product_id = product.id
            WHERE product.code IN ('hrdpa', 'rdpa')
            GROUP BY product.code, domain.code, domain.grid_width, domain.grid_height
            ORDER BY product.code;
            """
        )
        rows = cursor.fetchall()

    assert rows == [
        ("hrdpa", "continental", 2538, 1288, 4, 4, 4, 4, True, True, True, True),
        ("rdpa", "north_america", 1140, 1045, 4, 4, 4, 4, True, True, True, True),
    ]


def test_product_time_semantics_enforce_nullable_analysis_forecast_hour() -> None:
    assert TEST_DATABASE_URL is not None
    loader = SqlFileLoader()
    with (
        psycopg.connect(TEST_DATABASE_URL) as connection,
        connection.transaction(force_rollback=True),
        connection.cursor() as cursor,
    ):
        cursor.execute(
            """
            INSERT INTO catalogue.product_run (
                product_id, domain_id, run_time, source_status, processing_status
            )
            SELECT product.id, domain.id, '2042-01-01T12:00:00Z',
                'discovered', 'processing'
            FROM catalogue.product
            JOIN catalogue.domain ON domain.product_id = product.id
            WHERE product.code = 'hrdpa' AND domain.code = 'continental'
            RETURNING id;
            """
        )
        run_row = cursor.fetchone()
        assert run_row is not None
        valid_parameters = {
            "product_run_id": run_row[0],
            "valid_time": datetime(2042, 1, 1, 12, tzinfo=UTC),
            "forecast_hour": None,
            "interval_start": datetime(2042, 1, 1, 6, tzinfo=UTC),
            "interval_end": datetime(2042, 1, 1, 12, tzinfo=UTC),
            "time_kind": "accumulation",
        }
        cursor.execute(
            loader.load("ingestion/upsert_product_time.sql"), valid_parameters
        )
        registered = cursor.fetchone()

        assert registered is not None
        assert registered[2] == datetime(2042, 1, 1, 12, tzinfo=UTC)
        assert registered[3] is None
        assert registered[4:7] == (
            datetime(2042, 1, 1, 6, tzinfo=UTC),
            datetime(2042, 1, 1, 12, tzinfo=UTC),
            "accumulation",
        )

        invalid_parameters = {**valid_parameters, "forecast_hour": 0}
        with (
            pytest.raises(psycopg.errors.CheckViolation),
            connection.transaction(),
        ):
            cursor.execute(
                loader.load("ingestion/upsert_product_time.sql"),
                invalid_parameters,
            )


def test_product_time_semantics_still_require_forecast_lead_hours() -> None:
    assert TEST_DATABASE_URL is not None
    loader = SqlFileLoader()
    with (
        psycopg.connect(TEST_DATABASE_URL) as connection,
        connection.transaction(force_rollback=True),
        connection.cursor() as cursor,
    ):
        cursor.execute(
            """
            INSERT INTO catalogue.product_run (
                product_id, domain_id, run_time, source_status, processing_status
            )
            SELECT product.id, domain.id, '2042-01-01T12:00:00Z',
                'discovered', 'processing'
            FROM catalogue.product
            JOIN catalogue.domain ON domain.product_id = product.id
            WHERE product.code = 'hrdps' AND domain.code = 'continental'
            RETURNING id;
            """
        )
        run_row = cursor.fetchone()
        assert run_row is not None

        with (
            pytest.raises(psycopg.errors.CheckViolation),
            connection.transaction(),
        ):
            cursor.execute(
                loader.load("ingestion/upsert_product_time.sql"),
                {
                    "product_run_id": run_row[0],
                    "valid_time": datetime(2042, 1, 1, 12, tzinfo=UTC),
                    "forecast_hour": None,
                    "interval_start": None,
                    "interval_end": None,
                    "time_kind": "instant",
                },
            )


def test_mapped_ingestion_can_resolve_a_registered_source_from_ids_only() -> None:
    assert TEST_DATABASE_URL is not None
    loader = SqlFileLoader()
    with (
        psycopg.connect(TEST_DATABASE_URL) as connection,
        connection.transaction(force_rollback=True),
        connection.cursor() as cursor,
    ):
            cursor.execute(
                """
                INSERT INTO catalogue.product_run (
                    product_id, domain_id, run_time, source_status, processing_status
                )
                SELECT product.id, domain.id, '2042-01-01T12:00:00Z',
                    'discovered', 'processing'
                FROM catalogue.product
                JOIN catalogue.domain ON domain.product_id = product.id
                WHERE product.code = 'hrdps' AND domain.code = 'continental'
                RETURNING id;
                """
            )
            run_row = cursor.fetchone()
            assert run_row is not None
            cursor.execute(
                """
                INSERT INTO ingestion.source_object (
                    provider_id, product_id, product_run_id, canonical_key,
                    observed_url, response_headers, reported_size_bytes
                )
                SELECT provider.id, product.id, %s, 'test/id-only-source',
                    'https://dd.weather.gc.ca/object.grib2',
                    '{"listing_size_is_exact":true}'::jsonb, 1234
                FROM catalogue.provider
                JOIN catalogue.product ON product.provider_id = provider.id
                WHERE provider.code = 'eccc' AND product.code = 'hrdps'
                RETURNING id;
                """,
                (run_row[0],),
            )
            source_row = cursor.fetchone()
            assert source_row is not None
            cursor.execute(
                loader.load("ingestion/get_source_object_for_processing.sql"),
                {"source_object_id": source_row[0]},
            )
            resolved = cursor.fetchone()

    assert resolved is not None
    assert resolved[1] == run_row[0]
    assert resolved[2:4] == ("hrdps", "continental")
    assert resolved[6:8] == (1234, True)


def test_backup_role_can_read_all_application_objects_without_mutating_them() -> None:
    assert TEST_DATABASE_URL is not None
    with psycopg.connect(TEST_DATABASE_URL) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                has_table_privilege('weather_backup', 'app.schema_migration', 'SELECT'),
                has_table_privilege('weather_backup', 'app.schema_migration', 'INSERT'),
                bool_and(has_schema_privilege(
                    'weather_backup', schema_name, 'USAGE'
                ))
            FROM unnest(ARRAY['app', 'catalogue', 'ingestion', 'display', 'audit'])
                AS configured(schema_name);
            """
        )
        table_and_schema_privileges = cursor.fetchone()
        cursor.execute(
            """
            SELECT COALESCE(bool_and(has_sequence_privilege(
                'weather_backup', quote_ident(sequence_schema) || '.'
                    || quote_ident(sequence_name), 'SELECT'
            )), true)
            FROM information_schema.sequences
            WHERE sequence_schema IN ('app', 'catalogue', 'ingestion', 'display', 'audit');
            """
        )
        sequence_privilege = cursor.fetchone()

    assert table_and_schema_privileges == (True, False, True)
    assert sequence_privilege == (True,)
