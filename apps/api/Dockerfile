FROM python:3.12-slim AS config-resolver

WORKDIR /app

COPY scripts/resolve_provider_config.py scripts/
COPY packages/librarian_config packages/librarian_config

ENV PYTHONPATH=/app/packages

ENTRYPOINT ["python", "scripts/resolve_provider_config.py"]


FROM python:3.12-slim AS runtime

WORKDIR /app

COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY packages/pyproject.toml packages/pyproject.toml
COPY apps/api apps/api
COPY packages packages
# These are operational commands used by the runtime API/worker deployment.
COPY scripts/index_opensearch.py scripts/process_summary_jobs.py scripts/

RUN pip install --no-cache-dir -e apps/api -e packages

EXPOSE 8000

CMD ["uvicorn", "librarian_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "apps/api"]


FROM runtime AS test

# Keep test-only code and developer dependencies out of the deployable runtime
# image. The verification harness still inherits and exercises runtime above.
COPY tests tests
COPY scripts/evaluate_retrieval.py scripts/verify_compose.py scripts/

RUN pip install --no-cache-dir -e "apps/api[dev]" -e "packages[dev]"
