# Librarian Demo UI

A React + TypeScript portfolio frontend for Librarian. It demonstrates the
core interaction—ask a question, receive a grounded answer, and inspect the
supporting citations—using a small public-domain sample corpus.

## Run locally

```bash
cd apps/web
npm install
npm run dev
npm test
```

Then visit the Vite URL shown in the terminal. Run `npm run build` before
deploying; its static output is written to `dist/`.

## Deploy

Deploy `apps/web` to Cloudflare Pages with `npm run build` and `dist/` as the
output directory. The UI intentionally keeps its rights-safe demo data local;
a future API client can replace the React demo data without changing the
interaction design.
