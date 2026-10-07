"""Request-contract checks runnable without starting the application or a database."""

import importlib
import unittest

from pydantic import ValidationError


class CampaignSchemaTests(unittest.TestCase):
    def setUp(self):
        try:
            self.schemas = importlib.import_module("app.campaign_schemas")
        except ModuleNotFoundError as exc:
            self.fail(f"Campaign request schemas must be importable: {exc}")
        self.basic = {
            "project_name": "G6 launch",
            "brand": "XPENG",
            "vehicle_model": "G6",
            "markets": ["GB"],
            "primary_market": "GB",
            "start_date": "2026-10-01",
            "end_date": "2026-11-01",
            "budget_total": 60000,
            "owner": "Owner",
        }

    def test_create_preserves_dates_and_has_independent_collection_defaults(self):
        first = self.schemas.CampaignCreate(**self.basic)
        second = self.schemas.CampaignCreate(**self.basic)
        first.collaborators.append("Analyst")
        self.assertEqual(second.collaborators, [])
        self.assertEqual(first.model_dump(mode="json")["start_date"], "2026-10-01")
        self.assertEqual(first.actor_role, "project_owner")
        self.assertIsNone(first.currency)
        self.assertIsNone(first.timezone)

    def test_create_rejects_invalid_scope_period_budget_and_blank_name(self):
        for change in (
            {"markets": []}, {"primary_market": "DE"}, {"primary_market": "US"},
            {"end_date": "2026-09-01"}, {"budget_total": -1},
            {"budget_total": float("inf")}, {"project_name": "   "},
            {"unexpected": "silently discarded"},
        ):
            with self.subTest(change=change), self.assertRaises(ValidationError):
                self.schemas.CampaignCreate(**(self.basic | change))

    def test_patch_is_partial_but_validates_supplied_fields(self):
        patch = self.schemas.CampaignPatch(expected_revision=1, budget_total=0)
        self.assertEqual(
            patch.model_dump(exclude_none=True, exclude={"actor", "actor_role"}),
            {"expected_revision": 1, "budget_total": 0},
        )
        for change in ({"budget_total": -1}, {"expected_revision": 0},
                       {"start_date": "2026-11-01", "end_date": "2026-10-01"},
                       {"markets": ["DE"], "primary_market": "GB"}):
            with self.subTest(change=change), self.assertRaises(ValidationError):
                self.schemas.CampaignPatch(**({"expected_revision": 1} | change))

    def test_frontend_strategy_and_milestones_accept_their_complete_contract(self):
        created = self.schemas.CampaignCreate(**self.basic, milestones=[{
            "name": "Approval", "planned_date": "2026-10-02", "owner": "Owner",
            "status": "pending",
        }])
        self.assertEqual(created.milestones[0].model_dump(mode="json")["planned_date"], "2026-10-02")
        strategy = self.schemas.StrategyPayload(expected_revision=1, audiences=[{
            "name": "Families", "market": "GB", "language": "English",
            "purchase_stage": "Consideration", "priority": "core",
        }], platforms=["YouTube"], content_formats=["Test drive"],
            usage_rights_need="One year", competitor_exclusivity="30 days")
        self.assertEqual(strategy.audiences[0].market, "GB")
        self.assertEqual(strategy.usage_rights_need, "One year")
        reach = self.schemas.StrategyPayload(expected_revision=1, audiences=[{
            "name": "General viewers", "market": "GB", "language": "English",
            "purchase_stage": "Awareness", "priority": "reach",
        }])
        self.assertEqual(reach.audiences[0].priority, "reach")
        with self.assertRaises(ValidationError):
            self.schemas.StrategyPayload(expected_revision=1, audiences=[{
                "name": "Families", "market": "GB", "language": "English",
                "purchase_stage": "Consideration", "priority": "core", "unknown": True,
            }])

    def test_measurement_and_requirements_preserve_editable_draft_fields(self):
        metric = self.schemas.MeasurementPlanPayload(expected_revision=1, items=[{
            "metric_code": "leads", "name": "Leads", "target_value": 500,
            "unit": "people", "formula": "", "data_source": "CRM",
            "data_status": "manual", "observation_window": "30 days",
            "owner": "Analyst", "refresh_frequency": "Daily", "is_primary": True,
        }])
        self.assertEqual(metric.items[0].model_dump()["formula"], "")
        requirements = self.schemas.KolRequirementsPayload(expected_revision=1,
            roles=[{"role_code": "reviewer", "role_name": "Reviewer", "market": "GB",
                    "platform": "YouTube", "required_count": 2, "content_format": "Test drive",
                    "audience_requirement": "UK", "score_preferences": [],
                    "risk_threshold": "Critical blocks", "quote_min": 100,
                    "quote_cap": 1000, "estimated": True}],
            budget_items=[{"category": "Creator fees", "amount": 2000,
                           "estimated": True, "assumption": None}])
        self.assertEqual(requirements.roles[0].quote_cap, 1000)
        self.assertIsNone(requirements.budget_items[0].assumption)
        with self.assertRaises(ValidationError):
            self.schemas.KolRequirementsPayload(expected_revision=1, budget_items=[{
                "category": "Fees", "amount": -1,
            }])

    def test_actions_reject_unknown_decisions_targets_roles_and_invalid_versions(self):
        self.assertEqual(len(self.schemas.PublishPayload().targets), 6)
        self.assertEqual(self.schemas.DecisionPayload(expected_revision=1, decision="approve").risk_signoff, False)
        self.assertEqual(self.schemas.EntityLinkPayload(entity_type="kol", entity_id="42").entity_id, "42")
        for model, payload in (
            (self.schemas.DecisionPayload, {"expected_revision": 1, "decision": "anything"}),
            (self.schemas.PublishPayload, {"targets": ["anything"]}),
            (self.schemas.PublishPayload, {"version_number": 0}),
            (self.schemas.VersionedAction, {"expected_revision": 1, "actor_role": "anything"}),
            (self.schemas.EntityLinkPayload, {"entity_type": "kol", "entity_id": ""}),
        ):
            with self.subTest(model=model.__name__, payload=payload), self.assertRaises(ValidationError):
                model(**payload)


if __name__ == "__main__":
    unittest.main()
