# Librarian Web UI Proposal

## Recommendation

Build **Librarian Demo**: a polished, public web interface for a small,
rights-safe sample library. It should demonstrate the product's strongest idea:
people can ask natural-language questions of a book collection and inspect the
specific passages that support each answer.

The public demo is not a deployment of a personal EPUB collection. Personal
books, local SQLite data, Ollama, and the Codex broker remain local. The demo
uses a curated corpus of public-domain or explicitly licensed books and a
prebuilt, read-only index. This avoids copyright and privacy problems while
giving a recruiter a fast, reliable experience.

## What a visitor should see

The visual direction should feel like a quiet research library rather than a
generic chatbot: warm off-white background, ink/dark-green typography, book
cover or spine accents, restrained motion, and generous reading space.

### Primary screens

1. **Explore / Ask**
   - A prominent question box with clickable starter prompts.
   - Filters for author, book, genre, and topic tag.
   - An answer panel that reveals a concise grounded response.
   - Citation cards underneath: book, author, chapter, source excerpt, and a
     relevance indicator. A citation is the main product proof, not a footnote.

2. **Discover**
   - A natural-language recommendation prompt (for example, “political
     intrigue and worldbuilding”).
   - Ranked book cards with the reason each title fits.
   - Genre and topic chips based on the API's existing metadata.

3. **Library**
   - Searchable grid/list of the sample books.
   - Book detail drawer or route with summary, chapter summaries, genres, tags,
     and “ask about this book” action.

4. **How it works**
   - A compact pipeline visual: EPUB -> structure-aware chunks -> embeddings +
     hybrid retrieval -> cited answer.
   - A short explanation of the evaluation work already in this repository.
   - Links to the GitHub repository and an architecture/evaluation write-up.

5. **Project status**
   - A small, non-technical footer/card that says this is a public demo corpus
     and links to the source licenses. Do not expose ingestion controls or any
     personal-library paths on the public application.

## Technical shape

```text
Browser
  -> React + TypeScript UI on Cloudflare Pages
      -> public demo API on Render
          -> curated read-only corpus + retrieval/generation adapter

Personal local Librarian (unchanged)
  -> SQLite + OpenSearch + Ollama + private EPUBs
```

### Frontend

Use **React + TypeScript + Vite** in `apps/web/`. It is deliberately small,
quick to deploy as a static site, and pairs naturally with the FastAPI API. Use
React Router, plain CSS or Tailwind, and a thin typed `api.ts` client. Avoid a
large UI framework until the interaction model is proven.

The UI should call only a small public contract:

- `GET /books` for library and filters.
- `POST /search/hybrid` for evidence-first search.
- `POST /chat` for cited answers.
- `POST /recommendations` for discovery.
- `GET /books/{book_id}/genres` and the existing summary endpoint data for book
  detail.

Use a same-origin `/api` route; the production build
must never contain a local URL. Add CORS in FastAPI for the Pages production
domain and local Vite development origin.

### Demo API

Do not try to run the current Docker Compose stack unchanged on free hosting:
the deployed service would lose its local SQLite data whenever it sleeps or
restarts, and a hosted Ollama/OpenSearch stack is too resource-intensive for a
free portfolio demo.

Instead, introduce a **demo mode** with these properties:

- A checked-in, versioned JSON export of a small public-domain corpus's book
  metadata, summaries, citations, and precomputed example responses.
- Search and recommendation use precomputed results or a lightweight hosted
  retrieval service; no upload or ingestion endpoints are public.
- Chat either returns precomputed answers for curated prompts or uses a hosted
  provider behind rate limiting. Precomputed prompts are the best first launch:
  they are instant, cost-free, and let every answer visibly demonstrate
  citations.
- A request limit and input-length limit protect any live generation option.

This makes a real, interactive product demonstration while preserving the
local-first architecture as the project's main technical story.

## Free hosting plan

**Primary recommendation: Cloudflare Pages for the UI, Render Free for the
small demo API.** Cloudflare Pages has Git integration, preview deploys, and a
current $0 tier with unlimited static requests/bandwidth and 500 builds/month.
Render's free tier can run a Python web service, but it sleeps after 15 idle
minutes, can take about a minute to wake, and loses local files on restart.
That is why the API should be stateless and load its read-only demo data from
the repository at startup rather than depend on SQLite. [Cloudflare Pages
pricing](https://pages.cloudflare.com/) · [Render free-tier
limits](https://render.com/docs/free)

If a no-backend first version is preferred, deploy the Vite app alone to
Cloudflare Pages and ship a static `demo-data.json`. That is the fastest path to
a shareable portfolio URL; it exercises the exact visual and citation
interaction with zero runtime cost. GitHub Pages is also viable for a static
portfolio site, though its published-site guidance includes a 1 GB recommended
source limit and a 100 GB/month soft bandwidth limit. [GitHub Pages
limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits)

## Delivery plan

### Milestone 1 — Portfolio shell (about 1–2 focused sessions)

- Create `apps/web/` with TypeScript, Vite, routing, responsive layout, and a
  deploy workflow.
- Implement the Explore screen using deterministic `demo-data.json` responses.
- Add citation cards, library grid, sample prompts, and the “How it works”
  page.
- Deploy to Cloudflare Pages with a `*.pages.dev` URL; add that URL, screenshots,
  and an architecture summary to the repository README.

**Definition of done:** a recruiter can visit one URL, ask or choose a sample
question, receive an answer, open its sources, and understand the engineering
story without installing anything.

### Milestone 2 — Live API integration (about 1–2 focused sessions)

- Add the typed API client and loading/error/empty states.
- Add a public `demo` FastAPI configuration that disables ingestion and uses
  only public corpus data.
- Add CORS, basic rate limiting, health check, and a Render blueprint/deploy
  configuration.
- Switch the static UI to use the live API in production while keeping static
  fallback data for preview builds.

**Definition of done:** the deployed UI calls the live demo API and gracefully
explains its first-load delay if the free service is waking.

### Milestone 3 — Stronger product story (later)

- Add source-side-by-side reading, shareable query URLs, and accessible
  keyboard navigation.
- Add an evaluation page with retrieval precision, latency, and version
  metadata drawn from the existing evaluation reports.
- Add an optional "Run locally with your own EPUBs" path that points people to
  the Docker/Ollama setup, clearly separated from the hosted demo.

## Portfolio framing

Use a plain claim such as:

> Librarian is a local-first RAG system for EPUB collections. This public demo
> uses a rights-safe sample corpus to show hybrid retrieval, grounded answers,
> source citations, and evaluation-oriented AI engineering.

Link to the live demo first, then the repository. Add three concise proof
points: local-first ingestion, citation-backed retrieval, and deterministic
evaluation. A short GIF showing question -> answer -> opened citation will do
more on a résumé/project page than a long feature list.

## Decisions to make before implementation

1. Pick the demo corpus (three to eight public-domain or explicitly licensed
   EPUBs; Project Gutenberg is a likely source, subject to each title's rights
   and license).
2. Decide whether v1 should be entirely deterministic/static (recommended) or
   include a live generated-answer endpoint.
3. Choose whether the public demo lives in this repository under `apps/web/` or
   in a separate public `librarian-demo` repository. Keeping it here better
   demonstrates full-stack cohesion; a separate repository gives the portfolio
   UI a cleaner, smaller codebase.
