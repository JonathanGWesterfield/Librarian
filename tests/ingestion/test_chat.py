import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from time import sleep
from unittest.mock import patch

REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]
PACKAGES_DIR = REPO_ROOT / "packages"
sys.path.insert(0, str(PACKAGES_DIR))

from librarian_chat.chat import (
    ChatOptions,
    answer_question,
    prepare_answer_question,
    stream_answer_question,
)
from librarian_chat.generation import GenerationError
from librarian_ingestion.embedding_ops import EmbedQueryResult
from librarian_search.opensearch import OpenSearchError
from librarian_search.search import SearchResponse, SearchResult
from librarian_storage.storage import BookRecord, SQLiteIngestionStore, utc_now


class ChatTests(unittest.TestCase):
    def test_streamed_chat_reuses_prepared_evidence_and_emits_extractive_tokens(self) -> None:
        """Streaming reuses retrieval and never lets native fragments alter a claim."""
        question = "How brutal is war?"
        generator = _FakeStreamingGenerator(
            ["The front is a cage ", "in which we must await fearfully."]
        )
        with (
            patch("librarian_chat.chat.embed_query", return_value=_query_embedding()) as embed,
            patch("librarian_chat.chat.resolve_chat_retrieval_backend", return_value="sqlite"),
            patch("librarian_chat.chat.search_chunks", return_value=_search_response()) as search,
            patch("librarian_chat.chat.create_configured_generator", return_value=generator),
        ):
            preparation = prepare_answer_question(
                ChatOptions(
                    question=question,
                    database_url="sqlite:///tmp/librarian.db",
                    embedding_provider="ollama",
                    embedding_model="all-minilm",
                    generation_provider="ollama",
                    generation_model="qwen2.5:7b",
                    answer_capability="quality",
                )
            )
            events = list(stream_answer_question(preparation))

        self.assertEqual([event.event for event in events], ["retrieval", "token", "complete"])
        self.assertEqual(events[0].data["sources"][0]["source_id"], "S1")
        self.assertEqual(
            events[1].data,
            {"text": "War is brutal and terrifying at the front. [S1]"},
        )
        self.assertEqual(
            events[-1].data["answer"],
            "War is brutal and terrifying at the front. [S1]",
        )
        self.assertIsNotNone(events[-1].data["timings"]["time_to_first_token_seconds"])
        self.assertEqual(embed.call_count, 1)
        self.assertEqual(search.call_count, 1)
        self.assertEqual(generator.generate_calls, 0)

    def test_streamed_insufficiency_never_exposes_diagnostic_citations(self) -> None:
        """The retrieval event and completion both stay citation-free after a guard refusal."""
        question = "Who opens the garden gate?"
        generator = _FakeStreamingGenerator(["This must not run."])
        with (
            patch("librarian_chat.chat.embed_query", return_value=_query_embedding_for(question)),
            patch("librarian_chat.chat.resolve_chat_retrieval_backend", return_value="sqlite"),
            patch(
                "librarian_chat.chat.search_chunks",
                return_value=_chat_search_response(question, text="A brass robin counted three silver seeds."),
            ),
            patch("librarian_chat.chat.create_configured_generator", return_value=generator),
        ):
            events = list(
                stream_answer_question(
                    prepare_answer_question(
                        ChatOptions(
                            question=question,
                            database_url="sqlite:///tmp/librarian.db",
                            embedding_provider="ollama",
                            embedding_model="all-minilm",
                            generation_provider="ollama",
                            generation_model="qwen2.5:1.5b",
                            answer_capability="lightweight",
                        )
                    )
                )
            )

        self.assertEqual([event.event for event in events], ["retrieval", "complete"])
        self.assertEqual(events[0].data["sources"], [])
        self.assertEqual(events[-1].data["sources"], [])
        self.assertIn("enough relevant body-text evidence", events[-1].data["answer"])
        self.assertEqual(generator.generate_calls, 0)

    def test_event_question_includes_relevant_source_context_without_speculation(self) -> None:
        """The UAT garden event gets its adjacent outcome, not a model inference."""
        question = "What happened when Mara opened the garden gate?"
        source_text = (
            "Mara opened the gate with a borrowed key. "
            "The clockwork garden answered in careful ticking."
        )
        generator = _FakeStreamingGenerator(
            [
                "Mara's action was motivated by the garden's ticking. ",
                "The garden responded to her presence.",
            ]
        )
        with (
            patch("librarian_chat.chat.embed_query", return_value=_query_embedding_for(question)),
            patch("librarian_chat.chat.resolve_chat_retrieval_backend", return_value="sqlite"),
            patch(
                "librarian_chat.chat.search_chunks",
                return_value=_chat_search_response(question, text=source_text),
            ),
            patch("librarian_chat.chat.create_configured_generator", return_value=generator),
        ):
            options = ChatOptions(
                question=question,
                database_url="sqlite:///tmp/librarian.db",
                embedding_provider="ollama",
                embedding_model="all-minilm",
                generation_provider="ollama",
                generation_model="qwen2.5:7b",
                answer_capability="quality",
            )
            response = answer_question(options)
            events = list(
                stream_answer_question(
                    prepare_answer_question(options)
                )
            )

        emitted_text = "".join(event.data["text"] for event in events if event.event == "token")
        expected = (
            "Mara opened the gate with a borrowed key. [S1]\n\n"
            "The clockwork garden answered in careful ticking. [S1]"
        )
        self.assertEqual(
            [event.event for event in events],
            ["retrieval", "token", "token", "complete"],
        )
        self.assertEqual(emitted_text, expected)
        self.assertEqual(response.answer, expected)
        self.assertNotIn("motivated", emitted_text.casefold())
        self.assertNotIn("presence", emitted_text.casefold())
        self.assertEqual(events[-1].data["answer"], emitted_text)
        self.assertEqual(events[-1].data["sources"][0]["source_id"], "S1")
        self.assertEqual(generator.messages, [])

    def test_event_context_rule_skips_an_unrelated_next_sentence(self) -> None:
        """Sentence adjacency alone must not drag unrelated prose into an answer."""
        question = "What happened when Mara opened the garden gate?"
        source_text = (
            "Mara opened the garden gate with a borrowed key. "
            "A brass robin counted three silver seeds."
        )
        generator = _FakeGenerator()
        with (
            patch("librarian_chat.chat.embed_query", return_value=_query_embedding_for(question)),
            patch("librarian_chat.chat.resolve_chat_retrieval_backend", return_value="sqlite"),
            patch(
                "librarian_chat.chat.search_chunks",
                return_value=_chat_search_response(question, text=source_text),
            ),
            patch("librarian_chat.chat.create_configured_generator", return_value=generator),
        ):
            response = answer_question(
                ChatOptions(
                    question=question,
                    database_url="sqlite:///tmp/librarian.db",
                    embedding_provider="ollama",
                    embedding_model="all-minilm",
                    generation_provider="ollama",
                    generation_model="qwen2.5:7b",
                    answer_capability="quality",
                )
            )

        self.assertEqual(
            response.answer,
            "Mara opened the garden gate with a borrowed key. [S1]",
        )
        self.assertNotIn("brass robin", response.answer.casefold())
        self.assertEqual(generator.messages, [])

    def test_json_quality_answer_preserves_a_source_negation(self) -> None:
        """A model cannot turn a cited denial into its positive opposite."""
        question = "Did Mara open the garden gate?"
        generator = _FakeGenerator()
        with (
            patch("librarian_chat.chat.embed_query", return_value=_query_embedding_for(question)),
            patch("librarian_chat.chat.resolve_chat_retrieval_backend", return_value="sqlite"),
            patch(
                "librarian_chat.chat.search_chunks",
                return_value=_chat_search_response(
                    question,
                    text="Mara did not open the garden gate; Theo opened it instead.",
                ),
            ),
            patch("librarian_chat.chat.create_configured_generator", return_value=generator),
        ):
            response = answer_question(
                ChatOptions(
                    question=question,
                    database_url="sqlite:///tmp/librarian.db",
                    embedding_provider="ollama",
                    embedding_model="all-minilm",
                    generation_provider="ollama",
                    generation_model="qwen2.5:7b",
                    answer_capability="quality",
                )
            )

        self.assertEqual(
            response.answer,
            "Mara did not open the garden gate; Theo opened it instead. [S1]",
        )
        self.assertEqual(generator.messages, [])

    def test_stream_quality_answer_preserves_subject_object_relationships(self) -> None:
        """A reversed relationship cannot pass merely because its words overlap."""
        question = "Who followed Theo through the garden gate?"
        generator = _FakeStreamingGenerator(["Theo followed Mara through the garden gate."])
        with (
            patch("librarian_chat.chat.embed_query", return_value=_query_embedding_for(question)),
            patch("librarian_chat.chat.resolve_chat_retrieval_backend", return_value="sqlite"),
            patch(
                "librarian_chat.chat.search_chunks",
                return_value=_chat_search_response(
                    question,
                    text="Mara followed Theo through the garden gate.",
                ),
            ),
            patch("librarian_chat.chat.create_configured_generator", return_value=generator),
        ):
            events = list(
                stream_answer_question(
                    prepare_answer_question(
                        ChatOptions(
                            question=question,
                            database_url="sqlite:///tmp/librarian.db",
                            embedding_provider="ollama",
                            embedding_model="all-minilm",
                            generation_provider="ollama",
                            generation_model="qwen2.5:7b",
                            answer_capability="quality",
                        )
                    )
                )
            )

        self.assertEqual([event.event for event in events], ["retrieval", "token", "complete"])
        self.assertEqual(
            events[1].data["text"],
            "Mara followed Theo through the garden gate. [S1]",
        )
        self.assertNotIn("Theo followed Mara", events[-1].data["answer"])
        self.assertEqual(generator.messages, [])

    def test_json_quality_answer_does_not_invent_causality(self) -> None:
        """Temporal source text cannot become a causal model conclusion."""
        question = "Why did the garden tick after Mara left?"
        generator = _FakeGenerator()
        with (
            patch("librarian_chat.chat.embed_query", return_value=_query_embedding_for(question)),
            patch("librarian_chat.chat.resolve_chat_retrieval_backend", return_value="sqlite"),
            patch(
                "librarian_chat.chat.search_chunks",
                return_value=_chat_search_response(
                    question,
                    text="The garden ticked after Mara left.",
                ),
            ),
            patch("librarian_chat.chat.create_configured_generator", return_value=generator),
        ):
            response = answer_question(
                ChatOptions(
                    question=question,
                    database_url="sqlite:///tmp/librarian.db",
                    embedding_provider="ollama",
                    embedding_model="all-minilm",
                    generation_provider="ollama",
                    generation_model="qwen2.5:7b",
                    answer_capability="quality",
                )
            )

        self.assertEqual(response.answer, "The garden ticked after Mara left. [S1]")
        self.assertNotIn("because", response.answer.casefold())
        self.assertEqual(generator.messages, [])

    def test_quality_stream_exposes_retrieval_and_answer_without_waiting_for_a_model(self) -> None:
        """Useful source progress and source text do not wait for an invalid model answer."""
        question = "Who opens the garden gate?"
        generator = _DelayedStreamingGenerator(
            ["The garden loves Mara."], delay_seconds=0.08
        )
        with (
            patch("librarian_chat.chat.embed_query", return_value=_query_embedding_for(question)),
            patch("librarian_chat.chat.resolve_chat_retrieval_backend", return_value="sqlite"),
            patch(
                "librarian_chat.chat.search_chunks",
                return_value=_chat_search_response(
                    question,
                    text="Mara opened the garden gate with a borrowed key.",
                ),
            ),
            patch("librarian_chat.chat.create_configured_generator", return_value=generator),
        ):
            events = stream_answer_question(
                prepare_answer_question(
                    ChatOptions(
                        question=question,
                        database_url="sqlite:///tmp/librarian.db",
                        embedding_provider="ollama",
                        embedding_model="all-minilm",
                        generation_provider="ollama",
                        generation_model="qwen2.5:7b",
                        answer_capability="quality",
                    )
                )
            )
            retrieval = next(events)
            self.assertEqual(generator.stream_calls, 0)
            remaining_events = list(events)

        self.assertEqual(retrieval.event, "retrieval")
        self.assertEqual(retrieval.data["sources"][0]["source_id"], "S1")
        self.assertEqual(generator.stream_calls, 0)
        completion = remaining_events[-1]
        self.assertEqual([event.event for event in remaining_events], ["token", "complete"])
        self.assertEqual(
            completion.data["answer"],
            "Mara opened the garden gate with a borrowed key. [S1]",
        )
        self.assertLess(
            retrieval.data["timings"]["time_to_first_event_seconds"],
            0.04,
        )
        self.assertIsNotNone(completion.data["timings"]["time_to_first_token_seconds"])
        self.assertLess(completion.data["timings"]["total_seconds"], 0.04)

    def test_quality_stream_emits_the_exact_source_sentence_early(self) -> None:
        """Streaming preserves the source wording instead of an inflected rewrite."""
        question = "Who opens the garden gate?"
        source_text = "Mara opened the garden gate with a borrowed key."
        generator = _FakeStreamingGenerator(
            ["Mara opens the garden ", "gate with a borrowed key."]
        )
        with (
            patch("librarian_chat.chat.embed_query", return_value=_query_embedding_for(question)),
            patch("librarian_chat.chat.resolve_chat_retrieval_backend", return_value="sqlite"),
            patch(
                "librarian_chat.chat.search_chunks",
                return_value=_chat_search_response(question, text=source_text),
            ),
            patch("librarian_chat.chat.create_configured_generator", return_value=generator),
        ):
            events = list(
                stream_answer_question(
                    prepare_answer_question(
                        ChatOptions(
                            question=question,
                            database_url="sqlite:///tmp/librarian.db",
                            embedding_provider="ollama",
                            embedding_model="all-minilm",
                            generation_provider="ollama",
                            generation_model="qwen2.5:7b",
                            answer_capability="quality",
                        )
                    )
                )
            )

        self.assertEqual([event.event for event in events], ["retrieval", "token", "complete"])
        self.assertEqual(
            events[1].data["text"],
            "Mara opened the garden gate with a borrowed key. [S1]",
        )
        self.assertEqual(events[-1].data["answer"], events[1].data["text"])
        self.assertIsNotNone(events[-1].data["timings"]["time_to_first_token_seconds"])

    def test_quality_stream_does_not_consume_model_citation_fragments(self) -> None:
        """The service owns citations and does not trust a model-provided source ID."""
        question = "Who opens the garden gate?"
        source_text = "Mara opened the garden gate with a borrowed key."
        generator = _FakeStreamingGenerator(
            ["Mara opened the garden gate with a borrowed key.", " [S1]"]
        )
        with (
            patch("librarian_chat.chat.embed_query", return_value=_query_embedding_for(question)),
            patch("librarian_chat.chat.resolve_chat_retrieval_backend", return_value="sqlite"),
            patch(
                "librarian_chat.chat.search_chunks",
                return_value=_chat_search_response(question, text=source_text),
            ),
            patch("librarian_chat.chat.create_configured_generator", return_value=generator),
        ):
            events = list(
                stream_answer_question(
                    prepare_answer_question(
                        ChatOptions(
                            question=question,
                            database_url="sqlite:///tmp/librarian.db",
                            embedding_provider="ollama",
                            embedding_model="all-minilm",
                            generation_provider="ollama",
                            generation_model="qwen2.5:7b",
                            answer_capability="quality",
                        )
                    )
                )
            )

        self.assertEqual([event.event for event in events], ["retrieval", "token", "complete"])
        expected = "Mara opened the garden gate with a borrowed key. [S1]"
        self.assertEqual(events[1].data["text"], expected)
        self.assertEqual(events[-1].data["answer"], expected)

    def test_quality_stream_uses_only_the_exact_relevant_source_sentence(self) -> None:
        """A narrow question does not add unrelated model-selected passages."""
        question = "Who opens the garden gate?"
        generator = _FakeStreamingGenerator(
            [
                "Mara opens the garden gate with a borrowed key. [S1] The garden ",
                "answers in careful ticking. [S2]",
            ]
        )
        with (
            patch("librarian_chat.chat.embed_query", return_value=_query_embedding_for(question)),
            patch("librarian_chat.chat.resolve_chat_retrieval_backend", return_value="sqlite"),
            patch(
                "librarian_chat.chat.search_chunks",
                return_value=_two_source_chat_search_response(question),
            ),
            patch("librarian_chat.chat.create_configured_generator", return_value=generator),
        ):
            events = list(
                stream_answer_question(
                    prepare_answer_question(
                        ChatOptions(
                            question=question,
                            database_url="sqlite:///tmp/librarian.db",
                            embedding_provider="ollama",
                            embedding_model="all-minilm",
                            generation_provider="ollama",
                            generation_model="qwen2.5:7b",
                            answer_capability="quality",
                        )
                    )
                )
            )

        expected_tokens = ["Mara opened the garden gate with a borrowed key. [S1]"]
        self.assertEqual(
            [event.event for event in events],
            ["retrieval", "token", "complete"],
        )
        self.assertEqual(
            [event.data["text"] for event in events if event.event == "token"],
            expected_tokens,
        )
        self.assertEqual(events[-1].data["answer"], "".join(expected_tokens))

    def test_later_unsupported_sentence_keeps_completion_equal_to_visible_safe_text(self) -> None:
        """Never append a fallback after already streaming a verified sentence."""
        question = "Who opens the garden gate?"
        source_text = "Mara opened the garden gate with a borrowed key."
        generator = _FakeStreamingGenerator(
            [
                "Mara opens the garden gate with a borrowed key. "
                "The garden loves Mara."
            ]
        )
        with (
            patch("librarian_chat.chat.embed_query", return_value=_query_embedding_for(question)),
            patch("librarian_chat.chat.resolve_chat_retrieval_backend", return_value="sqlite"),
            patch(
                "librarian_chat.chat.search_chunks",
                return_value=_chat_search_response(question, text=source_text),
            ),
            patch("librarian_chat.chat.create_configured_generator", return_value=generator),
        ):
            events = list(
                stream_answer_question(
                    prepare_answer_question(
                        ChatOptions(
                            question=question,
                            database_url="sqlite:///tmp/librarian.db",
                            embedding_provider="ollama",
                            embedding_model="all-minilm",
                            generation_provider="ollama",
                            generation_model="qwen2.5:7b",
                            answer_capability="quality",
                        )
                    )
                )
            )

        self.assertEqual([event.event for event in events], ["retrieval", "token", "complete"])
        self.assertEqual(events[-1].data["answer"], events[1].data["text"])
        self.assertNotIn("loves", events[-1].data["answer"])

    def test_irrelevant_quality_stream_keeps_terminal_refusal_citation_free(self) -> None:
        """Irrelevant retrieval candidates never become evidence for a model claim."""
        question = "Who opens the garden gate?"
        generator = _FakeStreamingGenerator(["The garden loves Mara."])
        with (
            patch("librarian_chat.chat.embed_query", return_value=_query_embedding_for(question)),
            patch("librarian_chat.chat.resolve_chat_retrieval_backend", return_value="sqlite"),
            patch(
                "librarian_chat.chat.search_chunks",
                return_value=_chat_search_response(
                    question,
                    text="A brass robin counted three silver seeds.",
                ),
            ),
            patch("librarian_chat.chat.create_configured_generator", return_value=generator),
        ):
            events = list(
                stream_answer_question(
                    prepare_answer_question(
                        ChatOptions(
                            question=question,
                            database_url="sqlite:///tmp/librarian.db",
                            embedding_provider="ollama",
                            embedding_model="all-minilm",
                            generation_provider="ollama",
                            generation_model="qwen2.5:7b",
                            answer_capability="quality",
                        )
                    )
                )
        )

        self.assertEqual([event.event for event in events], ["retrieval", "complete"])
        self.assertEqual(events[0].data["sources"], [])
        self.assertIsNotNone(events[0].data["timings"]["time_to_first_event_seconds"])
        self.assertEqual(events[-1].data["sources"], [])
        self.assertIn("enough relevant body-text evidence", events[-1].data["answer"])
        self.assertIsNone(events[-1].data["timings"]["time_to_first_token_seconds"])

    def test_streaming_does_not_depend_on_a_failing_native_generator(self) -> None:
        """A configured provider cannot make a source-faithful answer fail."""
        generator = _FailingStreamingGenerator()
        with (
            patch("librarian_chat.chat.embed_query", return_value=_query_embedding()),
            patch("librarian_chat.chat.resolve_chat_retrieval_backend", return_value="sqlite"),
            patch("librarian_chat.chat.search_chunks", return_value=_search_response()),
            patch("librarian_chat.chat.create_configured_generator", return_value=generator),
        ):
            events = list(
                stream_answer_question(
                    prepare_answer_question(
                        ChatOptions(
                            question="How brutal is war?",
                            database_url="sqlite:///tmp/librarian.db",
                            embedding_provider="ollama",
                            embedding_model="all-minilm",
                            generation_provider="ollama",
                            generation_model="qwen2.5:7b",
                            answer_capability="quality",
                        )
                    )
                )
            )

        self.assertEqual([event.event for event in events], ["retrieval", "token", "complete"])
        self.assertEqual(events[-1].data["answer"], "War is brutal and terrifying at the front. [S1]")
        self.assertIsNotNone(events[-1].data["timings"]["time_to_first_token_seconds"])

    def test_non_streaming_provider_uses_the_same_extractive_stream_contract(self) -> None:
        """Provider selection cannot change the factual claims exposed by SSE."""
        generator = _FakeGenerator()
        with (
            patch("librarian_chat.chat.embed_query", return_value=_query_embedding()),
            patch("librarian_chat.chat.resolve_chat_retrieval_backend", return_value="sqlite"),
            patch("librarian_chat.chat.search_chunks", return_value=_search_response()),
            patch("librarian_chat.chat.create_configured_generator", return_value=generator),
        ):
            events = list(
                stream_answer_question(
                    prepare_answer_question(
                        ChatOptions(
                            question="How brutal is war?",
                            database_url="sqlite:///tmp/librarian.db",
                            embedding_provider="ollama",
                            embedding_model="all-minilm",
                            generation_provider="codex",
                            generation_model="codex",
                            answer_capability="quality",
                        )
                    )
                )
            )

        self.assertEqual([event.event for event in events], ["retrieval", "token", "complete"])
        self.assertEqual(events[-1].data["answer"], "War is brutal and terrifying at the front. [S1]")
        self.assertIsNotNone(events[-1].data["timings"]["time_to_first_token_seconds"])

    def test_answer_question_retrieves_sources_and_assembles_an_extractive_answer(self) -> None:
        """The JSON route returns exact source text and never invokes generation."""
        fake_search = SearchResponse(
            query="How brutal is war?",
            embedding_provider="ollama",
            embedding_model="all-minilm",
            dimensions=2,
            candidate_count=2,
            filters={"author": "Erich Maria Remarque"},
            results=[
                SearchResult(
                    score=0.9,
                    chunk_id="book:0",
                    book_id="book",
                    relative_path="All Quiet.epub",
                    title="All Quiet on the Western Front",
                    authors=["Erich Maria Remarque"],
                    publisher=None,
                    chunk_index=0,
                    text="War is brutal and terrifying at the front.",
                    embedding_provider="ollama",
                    embedding_model="all-minilm",
                    dimensions=2,
                )
            ],
        )
        generator = _FakeGenerator()

        with (
            patch("librarian_chat.chat.embed_query", return_value=_query_embedding()),
            patch("librarian_chat.chat.resolve_chat_retrieval_backend", return_value="sqlite"),
            patch("librarian_chat.chat.search_chunks", return_value=fake_search),
            patch(
                "librarian_chat.chat.create_configured_generator",
                return_value=generator,
            ),
        ):
            response = answer_question(
                ChatOptions(
                    question=" How brutal is war? ",
                    database_url="sqlite:///tmp/librarian.db",
                    embedding_provider="ollama",
                    embedding_model="all-minilm",
                    generation_provider="ollama",
                    generation_model="llama3.2:3b",
                    answer_capability="quality",
                    retrieval_limit=20,
                    author="Erich Maria Remarque",
                )
            )

        self.assertEqual(response.question, "How brutal is war?")
        self.assertEqual(response.answer, "War is brutal and terrifying at the front. [S1]")
        self.assertEqual(response.answer_capability, "quality")
        self.assertEqual(response.filters, {"author": "Erich Maria Remarque"})
        self.assertEqual(response.candidate_count, 2)
        self.assertEqual(response.retrieval_backend, "sqlite")
        self.assertEqual(response.sources[0].source_id, "S1")
        self.assertEqual(response.sources[0].title, "All Quiet on the Western Front")
        self.assertGreaterEqual(response.timings.query_embedding_seconds, 0.0)
        self.assertGreaterEqual(response.timings.retrieval_seconds, 0.0)
        self.assertGreaterEqual(response.timings.prompt_construction_seconds, 0.0)
        self.assertGreaterEqual(response.timings.generation_seconds, 0.0)
        self.assertGreaterEqual(response.timings.total_seconds, 0.0)
        self.assertEqual(generator.messages, [])

    def test_answer_question_uses_opensearch_hybrid_when_auto_backend_is_healthy(self) -> None:
        """Auto chat retrieval should use the indexed hybrid path and keep scope."""
        generator = _FakeGenerator()
        fake_search = _search_response()

        with (
            patch("librarian_chat.chat.embed_query", return_value=_query_embedding()),
            patch("librarian_chat.chat.resolve_chat_retrieval_backend", return_value="auto"),
            patch(
                "librarian_chat.chat.hybrid_search_chunks", return_value=fake_search
            ) as hybrid_search,
            patch("librarian_chat.chat.search_chunks") as sqlite_search,
            patch(
                "librarian_chat.chat.create_configured_generator",
                return_value=generator,
            ),
        ):
            response = answer_question(
                ChatOptions(
                    question="How brutal is war?",
                    database_url="sqlite:///tmp/librarian.db",
                    embedding_provider="ollama",
                    embedding_model="all-minilm",
                    generation_provider="ollama",
                    generation_model="llama3.2:3b",
                    answer_capability="quality",
                    retrieval_limit=20,
                    book_title="All Quiet",
                    author="Erich Maria Remarque",
                )
            )

        self.assertEqual(response.retrieval_backend, "opensearch")
        sqlite_search.assert_not_called()
        hybrid_options = hybrid_search.call_args.args[0]
        self.assertEqual(hybrid_options.query_embedding, _query_embedding())
        self.assertEqual(hybrid_options.book_title, "All Quiet")
        self.assertEqual(hybrid_options.author, "Erich Maria Remarque")
        self.assertEqual(hybrid_options.limit, 20)
        self.assertEqual(response.sources[0].to_dict(), {
            "source_id": "S1",
            "score": 0.9,
            "chunk_id": "book:0",
            "book_id": "book",
            "relative_path": "All Quiet.epub",
            "title": "All Quiet on the Western Front",
            "authors": ["Erich Maria Remarque"],
            "chunk_index": 0,
            "content_type": "body",
            "text": "War is brutal and terrifying at the front.",
        })
        self.assertEqual(set(response.timings.to_dict()), {
            "query_embedding_seconds",
            "retrieval_seconds",
            "prompt_construction_seconds",
            "generation_seconds",
            "total_seconds",
        })

    def test_answer_question_falls_back_to_sqlite_when_auto_opensearch_is_unavailable(self) -> None:
        """An unavailable projection must not stop source-of-truth chat retrieval."""
        generator = _FakeGenerator()
        fake_search = _search_response()

        with (
            patch("librarian_chat.chat.embed_query", return_value=_query_embedding()),
            patch("librarian_chat.chat.resolve_chat_retrieval_backend", return_value="auto"),
            patch(
                "librarian_chat.chat.hybrid_search_chunks",
                side_effect=OpenSearchError("index is unavailable"),
            ),
            patch(
                "librarian_chat.chat.search_chunks", return_value=fake_search
            ) as sqlite_search,
            patch(
                "librarian_chat.chat.create_configured_generator",
                return_value=generator,
            ),
        ):
            response = answer_question(
                ChatOptions(
                    question="How brutal is war?",
                    database_url="sqlite:///tmp/librarian.db",
                    embedding_provider="ollama",
                    embedding_model="all-minilm",
                    generation_provider="ollama",
                    generation_model="llama3.2:3b",
                    answer_capability="quality",
                    retrieval_limit=20,
                    book_id="book",
                )
            )

        self.assertEqual(response.retrieval_backend, "sqlite")
        sqlite_options = sqlite_search.call_args.args[0]
        self.assertEqual(sqlite_options.query_embedding, _query_embedding())
        self.assertEqual(sqlite_options.book_id, "book")
        self.assertEqual(response.sources[0].source_id, "S1")

    def test_author_view_question_auto_scopes_the_unique_named_author_for_spelled_and_misspelled_terms(self) -> None:
        """Whole-library author questions must not leak evidence from other writers."""
        with TemporaryDirectory() as temp_dir:
            database_url = _seed_author_scope_database(Path(temp_dir) / "librarian.db")
            for question in (
                "What does C.S. Lewis say about modern Christianity?",
                "What does C.S. Lewis say about modern Chrisitanity?",
            ):
                generator = _FakeGenerator()
                fake_search = _author_search_response(question, count=10)
                with (
                    patch(
                        "librarian_chat.chat.embed_query",
                        return_value=_query_embedding_for(question),
                    ),
                    patch(
                        "librarian_chat.chat.resolve_chat_retrieval_backend",
                        return_value="opensearch",
                    ),
                    patch(
                        "librarian_chat.chat.hybrid_search_chunks",
                        return_value=fake_search,
                    ) as hybrid_search,
                    patch(
                        "librarian_chat.chat.create_configured_generator",
                        return_value=generator,
                    ),
                ):
                    response = answer_question(
                        ChatOptions(
                            question=question,
                            database_url=database_url,
                            embedding_provider="ollama",
                            embedding_model="all-minilm",
                            generation_provider="ollama",
                            generation_model="qwen2.5:7b",
                            answer_capability="quality",
                        )
                    )

                self.assertEqual(response.retrieval_backend, "opensearch")
                self.assertEqual(hybrid_search.call_args.args[0].author, "C. S. Lewis")
                self.assertEqual(hybrid_search.call_args.args[0].query, question)
                self.assertEqual(generator.messages, [])
                self.assertEqual(len(response.sources), 10)
                self.assertEqual(response.answer.count("[S"), 10)

    def test_broad_author_question_with_only_one_body_source_does_not_generate(self) -> None:
        """A single weak passage must never be turned into a model-prior synthesis."""
        question = "What does C.S. Lewis say about modern Christianity?"
        with TemporaryDirectory() as temp_dir:
            database_url = _seed_author_scope_database(Path(temp_dir) / "librarian.db")
            generator = _FakeGenerator()
            with (
                patch(
                    "librarian_chat.chat.embed_query",
                    return_value=_query_embedding_for(question),
                ),
                patch(
                    "librarian_chat.chat.resolve_chat_retrieval_backend",
                    return_value="sqlite",
                ),
                patch(
                    "librarian_chat.chat.search_chunks",
                    return_value=_author_search_response(question, count=1),
                ),
                patch(
                    "librarian_chat.chat.create_configured_generator",
                    return_value=generator,
                ),
            ):
                response = answer_question(
                    ChatOptions(
                        question=question,
                        database_url=database_url,
                        embedding_provider="ollama",
                        embedding_model="all-minilm",
                        generation_provider="ollama",
                        generation_model="qwen2.5:7b",
                        answer_capability="quality",
                    )
                )

        self.assertIn("enough distinct body-text passages", response.answer)
        self.assertEqual(generator.messages, [])
        self.assertEqual(response.sources, [])

    def test_lightweight_lookup_is_extractive_for_scoped_and_unscoped_gate_questions(self) -> None:
        """A lightweight lookup must preserve Mara as the source sentence subject."""
        question = "Who opens the garden gate?"
        search_response = _chat_search_response(
            question,
            text=(
                "The clockwork garden woke at dawn.\n"
                "A brass robin counted three silver seeds.\n"
                "Mara opened the gate with a borrowed key."
            ),
        )
        for book_title in (None, "The Clockwork Garden"):
            generator = _FakeGenerator()
            with (
                patch(
                    "librarian_chat.chat.embed_query",
                    return_value=_query_embedding_for(question),
                ),
                patch(
                    "librarian_chat.chat.resolve_chat_retrieval_backend",
                    return_value="sqlite",
                ),
                patch(
                    "librarian_chat.chat.search_chunks", return_value=search_response
                ) as search_chunks,
                patch(
                    "librarian_chat.chat.create_configured_generator",
                    return_value=generator,
                ),
            ):
                response = answer_question(
                    ChatOptions(
                        question=question,
                        database_url="sqlite:///tmp/librarian.db",
                        embedding_provider="ollama",
                        embedding_model="all-minilm",
                        generation_provider="ollama",
                        generation_model="qwen2.5:1.5b",
                        answer_capability="lightweight",
                        book_title=book_title,
                    )
                )

            self.assertEqual(response.answer, "Mara opened the gate with a borrowed key. [S1]")
            self.assertEqual(search_chunks.call_args.args[0].book_title, book_title)
            self.assertEqual(generator.messages, [])

    def test_lightweight_lookup_safely_matches_wakes_to_woke_in_a_scoped_book(self) -> None:
        """Irregular factual inflections still return the exact cited sentence."""
        question = "What wakes at dawn?"
        generator = _FakeGenerator()
        with (
            patch(
                "librarian_chat.chat.embed_query",
                return_value=_query_embedding_for(question),
            ),
            patch(
                "librarian_chat.chat.resolve_chat_retrieval_backend",
                return_value="sqlite",
            ),
            patch(
                "librarian_chat.chat.search_chunks",
                return_value=_chat_search_response(
                    question,
                    text="The clockwork garden woke at dawn.",
                ),
            ) as search_chunks,
            patch(
                "librarian_chat.chat.create_configured_generator",
                return_value=generator,
            ),
        ):
            response = answer_question(
                ChatOptions(
                    question=question,
                    database_url="sqlite:///tmp/librarian.db",
                    embedding_provider="ollama",
                    embedding_model="all-minilm",
                    generation_provider="ollama",
                    generation_model="qwen2.5:1.5b",
                    answer_capability="lightweight",
                    book_title="The Clockwork Garden",
                )
            )

        self.assertEqual(response.answer, "The clockwork garden woke at dawn. [S1]")
        self.assertEqual(response.sources[0].text, "The clockwork garden woke at dawn.")
        self.assertEqual(search_chunks.call_args.args[0].book_title, "The Clockwork Garden")
        self.assertEqual(generator.messages, [])

    def test_lightweight_lookup_refuses_when_no_source_sentence_supports_the_question(self) -> None:
        """Never fall through to a small model after extractive support fails."""
        question = "Who opens the garden gate?"
        generator = _FakeGenerator()
        with (
            patch(
                "librarian_chat.chat.embed_query",
                return_value=_query_embedding_for(question),
            ),
            patch(
                "librarian_chat.chat.resolve_chat_retrieval_backend",
                return_value="sqlite",
            ),
            patch(
                "librarian_chat.chat.search_chunks",
                return_value=_chat_search_response(
                    question,
                    text="A brass robin counted three silver seeds.",
                ),
            ),
            patch(
                "librarian_chat.chat.create_configured_generator",
                return_value=generator,
            ),
        ):
            response = answer_question(
                ChatOptions(
                    question=question,
                    database_url="sqlite:///tmp/librarian.db",
                    embedding_provider="ollama",
                    embedding_model="all-minilm",
                    generation_provider="ollama",
                    generation_model="qwen2.5:1.5b",
                    answer_capability="lightweight",
                )
            )

        self.assertIn("enough relevant body-text evidence", response.answer)
        self.assertEqual(generator.messages, [])
        self.assertEqual(response.sources, [])

    def test_publication_question_requires_non_body_publisher_evidence(self) -> None:
        """Body prose cannot become a citation for a publisher question."""
        question = "Who published The Clockwork Garden?"
        body_only = _chat_search_response(
            question,
            text="The clockwork garden woke at dawn.",
        )
        front_matter = _chat_search_response(
            question,
            text="Published by Fixture Press in 2024.",
            content_type="front_matter",
        )
        for search_response, expected_answer in (
            (
                body_only,
                "I could not find publication or edition evidence in the local EPUB content to answer that reliably.",
            ),
            (front_matter, "Published by Fixture Press in 2024. [S1]"),
        ):
            generator = _FakeGenerator()
            with (
                patch(
                    "librarian_chat.chat.embed_query",
                    return_value=_query_embedding_for(question),
                ),
                patch(
                    "librarian_chat.chat.resolve_chat_retrieval_backend",
                    return_value="sqlite",
                ),
                patch(
                    "librarian_chat.chat.search_chunks", return_value=search_response
                ) as search_chunks,
                patch(
                    "librarian_chat.chat.create_configured_generator",
                    return_value=generator,
                ),
            ):
                response = answer_question(
                    ChatOptions(
                        question=question,
                        database_url="sqlite:///tmp/librarian.db",
                        embedding_provider="ollama",
                        embedding_model="all-minilm",
                        generation_provider="ollama",
                        generation_model="qwen2.5:1.5b",
                        answer_capability="lightweight",
                    )
                )

            self.assertEqual(response.answer, expected_answer)
            self.assertTrue(search_chunks.call_args.args[0].include_non_content)
            self.assertEqual(generator.messages, [])
            if search_response is body_only:
                self.assertEqual(response.sources, [])
        self.assertEqual(body_only.results[0].content_type, "body")

    def test_publication_fact_questions_reject_unrelated_front_matter(self) -> None:
        """A publisher identity and a date each need their own evidence."""
        cases = (
            (
                "Which publisher published The Clockwork Garden?",
                "Published in 2024.",
            ),
            (
                "What is the publication date of The Clockwork Garden?",
                "Copyright 2024.",
            ),
        )
        for question, evidence in cases:
            with self.subTest(question=question):
                generator = _FakeGenerator()
                with (
                    patch(
                        "librarian_chat.chat.embed_query",
                        return_value=_query_embedding_for(question),
                    ),
                    patch(
                        "librarian_chat.chat.resolve_chat_retrieval_backend",
                        return_value="sqlite",
                    ),
                    patch(
                        "librarian_chat.chat.search_chunks",
                        return_value=_chat_search_response(
                            question,
                            text=evidence,
                            content_type="front_matter",
                        ),
                    ) as search_chunks,
                    patch(
                        "librarian_chat.chat.create_configured_generator",
                        return_value=generator,
                    ),
                ):
                    response = answer_question(
                        ChatOptions(
                            question=question,
                            database_url="sqlite:///tmp/librarian.db",
                            embedding_provider="ollama",
                            embedding_model="all-minilm",
                            generation_provider="ollama",
                            generation_model="qwen2.5:1.5b",
                            answer_capability="lightweight",
                        )
                    )

                self.assertEqual(
                    response.answer,
                    "I could not find publication or edition evidence in the local EPUB "
                    "content to answer that reliably.",
                )
                self.assertEqual(response.sources, [])
                self.assertEqual(generator.messages, [])
                self.assertTrue(search_chunks.call_args.args[0].include_non_content)

    def test_publication_questions_require_evidence_for_the_requested_fact(self) -> None:
        """Publisher labels answer entity questions while dates answer date questions."""
        cases = (
            (
                "What publisher published The Clockwork Garden?",
                "Publisher: Fixture Press.",
                "Publisher: Fixture Press. [S1]",
            ),
            (
                "Name the publisher of The Clockwork Garden.",
                "Published by Fixture Press in 2024.",
                "Published by Fixture Press in 2024. [S1]",
            ),
            (
                "What year was The Clockwork Garden published?",
                "Published in 2024.",
                "Published in 2024. [S1]",
            ),
            (
                "What is the publication date of The Clockwork Garden?",
                "Publication date: 2024.",
                "Publication date: 2024. [S1]",
            ),
        )
        for question, evidence, expected_answer in cases:
            with self.subTest(question=question):
                generator = _FakeGenerator()
                with (
                    patch(
                        "librarian_chat.chat.embed_query",
                        return_value=_query_embedding_for(question),
                    ),
                    patch(
                        "librarian_chat.chat.resolve_chat_retrieval_backend",
                        return_value="sqlite",
                    ),
                    patch(
                        "librarian_chat.chat.search_chunks",
                        return_value=_chat_search_response(
                            question,
                            text=evidence,
                            content_type="front_matter",
                        ),
                    ) as search_chunks,
                    patch(
                        "librarian_chat.chat.create_configured_generator",
                        return_value=generator,
                    ),
                ):
                    response = answer_question(
                        ChatOptions(
                            question=question,
                            database_url="sqlite:///tmp/librarian.db",
                            embedding_provider="ollama",
                            embedding_model="all-minilm",
                            generation_provider="ollama",
                            generation_model="qwen2.5:1.5b",
                            answer_capability="lightweight",
                        )
                    )

                self.assertEqual(response.answer, expected_answer)
                self.assertEqual(len(response.sources), 1)
                self.assertEqual(generator.messages, [])
                self.assertTrue(search_chunks.call_args.args[0].include_non_content)


def _query_embedding() -> EmbedQueryResult:
    return EmbedQueryResult(
        query="How brutal is war?",
        embedding_provider="ollama",
        embedding_model="all-minilm",
        dimensions=2,
        vector=[1.0, 0.0],
    )


def _query_embedding_for(question: str) -> EmbedQueryResult:
    return EmbedQueryResult(
        query=question,
        embedding_provider="ollama",
        embedding_model="all-minilm",
        dimensions=2,
        vector=[1.0, 0.0],
    )


def _seed_author_scope_database(database_path: Path) -> str:
    with SQLiteIngestionStore(database_path) as store:
        for book_id, author in (("lewis", "C. S. Lewis"), ("other", "Other Author")):
            store.save_book_with_chunks(
                BookRecord(
                    id=book_id,
                    source_path=f"/books/{book_id}.epub",
                    relative_path=f"{book_id}.epub",
                    file_hash=book_id,
                    size_bytes=100,
                    title=f"{author} Book",
                    authors=[author],
                    status="ingested",
                    ingested_at=utc_now(),
                ),
                [],
            )
    return f"sqlite:///{database_path}"


def _author_search_response(question: str, *, count: int) -> SearchResponse:
    return SearchResponse(
        query=question,
        embedding_provider="ollama",
        embedding_model="all-minilm",
        dimensions=2,
        candidate_count=count,
        filters={"author": "C. S. Lewis"},
        results=[
            SearchResult(
                score=0.9 - (index / 100),
                chunk_id=f"lewis:{index}",
                book_id="lewis",
                relative_path="screwtape.epub",
                title="The Screwtape Letters",
                authors=["C. S. Lewis"],
                publisher=None,
                chunk_index=index,
                text=(
                    f"Lewis examines modern Christianity through moral choice {index} "
                    "and self-deception."
                ),
                embedding_provider="ollama",
                embedding_model="all-minilm",
                dimensions=2,
            )
            for index in range(count)
        ],
    )


def _chat_search_response(
    question: str,
    *,
    text: str,
    content_type: str = "body",
) -> SearchResponse:
    return SearchResponse(
        query=question,
        embedding_provider="ollama",
        embedding_model="all-minilm",
        dimensions=2,
        candidate_count=1,
        filters={},
        results=[
            SearchResult(
                score=0.9,
                chunk_id="clockwork:0",
                book_id="clockwork",
                relative_path="clockwork.epub",
                title="The Clockwork Garden",
                authors=["Test Author"],
                publisher="Fixture Press",
                chunk_index=0,
                content_type=content_type,
                text=text,
                embedding_provider="ollama",
                embedding_model="all-minilm",
                dimensions=2,
            )
        ],
    )


def _two_source_chat_search_response(question: str) -> SearchResponse:
    """Provide two separately citable sentences for stream-boundary coverage."""
    return SearchResponse(
        query=question,
        embedding_provider="ollama",
        embedding_model="all-minilm",
        dimensions=2,
        candidate_count=2,
        filters={},
        results=[
            SearchResult(
                score=0.9,
                chunk_id="clockwork:0",
                book_id="clockwork",
                relative_path="clockwork.epub",
                title="The Clockwork Garden",
                authors=["Test Author"],
                publisher="Fixture Press",
                chunk_index=0,
                text="Mara opened the garden gate with a borrowed key.",
                embedding_provider="ollama",
                embedding_model="all-minilm",
                dimensions=2,
            ),
            SearchResult(
                score=0.8,
                chunk_id="clockwork:1",
                book_id="clockwork",
                relative_path="clockwork.epub",
                title="The Clockwork Garden",
                authors=["Test Author"],
                publisher="Fixture Press",
                chunk_index=1,
                text="The clockwork garden answered in careful ticking.",
                embedding_provider="ollama",
                embedding_model="all-minilm",
                dimensions=2,
            ),
        ],
    )


def _search_response() -> SearchResponse:
    return SearchResponse(
        query="How brutal is war?",
        embedding_provider="ollama",
        embedding_model="all-minilm",
        dimensions=2,
        candidate_count=2,
        filters={"author": "Erich Maria Remarque"},
        results=[
            SearchResult(
                score=0.9,
                chunk_id="book:0",
                book_id="book",
                relative_path="All Quiet.epub",
                title="All Quiet on the Western Front",
                authors=["Erich Maria Remarque"],
                publisher=None,
                chunk_index=0,
                text="War is brutal and terrifying at the front.",
                embedding_provider="ollama",
                embedding_model="all-minilm",
                dimensions=2,
            )
        ],
    )


class _FakeGenerator:
    provider = "ollama"
    model = "llama3.2:3b"

    def __init__(self) -> None:
        self.messages = []

    def generate(self, messages, *, response_format=None):
        self.messages = messages
        return "War is described as terrifying. [S1]"


class _FakeStreamingGenerator(_FakeGenerator):
    """A structural Ollama-like generator for stream orchestration tests."""

    def __init__(self, chunks: list[str]) -> None:
        super().__init__()
        self.chunks = chunks
        self.generate_calls = 0

    def generate(self, messages, *, response_format=None):
        self.generate_calls += 1
        return super().generate(messages, response_format=response_format)

    def stream(self, messages):
        self.messages = messages
        yield from self.chunks


class _DelayedStreamingGenerator(_FakeStreamingGenerator):
    """A slow native-like stream used to verify progress arrives before completion."""

    def __init__(self, chunks: list[str], *, delay_seconds: float) -> None:
        super().__init__(chunks)
        self.delay_seconds = delay_seconds
        self.stream_calls = 0

    def stream(self, messages):
        self.messages = messages
        self.stream_calls += 1
        sleep(self.delay_seconds)
        yield from self.chunks


class _FailingStreamingGenerator(_FakeStreamingGenerator):
    def __init__(self) -> None:
        super().__init__([])

    def stream(self, messages):
        self.messages = messages
        raise GenerationError("fixture stream failed")
        yield ""


if __name__ == "__main__":
    unittest.main()
