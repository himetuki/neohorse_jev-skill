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


def sentinel(name):
    """Obviously fake stand-in for presence checks; never a real credential."""
    return f"presence-check-{name.lower()}"


class SetupTests(unittest.TestCase):
    def test_setup_is_read_only_and_does_not_expose_keys(self):
        for env, recommendation in [({}, None),
                                    ({"OPENROUTER_API_KEY": sentinel("OPENROUTER_API_KEY")}, "openrouter"),
                                    ({"TYPESAFE_API_KEY": sentinel("TYPESAFE_API_KEY")}, "typesafe"),
                                    ({"NEO_HORSE_API_KEY": sentinel("NEO_HORSE_API_KEY")}, "neohorse"),
                                    ({"OPENROUTER_API_KEY": sentinel("OPENROUTER_API_KEY"),
                                      "TYPESAFE_API_KEY": sentinel("TYPESAFE_API_KEY")}, "openrouter")]:
            output = io.StringIO()
            with patch.dict(os.environ, env, clear=True), patch("jev.urllib.request.build_opener") as network, \
                    contextlib.redirect_stdout(output):
                self.assertEqual(jev.main(["setup"]), 0)
                network.assert_not_called()
            result = json.loads(output.getvalue())
            self.assertEqual(result["recommended_provider"], recommendation)
            self.assertTrue(result["requires_user_choice"])
            self.assertFalse(result["jev_called"])
            self.assertNotIn("presence-check", output.getvalue())

    def test_explicit_typesafe_uses_only_typesafe_credential(self):
        payload = {"model": "jev-1.13.0", "state": "fixture", "questions": {
            "q": {"type": "noul", "instructions": "Does the evidence support the claim?"}}}
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": sentinel("TYPESAFE_API_KEY"),
                                     "OPENROUTER_API_KEY": sentinel("OPENROUTER_API_KEY")}, clear=True), \
                patch("jev.urllib.request.build_opener") as opener:
            opener.return_value.open.return_value.__enter__.return_value.read.return_value = b'{"answers":{}}'
            jev.request_decisions(payload, provider="typesafe")
            sent = opener.return_value.open.call_args.args[0]
            self.assertEqual(sent.full_url, "https://api.typesafe.ai/v1/systemone")
            self.assertEqual(sent.get_header("Authorization"),
                             f"Bearer {sentinel('TYPESAFE_API_KEY')}")
            self.assertEqual(json.loads(sent.data), payload)
            opener.return_value.open.assert_called_once()

    def test_no_key_or_http_error_never_falls_back(self):
        payload = {"model": "jev-1.13.0", "state": "fixture", "questions": {
            "q": {"type": "noul", "instructions": "Judge this fixture."}}}
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": sentinel("OPENROUTER_API_KEY")}, clear=True), \
                patch("jev.urllib.request.build_opener") as opener:
            with self.assertRaises(jev.JevError):
                jev.request_decisions(payload, provider="typesafe")
            opener.assert_not_called()
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": sentinel("TYPESAFE_API_KEY")}, clear=True), \
                patch("jev.urllib.request.build_opener") as opener:
            opener.return_value.open.side_effect = urllib.error.HTTPError(
                "https://api.typesafe.ai/v1/systemone", 403, "Denied", {}, io.BytesIO(b"provider-body"))
            with self.assertRaises(jev.JevError) as error:
                jev.request_decisions(payload, provider="typesafe")
            self.assertNotIn("presence-check", str(error.exception))
            self.assertNotIn("provider-body", str(error.exception))
            opener.return_value.open.assert_called_once()

    def test_explicit_typesafe_dry_run_maps_only_known_bundled_model(self):
        payload = {"model": jev.DEFAULT_MODEL, "state": "fixture", "questions": {
            "q": {"type": "noul", "instructions": "Judge this fixture."}}}
        for extra, expected in [([], "jev-1.13.0"), (["--model", "jev-latest"], "jev-latest")]:
            output = io.StringIO()
            with patch.dict(os.environ, {}, clear=True), patch("sys.stdin", io.StringIO(json.dumps(payload))), \
                    patch("jev.request_decisions") as network, contextlib.redirect_stdout(output):
                self.assertEqual(jev.main(["decide", "-", "--provider", "typesafe", "--dry-run", *extra]), 0)
                network.assert_not_called()
            self.assertEqual(json.loads(output.getvalue())["model"], expected)


class NeoHorseRouteTests(unittest.TestCase):
    """The fork's default real route: NeoHorse-Jev-4B on tokenrhythm.studio."""

    PUBLIC_DNS = [(2, 1, 6, "", ("93.184.216.34", 443))]

    def question_payload(self):
        return {"model": jev.NEOHORSE_MODEL, "state": "fixture", "questions": {
            "q": {"type": "noul", "instructions": "Does the evidence support the claim?"}}}

    def test_presence_recommends_neohorse_without_exposing_key(self):
        output = io.StringIO()
        with patch.dict(os.environ, {"NEO_HORSE_API_KEY": sentinel("NEO_HORSE_API_KEY")}, clear=True), \
                patch("jev.urllib.request.build_opener") as network, contextlib.redirect_stdout(output):
            self.assertEqual(jev.main(["setup"]), 0)
            network.assert_not_called()
        result = json.loads(output.getvalue())
        self.assertEqual(result["recommended_provider"], "neohorse")
        self.assertTrue(result["available"]["neohorse"])
        self.assertFalse(result["jev_called"])
        self.assertNotIn("presence-check", output.getvalue())

    def test_explicit_neohorse_uses_only_neohorse_credential(self):
        with patch.dict(os.environ, {"NEO_HORSE_API_KEY": sentinel("NEO_HORSE_API_KEY"),
                                     "OPENROUTER_API_KEY": sentinel("OPENROUTER_API_KEY")}, clear=True), \
                patch("jev.socket.getaddrinfo", return_value=self.PUBLIC_DNS), \
                patch("jev.urllib.request.build_opener") as opener:
            opener.return_value.open.return_value.__enter__.return_value.read.return_value = b'{"answers":{}}'
            payload = self.question_payload()
            jev.request_decisions(payload, provider="neohorse")
            sent = opener.return_value.open.call_args.args[0]
            self.assertEqual(sent.full_url, jev.NEOHORSE_URL)
            self.assertEqual(sent.get_header("Authorization"),
                             f"Bearer {sentinel('NEO_HORSE_API_KEY')}")
            self.assertEqual(json.loads(sent.data), payload)
            opener.return_value.open.assert_called_once()

    def test_no_key_or_http_error_never_falls_back(self):
        payload = self.question_payload()
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": sentinel("OPENROUTER_API_KEY")}, clear=True), \
                patch("jev.urllib.request.build_opener") as opener:
            with self.assertRaises(jev.JevError):
                jev.request_decisions(payload, provider="neohorse")
            opener.assert_not_called()
        with patch.dict(os.environ, {"NEO_HORSE_API_KEY": sentinel("NEO_HORSE_API_KEY")}, clear=True), \
                patch("jev.socket.getaddrinfo", return_value=self.PUBLIC_DNS), \
                patch("jev.urllib.request.build_opener") as opener:
            opener.return_value.open.side_effect = urllib.error.HTTPError(
                jev.NEOHORSE_URL, 403, "Denied", {}, io.BytesIO(b"provider-body"))
            with self.assertRaises(jev.JevError) as error:
                jev.request_decisions(payload, provider="neohorse")
            self.assertNotIn("presence-check", str(error.exception))
            self.assertNotIn("provider-body", str(error.exception))
            opener.return_value.open.assert_called_once()

    def test_explicit_neohorse_dry_run_maps_only_known_bundled_model(self):
        payload = {"model": jev.DEFAULT_MODEL, "state": "fixture", "questions": {
            "q": {"type": "noul", "instructions": "Judge this fixture."}}}
        for extra, expected in [([], jev.NEOHORSE_MODEL), (["--model", "custom-model"], "custom-model")]:
            output = io.StringIO()
            with patch.dict(os.environ, {}, clear=True), patch("sys.stdin", io.StringIO(json.dumps(payload))), \
                    patch("jev.request_decisions") as network, contextlib.redirect_stdout(output):
                self.assertEqual(jev.main(["decide", "-", "--provider", "neohorse", "--dry-run", *extra]), 0)
                network.assert_not_called()
            self.assertEqual(json.loads(output.getvalue())["model"], expected)


if __name__ == "__main__":
    unittest.main()
