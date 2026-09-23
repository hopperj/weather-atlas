ARG POSTGRES_BASE_IMAGE=postgres:18.4-alpine3.23
FROM ${POSTGRES_BASE_IMAGE}

# Alpine's stable PostGIS package is available for every architecture supported
# by the official PostgreSQL image, including arm64. Alpine installs extension
# metadata and modules below versioned directories, while the Docker Official
# Image builds PostgreSQL below /usr/local. Link the packaged files into the
# directories reported by the image's pg_config so CREATE EXTENSION can find
# both the control files and shared modules.
RUN apk add --no-cache "postgis~3.6" \
    && ln -sf /usr/share/postgresql18/extension/* /usr/local/share/postgresql/extension/ \
    && ln -sf /usr/lib/postgresql18/*.so /usr/local/lib/postgresql/
