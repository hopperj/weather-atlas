-- Parameters: source_object_id
-- Resolve one registered source identity for a mapped ingestion task. This lets
-- XCom carry only database IDs instead of remote URLs and filenames.
SELECT
    source_object.id AS source_object_id,
    source_object.product_run_id,
    product.code AS product_code,
    domain.code AS domain_code,
    product_run.run_time,
    source_object.observed_url,
    source_object.reported_size_bytes,
    CASE
        WHEN jsonb_typeof(source_object.response_headers -> 'listing_size_is_exact') = 'boolean'
            THEN (source_object.response_headers ->> 'listing_size_is_exact')::boolean
        ELSE false
    END AS size_is_exact,
    source_object.status
FROM ingestion.source_object AS source_object
JOIN catalogue.product AS product ON product.id = source_object.product_id
JOIN catalogue.product_run AS product_run ON product_run.id = source_object.product_run_id
JOIN catalogue.domain AS domain ON domain.id = product_run.domain_id
WHERE source_object.id = %(source_object_id)s
  AND source_object.status NOT IN ('pending_deletion', 'deleted');
