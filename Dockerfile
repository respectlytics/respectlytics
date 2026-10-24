# Respectlytics Community Edition. The base image is pinned by digest, so a build uses exactly
# the image that was tested; every package is installed from requirements.txt with its hash
# checked; and the app runs as an unprivileged user, never as root.
FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# psycopg2-binary carries its own libpq, so no compiler or system library is needed.
COPY requirements.txt .
RUN pip install --require-hashes -r requirements.txt

RUN useradd --system --uid 10001 --home-dir /app respectlytics
COPY . .
# The only folders the app writes to at run time: static files (collected at start), the GeoIP
# database (downloaded at start, from DB-IP or with MaxMind credentials from MaxMind) and logs.
RUN mkdir -p staticfiles geoip_data logs \
    && chown respectlytics:respectlytics staticfiles geoip_data logs \
    && cp entrypoint.sh /entrypoint.sh && chmod 755 /entrypoint.sh

USER respectlytics
EXPOSE 8080

ENTRYPOINT ["/entrypoint.sh"]
CMD ["gunicorn", "core.wsgi:application", "--bind", "0.0.0.0:8080", "--workers", "2", "--threads", "3"]
