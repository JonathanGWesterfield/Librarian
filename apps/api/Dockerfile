FROM python:3.12-slim AS config-resolver

WORKDIR /app

COPY scripts/resolve_provider_config.py scripts/
COPY packages/librarian_config packages/librarian_config
COPY packages/librarian_contracts packages/librarian_contracts

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

RUN apt-get update \
    && apt-get install --no-install-recommends -y git \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -e "apps/api[dev]" -e "packages[dev]"


# The isolated R2 contract gate needs the checked-in descriptor and its
# generation/preflight helpers. Keep these verification-only files out of the
# general test image and deployable runtime image.
FROM test AS answer-delivery-contract-gate

COPY proto/librarian/answer/v1/ proto/librarian/answer/v1/
COPY scripts/generate_contracts.sh scripts/prepare_r2_cutover.py scripts/resolve_provider_config.py scripts/


# The separate R2 composition supplies this build argument from its release
# pipeline.  A missing SHA fails the build instead of producing an image that
# could hand-shake as an unspecified release.  Keep this target after ``test``
# so normal R0 test-image builds never need an R2 release SHA.
FROM runtime AS r2-runtime

ARG STACK_RELEASE_SHA

COPY proto proto
COPY scripts/generate_stack_contract.py scripts/generate_stack_contract.py
COPY scripts/process_metadata_jobs.py scripts/process_metadata_jobs.py

RUN test -n "$STACK_RELEASE_SHA" \
    && python scripts/generate_stack_contract.py \
      --stack-release-sha "$STACK_RELEASE_SHA" \
      --output /app/librarian-stack-contract.json


FROM r2-runtime AS r2-evaluator

COPY tests tests
COPY scripts/evaluate_retrieval.py scripts/verify_compose.py scripts/

RUN pip install --no-cache-dir -e "apps/api[dev]" -e "packages[dev]"
