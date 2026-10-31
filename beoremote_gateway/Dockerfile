FROM python:3.13-slim-trixie

ARG BUILD_VERSION=0.6.0-dev11
ARG BUILD_ARCH=aarch64
LABEL io.hass.version="${BUILD_VERSION}" \
      io.hass.type="app" \
      io.hass.arch="${BUILD_ARCH}"

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends adb \
    && rm -rf /var/lib/apt/lists/* \
    && ln -s /data/adb/.android /root/.android
COPY requirements.txt .
COPY LICENSE ./LICENSE
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m pip uninstall -y pip
COPY gateway ./gateway
HEALTHCHECK --interval=15s --timeout=3s --start-period=30s --retries=3 CMD ["python", "-m", "gateway.health", "--check"]
CMD ["python", "-m", "gateway", "--options", "/data/options.json"]

