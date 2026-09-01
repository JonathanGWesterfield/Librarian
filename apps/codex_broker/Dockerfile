FROM node:22-bookworm-slim AS codex-cli

RUN npm install --global @openai/codex@0.144.6


FROM python:3.12-slim AS runtime

WORKDIR /app

# Copy the pinned CLI and its Node runtime without installing user credentials
# or host configuration into the image.
COPY --from=codex-cli /usr/local/bin/node /usr/local/bin/node
COPY --from=codex-cli /usr/local/lib/node_modules/@openai/codex /usr/local/lib/node_modules/@openai/codex
RUN ln -s /usr/local/lib/node_modules/@openai/codex/bin/codex.js /usr/local/bin/codex

COPY apps/codex_broker/pyproject.toml apps/codex_broker/pyproject.toml
COPY packages/pyproject.toml packages/pyproject.toml
COPY apps/codex_broker apps/codex_broker
COPY packages packages

RUN pip install --no-cache-dir -e packages -e apps/codex_broker

EXPOSE 3000

CMD ["uvicorn", "librarian_broker.main:app", "--host", "0.0.0.0", "--port", "3000", "--app-dir", "apps/codex_broker"]
