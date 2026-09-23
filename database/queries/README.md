# Application SQL queries

Runtime statements are grouped by feature and loaded by their repository-relative
name, for example:

```python
await executor.fetch_all("catalogue/list_products.sql")
```

Rules for every query:

- schema-qualify application tables;
- explicitly list selected columns; never use `SELECT *`;
- bind values with psycopg `%(parameter_name)s` placeholders;
- never interpolate a table, column, path, URL, or expression from user input;
- document expected parameters in a leading SQL comment;
- return stable public codes where a client does not need an internal ID;
- keep write transactions at the repository/service boundary.

Catalogue and asset read queries support the API and restricted tile service.
Ingestion queries implement idempotent registration and state transitions with
natural uniqueness constraints and `ON CONFLICT` handling.

Maintenance queries select bounded retention/audit candidates and implement the
two database transitions around a filesystem deletion. Selection, pending, and
deleted statements remain separate so the service can verify the exact local
file between transactions. Each write transition also records an audit event.
