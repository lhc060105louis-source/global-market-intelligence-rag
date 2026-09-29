from app.models import AssessmentInput, Kol, ScoreRecord
from app.services.importer import persist_assessment

from test_assessment import HIGH_VALUE_INPUTS, LOW_RISK_INPUTS


def test_raw_assessment_and_dimension_evidence_are_persisted(client):
    with client.app.state.session_factory() as session:
        kol = Kol(platform="YouTube", handle="@raw", country="GB")
        session.add(kol)
        session.flush()

        persist_assessment(
            session,
            kol,
            HIGH_VALUE_INPUTS,
            LOW_RISK_INPUTS,
            source="legacy-local-storage",
        )
        session.commit()

        raw = session.get(AssessmentInput, kol.id)
        assert raw.commercial_inputs == HIGH_VALUE_INPUTS
        assert raw.risk_inputs == LOW_RISK_INPUTS
        assert raw.source == "legacy-local-storage"
        audience = next(r for r in kol.score_records if r.dimension == "audience_fit")
        assert audience.auto_score == 92
        assert "geo=90" in audience.evidence
        assert audience.source == "legacy-local-storage"


def test_refreshing_assessment_preserves_manual_value_and_evidence(client):
    with client.app.state.session_factory() as session:
        kol = Kol(platform="YouTube", handle="@manual", country="GB")
        session.add(kol)
        session.flush()
        session.add(ScoreRecord(
            kol_id=kol.id, score_type="commercial", dimension="audience_fit",
            auto_score=1, manual_score=99,
            evidence="old automatic evidence", source="old collector",
            manual_evidence="analyst evidence", manual_source="analyst",
        ))
        session.flush()

        persist_assessment(
            session, kol, HIGH_VALUE_INPUTS, LOW_RISK_INPUTS,
            source="new collector",
        )
        session.flush()

        record = next(r for r in kol.score_records if r.dimension == "audience_fit")
        assert record.auto_score == 92
        assert record.manual_score == 99
        assert "geo=90" in record.evidence
        assert record.source == "new collector"
        assert record.manual_evidence == "analyst evidence"
        assert record.manual_source == "analyst"


def test_persisted_summary_uses_manual_over_auto_and_excludes_missing(client):
    partial = dict(HIGH_VALUE_INPUTS)
    del partial["focus"]
    with client.app.state.session_factory() as session:
        kol = Kol(platform="YouTube", handle="@effective", country="GB")
        session.add(kol)
        session.flush()
        session.add(ScoreRecord(
            kol_id=kol.id, score_type="commercial", dimension="audience_fit",
            manual_score=50,
        ))
        session.flush()

        persist_assessment(session, kol, partial, {}, source="assessment")
        session.flush()

        assert kol.score_summary.commercial_completeness == 0.85
        expected = (
            50 * 20 + 74 * 15 + 81 * 15 + 96 * 15 + 90 * 10 + 92 * 10
        ) / 85
        assert kol.score_summary.commercial_score == round(expected, 1)
        assert kol.score_summary.risk_score is None
