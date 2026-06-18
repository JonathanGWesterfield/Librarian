# Evaluation Strategy

Librarian needs empirical evaluation before retrieval or generation changes can
be trusted. The goal is to compare changes such as hybrid retrieval, different
embedding models, local LLMs, Codex broker generation, richer metadata, and
reranking with repeatable evidence instead of subjective impressions.

## Evaluation Layers

### Retrieval Evaluation

Retrieval evaluation asks whether Librarian found the right evidence before any
answer is generated.

Useful metrics:

- `Hit@K`: at least one expected relevant chunk/book appears in the top `K`.
- `Recall@K`: how much known relevant evidence appears in the top `K`.
- `Precision@K`: how much of the top `K` is relevant.
- `MRR`: mean reciprocal rank, rewarding the first relevant result appearing
  near the top.
- `nDCG`: rewards ranking highly relevant chunks above mildly relevant chunks.

This layer is the best place to measure embedding model changes, chunking
changes, metadata filters, hybrid search, and reranking.

### Answer Quality Evaluation

Answer evaluation asks whether the generated response is useful and grounded in
retrieved sources.

Useful rubric dimensions:

- `Correctness`: the answer is factually right.
- `Completeness`: the answer covers the important expected points.
- `Groundedness`: claims are supported by retrieved chunks.
- `Citation accuracy`: cited chunks actually support the claims attached to
  them.
- `Faithfulness`: the answer does not add unsupported information.
- `Usefulness`: the answer is clear, concise, and helpful for the user.

### End-to-End Evaluation

End-to-end evaluation asks whether the full system solved the user task. This is
the most realistic test, but it mixes retrieval and generation quality. Use it
as a product health signal, not as the only debugging tool.

Example checks for a question like "How brutal and terrible is war?":

- Relevant war passages are retrieved.
- The answer synthesizes the passages instead of listing snippets.
- Claims are cited.
- Citations point to supporting chunks.
- The answer avoids broad claims not supported by the local library context.

## Benchmark Dataset

Create a small golden dataset of evaluation cases. Each case should contain
enough information to score retrieval and answer quality separately.

Example shape:

```json
{
  "id": "war-brutality",
  "query": "How brutal and terrible is war?",
  "expected_books": ["All Quiet on the Western Front"],
  "expected_topics": ["fear", "death", "trauma", "dehumanization"],
  "ideal_answer_notes": [
    "War is physically brutal",
    "War destroys innocence",
    "Soldiers are psychologically damaged"
  ],
  "must_cite": true
}
```

Include a mix of:

- Specific factual questions.
- Broad thematic questions.
- Recommendation questions.
- Author-scoped questions.
- Negative/insufficient-evidence questions.

## Human-Graded Evaluation

Human grading is the most trustworthy early signal. Use a simple 1-5 rubric:

- `5`: excellent, grounded, complete, and strongly cited.
- `4`: good, with minor missing nuance.
- `3`: partially useful but incomplete or weakly cited.
- `2`: weak, shallow, or poorly grounded.
- `1`: wrong, unsupported, or misleading.

Use human grading to calibrate automated judging.

## LLM-as-Judge Evaluation

An evaluator model can score answers against the query, expected answer notes,
and retrieved source chunks.

Benefits:

- Fast enough for repeated experiments.
- Useful for comparing many configurations.
- Can score multiple rubric dimensions consistently.

Risks:

- May reward fluent but unsupported answers.
- May have bias toward longer answers.
- Needs calibration against human scores.

For Librarian, prefer local evaluation first when possible, with Codex/OpenAI as
an optional evaluator for higher-quality offline reports.

## Pairwise Evaluation

Pairwise evaluation compares two system outputs for the same query:

- Baseline vector search vs hybrid retrieval.
- Local LLM answer vs Codex broker answer.
- Old chunker vs improved chunker.

Pairwise judgments are often easier and more reliable than absolute scores:
"Which answer is more grounded, complete, and useful?"

## Regression Evaluation

Regression evaluation keeps a benchmark suite stable over time and records
metrics for each run.

Track at least:

- Retrieval metrics such as `Hit@K`, `Recall@K`, `MRR`, and `nDCG`.
- Answer rubric scores.
- Citation accuracy.
- Latency.
- Retrieved chunk count.
- Embedding provider/model.
- Generation provider/model.
- Git commit SHA.

Store results as JSON or CSV so runs can be compared over time.

## Recommended First Implementation

Start with three tracks:

1. Retrieval benchmark: query to expected book/chunk/topic, scored with
   `Hit@K`, `Recall@K`, and rank.
2. Answer rubric benchmark: query to expected answer notes, scored for
   correctness, groundedness, citation accuracy, completeness, and usefulness.
3. Comparison reports: save JSON/CSV outputs for baseline vs changed runs.

Keep retrieval evaluation separate from answer evaluation. If an answer gets
worse, we need to know whether retrieval failed, generation failed, or both.

## North Star Report

Every evaluation metric should eventually roll up into one report that can be
read at a glance. The report should show overall quality, break down retrieval
quality separately from answer quality, and highlight the weakest areas to
improve next.

The report should answer:

- Are relevant books or chunks appearing in the top results?
- Are the best results ranked near the top?
- Are generated answers correct, grounded, complete, and cited?
- Which benchmark cases regressed?
- Which provider, model, chunker, and retrieval settings produced the run?
- How much latency did the configuration add?

This makes evaluation useful for engineering decisions. A change such as hybrid
retrieval, a new embedding model, richer metadata, or a different generator
should produce a comparable report rather than a vague impression.

The current committed retrieval reports live at
`docs/evaluation-retrieval-report.json` for machine-readable output and
`docs/evaluation-report.md` for human review. Regenerate both with:

```bash
python3 scripts/evaluate_retrieval.py
```

CI runs `python3 scripts/evaluate_retrieval.py --check` so pull requests fail
when the committed report is stale.

GitHub Actions also appends the report to the PR Checks summary with dynamic
run metadata. That summary includes elapsed time, git commit, branch, and dirty
state. These fields are intentionally excluded from the committed smoke report
files so the checked-in reports remain deterministic across commits.

Live golden-corpus reports are generated locally from the ingested SQLite
database and live query embeddings. They are written separately so CI can keep
using the deterministic smoke report:

```bash
python3 scripts/evaluate_retrieval.py --live \
  --database-url sqlite:///data/librarian.db \
  --embedding-provider ollama \
  --embedding-model all-minilm
```

The live machine-readable report is written to
`docs/evaluation-live-retrieval-report.json`; the live human-readable report is
written to `docs/evaluation-live-report.md`.

Live reports include run metadata by default. The `Run Metadata` section records
elapsed report time and git metadata, while the live embedding and answer
sections include total, mean, and max latency for search and answer generation.

To include generated answer quality from the live chat stack, add
`--live-answers` and generation settings:

```bash
python3 scripts/evaluate_retrieval.py --live --live-answers \
  --database-url sqlite:///data/librarian.db \
  --embedding-provider ollama \
  --embedding-model all-minilm \
  --generation-provider ollama \
  --generation-model llama3.2:3b \
  --retrieval-limit 30
```

The same live report files are updated. The Markdown report includes an
`Answer Generation` section with the generation provider, generation model,
retrieval limit, evaluated question count, and source count before the answer
quality metrics.

The first real-library benchmark lives at
`tests/fixtures/evaluation/golden_retrieval_corpus.json`. It is book-level on
purpose: each case names expected EPUB filenames from the local library without
committing the books or hand-labeling exact chunks. Live retrieval report
generation uses this corpus against an ingested local database. Individual
cases can later be upgraded from book-level labels to chunk-level labels as we
inspect retrieved passages.

The first answer-quality benchmark lives at
`tests/fixtures/evaluation/answer_quality_benchmark.json`. It is deterministic
and heuristic-based: it checks expected concepts, source citation validity,
whether cited sources support covered concepts, and whether insufficient
evidence answers refuse correctly. This is not a replacement for human review
or an LLM-as-judge pass, but it gives us a stable first regression signal for
generated answers.

The first live answer-quality corpus lives at
`tests/fixtures/evaluation/golden_answer_quality_corpus.json`. It contains
questions, expected concepts, citation expectations, and refusal expectations,
but no generated answers. Live report generation sends those questions through
the current retrieval and chat stack, then scores the generated answers against
the same deterministic answer-quality rubric.
