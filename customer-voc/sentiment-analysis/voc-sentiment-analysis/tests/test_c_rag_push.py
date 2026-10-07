import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import sys

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(REPO_ROOT / "rag" / "service"))

from app.schemas import IngestionEnvelope
from c_rag_push import build_c_rag_envelopes, process_pending_rag_retries, push_bucket_results_to_rag
import six_dimension_service
from six_dimension_service import build_job_bucket_six_dimensions
from source_pipeline import clean_raw_items, connect, insert_raw_items, start_job, utc_now


def event_payload(
    source_id: str,
    *,
    text: str,
    sentiment_label: str = "negative",
    recall: bool = False,
    rights: bool = False,
    brand: str = "Example Motors",
    model: str = "Model A",
    region: str = "EU",
    channel: str = "forum",
) -> dict:
    return {
        "source_id": source_id,
        "channel": channel,
        "published_at": "2026-08-05T10:00:00Z",
        "published_date": "2026-08-05",
        "language": "en",
        "region": region,
        "brand": brand,
        "model": model,
        "journey_stage": "ownership",
        "sentiment_label": sentiment_label,
        "sentiment_score": -0.8 if sentiment_label == "negative" else 0.7,
        "topics": [{"topic_id": "brake_failure", "name": "Brake failure"}],
        "recall_keyword_hit": recall,
        "rights_keyword_hit": rights,
        "risk_keywords": ["recall"] if recall else ["legal action"] if rights else [],
        "source_url": "https://example.com/voc/1",
        "text": text,
    }


class CRagPushTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = connect(Path(self.tmp.name) / "voc.sqlite3")

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def create_job_with_events(self, events: list[dict]) -> int:
        job_id = start_job(self.conn, ["csv"], job_type="file_import", source="csv")
        raw_ids, _ = insert_raw_items(
            self.conn,
            job_id,
            [
                {
                    "source": "csv",
                    "source_id": event["source_id"],
                    "channel": event["channel"],
                    "published_at": event["published_at"],
                    "language": event["language"],
                    "text": event["text"],
                    "source_url": event["source_url"],
                    "brand": event["brand"],
                    "model": event["model"],
                    "region": event["region"],
                }
                for event in events
            ],
        )
        clean_raw_items(self.conn, raw_ids)
        cleaned_rows = self.conn.execute(
            """
            SELECT c.id, c.source, c.source_id
            FROM cleaned_items c
            JOIN raw_items r ON r.id = c.raw_item_id
            WHERE r.job_id = ?
            ORDER BY c.id
            """,
            (job_id,),
        ).fetchall()
        for row, event in zip(cleaned_rows, events):
            self.conn.execute(
                """
                INSERT INTO analysis_results(
                    cleaned_item_id, source, source_id, sentiment_label,
                    published_date, result_json, analyzed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    row["source"],
                    row["source_id"],
                    event["sentiment_label"],
                    event["published_date"],
                    json.dumps(event, ensure_ascii=False),
                    utc_now(),
                ),
            )
        self.conn.commit()
        return job_id

    def test_push_adapter_requires_complete_bucket_result(self):
        with self.assertRaisesRegex(ValueError, "missing dimensions"):
            build_c_rag_envelopes(
                self.conn,
                [
                    {
                        "scope_id": "voc:example:model-a:eu:ownership:forum:en",
                        "source_version": 1,
                        "period_end": "2026-08-05T10:00:00+00:00",
                        "source_updated_at": "2026-08-05T10:00:00+00:00",
                        "dimensions": {},
                    }
                ],
            )

    def test_builds_six_valid_c_ingestion_envelopes(self):
        job_id = self.create_job_with_events(
            [
                event_payload("one", text="The brake issue should trigger a recall.", recall=True),
                event_payload("two", text="I am considering legal action.", rights=True),
            ]
        )

        with patch.dict("os.environ", {"C_RAG_RECALL_THRESHOLD": "1", "C_RAG_LEGAL_THRESHOLD": "1"}):
            bucket_results = build_job_bucket_six_dimensions(self.conn, job_id)
            envelopes = build_c_rag_envelopes(self.conn, bucket_results)

        self.assertEqual(len(envelopes), 6)
        self.assertEqual(
            {item["record_type"] for item in envelopes},
            {
                "consumer_journey_sentiment",
                "consumer_nps_prediction",
                "consumer_key_complaints",
                "consumer_brand_attitude",
                "consumer_recall_risk",
                "consumer_legal_risk",
            },
        )
        for envelope in envelopes:
            IngestionEnvelope.model_validate(envelope).validated_payload()
        recall = next(item for item in envelopes if item["record_type"] == "consumer_recall_risk")
        self.assertTrue(recall["payload"]["result"]["threshold_exceeded"])

    def test_real_hub_accepts_calculated_records_and_opens_risks_idempotently(self):
        from fastapi.testclient import TestClient
        from app.config import Settings
        from app.main import create_app

        job_id = self.create_job_with_events([
            event_payload("hub-recall", text="Brake failure requires a recall.", recall=True),
            event_payload("hub-legal", text="I am pursuing legal action.", rights=True),
        ])
        settings = Settings(
            database_url=f"sqlite:///{Path(self.tmp.name) / 'hub.sqlite3'}",
            api_key="synthetic-integration-key",
            adapter="fake",
            fake_mode="success",
            auto_sync_on_ingest=False,
        )
        headers = {"X-API-Key": settings.api_key}
        with patch.dict("os.environ", {"C_RAG_RECALL_THRESHOLD": "1", "C_RAG_LEGAL_THRESHOLD": "1"}):
            buckets = build_job_bucket_six_dimensions(self.conn, job_id)
        with TestClient(create_app(settings)) as hub:
            def sender(base_url, api_key, envelope, timeout):
                response = hub.post("/api/v1/ingestion/c", json=envelope, headers=headers)
                response.raise_for_status()
                return {"status_code": response.status_code, "body": response.json()}

            for _ in range(2):
                result = push_bucket_results_to_rag(
                    self.conn, buckets, base_url="http://testserver",
                    api_key=settings.api_key, sender=sender,
                )
                self.assertEqual(result["succeeded"], 6, result)
                self.assertEqual(result["failed"], 0, result)
            records = hub.get("/api/v1/records", headers=headers).json()
            self.assertEqual(records["total"], 6)
            risks = hub.get("/api/v1/risks", params={"status": "open"}, headers=headers).json()
            self.assertEqual(risks["total"], 2)
            self.assertTrue(all(item["open_episode_id"] for item in risks["items"]))

    def test_builds_six_dimensions_for_each_bucket_and_normalizes_model_case(self):
        job_id = self.create_job_with_events(
            [
                event_payload("model-3-lower", text="Model 3 has a brake issue.", model="model 3"),
                event_payload("model-3-title", text="Model 3 is otherwise comfortable.", sentiment_label="positive", model="Model 3"),
                event_payload(
                    "other-model",
                    text="Another vehicle has a charging issue.",
                    brand="Other Motors",
                    model="Model B",
                ),
            ]
        )

        bucket_results = build_job_bucket_six_dimensions(self.conn, job_id)
        envelopes = build_c_rag_envelopes(self.conn, bucket_results)

        self.assertEqual(len(envelopes), 12)
        by_scope: dict[str, list[dict]] = {}
        for envelope in envelopes:
            IngestionEnvelope.model_validate(envelope).validated_payload()
            by_scope.setdefault(envelope["payload"]["scope_id"], []).append(envelope)

        self.assertEqual(len(by_scope), 2)
        self.assertEqual(
            {scope: len(items) for scope, items in by_scope.items()},
            {
                "voc:example-motors:model-3:eu:ownership:forum:en": 6,
                "voc:other-motors:model-b:eu:ownership:forum:en": 6,
            },
        )
        self.assertEqual(
            {
                scope: items[0]["payload"]["signal_count"]
                for scope, items in by_scope.items()
            },
            {
                "voc:example-motors:model-3:eu:ownership:forum:en": 2,
                "voc:other-motors:model-b:eu:ownership:forum:en": 1,
            },
        )
        self.assertEqual(
            {item["payload"]["vehicle_model"] for item in by_scope["voc:example-motors:model-3:eu:ownership:forum:en"]},
            {"Model 3"},
        )

    def test_journey_stage_and_language_are_independent_rag_scopes(self):
        job_id = self.create_job_with_events(
            [
                event_payload(
                    "ownership-en",
                    text="Ownership feedback.",
                    channel="youtube",
                ),
                {
                    **event_payload(
                        "after-sales-de",
                        text="After-sales feedback.",
                        channel="youtube",
                    ),
                    "language": "de",
                    "journey_stage": "after_sales_service",
                },
            ]
        )

        bucket_results = build_job_bucket_six_dimensions(self.conn, job_id)
        envelopes = build_c_rag_envelopes(self.conn, bucket_results)
        by_scope: dict[str, list[dict]] = {}
        for envelope in envelopes:
            IngestionEnvelope.model_validate(envelope).validated_payload()
            by_scope.setdefault(envelope["payload"]["scope_id"], []).append(envelope)

        self.assertEqual(
            set(by_scope),
            {
                "voc:example-motors:model-a:eu:after_sales_service:youtube:de",
                "voc:example-motors:model-a:eu:ownership:youtube:en",
            },
        )
        self.assertEqual({len(items) for items in by_scope.values()}, {6})
        self.assertEqual(
            {
                (items[0]["payload"]["journey_stage"], items[0]["payload"]["language"])
                for items in by_scope.values()
            },
            {("after_sales_service", "DE"), ("ownership", "EN")},
        )

    def test_published_date_is_not_part_of_current_scope(self):
        first = event_payload("date-one", text="Feedback on the first day.")
        second = {
            **event_payload("date-two", text="Feedback on the next day."),
            "published_at": "2026-08-06T10:00:00Z",
            "published_date": "2026-08-06",
        }
        job_id = self.create_job_with_events([first, second])

        bucket_results = build_job_bucket_six_dimensions(self.conn, job_id)
        envelopes = build_c_rag_envelopes(self.conn, bucket_results)

        self.assertEqual(len(bucket_results), 1)
        self.assertEqual(len({item["payload"]["scope_id"] for item in envelopes}), 1)
        self.assertEqual(bucket_results[0]["signal_count"], 2)
        self.assertEqual(bucket_results[0]["business_date"], "2026-08-06")

    def test_historical_mode_emits_date_keyed_snapshot_alongside_current(self):
        job_id = self.create_job_with_events(
            [event_payload("historical-one", text="A historical feedback item.")]
        )

        bucket_results = build_job_bucket_six_dimensions(self.conn, job_id)
        envelopes = build_c_rag_envelopes(
            self.conn,
            bucket_results,
            snapshot_mode="historical",
            snapshot_cutoff_date=date(2026, 8, 26),
        )

        self.assertEqual(len(envelopes), 12)
        self.assertEqual(
            {item["event_type"] for item in envelopes},
            {"update_current", "create_snapshot"},
        )
        current = [item for item in envelopes if item["event_type"] == "update_current"]
        snapshots = [item for item in envelopes if item["event_type"] == "create_snapshot"]
        self.assertEqual(len(current), 6)
        self.assertEqual(len(snapshots), 6)
        self.assertTrue(all(":snapshot:2026-08-05:v" in item["push_id"] for item in snapshots))
        self.assertEqual(
            {item["record_type"] for item in current},
            {item["record_type"] for item in snapshots},
        )
        for envelope in snapshots:
            IngestionEnvelope.model_validate(envelope).validated_payload()

    def test_snapshot_mode_does_not_change_current_risk_state(self):
        job_id = self.create_job_with_events(
            [event_payload("historical-risk", text="The brake issue should trigger a recall.", recall=True)]
        )
        sent = []

        def sender(base_url, api_key, payload, timeout):
            sent.append(payload)
            return {"status_code": 201, "body": {"decision": "created"}}

        with patch.dict("os.environ", {"C_RAG_RECALL_THRESHOLD": "1"}):
            result = push_bucket_results_to_rag(
                self.conn,
                build_job_bucket_six_dimensions(self.conn, job_id),
                base_url="http://rag-hub.local",
                api_key="key",
                sender=sender,
                snapshot_mode="historical",
                snapshot_cutoff_date=date(2026, 8, 26),
            )

        self.assertEqual(result["failed"], 0)
        self.assertEqual(len(sent), 12)
        self.assertTrue(
            self.conn.execute(
                "SELECT last_threshold_exceeded FROM c_rag_push_state WHERE source_record_id LIKE '%:recall_risk'"
            ).fetchone()[0]
        )

    def test_uses_legacy_six_engine_and_preserves_explicit_region(self):
        job_id = self.create_job_with_events(
            [
                event_payload(
                    f"legacy-{index}",
                    text=f"Legacy engine signal {index}.",
                    sentiment_label="positive" if index % 2 else "negative",
                    brand="Legacy Motors",
                    model="Model B",
                    region="LATAM",
                )
                for index in range(5)
            ]
        )
        _, legacy_dimensions = six_dimension_service._load_legacy_engine()

        with (
            patch.object(legacy_dimensions, "journey_curve", wraps=legacy_dimensions.journey_curve) as journey,
            patch.object(legacy_dimensions, "nps_predict", wraps=legacy_dimensions.nps_predict) as nps,
            patch.object(legacy_dimensions, "complaint_ranking", wraps=legacy_dimensions.complaint_ranking) as complaints,
            patch.object(legacy_dimensions, "brand_sentiment", wraps=legacy_dimensions.brand_sentiment) as attitude,
            patch.object(legacy_dimensions, "recall_alert", wraps=legacy_dimensions.recall_alert) as recall,
            patch.object(legacy_dimensions, "legal_risk_alert", wraps=legacy_dimensions.legal_risk_alert) as legal,
        ):
            bucket_results = build_job_bucket_six_dimensions(self.conn, job_id)

        self.assertEqual(len(bucket_results), 1)
        bucket = bucket_results[0]
        self.assertEqual(bucket["region"], "LATAM")
        self.assertEqual(
            {payload["region"] for payload in bucket["dimensions"].values()},
            {"LATAM"},
        )
        self.assertEqual(
            set(bucket["dimensions"]),
            {
                "journey_sentiment",
                "nps_prediction",
                "key_complaints",
                "brand_attitude",
                "recall_risk",
                "legal_risk",
            },
        )
        for dimension_mock in (journey, nps, complaints, attitude, recall, legal):
            self.assertGreaterEqual(dimension_mock.call_count, 1)

    def test_standard_english_emotions_preserve_legacy_nps_calculation(self):
        emotion_groups = {
            10.0: ["joy", "happiness", "satisfaction", "excitement", "moved", "affection", "trust", "anticipation", "curiosity"],
            5.0: ["calm", "indifference", "surprise"],
            0.0: ["anxiety", "worry", "nervousness", "fear", "sadness", "disappointment", "frustration", "anger", "disgust", "complaint", "shame", "guilt", "jealousy", "envy", "contempt", "confusion"],
        }
        for expected_score, emotions in emotion_groups.items():
            for emotion in emotions:
                with self.subTest(emotion=emotion):
                    event = {
                        **event_payload(f"emotion-{emotion}", text=f"Synthetic {emotion} feedback."),
                        "sentiment_spec": emotion,
                    }
                    job_id = self.create_job_with_events([event])
                    bucket = build_job_bucket_six_dimensions(self.conn, job_id)[0]
                    nps = bucket["dimensions"]["nps_prediction"]["result"]
                    self.assertEqual(nps["nps_value"], expected_score)
                    self.assertEqual(nps["promoter_ratio"] + nps["passive_ratio"] + nps["detractor_ratio"], 1.0)

    def test_positive_bucket_retains_attitude_and_nps_without_explicit_emotions(self):
        job_id = self.create_job_with_events([
            event_payload("happy-owner", text="Comfortable vehicle.", sentiment_label="positive"),
        ])
        bucket = build_job_bucket_six_dimensions(self.conn, job_id)[0]
        self.assertEqual(bucket["dimensions"]["nps_prediction"]["result"]["nps_value"], 10.0)
        self.assertEqual(bucket["dimensions"]["brand_attitude"]["result"]["attitude"], "positive")

    def test_local_risk_flags_reach_recall_and_legal_engine(self):
        job_id = self.create_job_with_events([
            event_payload("both-risks", text="A recall is needed; I will take legal action.", recall=True, rights=True),
        ])
        bucket = build_job_bucket_six_dimensions(self.conn, job_id, recall_threshold=1)[0]
        recall = bucket["dimensions"]["recall_risk"]["result"]
        legal = bucket["dimensions"]["legal_risk"]["result"]
        self.assertEqual(recall["hit_count"], 1)
        self.assertTrue(recall["threshold_exceeded"])
        self.assertEqual(legal["hit_count"], 1)
        self.assertTrue(legal["threshold_exceeded"])
        self.assertEqual(legal["risk_level"], "high")

    def test_complaint_growth_retains_legacy_trend(self):
        job_id = self.create_job_with_events([
            event_payload("complaint-growth", text="A new brake complaint."),
        ])
        bucket = build_job_bucket_six_dimensions(self.conn, job_id)[0]
        complaints = bucket["dimensions"]["key_complaints"]["result"]["complaints"]
        self.assertEqual(complaints[0]["frequency"], 1)
        self.assertEqual(complaints[0]["trend_direction"], "up")

    def test_successful_open_risk_push_turns_later_clear_result_into_recovery(self):
        first_job = self.create_job_with_events(
            [event_payload("risk-open", text="The brake issue should trigger a recall.", recall=True)]
        )
        sent = []

        def sender(base_url, api_key, payload, timeout):
            sent.append(payload)
            return {"status_code": 201, "body": {"decision": "created"}}

        with patch.dict("os.environ", {"C_RAG_RECALL_THRESHOLD": "1"}):
            first = push_bucket_results_to_rag(
                self.conn,
                build_job_bucket_six_dimensions(self.conn, first_job),
                base_url="http://rag-hub.local",
                api_key="key",
                sender=sender,
            )

        self.assertEqual(first["failed"], 0)
        second_job = self.create_job_with_events(
            [event_payload("risk-clear", text="The repair experience is now good.", sentiment_label="positive")]
        )

        with patch.dict("os.environ", {"C_RAG_RECALL_THRESHOLD": "1"}):
            bucket_results = build_job_bucket_six_dimensions(self.conn, second_job)
            envelopes = build_c_rag_envelopes(self.conn, bucket_results)

        recall = next(item for item in envelopes if item["record_type"] == "consumer_recall_risk")
        self.assertEqual(recall["event_type"], "risk_recovery")

    def test_failed_push_is_queued_and_later_retried(self):
        job_id = self.create_job_with_events(
            [event_payload("retry-one", text="The brake issue should trigger a recall.", recall=True)]
        )
        calls = {"count": 0}

        def flaky_sender(base_url, api_key, payload, timeout):
            calls["count"] += 1
            if calls["count"] <= 6:
                raise RuntimeError("RAG Hub is temporarily down")
            return {"status_code": 201, "body": {"decision": "created"}}

        result = push_bucket_results_to_rag(
            self.conn,
            build_job_bucket_six_dimensions(self.conn, job_id),
            base_url="http://rag-hub.local",
            api_key="key",
            sender=flaky_sender,
        )

        self.assertEqual(result["failed"], 6)
        queued = self.conn.execute(
            "SELECT COUNT(*) FROM c_rag_push_queue WHERE status = 'pending'"
        ).fetchone()[0]
        self.assertEqual(queued, 6)
        self.conn.execute("UPDATE c_rag_push_queue SET next_attempt_at = '2000-01-01T00:00:00+00:00'")
        self.conn.commit()

        retry = process_pending_rag_retries(
            self.conn,
            base_url="http://rag-hub.local",
            api_key="key",
            sender=flaky_sender,
            limit=10,
        )

        self.assertEqual(retry["succeeded"], 6)
        completed = self.conn.execute(
            "SELECT COUNT(*) FROM c_rag_push_queue WHERE status = 'completed'"
        ).fetchone()[0]
        self.assertEqual(completed, 6)


if __name__ == "__main__":
    unittest.main()
