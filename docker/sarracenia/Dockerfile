FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/home/sarra \
    USER=sarra \
    LOGNAME=sarra \
    XDG_CACHE_HOME=/var/lib/sarracenia/cache \
    XDG_CONFIG_HOME=/etc

RUN pip install --no-cache-dir "metpx-sr3[amqp]==3.2.0.post1" \
    && useradd --uid 50000 --gid 0 --home-dir /home/sarra --shell /usr/sbin/nologin sarra \
    && mkdir -p /home/sarra /etc/sr3/subscribe /var/lib/sarracenia/cache \
    && chown -R 50000:0 /home/sarra /var/lib/sarracenia

COPY docker/sarracenia/weatherapp.conf /etc/sr3/subscribe/weatherapp.conf
COPY --chown=50000:0 --chmod=600 docker/sarracenia/credentials.conf /etc/sr3/credentials.conf

USER 50000:0
CMD ["sh", "-c", "mkdir -p /var/lib/sarracenia/cache/sr3/subscribe/weatherapp && exec sr3 foreground subscribe/weatherapp"]
