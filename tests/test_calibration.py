import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evals import calibration as c


class CalibrationRunnerTests(unittest.TestCase):
    def fixture(self, root):
        samples = [{"id": task + ":0", "task": task, "input": "Question\nOptions:\n(A) First\n(B) Second",
                    "target": "(A)", "criteria": {"(A)": "First", "(B)": "Second"}} for task in c.TASKS]
        c.dump(root / "samples.json", samples)
        plan = {"jev_model": "fake-jev", "base_model": "fake-base", "instructions": c.INSTRUCTIONS,
                "base_system": c.BASE_SYSTEM, "base_options": c.BASE_OPTIONS, "source_sha256": {},
                "samples_sha256": c.digest((root / "samples.json").read_bytes())}
        c.dump(root / "manifest.json", plan)
        return samples, plan

    def jev_response(self, payload, provider=None, **kwargs):
        # The fork's calibration runner pins the NeoHorse helper transport.
        self.assertEqual(provider, "neohorse")
        return {"answers": {"answer": {"type": "choice", "choice": "(A)", "confidence": 0.6,
            "probabilities": {"(A)": 0.8, "(B)": 0.2}}}, "usage": {"cost": 0.001}}

    def base_response(self, url, payload):
        return {"choices": [{"message": {"content": '{"choice":"(A)"}'}}], "usage": {"cost": 0.002}}

    def test_native_options(self):
        self.assertEqual(c.criteria("Options:\n(A) One\n(B) Two"), {"(A)": "One", "(B)": "Two"})
        self.assertEqual(c.criteria("Question\nOptions:\n- Yes\n- No"), {"Yes": "Yes", "No": "No"})
        with self.assertRaises(ValueError):
            c.criteria("invent some options")

    def test_payload_has_no_gold(self):
        with tempfile.TemporaryDirectory() as tmp:
            samples, plan = self.fixture(Path(tmp))
            for kind in ("jev", "base"):
                first = c.payload_for(samples[0], kind, plan)
                samples[0]["target"] = "GOLD_SENTINEL"
                self.assertEqual(first, c.payload_for(samples[0], kind, plan))
                self.assertNotIn("GOLD_SENTINEL", json.dumps(first))

    def test_complete_fake_campaign_and_routes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            with patch.object(c.jev, "request_decisions", self.jev_response), patch.object(c.jev, "http_json", self.base_response):
                result = c.run(root)
                self.assertEqual(result["base"]["overall"]["correct"], 4)
                self.assertEqual(result["cascade"]["top_probability"]["buckets"]["base"]["n"], 4)
                self.assertEqual(result["cascade"]["confidence"]["human_items_unresolved"], 4)
                self.assertEqual(result["cascade"]["confidence"]["correct_over_all_items"], 0)
                self.assertEqual(result["usage"]["jev"]["calls"], 4)
                with self.assertRaises(FileExistsError):
                    c.run(root)

    def test_selected_base_failure_is_unresolved_and_counted_wrong(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            with patch.object(c.jev, "request_decisions", self.jev_response), patch.object(
                    c.jev, "http_json", side_effect=c.jev.JevError("unavailable", http_status=500)):
                result = c.run(root)
            route = result["cascade"]["top_probability"]
            self.assertEqual(route["automatic_attempted_coverage"], 1)
            self.assertEqual(route["automatic_valid_coverage"], 0)
            self.assertEqual(route["automatic_errors_unresolved"], 4)
            self.assertEqual(route["automatic_accuracy"], 0)
            self.assertEqual(result["base"]["overall"]["accuracy"], 0)

    def test_summary_rejects_tampered_derived_prediction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            with patch.object(c.jev, "request_decisions", self.jev_response), patch.object(c.jev, "http_json", self.base_response):
                c.run(root)
            path = root / "events.jsonl"
            events = [json.loads(line) for line in path.read_text().splitlines()]
            events[0]["prediction"] = "(B)"
            path.write_text("\n".join(json.dumps(event) for event in events) + "\n")
            with self.assertRaisesRegex(ValueError, "raw response"):
                c.summarize_run(root)

    def test_fatal_error_stops_and_keeps_sanitized_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            with patch.object(c.jev, "request_decisions", side_effect=c.jev.JevError("SECRET", http_status=403)) as request:
                with self.assertRaises(ValueError):
                    c.run(root)
                self.assertEqual(request.call_count, 1)
            self.assertTrue((root / "aborted.json").exists())
            self.assertNotIn("SECRET", (root / "events.jsonl").read_text())
            with self.assertRaises(ValueError):
                c.summarize_run(root)

    def test_changed_sample_fails_before_api(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            with (root / "samples.json").open("a") as handle:
                handle.write("\n")
            with self.assertRaisesRegex(ValueError, "Samples changed"):
                c.run(root)
            self.assertFalse((root / "events.jsonl").exists())

    def test_partial_and_duplicate_not_completed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            (root / "events.jsonl").write_text("")
            with self.assertRaises(ValueError):
                c.summarize_run(root)

    def test_invalid_base_choice(self):
        with tempfile.TemporaryDirectory() as tmp:
            sample = self.fixture(Path(tmp))[0][0]
            for content in ('{"choice":"invented"}', '{"choice":["(A)"]}', '{"choice":"(A)","extra":0}'):
                with self.subTest(content=content), self.assertRaises((ValueError, TypeError)):
                    c.parse_prediction(sample, "base", {}, {"choices": [{"message": {"content": content}}]})


if __name__ == "__main__":
    unittest.main()
