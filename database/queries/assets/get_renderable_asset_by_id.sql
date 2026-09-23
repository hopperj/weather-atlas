-- Parameters: asset_id bigint, style_id bigint, asset_sha256 text
SELECT
    asset.id AS asset_id,
    asset.relative_path,
    asset.sha256 AS asset_sha256,
    asset.nodata_value,
    variable_style.id AS style_id,
    variable_style.resampling_method,
    palette.definition AS palette_definition
FROM catalogue.asset
JOIN display.variable_style ON variable_style.id = %(style_id)s
JOIN display.palette ON palette.id = variable_style.palette_id
WHERE asset.id = %(asset_id)s
  AND asset.sha256 = %(asset_sha256)s
  AND asset.status = 'available'
  AND asset.storage_backend = 'local'
  AND asset.asset_role IN ('processed_cog', 'derived_cog')
  AND variable_style.enabled
  AND palette.enabled
  AND variable_style.variable_id = (
      SELECT product_field.variable_id
      FROM catalogue.product_field
      WHERE product_field.id = asset.product_field_id
  )
  AND (
      variable_style.product_field_id IS NULL
      OR variable_style.product_field_id = asset.product_field_id
  )
LIMIT 1;
