SELECT payload, content_version, generated_at, valid_until
FROM catalogue.forecast_prepared WHERE area_id = %(area_id)s AND kind = %(kind)s;
