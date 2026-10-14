FROM node:22-alpine AS build

# Keep the workspace layout used by the checked-in TypeScript contract tests.
# They import the versioned schema and deterministic answer fixtures relative to
# apps/web/src, so copying only the web application makes `tsc --noEmit` fail
# in the Compose image build.
WORKDIR /workspace/apps/web

COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci

COPY apps/web ./
COPY schemas/librarian/answer/v1 /workspace/schemas/librarian/answer/v1
COPY tests/fixtures/answer_delivery/v1 /workspace/tests/fixtures/answer_delivery/v1
RUN npm run build


FROM nginx:1.27-alpine AS runtime

COPY apps/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /workspace/apps/web/dist /usr/share/nginx/html

EXPOSE 8080
