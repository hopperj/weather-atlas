# Environment boundaries

As of 2026-09-24, the user designates:

- **Production (prod):** `sparky` (`10.0.0.243`), repository
  `/home/hopperj/weather-atlas`. Production weather data and service files are
  under its NAS-backed `data` directory; PostgreSQL and monitoring databases
  remain under local `postgres_data`.
- **Development (dev):** this Mac (`wolf359`), repository
  `/Users/hopperj/work/hobby/weatherapp`.

Default code changes, builds, and tests to development. A request to implement
or test a feature does not by itself authorize deployment, migrations, restarts,
or other mutations on production. Production changes must be within an explicit
production/deployment request; identify the target environment before acting.

Keep development databases, writable storage, credentials, and subscriber queue
identities separate from production. Do not restart the old Mac collectors using
their migrated production queue identity or automatically sync development data
over production. Do not change traffic routing as a side effect of local work.

The designation does not prove public traffic has been redirected. At the last
migration verification, public routing still targeted the old Mac deployment.
Verify routing before claiming a public cutover has completed.

See `docs/operations.md` and `docs/sparky-migration.md` for deployment details
and the dated migration checks.
