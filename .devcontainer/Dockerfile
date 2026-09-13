FROM node:22-bookworm-slim AS node
FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && if [ -f /etc/apt/sources.list.d/yarn.list ]; then mv /etc/apt/sources.list.d/yarn.list /etc/apt/sources.list.d/yarn.list.disabled; fi \
    && apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/* \
    && node --version && npm --version && ffmpeg -version
ENV NEXT_TELEMETRY_DISABLED=1
