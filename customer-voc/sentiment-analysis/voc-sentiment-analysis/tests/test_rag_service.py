import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from rag_service import RagCase, RagService, SentenceTransformerEmbedder
from sentiment_analyzer import normalize_result
from voc_analyzer import analyze_voc_rows


class StaticEmbedder:
    def __init__(self, vectors=None):
        self.vectors = vectors or {}

    def encode(self, texts):
        return [self.vectors.get(text, [1.0, 0.0]) for text in texts]


def make_case(text, *, source_type="synthetic_seed", topic_id="winter_range_drop"):
    return RagCase.from_dict(
        {
            "text": text,
            "language": "en",
            "parent_topic": "battery_range",
            "topic_id": topic_id,
            "sentiment_label": "negative",
            "sentiment_spec": "complaint",
            "source_type": source_type,
        }
    )


def write_cases(path: Path, cases):
    path.write_text(
        "".join(json.dumps(asdict(case), ensure_ascii=False) + "\n" for case in cases),
        encoding="utf-8",
    )


class RagServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.store = Path(self.temporary_directory.name) / "cases.jsonl"

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_environment_defaults_to_english_semantic_embedding(self):
        captured = []

        def fake_init(embedder, model_name):
            captured.append(model_name)

        with patch.dict(
            "os.environ",
            {"VOC_RAG_ENABLED": "true", "RAG_CASE_STORE": str(self.store)},
            clear=True,
        ), patch.object(SentenceTransformerEmbedder, "__init__", fake_init):
            service = RagService.from_env()

        self.assertEqual(captured, ["sentence-transformers/all-MiniLM-L6-v2"])
        self.assertEqual(service.medium_threshold, 0.55)
        self.assertEqual(service.high_threshold, 0.75)

    def test_unknown_embedding_provider_is_rejected_when_rag_is_enabled(self):
        with patch.dict(
            "os.environ",
            {
                "VOC_RAG_ENABLED": "true",
                "RAG_EMBEDDING_PROVIDER": "typo",
                "RAG_CASE_STORE": str(self.store),
            },
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "Unsupported RAG_EMBEDDING_PROVIDER"):
                RagService.from_env()

    def test_synthetic_cases_require_dynamic_few_shot_even_at_high_similarity(self):
        write_cases(self.store, [make_case(f"Synthetic case {i}") for i in range(3)])
        service = RagService(
            self.store,
            embedder=StaticEmbedder(),
            high_threshold=0.8,
            medium_threshold=0.5,
            direct_real_cases=1,
        )

        decision = service.route("My driving range drops sharply in cold winter weather.")

        self.assertEqual(decision.route, "dynamic_few_shot")
        self.assertEqual(len(decision.examples), 3)

    def test_real_consensus_can_use_direct_route_without_copying_entities(self):
        write_cases(
            self.store,
            [make_case(f"Observed case {i}", source_type="pseudo_real") for i in range(3)],
        )
        service = RagService(
            self.store,
            embedder=StaticEmbedder(),
            high_threshold=0.8,
            medium_threshold=0.5,
            direct_real_cases=3,
        )

        decision = service.route("In December my driving range is half of what I get in summer.")
        result = service.direct_result(decision)

        self.assertEqual(decision.route, "direct")
        self.assertEqual(result["topics"][0]["topic_id"], "winter_range_drop")
        self.assertEqual(result["entities"], [])

    def test_pseudo_real_case_is_persisted_only_when_signals_agree(self):
        write_cases(
            self.store,
            [make_case("Range drops quickly in winter"), make_case("The battery performs poorly in cold weather"), make_case("December range is cut in half")],
        )
        service = RagService(
            self.store,
            embedder=StaticEmbedder(),
            high_threshold=0.8,
            medium_threshold=0.5,
        )
        matches = service.retrieve("Battery drain is much worse during winter.")
        result = {
            "label": "negative",
            "topic": "battery_range",
            "sentiment_spec": "complaint",
            "topics": [{"topic_id": "winter_range_drop"}],
        }

        accepted = service.consider_pseudo_real(
            "Battery drain is much worse during winter.", result, matches, language="en"
        )

        self.assertTrue(accepted)
        self.assertEqual(service.flush_pending(), 1)
        reloaded = RagService(self.store, embedder=StaticEmbedder())
        self.assertEqual(reloaded.cases[-1].source_type, "pseudo_real")

    def test_case_loader_rejects_parent_child_mismatch(self):
        valid = make_case("Valid case")
        invalid = RagCase.from_dict(
            {
                "text": "charging station does not accept cash",
                "language": "en",
                "parent_topic": "charging",
                "topic_id": "safety_warning",
                "sentiment_label": "negative",
                "sentiment_spec": "complaint",
                "source_type": "pseudo_real",
            }
        )
        write_cases(self.store, [valid, invalid])

        service = RagService(self.store, embedder=StaticEmbedder())

        self.assertEqual([case.case_id for case in service.cases], [valid.case_id])

    def test_normalizer_aligns_parent_topic_with_specific_topic_id(self):
        normalized = normalize_result(
            {
                "label": "negative",
                "topic": "charging",
                "journey_stage": "full_journey",
                "sentiment_spec": "complaint",
                "sentiment_score": -1,
                "sentiment_strength": 4,
                "sentiment_categories": [{"code": "charging", "strength": 4}],
                "entities": [],
                "topics": [{"topic_id": "safety_warning"}],
            },
            "The driver assistance system suddenly hit the brakes.",
        )

        self.assertEqual(normalized["topic"], "safety_recall")
        self.assertEqual(normalized["topics"][0]["topic_id"], "safety_warning")
        self.assertEqual(normalized["sentiment_categories"][0]["code"], "safety_recall")

    def test_pseudo_real_rejects_parent_child_mismatch(self):
        write_cases(
            self.store,
            [make_case("Range drops quickly in winter"), make_case("The battery performs poorly in cold weather"), make_case("December range is cut in half")],
        )
        service = RagService(self.store, embedder=StaticEmbedder(), medium_threshold=0.5)
        matches = service.retrieve("charging station does not accept cash")
        inconsistent = {
            "label": "negative",
            "topic": "charging",
            "sentiment_spec": "complaint",
            "topics": [{"topic_id": "safety_warning"}],
        }

        accepted = service.consider_pseudo_real(
            "charging station does not accept cash", inconsistent, matches, language="en"
        )

        self.assertFalse(accepted)

    def test_pseudo_real_rejects_coarse_rule_match_without_retrieval_consensus(self):
        cases = [
            make_case("vehicle will not connect to the charger", topic_id="charging_failure"),
            RagCase.from_dict(
                {
                    "text": "too few charging stations",
                    "language": "en",
                    "parent_topic": "charging",
                    "topic_id": "charging_network",
                    "sentiment_label": "negative",
                    "sentiment_spec": "complaint",
                    "source_type": "synthetic_seed",
                }
            ),
            make_case("low temperaturedoes not hold up"),
        ]
        write_cases(self.store, cases)
        service = RagService(
            self.store,
            embedder=StaticEmbedder(),
            high_threshold=0.8,
            medium_threshold=0.5,
        )
        matches = service.retrieve("A new fast-charging station opened today.")
        result = {
            "label": "positive",
            "topic": "charging",
            "sentiment_spec": "satisfaction",
            "topics": [{"topic_id": "charging_failure"}],
        }

        accepted = service.consider_pseudo_real(
            "A new fast-charging station opened today.", result, matches, language="en"
        )

        self.assertFalse(accepted)

    def test_dynamic_pipeline_calls_llm_once_and_passes_retrieved_examples(self):
        write_cases(self.store, [make_case(f"Reference case {i}") for i in range(3)])
        service = RagService(
            self.store,
            embedder=StaticEmbedder(),
            high_threshold=0.8,
            medium_threshold=0.5,
            direct_real_cases=1,
        )
        calls = []

        def fake_analyze(host, model, text, context, retrieved_examples=None):
            calls.append(retrieved_examples)
            return {
                "label": "negative",
                "topic": "battery_range",
                "journey_stage": "full_journey",
                "sentiment_spec": "complaint",
                "sentiment_categories": [{"code": "battery_range", "strength": 4}],
                "entities": [],
                "topics": [{"topic_id": "winter_range_drop"}],
            }

        rows = [
            {
                "source_id": "source-1",
                "channel": "forum",
                "published_at": "2026-07-28",
                "language": "en",
                "text": "Battery charge keeps dropping much faster than expected.",
                "review_status": "review_pass",
            }
        ]

        report = analyze_voc_rows(
            rows,
            analyze_func=fake_analyze,
            max_workers=1,
            rag=service,
        )

        self.assertEqual(len(calls), 1)
        self.assertEqual(len(calls[0]), 3)
        self.assertEqual(report["rag_summary"]["routes"], {"dynamic_few_shot": 1})


if __name__ == "__main__":
    unittest.main()
