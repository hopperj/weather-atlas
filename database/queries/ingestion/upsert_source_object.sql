-- Parameters:
--   provider_code, product_code, product_run_id (nullable), canonical_key,
--   observed_url, observed_aliases, response_headers, reported_size_bytes
WITH resolved_identity AS (
    SELECT
        provider.id AS provider_id,
        product.id AS product_id
    FROM catalogue.provider AS provider
    JOIN catalogue.product AS product ON product.provider_id = provider.id
    WHERE provider.code = %(provider_code)s
      AND product.code = %(product_code)s
)
INSERT INTO ingestion.source_object (
    provider_id,
    product_id,
    product_run_id,
    canonical_key,
    observed_url,
    observed_aliases,
    response_headers,
    reported_size_bytes
)
SELECT
    resolved_identity.provider_id,
    resolved_identity.product_id,
    %(product_run_id)s,
    %(canonical_key)s,
    %(observed_url)s,
    %(observed_aliases)s,
    %(response_headers)s,
    %(reported_size_bytes)s
FROM resolved_identity
ON CONFLICT (provider_id, canonical_key) DO UPDATE
SET product_run_id = COALESCE(ingestion.source_object.product_run_id, EXCLUDED.product_run_id),
    observed_url = EXCLUDED.observed_url,
    observed_aliases = EXCLUDED.observed_aliases,
    response_headers = EXCLUDED.response_headers,
    reported_size_bytes = COALESCE(EXCLUDED.reported_size_bytes, ingestion.source_object.reported_size_bytes),
    local_raw_path = CASE
        WHEN ingestion.source_object.status IN ('pending_deletion', 'deleted') THEN NULL
        ELSE ingestion.source_object.local_raw_path
    END,
    actual_size_bytes = CASE
        WHEN ingestion.source_object.status IN ('pending_deletion', 'deleted') THEN NULL
        ELSE ingestion.source_object.actual_size_bytes
    END,
    sha256 = CASE
        WHEN ingestion.source_object.status IN ('pending_deletion', 'deleted') THEN NULL
        ELSE ingestion.source_object.sha256
    END,
    status = CASE
        WHEN ingestion.source_object.status IN ('pending_deletion', 'deleted')
            THEN 'discovered'
        ELSE ingestion.source_object.status
    END,
    downloaded_at = CASE
        WHEN ingestion.source_object.status IN ('pending_deletion', 'deleted') THEN NULL
        ELSE ingestion.source_object.downloaded_at
    END,
    last_error_class = CASE
        WHEN ingestion.source_object.status IN ('pending_deletion', 'deleted') THEN NULL
        ELSE ingestion.source_object.last_error_class
    END,
    last_error_message = CASE
        WHEN ingestion.source_object.status IN ('pending_deletion', 'deleted') THEN NULL
        ELSE ingestion.source_object.last_error_message
    END,
    last_error_detail = CASE
        WHEN ingestion.source_object.status IN ('pending_deletion', 'deleted')
            THEN '{}'::jsonb
        ELSE ingestion.source_object.last_error_detail
    END,
    last_observed_at = clock_timestamp(),
    updated_at = clock_timestamp()
WHERE ingestion.source_object.product_id = EXCLUDED.product_id
RETURNING
    id,
    provider_id,
    product_id,
    product_run_id,
    canonical_key,
    observed_url,
    reported_size_bytes,
    actual_size_bytes,
    local_raw_path,
    sha256,
    status,
    download_attempts,
    first_observed_at,
    last_observed_at,
    downloaded_at,
    created_at,
    updated_at;
