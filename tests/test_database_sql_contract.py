import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[1]
MIGRATION_ROOT = PROJECT_ROOT / "database" / "migrations"
QUERY_ROOT = PROJECT_ROOT / "database" / "queries"


def test_phase_one_migrations_are_ordered_and_self_recording() -> None:
    migration_names = [path.name for path in sorted(MIGRATION_ROOT.glob("*.sql"))]

    assert migration_names[:6] == [
        "0001_initialize_application.sql",
        "0002_create_roles_and_schemas.sql",
        "0003_create_catalogue.sql",
        "0004_create_ingestion.sql",
        "0005_create_display.sql",
        "0006_seed_initial_catalogue.sql",
    ]
    assert migration_names == sorted(migration_names)
    assert len(migration_names) == len(set(migration_names))

    for migration_path in sorted(MIGRATION_ROOT.glob("*.sql")):
        sql = migration_path.read_text(encoding="utf-8")
        assert "\\set ON_ERROR_STOP on" in sql
        assert re.search(r"\bBEGIN;", sql)
        assert "INSERT INTO app.schema_migration" in sql
        assert re.search(r"\bCOMMIT;\s*$", sql)


def test_runtime_queries_are_reviewable_parameterized_sql() -> None:
    query_paths = sorted(QUERY_ROOT.rglob("*.sql"))

    assert query_paths
    for query_path in query_paths:
        sql = query_path.read_text(encoding="utf-8")
        assert sql.strip(), query_path
        assert not re.search(r"SELECT\s+\*", sql, flags=re.IGNORECASE), query_path
        assert "{" not in sql.replace("'{}'::jsonb", ""), query_path


def test_privileged_role_bootstrap_is_separate_from_migrations() -> None:
    bootstrap = (
        PROJECT_ROOT / "database" / "bootstrap" / "create_application_roles.sql"
    ).read_text(encoding="utf-8")
    role_migration = (MIGRATION_ROOT / "0002_create_roles_and_schemas.sql").read_text(
        encoding="utf-8"
    )

    assert "CREATE ROLE weather_owner" in bootstrap
    assert "CREATE ROLE weather_owner" not in role_migration
    assert "run the administrator role bootstrap first" in role_migration


def test_seeded_palette_shape_has_interpolation_and_numeric_stops() -> None:
    seed_sql = (MIGRATION_ROOT / "0006_seed_initial_catalogue.sql").read_text(encoding="utf-8")

    assert '"interpolation":"linear"' in seed_sql
    assert '"stops":[{"value":' in seed_sql
    assert '"color":"#' in seed_sql


def test_configured_catalogue_migration_preserves_backup_boundaries() -> None:
    catalogue_sql = (
        MIGRATION_ROOT / "0008_catalogue_configured_weather_fields.sql"
    ).read_text(encoding="utf-8")

    assert "GRANT SELECT ON app.schema_migration TO weather_backup" in catalogue_sql
    assert "GRANT SELECT ON ALL SEQUENCES" in catalogue_sql
    assert "ALTER DEFAULT PRIVILEGES" in catalogue_sql
    assert not re.search(
        r"GRANT\s+(?:INSERT|UPDATE|DELETE|TRUNCATE|USAGE).*TO\s+weather_backup",
        catalogue_sql,
        flags=re.IGNORECASE | re.DOTALL,
    )


def test_run_finalization_keeps_core_fields_visible_while_run_is_partial() -> None:
    sql = (QUERY_ROOT / "ingestion" / "finalize_product_run.sql").read_text(
        encoding="utf-8"
    )

    assert "asset_counts.processed_count < product_run.expected_asset_count" in sql
    assert "THEN 'partially_available'" in sql
    assert "is_visible = required_state.core_available" in sql


def test_rediscovery_revives_payloads_deleted_by_an_older_retention_policy() -> None:
    source_sql = (
        QUERY_ROOT / "ingestion" / "upsert_source_object.sql"
    ).read_text(encoding="utf-8")
    run_sql = (
        QUERY_ROOT / "ingestion" / "upsert_product_run.sql"
    ).read_text(encoding="utf-8")

    assert "status IN ('pending_deletion', 'deleted')" in source_sql
    assert "THEN 'discovered'" in source_sql
    assert "source_status = 'expired'" in run_sql
    assert "THEN NULL" in run_sql


def test_recovery_queue_includes_registered_sources_without_available_assets() -> None:
    sql = (
        QUERY_ROOT / "ingestion" / "recover_source_objects.sql"
    ).read_text(encoding="utf-8")

    assert "source_object.status IN" in sql
    assert "'deleted'" in sql
    assert "asset.status = 'available'" in sql
    assert "source_sha256" in sql
    assert "THEN 'discovered'" in sql
    assert "FOR UPDATE OF source_object SKIP LOCKED" in sql
    assert "last_error_class IS DISTINCT FROM 'SourceUnavailableError'" in sql


def test_hrepa_migration_enables_reviewed_netcdf_fields_and_styles() -> None:
    sql = (
        MIGRATION_ROOT / "0015_enable_hrepa_netcdf_ingestion.sql"
    ).read_text(encoding="utf-8")

    assert "'canada_northern_us'" in sql
    assert "'precipitation_6h_ensemble'" in sql
    assert "'precipitation_6h_percentile_25'" in sql
    assert "'precipitation_6h_percentile_75'" in sql
    assert "'netcdf_variable'" in sql
    assert "'historical_archive'" in sql


def test_retain_forever_products_are_excluded_from_age_retention() -> None:
    asset_sql = (
        QUERY_ROOT / "maintenance" / "list_asset_retention_candidates.sql"
    ).read_text(encoding="utf-8")
    source_sql = (
        QUERY_ROOT / "maintenance" / "list_source_retention_candidates.sql"
    ).read_text(encoding="utf-8")

    assert "retain_forever" in asset_sql
    assert "retain_forever" in source_sql


def test_retention_never_selects_referenced_simulation_files() -> None:
    asset_sql = (
        QUERY_ROOT / "maintenance" / "list_asset_retention_candidates.sql"
    ).read_text(encoding="utf-8")
    source_sql = (
        QUERY_ROOT / "maintenance" / "list_source_retention_candidates.sql"
    ).read_text(encoding="utf-8")

    assert "simulation.run_artifact" in asset_sql
    assert "simulation.run_input" in asset_sql
    assert "simulation.run_input" in source_sql
    assert "operational_days" in asset_sql
    assert "interactive_days" in asset_sql


def test_timeline_queries_filter_frames_by_selected_field() -> None:
    run_sql = (
        QUERY_ROOT / "catalogue" / "list_runs_for_product.sql"
    ).read_text(encoding="utf-8")
    time_sql = (
        QUERY_ROOT / "catalogue" / "list_times_for_run.sql"
    ).read_text(encoding="utf-8")

    assert "%(field_code)s" in run_sql
    assert "%(field_code)s" in time_sql
    assert "asset.product_field_id" in time_sql


def test_cross_run_timeline_prefers_the_shortest_forecast_lead() -> None:
    sql = (
        QUERY_ROOT / "catalogue" / "list_best_timeline.sql"
    ).read_text(encoding="utf-8")

    assert "PARTITION BY product_time.valid_time" in sql
    assert "product_time.forecast_hour ASC NULLS FIRST" in sql
    assert "product_run.run_time DESC" in sql
    assert "MAX(valid_time) FILTER (WHERE valid_time <= clock_timestamp())" in sql
    assert "INTERVAL '24 hours'" in sql
    assert "%(start_time)s" in sql
    assert "%(end_time)s" in sql
    assert "%(field_code)s" in sql
    assert "%(domain_code)s" in sql


def test_cross_run_timeline_migration_adds_bounded_lookup_indexes() -> None:
    sql = (
        MIGRATION_ROOT / "0016_optimize_cross_run_timeline.sql"
    ).read_text(encoding="utf-8")

    assert "product_time_valid_run_idx" in sql
    assert "asset_available_time_field_idx" in sql
    assert "app.schema_migration" in sql


def test_cloud_cover_activation_enables_all_deterministic_forecast_products() -> None:
    sql = (MIGRATION_ROOT / "0017_enable_total_cloud_cover.sql").read_text(
        encoding="utf-8"
    )

    assert "'total_cloud_cover'" in sql
    assert "'gdps', 'hrdps', 'rdps'" in sql
    assert "download_enabled = true" in sql
    assert "processing_enabled = true" in sql
    assert "displayable = true" in sql


def test_full_forecast_activation_enables_all_thirty_configured_fields() -> None:
    sql = (
        MIGRATION_ROOT / "0018_enable_all_configured_forecast_fields.sql"
    ).read_text(encoding="utf-8")

    assert "'gdps', 'hrdps', 'rdps'" in sql
    assert "download_enabled = true" in sql
    assert "processing_enabled = true" in sql
    assert "displayable = true" in sql
    assert "<> 30" in sql


def test_analysis_catalogue_migration_enforces_time_semantics_and_activation_gate() -> None:
    sql = (MIGRATION_ROOT / "0009_register_precipitation_analyses.sql").read_text(
        encoding="utf-8"
    )

    assert "ADD COLUMN source_producer text" in sql
    assert "product_field_source_uk UNIQUE NULLS NOT DISTINCT" in sql
    assert "CREATE FUNCTION catalogue.enforce_product_time_semantics()" in sql
    assert "analysis product times require forecast_hour to be NULL" in sql
    assert "forecast product times require forecast_hour" in sql
    assert "'real_payload_metadata_unit_band_and_pixel_validation'" in sql
    assert re.search(
        r"false,\s*true,\s*false,\s*jsonb_build_object",
        sql,
        flags=re.IGNORECASE,
    )
