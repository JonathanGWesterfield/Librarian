FROM node:22-bookworm-slim AS codex-cli

RUN npm install --global @openai/codex@0.144.6


FROM python:3.12-slim AS base

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


FROM base AS runtime

EXPOSE 3000

CMD ["uvicorn", "librarian_broker.main:app", "--host", "0.0.0.0", "--port", "3000", "--app-dir", "apps/codex_broker"]


# This target is selected only by docker-compose.r2.yml.  It packages the
# release-bound manifest and starts a gRPC listener exclusively; R0 continues
# to use the HTTP ``runtime`` target above until the atomic M03 cutover.
FROM base AS r2-runtime

ARG STACK_RELEASE_SHA

COPY proto proto
COPY scripts/generate_stack_contract.py scripts/generate_stack_contract.py

RUN test -n "$STACK_RELEASE_SHA" \
    && python scripts/generate_stack_contract.py \
      --stack-release-sha "$STACK_RELEASE_SHA" \
      --output /app/librarian-stack-contract.json

EXPOSE 50051

CMD ["python", "-m", "librarian_broker.r2_main"]
