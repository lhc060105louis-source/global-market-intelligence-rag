from app.record_display import build_record_display
from conftest import AUTH, base_envelope, business_payload, consumer_payload, kol_cooperation_payload, kol_payload


def post(client, path, body):
    return client.post(path, headers=AUTH, json=body)


def test_consumer_feedback_categories_and_templates():
    expected_types = {
        "consumer_journey_sentiment": "journey_sentiment",
        "consumer_nps_prediction": "nps_prediction",
        "consumer_key_complaints": "key_complaints",
        "consumer_brand_attitude": "brand_attitude",
    }
    for record_type, dimension in expected_types.items():
        display = build_record_display(
            source_system="C", record_type=record_type, payload_json=consumer_payload(dimension),
        )
        assert display["display_category"] == "feedback"
        assert display["risk_state"] == "none"
        assert display["display_summary"]
        assert "journey_curve" not in display["display_summary"]
        assert "{" not in display["display_summary"]


def test_risk_records_use_structured_threshold_only():
    payload = consumer_payload("recall_risk")
    payload["result"]["threshold_exceeded"] = False
    normal = build_record_display(
        source_system="C", record_type="consumer_recall_risk", payload_json=payload,
    )
    assert normal["display_category"] == "risk_assessment"
    assert normal["risk_state"] == "normal"
    assert "no production alert has been triggered" in normal["display_summary"]

    payload["result"]["threshold_exceeded"] = True
    alert = build_record_display(
        source_system="C", record_type="consumer_recall_risk", payload_json=payload,
    )
    assert alert["display_category"] == "risk_alert"
    assert alert["risk_state"] == "alert"
    assert "production risk alert" in alert["display_summary"]


def test_summary_omits_missing_values_without_serializing_objects():
    payload = consumer_payload("journey_sentiment")
    payload["result"].pop("negative_ratio")
    payload["period_end"] = None
    display = build_record_display(
        source_system="C", record_type="consumer_journey_sentiment", payload_json=payload,
    )
    assert "Negative sentiment" not in display["display_summary"]
    assert "Reporting period: 2026-08-04" in display["display_summary"]
    assert "journey_curve" not in display["display_summary"]


def test_business_and_kol_use_formal_text_fields():
    business = build_record_display(
        source_system="B", record_type="business_policy", payload_json=business_payload(),
    )
    assert business["display_category"] == "policy"
    assert business["display_summary"] == business_payload()["published_summary"]

    cooperation = build_record_display(
        source_system="KOL", record_type="kol_cooperation_result", payload_json=kol_cooperation_payload(),
    )
    assert cooperation["display_category"] == "kol_trend"
    assert cooperation["display_summary"].startswith("Suitable for another campaign")
    assert "project_name" not in cooperation["display_summary"]

    assessment = build_record_display(
        source_system="KOL", record_type="kol_current_assessment", payload_json=kol_payload(),
    )
    assert assessment["display_summary"] == kol_payload()["cooperation_conclusion"]


def test_records_list_and_detail_expose_same_display_fields(client):
    body = base_envelope(
        "C", "consumer_journey_sentiment", "display-c-1", consumer_payload(), push_id="display-c-1",
    )
    created = post(client, "/api/v1/ingestion/c", body)
    assert created.status_code == 201
    record_id = created.json()["record_id"]

    listed = client.get("/api/v1/records?status=active&record_mode=current", headers=AUTH)
    assert listed.status_code == 200
    list_record = next(item for item in listed.json()["items"] if item["id"] == record_id)
    detail = client.get(f"/api/v1/records/{record_id}", headers=AUTH)
    assert detail.status_code == 200
    detail_record = detail.json()["record"]

    assert {
        key: list_record[key] for key in ("display_category", "risk_state", "display_summary")
    } == {
        key: detail_record[key] for key in ("display_category", "risk_state", "display_summary")
    }
    assert list_record["retrieval_text"] == detail_record["retrieval_text"]
