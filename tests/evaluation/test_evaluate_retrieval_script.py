import importlib.util
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES_DIR = REPO_ROOT / "packages"
sys.path.insert(0, str(PACKAGES_DIR))

from librarian_chat.chat import ChatResponse, ChatSource
from librarian_search.search import SearchResponse, SearchResult

SCRIPT_PATH = REPO_ROOT / "scripts/evaluate_retrieval.py"


class EvaluateRetrievalScriptTests(unittest.TestCase):
    def test_generate_live_report_document_scores_golden_corpus_with_search_results(
        self,
    ) -> None:
        """Verify live mode scores real search results against corpus labels.
        The golden corpus has expected EPUB filenames, while live search
        returns ranked chunks. This test proves the report bridges those two
        shapes without needing Ollama or a local SQLite database in CI.
        """
        module = _load_script_module()
        with TemporaryDirectory() as temp_dir:
            corpus_path = Path(temp_dir) / "golden.json"
            corpus_path.write_text(
                json.dumps(
                    {
                        "benchmark": {
                            "name": "unit-golden",
                            "mode": "live_search_expected_books",
                        },
                        "k_values": [1, 2],
                        "primary_k": 2,
                        "cases": [
                            {
                                "id": "war",
                                "query": "war brutality",
                                "relevant_relative_paths": ["all-quiet.epub"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            document = module.generate_live_report_document(
                corpus_path,
                database_url="sqlite:///tmp/librarian.db",
                embedding_provider="ollama",
                embedding_model="all-minilm",
                limit=2,
                search_fn=_fake_search,
            )

        self.assertEqual(document["benchmark"]["mode"], "live_search")
        self.assertEqual(document["run"]["mode"], "live_search")
        self.assertEqual(document["run"]["embedding_provider"], "ollama")
        self.assertEqual(document["run"]["embedding_model"], "all-minilm")
        self.assertEqual(document["run"]["embedding_dimensions"], 2)
        self.assertEqual(document["retrieval"]["aggregate"]["case_count"], 1)
        self.assertEqual(document["retrieval"]["aggregate"]["hit_rate_at_k"][1], 1.0)
        self.assertEqual(document["retrieval"]["aggregate"]["mean_recall_at_k"][2], 1.0)

    def test_generate_live_report_document_can_score_live_chat_answers(
        self,
    ) -> None:
        """Verify live answer mode evaluates generated chat responses.
        The answer corpus contains only questions and expected terms; the
        script must call the chat layer, convert sources into evaluator input,
        and record generation metadata for the human-readable report.
        """
        module = _load_script_module()
        with TemporaryDirectory() as temp_dir:
            retrieval_corpus_path = Path(temp_dir) / "golden-retrieval.json"
            retrieval_corpus_path.write_text(
                json.dumps(
                    {
                        "benchmark": {
                            "name": "unit-golden",
                            "mode": "live_search_expected_books",
                        },
                        "k_values": [1],
                        "primary_k": 1,
                        "cases": [
                            {
                                "id": "war",
                                "query": "war brutality",
                                "relevant_relative_paths": ["all-quiet.epub"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            answer_corpus_path = Path(temp_dir) / "golden-answers.json"
            answer_corpus_path.write_text(
                json.dumps(
                    {
                        "benchmark": {
                            "name": "unit-answer-golden",
                            "mode": "live_chat_expected_terms",
                        },
                        "cases": [
                            {
                                "id": "war-answer",
                                "question": "How brutal and terrible is war?",
                                "expected_terms": ["fear", "death", "trauma"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            document = module.generate_live_report_document(
                retrieval_corpus_path,
                live_answer_corpus_path=answer_corpus_path,
                live_answers=True,
                database_url="sqlite:///tmp/librarian.db",
                embedding_provider="ollama",
                embedding_model="all-minilm",
                generation_provider="noop",
                generation_model="deterministic",
                limit=1,
                retrieval_limit=3,
                search_fn=_fake_search,
                answer_fn=_fake_answer,
            )

        answer_quality = document["answer_quality"]
        self.assertEqual(answer_quality["aggregate"]["case_count"], 1)
        self.assertEqual(answer_quality["aggregate"]["mean_overall_score"], 1.0)
        self.assertEqual(document["run"]["answer_quality"]["mode"], "live_chat")
        self.assertEqual(
            document["run"]["answer_quality"]["generation_provider"],
            "noop",
        )
        self.assertEqual(document["run"]["answer_quality"]["retrieval_limit"], 3)
        self.assertEqual(document["run"]["answer_quality"]["total_sources_returned"], 1)


def _fake_search(_options) -> SearchResponse:
    return SearchResponse(
        query="war brutality",
        embedding_provider="ollama",
        embedding_model="all-minilm",
        dimensions=2,
        candidate_count=12,
        results=[
            SearchResult(
                score=0.9,
                chunk_id="all-quiet:0",
                book_id="all-quiet",
                relative_path="all-quiet.epub",
                title="All Quiet",
                authors=["Erich Maria Remarque"],
                publisher=None,
                chunk_index=0,
                text="War is brutal.",
                embedding_provider="ollama",
                embedding_model="all-minilm",
                dimensions=2,
            )
        ],
    )


def _fake_answer(options) -> ChatResponse:
    return ChatResponse(
        question=options.question,
        answer="The passages describe war through fear, death, and trauma [S1].",
        embedding_provider=options.embedding_provider or "ollama",
        embedding_model=options.embedding_model or "all-minilm",
        generation_provider=options.generation_provider or "noop",
        generation_model=options.generation_model or "deterministic",
        retrieval_limit=options.retrieval_limit,
        candidate_count=9,
        sources=[
            ChatSource(
                source_id="S1",
                score=0.9,
                chunk_id="all-quiet:0",
                book_id="all-quiet",
                relative_path="all-quiet.epub",
                title="All Quiet",
                authors=["Erich Maria Remarque"],
                chunk_index=0,
                text="The soldiers live with fear, death, and trauma at the front.",
            )
        ],
    )


def _load_script_module():
    spec = importlib.util.spec_from_file_location(
        "evaluate_retrieval_script",
        SCRIPT_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    unittest.main()
