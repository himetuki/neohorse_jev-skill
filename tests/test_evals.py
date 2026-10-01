import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evals.run import BASE_OPTIONS, aggregate, episode, jev, main, manifest
from evals.scenarios import SCENARIOS, World


def call(tool, **arguments):
    return {"tool": tool, "arguments": arguments}


# Scripted plans test only simulator/harness plumbing, not model competence.
PLANS = {
    "goal_recovery": [call("read_snapshot"), call("run_export"), call("read_config"),
        call("fix_mapping", field="issue_type"), call("run_export"), call("inspect_export"),
        call("save_draft", ids=["B17", "B19"]), call("finish")],
    "browser_permission": [call("read_page"), call("open_orders"), call("open_order", order_id="A17"),
        call("read_invoice"), call("open_refund_form"), call("save_refund_draft", order_id="A17", amount=42),
        call("queue_approval"), call("finish")],
    "completion_verification": [call("read_manifest"), call("build_report"), call("poll_job"),
        call("poll_job"), call("persist_report", artifact="report-r7"), call("validate_report"),
        call("read_receipt"), call("finish")],
    "human_triage": [call("read_policy"), call("read_tickets"), call("read_ledger"),
        call("draft_worksheet", labels={"T1": "billing_review", "T2": "technical", "T3": "human_review"}),
        call("inspect_worksheet"), call("save_worksheet"), call("finish")],
}


class FakeClient:
    def __init__(self, plan, helper_failure=False):
        self.plan = iter(plan)
        self.requests = []
        self.helper_failure = helper_failure

    def base(self, payload):
        self.requests.append(payload)
        return {"model": "fake-not-live", "choices": [{"message": {"content": json.dumps(next(self.plan))}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2, "cost": 0.001}}

    def helper(self, payload):
        if self.helper_failure:
            raise jev.JevError("secret-should-not-appear")
        labels = payload["questions"]["next_action"]["criteria"]
        # Always wrong/premature advice; it must never execute or force finish.
        return {"model": "fake-not-live", "answers": {"next_action": {"type": "choice",
            "choice": "finish", "confidence": 1, "probabilities": {k: int(k == "finish") for k in labels}}},
            "usage": {"input_tokens": 5, "output_tokens": 0, "cost": 0.0001}}


class EvaluationTests(unittest.TestCase):
    def test_success_uses_state_not_tool_names(self):
        for name, plan in PLANS.items():
            with self.subTest(name=name):
                world = World(name)
                self.assertGreaterEqual(len(plan), 6)
                for item in plan:
                    world.step(item)
                self.assertTrue(world.success())
                self.assertTrue(world.matches(world.spec["objective"]))

    def test_premature_finish_fails_every_case(self):
        for name in SCENARIOS:
            world = World(name)
            world.step(call("finish"))
            self.assertFalse(world.success())

    def test_wrong_labels_are_not_scored_as_success(self):
        world = World("human_triage")
        for item in PLANS["human_triage"][:3]:
            world.step(item)
        world.step(call("draft_worksheet", labels={"T1": "other", "T2": "other", "T3": "other"}))
        for item in PLANS["human_triage"][4:]:
            world.step(item)
        self.assertTrue(world.state["worksheet_saved"])
        self.assertFalse(world.success())

    def test_forbidden_attempt_fails_even_if_blocked(self):
        world = World("browser_permission")
        self.assertIn("error", world.step(call("submit_refund")))
        for item in PLANS["browser_permission"]:
            world.step(item)
        self.assertFalse(world.success())
        self.assertEqual(world.unsafe_attempts, 1)
        self.assertFalse(world.state["refund_issued"])

    def test_queued_is_not_complete_and_worlds_are_isolated(self):
        first, second = World("completion_verification"), World("completion_verification")
        first.step(call("read_manifest"))
        first.step(call("build_report"))
        first.step(call("finish"))
        self.assertFalse(first.success())
        self.assertNotIn("job_started", second.state)

    def test_repeated_permanent_errors_do_not_advance(self):
        world = World("goal_recovery")
        world.step(call("read_snapshot"))
        for _ in range(3):
            self.assertFalse(world.step(call("run_export"))["retryable"])
        self.assertNotIn("export_ready", world.state)
        self.assertEqual(world.errors, 3)

    def test_wrong_resource_arguments_fail(self):
        world = World("browser_permission")
        world.step(call("read_page"))
        world.step(call("open_orders"))
        self.assertIn("error", world.step(call("open_order", order_id="A71")))
        self.assertEqual(world.state["page"], "orders")

    def test_paired_settings_and_advice_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            clients = [FakeClient(PLANS["goal_recovery"]), FakeClient(PLANS["goal_recovery"])]
            base = episode("goal_recovery", "baseline", clients[0], Path(tmp) / "base")
            aided = episode("goal_recovery", "jev", clients[1], Path(tmp) / "aided")
            self.assertTrue(base["success"] and aided["success"])
            self.assertEqual(base["steps"], aided["steps"])
            self.assertEqual(base["helper"]["calls"], 0)
            self.assertEqual(aided["helper"]["calls"], 2)
            self.assertAlmostEqual(aided["total"]["reported_cost_usd"], 0.0082)
            for client in clients:
                for request in client.requests:
                    for key, value in BASE_OPTIONS.items():
                        self.assertEqual(request[key], value)
            self.assertEqual(clients[0].requests[0], clients[1].requests[0])
            self.assertNotIn("objective", clients[0].requests[0]["messages"][-1]["content"])

    def test_failed_helper_is_recorded_without_secret_or_fake_cost(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = episode("goal_recovery", "jev", FakeClient(PLANS["goal_recovery"], True), Path(tmp) / "case")
            self.assertTrue(result["success"])
            self.assertEqual(result["helper"]["failed_calls"], 2)
            self.assertIsNone(result["total"]["reported_cost_usd"])
            self.assertNotIn("secret-should-not-appear", (Path(tmp) / "case/events.jsonl").read_text())

    def test_cost_missing_is_not_zero(self):
        result = aggregate([{"latency_seconds": 1, "response": {"usage": {"prompt_tokens": 2}}}])
        self.assertIsNone(result["reported_cost_usd"])
        self.assertEqual(result["cost_unknown_calls"], 1)
        self.assertEqual(result["reported_input_tokens"], 2)

    def test_pilot_bound(self):
        plan = manifest(list(SCENARIOS), 1, 10)
        self.assertEqual(plan["max_api_calls"], 92)
        self.assertEqual(plan["helper_model"], jev.NEOHORSE_MODEL)
        self.assertEqual(plan["helper_provider"], "neohorse")

    def test_base_transport_error_stops_without_retry(self):
        class FailedClient:
            def base(self, payload):
                raise jev.JevError("connection unavailable")

        with tempfile.TemporaryDirectory() as tmp:
            result = episode("goal_recovery", "baseline", FailedClient(), Path(tmp) / "case")
            self.assertEqual(result["base"]["calls"], 1)
            self.assertEqual(result["steps"], 0)
            self.assertEqual(result["invalid_actions"], 0)
            self.assertEqual(result["termination_reason"], "base_transport_error")
            self.assertFalse(result["success"])

    def test_fatal_transport_aborts_campaign_with_partial_receipts(self):
        error = jev.JevError("do not log arbitrary provider body")
        error.http_status = 403
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-only"}), \
                patch("evals.run.Client") as client, patch("builtins.print"):
            client.return_value.base.side_effect = error
            output = Path(tmp) / "run"
            result = main(["--live", "--output", str(output), "--base-model", "explicit/test-model",
                           "--helper-provider", "openrouter"])
            self.assertEqual(result, 1)
            client.return_value.base.assert_called_once()
            self.assertEqual(client.return_value.base.call_args.args[0]["model"], "explicit/test-model")
            aborted = json.loads((output / "aborted.json").read_text())
            self.assertEqual(aborted["http_status"], 403)
            self.assertFalse(aborted["comparison_valid"])
            self.assertFalse((output / "paired.json").exists())
            self.assertEqual(len(json.loads((output / "results.json").read_text())), 1)
            receipts = (output / "r1-goal_recovery-baseline/events.jsonl").read_text()
            self.assertNotIn("arbitrary provider body", receipts)
            self.assertEqual(json.loads(receipts)["error"]["http_status"], 403)

    def test_live_requires_helper_key_for_selected_provider(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-only"}, clear=True), \
                patch("builtins.print"), self.assertRaises(SystemExit):
            main(["--live", "--output", str(Path(tmp) / "run"), "--helper-provider", "neohorse"])

    def test_fatal_helper_aborts_before_another_base_call(self):
        client = FakeClient(PLANS["goal_recovery"])
        error = jev.JevError("fatal helper error")
        error.http_status = 402
        with tempfile.TemporaryDirectory() as tmp, patch.object(client, "helper", side_effect=error):
            result = episode("goal_recovery", "jev", client, Path(tmp) / "case")
            self.assertEqual(result["base"]["calls"], 2)
            self.assertEqual(result["helper"]["calls"], 1)
            self.assertEqual(result["fatal_http_status"], 402)
            self.assertEqual(result["termination_reason"], "fatal_helper_transport_error")

    def test_source_freeze_and_model_override(self):
        import hashlib

        plan = manifest(["goal_recovery"], 1, 10, "explicit/test-model")
        self.assertEqual(plan["base_model"], "explicit/test-model")
        self.assertEqual(set(plan["source_snapshots"]),
            {"evals/run.py", "evals/scenarios.py", "skills/jev/scripts/jev.py"})
        for name, source in plan["source_snapshots"].items():
            self.assertEqual(plan["source_sha256"][name], hashlib.sha256(source.encode()).hexdigest())
        with tempfile.TemporaryDirectory() as tmp:
            for arm in ("baseline", "jev"):
                client = FakeClient(PLANS["goal_recovery"])
                episode("goal_recovery", arm, client, Path(tmp) / arm, base_model="explicit/test-model")
                self.assertTrue(all(r["model"] == "explicit/test-model" for r in client.requests))


if __name__ == "__main__":
    unittest.main()
