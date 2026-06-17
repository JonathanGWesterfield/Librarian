# Librarian Evaluation Report

## Overview

3 retrieval cases evaluated. Hit@5 is 67%, Recall@5 is 67%, and MRR is 50%.

- Overall retrieval score: `0.6111`
- Primary K: `5`
- Active benchmark: `deterministic-retrieval-smoke`
- Benchmark mode: `static_ranked_results`

## Embeddings

| Metric | Value |
| --- | --- |
| Live embedding evaluation | Not measured in this smoke report |
| Embedding provider | Not available until live retrieval is run |
| Embedding model | Not available until live retrieval is run |
| What this section should answer | Whether embedding model changes improve retrieval quality |

This section is intentionally a placeholder until the report runner is wired
to execute live search against the local SQLite database. Once live
retrieval runs, this section should list provider, model, dimensions,
embedding count, and retrieval deltas by model.

## Golden Corpus

| Metric | Value |
| --- | --- |
| Corpus name | `golden-library-retrieval` |
| Corpus mode | `live_search_expected_books` |
| Label granularity | `book` |
| Query cases | `20` |
| Expected book labels | `31` |
| Primary K | `10` |

The golden corpus is the real-library benchmark. It is currently
book-level and is not yet the source of the committed smoke report.
Once live retrieval is wired in, this section should become the main
retrieval quality signal.

### Golden Corpus Cases

| Case | Expected Books |
| --- | ---: |
| `war-brutality-all-quiet` | `1` |
| `epic-fall-rebellion-paradise-lost` | `1` |
| `psychohistory-foundation` | `1` |
| `robotics-three-laws-asimov` | `4` |
| `machine-learning-systems` | `1` |
| `cyberpunk-ai-neuromancer` | `1` |
| `dune-politics-religion-ecology` | `2` |
| `wizard-school-earthsea` | `1` |
| `gender-society-left-hand` | `1` |
| `theocratic-dystopia-handmaids-tale` | `1` |
| `witcher-monsters-destiny` | `7` |
| `negotiation-tactical-empathy` | `1` |
| `political-power-prince` | `1` |
| `justice-ideal-state-republic` | `1` |
| `spiritual-despair-kierkegaard` | `1` |
| `beauty-portrait-moral-corruption` | `1` |
| `japanese-feudal-politics-shogun` | `1` |
| `motorcycle-maintenance-quality` | `1` |
| `survival-wilderness-dog` | `1` |
| `cambodia-khmer-rouge` | `2` |

## Retrieval Metrics

| Metric | Value |
| --- | --- |
| Case count | `3` |
| Hit@5 | `0.6667` |
| Precision@5 | `0.1333` |
| Recall@5 | `0.6667` |
| Mean reciprocal rank | `0.5000` |

### Improvement Areas

- Candidate generation: some benchmark queries do not retrieve relevant evidence in the top 5.
- Coverage: relevant evidence is missing from the top 5; improve chunking, metadata filters, or hybrid retrieval.
- Noise: fewer than half of the top 5 results are relevant on average; improve filtering or reranking.
- Ranking: relevant evidence is not consistently near rank 1; reranking is likely the next useful lever.

### Weakest Cases

| Case | Hit@5 | Recall@5 | MRR | Reason |
| --- | ---: | ---: | ---: | --- |
| `missing-evidence` | `False` | `0.0000` | `0.0000` | No relevant evidence appeared in the top 5. |
| `clockwork-garden` | `True` | `1.0000` | `0.5000` | Relevant evidence appeared, but not at rank 1. |

### Retrieval Cases

| Case | Results | Relevant Results | Hit@5 | Precision@5 | Recall@5 | MRR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `war-brutality` | `2` | `1` | `True` | `0.2000` | `1.0000` | `1.0000` |
| `clockwork-garden` | `2` | `1` | `True` | `0.2000` | `1.0000` | `0.5000` |
| `missing-evidence` | `1` | `0` | `False` | `0.0000` | `0.0000` | `0.0000` |

## Report Freshness

GitHub Actions runs `scripts/check.sh`, which validates that the
committed JSON and Markdown reports match the current evaluation
fixture data.
