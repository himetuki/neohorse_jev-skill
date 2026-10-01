import contextlib
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/jev/scripts"))
import jev


def request(kind="choice"):
    question = {"type": kind, "instructions": "Judge the evidence."}
    if kind == "choice":
        question["criteria"] = {"continue": "Enough evidence", "review": "Unclear"}
    elif kind == "score":
        question["criteria"] = ["Low", "Medium", "High"]
    return {"model": jev.DEFAULT_MODEL, "state": {"evidence": "Synthetic"}, "questions": {"q": question}}


def choice(label="continue", probability=0.95):
    return {"answers": {"q": {"type": "choice", "choice": label,
                              "probabilities": {"continue": probability, "review": 1 - probability},
                              "confidence": 0.01}}, "usage": {"cost": 0.001}}


def call_cli(args, payload):
    output, errors = io.StringIO(), io.StringIO()
    with patch("sys.stdin", io.StringIO(json.dumps(payload))), \
            contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
        code = jev.main(args)
    return code, output.getvalue(), errors.getvalue()


class RequestTests(unittest.TestCase):
    def test_all_types(self):
        for kind in ["choice", "score", "noul"]:
            self.assertEqual(jev.validate_request(request(kind)), request(kind))

    def test_noul_criteria(self):
        value = request("noul")
        value["questions"]["q"]["criteria"] = {"true": "Established", "false": "Not established"}
        jev.validate_request(value)
        value["questions"]["q"]["criteria"].pop("false")
        with self.assertRaises(jev.JevError):
            jev.validate_request(value)

    def test_reject_bad_requests(self):
        for payload in [[], {}, {**request(), "messages": []}, {**request(), "questions": {}},
                        {**request(), "state": None}, {**request(), "state": True},
                        {**request(), "state": 42}, {**request(), "model": ""}]:
            with self.subTest(payload=payload), self.assertRaises(jev.JevError):
                jev.validate_request(payload)
        for kind, criteria in [("choice", []), ("choice", {"one": "only"}),
                               ("score", ["one"]), ("score", list(range(11))),
                               ("noul", None), ("text", {}), ("score", [1, 2]),
                               ("choice", {"a": 1, "b": 2})]:
            payload = request()
            payload["questions"]["q"].update(type=kind, criteria=criteria)
            with self.subTest(kind=kind), self.assertRaises(jev.JevError):
                jev.validate_request(payload)

    def test_nonfinite_json(self):
        for value in ["NaN", "Infinity", "-Infinity"]:
            with self.assertRaises(jev.JevError):
                jev.load_json('{"value":' + value + '}')

    def test_assets_valid(self):
        assets = Path(__file__).resolve().parents[1] / "skills/jev/assets"
        for path in assets.glob("*.json"):
            payload = json.loads(path.read_text())
            if "questions" in payload:
                with self.subTest(path=path.name):
                    jev.validate_request({"model": jev.DEFAULT_MODEL, **payload})


class ReportTests(unittest.TestCase):
    def test_uses_probability_not_api_confidence(self):
        report = jev.build_report(request(), choice())
        self.assertEqual(report["decisions"]["q"]["status"], "selected")
        self.assertFalse(report["policy"]["executes_actions"])
        self.assertEqual(report["response"]["usage"]["cost"], 0.001)

    def test_abstains_when_unclear(self):
        for response in [choice(probability=0.6), choice("review", 0.01), choice(probability=0.5)]:
            self.assertEqual(jev.build_report(request(), response)["decisions"]["q"]["status"], "needs_review")

    def test_margin(self):
        self.assertEqual(jev.build_report(request(), choice(probability=0.8), min_margin=0.7)
                         ["decisions"]["q"]["status"], "needs_review")

    def test_bad_response(self):
        for response in [{}, {"answers": {}}, {"answers": {"q": {"type": "score"}}},
                         choice("missing"), choice(probability=float("nan")), choice(probability=True),
                         choice(probability=1.5), choice("review", 0.99)]:
            with self.subTest(response=response), self.assertRaises(jev.JevError):
                jev.build_report(request(), response)

    def test_missing_distribution_label(self):
        response = choice()
        response["answers"]["q"]["probabilities"].pop("review")
        with self.assertRaises(jev.JevError):
            jev.build_report(request(), response)

    def test_invalid_distribution_not_selected(self):
        response = choice()
        response["answers"]["q"]["probabilities"] = {"continue": 1, "review": 0.5}
        with self.assertRaises(jev.JevError):
            jev.build_report(request(), response)

    def test_defer_needs_review(self):
        payload = request()
        payload["questions"]["q"]["criteria"] = {"work": "Work", "defer": "Not enough evidence"}
        response = {"answers": {"q": {"type": "choice", "choice": "defer",
                    "probabilities": {"work": 0, "defer": 1}, "confidence": 1}}}
        self.assertEqual(jev.build_report(payload, response)["decisions"]["q"]["status"], "needs_review")

    def test_large_candidate_set_cannot_hide_invalid_distribution(self):
        payload = request()
        payload["questions"]["q"]["criteria"] = {f"c{i}": "Candidate" for i in range(255)}
        response = {"answers": {"q": {"type": "choice", "choice": "c0", "confidence": 1,
                    "probabilities": {f"c{i}": 1 if i == 0 else 0.004 for i in range(255)}}}}
        with self.assertRaises(jev.JevError):
            jev.build_report(payload, response)

    def test_noul_true_false_and_uncertain(self):
        for probability, value, status in [(0.98, True, "selected"), (0.02, False, "selected"),
                                           (0.5, False, "needs_review"), (0.7, True, "needs_review")]:
            result = jev.build_report(request("noul"), {"answers": {"q": {"type": "noul", "noul": probability}}})
            self.assertEqual((result["decisions"]["q"]["value"], result["decisions"]["q"]["status"]), (value, status))

    def test_score_not_probability(self):
        def response(score):
            return {"answers": {"q": {"type": "score", "score": score,
                    "probabilities": {"0": 0, "1": 0.25, "2": 0.75},
                    "legend": {"0": "Low", "1": "Medium", "2": "High"}, "confidence": 0.5}}}
        result = jev.build_report(request("score"), response(1.75))
        self.assertEqual(result["decisions"]["q"], {"status": "scored", "value": 1.75, "levels": ["Low", "Medium", "High"]})
        for score in [True, -1, 3, float("inf")]:
            with self.assertRaises(jev.JevError):
                jev.build_report(request("score"), response(score))
        with self.assertRaises(jev.JevError):
            jev.build_report(request("score"), {"answers": {"q": {"type": "score", "score": 1}}})


class TransportTests(unittest.TestCase):
    def test_malformed_key_is_rejected_without_leaking_it(self):
        for key in ["secret-first\nsecret-second", "secret\rheader", "secret key", "secret-密钥"]:
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": key}), patch("jev.urllib.request.build_opener") as opener:
                with self.assertRaises(jev.JevError) as error:
                    jev.request_decisions(request())
                self.assertNotIn("secret", str(error.exception))
                opener.assert_not_called()

    def test_missing_key_before_network(self):
        with patch.dict(os.environ, {}, clear=True), patch("jev.urllib.request.build_opener") as opener:
            with self.assertRaises(jev.JevError):
                jev.request_decisions(request())
            opener.assert_not_called()

    def test_refuses_other_endpoints_and_redirects(self):
        with self.assertRaises(jev.JevError):
            jev.http_json("https://untrusted.example/", request())
        self.assertIsNone(jev.NoRedirect().redirect_request(None, None, 302, "", {}, "https://untrusted.example/"))

    def test_correct_endpoint_auth_and_no_retries(self):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "secret-test"}), patch("jev.urllib.request.build_opener") as opener:
            response = opener.return_value.open.return_value.__enter__.return_value
            response.read.return_value = json.dumps(choice()).encode()
            jev.request_decisions(request())
            sent = opener.return_value.open.call_args.args[0]
            self.assertEqual(sent.full_url, jev.DECISIONS_URL)
            self.assertEqual(sent.get_header("Authorization"), "Bearer secret-test")
            self.assertEqual(json.loads(sent.data), request())
            opener.return_value.open.assert_called_once()

    def test_error_does_not_print_provider_body_or_key(self):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "secret-test"}), patch("jev.urllib.request.build_opener") as opener:
            opener.return_value.open.side_effect = urllib.error.HTTPError(
                jev.DECISIONS_URL, 429, "secret-test", {}, io.BytesIO(b"private-record"))
            with self.assertRaisesRegex(jev.JevError, "HTTP 429") as error:
                jev.request_decisions(request())
            self.assertNotIn("secret-test", str(error.exception))
            self.assertNotIn("private-record", str(error.exception))
            self.assertEqual(error.exception.http_status, 429)
            opener.return_value.open.assert_called_once()


class CLITests(unittest.TestCase):
    def test_usage_error_is_not_review_exit(self):
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors), self.assertRaises(SystemExit) as stopped:
            jev.main(["decide"])
        self.assertEqual(stopped.exception.code, 1)
        self.assertIn("error", json.loads(errors.getvalue()))

    def test_dry_run_never_calls_network(self):
        with patch("jev.request_decisions") as api:
            code, output, _ = call_cli(["decide", "-", "--dry-run"], request())
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(output), request())
            api.assert_not_called()

    def test_missing_key_does_not_simulate_decisions(self):
        for environment in ({}, {"OPENROUTER_API_KEY": ""}):
            with self.subTest(environment=environment), \
                    patch.dict(os.environ, environment, clear=True), \
                    patch("jev.urllib.request.build_opener") as opener:
                code, output, errors = call_cli(["decide", "-"], request())
                self.assertEqual(code, 1)
                self.assertEqual(output, "")
                self.assertIn("OPENROUTER_API_KEY", json.loads(errors)["error"])
                opener.assert_not_called()

    def test_bad_threshold_no_spend(self):
        with patch("jev.request_decisions") as api:
            code, _, _ = call_cli(["decide", "-", "--min-probability", "nan"], request())
            self.assertEqual(code, 1)
            api.assert_not_called()

    def test_exit_review(self):
        with patch("jev.request_decisions", return_value=choice(probability=0.6)):
            code, output, _ = call_cli(["decide", "-"], request())
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(output)["decisions"]["q"]["status"], "needs_review")

    def test_empty_request(self):
        code, output, errors = call_cli(["decide", "-"], [])
        self.assertEqual(code, 1)
        self.assertEqual(output, "")
        self.assertIn("error", json.loads(errors))


class NeoHorseTests(unittest.TestCase):
    """The fork's default real route: NeoHorse-Jev-4B on tokenrhythm.studio."""

    def test_dry_run_maps_bundled_model_id(self):
        with patch("jev.request_decisions") as api:
            code, output, _ = call_cli(["decide", "-", "--provider", "neohorse", "--dry-run"], request())
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(output)["model"], jev.NEOHORSE_MODEL)
            api.assert_not_called()

    def test_bundled_model_id_mapped_on_live_path(self):
        with patch("jev.request_decisions", return_value=choice()) as api:
            call_cli(["decide", "-", "--provider", "neohorse"], request())
            self.assertEqual(api.call_args.args[0]["model"], jev.NEOHORSE_MODEL)

    def test_model_override_is_never_rewritten(self):
        payload = request()
        payload["model"] = "custom-model"
        with patch("jev.request_decisions", return_value=choice()) as api:
            call_cli(["decide", "-", "--provider", "neohorse"], payload)
            self.assertEqual(api.call_args.args[0]["model"], "custom-model")
        code, output, _ = call_cli(["decide", "-", "--provider", "neohorse", "--dry-run"], payload)
        self.assertEqual(json.loads(output)["model"], "custom-model")

    def test_missing_key_before_network(self):
        with patch.dict(os.environ, {}, clear=True), patch("jev.urllib.request.build_opener") as opener:
            with self.assertRaises(jev.JevError) as error:
                jev.request_decisions(request(), provider="neohorse")
            self.assertIn("NEO_HORSE_API_KEY", str(error.exception))
            opener.assert_not_called()

    def test_uses_documented_endpoint_without_openrouter_header(self):
        with patch.dict(os.environ, {"NEO_HORSE_API_KEY": "secret-test"}), \
                patch("jev.check_public_endpoint"), \
                patch("jev.urllib.request.build_opener") as opener:
            response = opener.return_value.open.return_value.__enter__.return_value
            response.read.return_value = json.dumps(choice()).encode()
            jev.request_decisions(request(), provider="neohorse")
            sent = opener.return_value.open.call_args.args[0]
            self.assertEqual(sent.full_url, jev.NEOHORSE_URL)
            self.assertEqual(sent.get_header("Authorization"), "Bearer secret-test")
            self.assertIsNone(sent.get_header("X-openrouter-title"))

    def test_unknown_provider_rejected(self):
        with self.assertRaises(jev.JevError):
            jev.request_decisions(request(), provider="untrusted")

    def test_guard_rejects_non_https_and_foreign_host(self):
        for url in ["http://tokenrhythm.studio/v1/decision", "https://untrusted.example/",
                    "https://tokenrhythm.studio.evil.example/v1/decision"]:
            with self.subTest(url=url), self.assertRaises(jev.JevError):
                jev.check_public_endpoint(url)

    def test_guard_rejects_private_resolution(self):
        for address in ["127.0.0.1", "10.0.0.5", "192.168.1.10", "169.254.169.254", "::1", "fd00::1"]:
            with self.subTest(address=address), \
                    patch("jev.socket.getaddrinfo", return_value=[(2, 1, 6, "", (address, 443))]):
                with self.assertRaisesRegex(jev.JevError, "blocked address"):
                    jev.check_public_endpoint(jev.NEOHORSE_URL)

    def test_guard_accepts_public_resolution(self):
        with patch("jev.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]):
            jev.check_public_endpoint(jev.NEOHORSE_URL)

    def test_guard_blocks_request_before_network(self):
        with patch.dict(os.environ, {"NEO_HORSE_API_KEY": "secret-test"}), \
                patch("jev.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 443))]), \
                patch("jev.urllib.request.build_opener") as opener:
            with self.assertRaises(jev.JevError):
                jev.request_decisions(request(), provider="neohorse")
            opener.assert_not_called()

    def test_setup_reports_presence_only(self):
        with patch.dict(os.environ, {"NEO_HORSE_API_KEY": "secret-test"}, clear=True):
            report = jev.setup_report()
        self.assertEqual(report["available"], {"openrouter": False, "typesafe": False, "neohorse": True})
        self.assertNotIn("secret-test", json.dumps(report))

    def test_documented_reduced_answer_shapes_accepted(self):
        payload = {"model": jev.NEOHORSE_MODEL, "state": {"evidence": "Synthetic"}, "questions": {
            "route": {"type": "choice", "instructions": "Pick a route.", "criteria": {"a": "Route A", "b": "Route B"}},
            "stop": {"type": "noul", "instructions": "Should we stop?"},
            "risk": {"type": "score", "instructions": "Rate the risk.", "criteria": ["Low", "High"]}}}
        response = {"answers": {
            "route": {"choice": "a", "probabilities": {"a": 0.9, "b": 0.1}},
            "stop": {"noul": 0.2},
            "risk": {"score": 1}}}
        report = jev.build_report(payload, response, provider="neohorse")
        self.assertEqual(report["decisions"]["route"]["value"], "a")
        self.assertFalse(report["decisions"]["stop"]["value"])
        self.assertEqual(report["decisions"]["risk"]["value"], 1)

    def test_other_providers_still_require_full_answer_shape(self):
        payload = {"model": jev.DEFAULT_MODEL, "state": {"evidence": "Synthetic"}, "questions": {
            "risk": {"type": "score", "instructions": "Rate the risk.", "criteria": ["Low", "High"]}}}
        with self.assertRaisesRegex(jev.JevError, "legend"):
            jev.build_report(payload, {"answers": {"risk": {"type": "score", "score": 1}}}, provider="openrouter")


if __name__ == "__main__":
    unittest.main()
