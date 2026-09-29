from copy import deepcopy
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings
from app.main import create_app


API_KEY = "test-key"
AUTH = {"X-API-Key": API_KEY}


@pytest.fixture
def client(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        api_key=API_KEY,
        adapter="fake",
        fake_mode="success",
        auto_sync_on_ingest=False,
        maxkb_sync_poll_interval_seconds=0.0,
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def client_factory(tmp_path):
    clients = []

    def factory(mode="success"):
        settings = Settings(
            database_url=f"sqlite:///{tmp_path / f'{mode}-{len(clients)}.db'}",
            api_key=API_KEY,
            adapter="fake",
            fake_mode=mode,
            auto_sync_on_ingest=False,
            maxkb_sync_poll_interval_seconds=0.0,
        )
        context = TestClient(create_app(settings))
        client = context.__enter__()
        clients.append(context)
        return client

    yield factory
    for context in clients:
        context.__exit__(None, None, None)


def base_envelope(source, record_type, source_id, payload, *, push_id="push-1", version=1, event="update_current"):
    return {
        "source_system": source,
        "source_record_id": source_id,
        "record_type": record_type,
        "event_type": event,
        "source_version": version,
        "effective_at": "2026-08-05T10:00:00+08:00",
        "source_updated_at": "2026-08-05T10:01:00+08:00",
        "source_url": "https://example.com/records/1",
        "push_id": push_id,
        "is_mock": False,
        "payload": deepcopy(payload),
    }


def consumer_payload(dimension="journey_sentiment", business_date="2026-08-05"):
    results = {
        "journey_sentiment": {
            "positive_ratio": 0.55, "negative_ratio": 0.25, "neutral_ratio": 0.2,
            "trend_direction": "up", "granularity": "daily",
        },
        "recall_risk": {
            "part": "battery", "risk_type": "overheat", "hit_count": 12,
            "threshold": 10, "threshold_exceeded": True,
            "first_hit_at": "2026-08-05T09:00:00+08:00", "risk_status": "open",
        },
        "nps_prediction": {
            "nps_value": 32.0, "change_from_previous": 2.0, "promoter_ratio": 0.5,
            "passive_ratio": 0.32, "detractor_ratio": 0.18,
        },
        "key_complaints": {
            "complaints": [{
                "topic_id": "topic-1", "topic_name": "Charging speed", "part": "charger",
                "frequency": 12, "average_sentiment_intensity": -0.7, "trend_direction": "up",
            }],
        },
        "brand_attitude": {
            "attitude": "positive", "positive_ratio": 0.55, "negative_ratio": 0.25,
            "neutral_ratio": 0.2, "trend_direction": "stable",
        },
        "legal_risk": {
            "part": "battery", "risk_type": "class_action", "hit_count": 6,
            "threshold": 5, "threshold_exceeded": True, "risk_level": "high", "risk_status": "open",
        },
    }
    return {
        "scope_id": "scope-eu-model-a", "dimension": dimension, "brand": "Example Motors",
        "vehicle_model": "Model A", "region": "EU", "journey_stage": "ownership",
        "channel": "social", "language": "en", "period_start": "2026-08-04T00:00:00+00:00",
        "period_end": "2026-08-04T23:59:59+00:00", "business_date": business_date,
        "signal_count": 42, "emotion_distribution": {"satisfied": 20, "angry": 5},
        "result": results[dimension],
    }


def business_payload():
    return {
        "entry_id": "entry-1", "entry_type": "policy", "title": "EU battery policy",
        "published_summary": "The approved policy summary.", "regions": ["EU"], "tags": ["battery"],
        "related_entities": [{"type": "regulator", "standard_name": "EC", "stable_id": "ec"}],
        "business_impact": "Reporting changes", "recommended_action": "Review reporting",
        "external_sources": [{"name": "Official source", "url": "https://example.com/policy"}],
        "publication_status": "published", "published_at": "2026-08-05T08:00:00+00:00",
    }


def kol_payload():
    return {
        "kol_id": "kol-1", "display_name": "Creator One", "primary_platform": "YouTube",
        "content_categories": ["auto"], "audience_regions": ["EU"], "commercial_score": 88.5,
        "commercial_dimensions": {"reach": 90}, "risk_score": 12.0, "risk_level": "low",
        "risk_tags": [], "cooperation_conclusion": "recommended",
    }


def kol_cooperation_payload():
    return {
        "cooperation_id": "coop-1", "kol_id": "kol-1", "project_id": "project-1",
        "project_name": "Model A launch", "brand": "Example Motors", "vehicle_model": "Model A",
        "final_stage": "completed", "distribution_conclusion": "Reached the target audience",
        "performance_summary": "Exceeded the view target", "public_opinion_conclusion": "Positive",
        "review_conclusion": "Suitable for another campaign",
        "cooperation_start": "2026-07-01T00:00:00+00:00",
        "cooperation_end": "2026-07-31T00:00:00+00:00",
    }
