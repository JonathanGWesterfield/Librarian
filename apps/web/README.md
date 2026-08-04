# Librarian Demo UI

A static, dependency-free portfolio frontend for Librarian. It demonstrates the
core interaction—ask a question, receive a grounded answer, and inspect the
supporting citations—using a small public-domain sample corpus.

## Run locally

```bash
python3 -m http.server 4173 --directory apps/web
```

Then visit `http://localhost:4173`.

## Deploy

Deploy `apps/web` as the static build/output directory on Cloudflare Pages. No
build command is required. The UI is intentionally static for a fast, free,
reliable demo; a future API client can replace the data in `app.js` without
changing the interaction design.
