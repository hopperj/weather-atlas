-- Parameters:
--   source_object_id (nullable), asset_id (nullable), check_name, status,
--   measured_value, expected_value, details
INSERT INTO ingestion.data_quality_result (
    source_object_id,
    asset_id,
    check_name,
    status,
    measured_value,
    expected_value,
    details
)
VALUES (
    %(source_object_id)s,
    %(asset_id)s,
    %(check_name)s,
    %(status)s,
    %(measured_value)s,
    %(expected_value)s,
    %(details)s
)
RETURNING
    id,
    source_object_id,
    asset_id,
    check_name,
    status,
    measured_value,
    expected_value,
    details,
    checked_at;
