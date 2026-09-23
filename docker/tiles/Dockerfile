FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install --yes --no-install-recommends libexpat1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY python ./python
COPY database/queries ./database/queries
COPY docker/python-logging.json ./docker/python-logging.json
RUN pip install --no-cache-dir .

USER 10001:10001
EXPOSE 8000

CMD ["uvicorn", "weather_tiles.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-config", "/app/docker/python-logging.json"]
