ARG AIRFLOW_BASE_IMAGE=apache/airflow:3.3.0

FROM debian:bookworm-slim AS model-build
RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        gfortran make libeccodes-dev libnetcdff-dev \
    && rm -rf /var/lib/apt/lists/*
COPY cffeps /build/cffeps
RUN make -C /build/cffeps -f Makefile.portable clean all \
    FFLAGS="-O2 -fbacktrace -ffree-line-length-none"
COPY flexpart/src /build/flexpart/src
RUN cd /build/flexpart/src \
    && ECCODES_MOD_DIR="$(dirname "$(find /usr/lib -name grib_api.mod -print -quit)")" \
    && CPATH="/usr/include:${ECCODES_MOD_DIR}" LIBRARY_PATH="/usr/lib/$(gcc -dumpmachine)" \
       make -f makefile_gfortran FC=gfortran clean \
    && CPATH="/usr/include:${ECCODES_MOD_DIR}" LIBRARY_PATH="/usr/lib/$(gcc -dumpmachine)" \
       make -f makefile_gfortran \
         FC=gfortran \
         eta=no \
         FFLAGS="-I/usr/include -I${ECCODES_MOD_DIR} -O3 -cpp -DUSE_NCF -UETA -g -fopenmp -Duseomp" \
         LDFLAGS="-O3 -fopenmp -L/usr/lib/$(gcc -dumpmachine) -Wl,-rpath=/usr/lib/$(gcc -dumpmachine) -leccodes -leccodes_f90 -lnetcdff -lnetcdf -lm"

FROM ${AIRFLOW_BASE_IMAGE}

USER root
RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        gdal-bin libeccodes-tools libgfortran5 libnetcdff7 \
    && rm -rf /var/lib/apt/lists/*

USER airflow
RUN python -m pip install --no-cache-dir \
    httpx==0.28.1 \
    pydantic==2.13.4 \
    "psycopg[binary,pool]==3.3.4" \
    PyYAML==6.0.3 \
    netCDF4==1.7.4 \
    numpy==2.5.1 \
    rasterio==1.5.0

COPY --chown=airflow:root python/weather_ingest /opt/weather/python/weather_ingest
COPY --chown=airflow:root python/weather_common /opt/weather/python/weather_common
COPY --chown=airflow:root database/queries /opt/weather/database/queries
COPY --chown=airflow:root config/smoke /opt/weather/config/smoke
COPY --chown=airflow:root flexpart/options /opt/weather/flexpart/options
COPY --from=model-build --chown=airflow:root /build/cffeps/bin/weatherapp-cffeps /opt/weather/bin/weatherapp-cffeps
COPY --from=model-build --chown=airflow:root /build/flexpart/src/FLEXPART /opt/weather/bin/FLEXPART
ENV PYTHONPATH=/opt/weather/python
