FROM debian:bookworm-slim AS build
RUN apt-get update && apt-get install -y --no-install-recommends gfortran make ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src/cffeps
COPY . .
RUN make -f Makefile.portable clean all FFLAGS="-O2 -fbacktrace -ffree-line-length-none"

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgfortran5 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /src/cffeps/bin/weatherapp-cffeps /usr/local/bin/weatherapp-cffeps
USER 65532:65532
ENTRYPOINT ["/usr/local/bin/weatherapp-cffeps"]
