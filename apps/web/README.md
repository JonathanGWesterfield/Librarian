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

Start the Docker stack with `scripts/start_local.sh` (or
`./scripts/start_local.ps1`) before `npm run dev`; it creates the ignored local
JSON configuration on first use. Then visit the Vite URL shown in the terminal.
Run `npm run build` before deploying; its static output is written to `dist/`.

## Production Compose UI

The standard launcher also builds `apps/web/Dockerfile` and starts a small Nginx
web service. It serves the production Vite build on `services.web_port`
(default `http://localhost:3000`) and proxies `/api/*` to the healthy FastAPI
service. This keeps the browser same-origin and does not put provider settings,
credentials, or an API URL in the compiled frontend.

## API connection

The app calls the same-origin public `/api` contract. At development-server
startup, Vite reads `../../config/librarian.json` and proxies `/api` to the
configured `services.api_port`. No frontend environment variable or build-time
API URL is used. After changing `services.api_port`, restart `npm run dev`.

For static hosting, route the public site's `/api` path to the Librarian API.
The built browser app still makes only same-origin `/api` requests, so it
contains no local host or provider configuration. Compose implements that
route with the bundled Nginx proxy; another host must provide an equivalent
reverse-proxy rule.

## Caching

The Nginx runtime revalidates `index.html` on every navigation, including the
SPA fallback. This prevents a browser from keeping an old application shell
after an image update changes Vite's hashed JavaScript or CSS filenames.
Fingerprinted files under `/assets/` are cached as immutable for one year.

## Deploy

Deploy `apps/web` to Cloudflare Pages with `npm run build` and `dist/` as the
output directory. Configure `/api` as a reverse proxy to the Librarian API.
