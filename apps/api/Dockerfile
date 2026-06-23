FROM python:3.12-slim

WORKDIR /app

COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY packages/pyproject.toml packages/pyproject.toml
COPY apps/api apps/api
COPY packages packages
COPY scripts scripts

RUN pip install --no-cache-dir -e apps/api -e packages

EXPOSE 8000

CMD ["uvicorn", "librarian_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "apps/api"]
