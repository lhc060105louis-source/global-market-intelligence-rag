from app.risk_investigation_schemas import AgentToolProposal

from app import risk_investigation


def test_fallback_reads_primary_record_then_unsearched_domain():
    context = {
        "risk": {"brand": "Aster", "vehicle_model": "Atlas X7", "part": "brake hose",
                 "region": "United States", "risk_type": "pressure loss"},
        "sources": [{"record_id": "primary-record"}],
    }

    first = risk_investigation._fallback_read_proposal(context, completed_calls=[], evidence_ids=set())
    assert first == AgentToolProposal(tool="get_record", arguments={"record_id": "primary-record"})

    second = risk_investigation._fallback_read_proposal(
        context,
        completed_calls=[{"tool": "get_record", "arguments": {"record_id": "primary-record"}}],
        evidence_ids={"primary-record"},
    )
    assert second is not None
    assert second.tool == "search_domain"
    assert second.arguments == {
        "target": "b_business", "query": "Aster Atlas X7 brake hose United States pressure loss"
    }
