-- Readiness probe for the public catalogue API.
-- Parameters: none.
SELECT to_regclass('catalogue.product') IS NOT NULL AS ready;
