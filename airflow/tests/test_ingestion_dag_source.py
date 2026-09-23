from pathlib import Path


def _source() -> str:
    return (Path(__file__).parents[1] / "dags" / "eccc_ingestion.py").read_text()


def test_ingestion_dag_factory_is_config_scheduled_parameterless_and_pool_constrained() -> None:
    source = _source()

    assert "load_ingestion_dag_definitions" in source
    assert "dag_id=definition.dag_id" in source
    assert "schedule=definition.schedule" in source
    assert "definition.maximum_objects_per_run" in source
    assert "recovery_limit = max(1, discovery_limit * 3 // 4)" in source
    assert "limit=recovery_limit" in source
    assert 'pool="eccc_downloads"' in source
    assert 'pool="cog_transforms"' in source
    assert "discover_available_objects" in source
    assert "params=" not in source
    assert "get_current_context" not in source
    assert "discover_inbox_objects" in source
    assert "globals()[_definition.dag_id]" in source


def test_ingestion_factory_wires_the_mapped_pipeline_in_order() -> None:
    source = _source()

    stages = (
        "prepared = discover_and_register()",
        "requests = requests_for_mapping(prepared)",
        "downloaded = download_source.expand(request=requests)",
        "validated = validate_source.expand(downloaded=downloaded)",
        "processed = create_cog.expand(validated=validated)",
        "finalized = finalize_run(prepared)",
        "processed >> finalized",
    )
    positions = tuple(source.index(stage) for stage in stages)
    assert positions == tuple(sorted(positions))


def test_ingestion_dags_inventory_missing_slots_without_putting_rasters_in_xcom() -> None:
    source = _source()

    assert "HttpsListingSource" in source
    assert "available_processing_slots" in source
    assert '"product_run_id": int(validated["product_run_id"])' in source
    assert '"asset_id": asset_id' in source
    assert '"processed_path"' not in source
