# Official ESPHome distribution: compiler, ESP-IDF, esptool and OTA CLI included.
FROM ghcr.io/esphome/esphome:2026.9.0
ARG BUILD_VERSION
ARG BUILD_ARCH
# The Supervisor passes BUILD_ARCH (aarch64, amd64). The image GitHub builds for Docker (docker.yml) builds both
# platforms at once, so there Docker's own TARGETARCH (arm64, amd64) fills the label.
ARG TARGETARCH
LABEL io.hass.version="${BUILD_VERSION}" io.hass.type="app" io.hass.arch="${BUILD_ARCH:-$TARGETARCH}"
RUN pip install --no-cache-dir 'aiohttp>=3.12,<4' PyYAML
COPY app /app
# Every text of the app, the editor and the screens, one file per language (app 0.2.90).
COPY translations /app/translations
# The Update badge shows what's new from the changelog (app 0.2.73).
COPY CHANGELOG.md /app/CHANGELOG.md
WORKDIR /app
# The ESPHome image checks its dashboard on port 6052, which this app never starts, so the container read
# "unhealthy" while everything worked (issue #23). This one asks our own server, on the port the page is on;
# under the Supervisor every other address gets a 403, so it is /health and not /.
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl --fail --silent --output /dev/null http://127.0.0.1:8099/health || exit 1
ENTRYPOINT []
CMD ["python3", "/app/server.py"]
