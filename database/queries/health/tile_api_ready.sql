-- Readiness probe for the restricted raster tile API.
-- Parameters: none.
SELECT to_regclass('catalogue.asset') IS NOT NULL AS ready;
