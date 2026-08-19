# Librarian Demo UI

A React + TypeScript frontend for Librarian. It loads the local library from
the API, asks evidence-first questions, and renders the returned source
passages as expandable citations.

## Run locally

```bash
cd apps/web
npm install
npm run dev
npm test
```

Then visit the Vite URL shown in the terminal. Run `npm run build` before
deploying; its static output is written to `dist/`.

## API connection

By default the app calls same-origin `/api`. Vite proxies that path to
`http://localhost:8000` during development, so no permissive API CORS setting
is required. Start the Librarian API with Docker Compose (or on port 8000) and
then run the Vite dev server.

For a separately hosted API, set `VITE_API_BASE_URL` to its base path or URL at
build time. For example:

```bash
VITE_API_BASE_URL=https://librarian.example.com/api npm run build
```

Static hosting should route `/api` to the Librarian API, or use the build-time
override above.

## Deploy

Deploy `apps/web` to Cloudflare Pages with `npm run build` and `dist/` as the
output directory. Configure `/api` as a reverse proxy to the Librarian API, or
set `VITE_API_BASE_URL` during the build.
