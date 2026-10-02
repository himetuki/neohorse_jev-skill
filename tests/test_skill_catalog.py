import contextlib
import io
import json
import re
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/jev/scripts"))
import jev


SCENARIOS = (
    "jev-triage", "jev-documents", "jev-ui", "jev-route",
    "jev-context", "jev-code-review", "jev-find-code", "jev-simulation", "jev-redteam",
)


class SkillCatalogTests(unittest.TestCase):
    def test_setup_and_all_skills_keep_explicit_modes(self):
        folders = list((ROOT / "skills").glob("*/SKILL.md"))
        self.assertEqual(len(folders), 11)
        for path in folders:
            text = path.read_text()
            for term in ("OPENROUTER_API_KEY", "TYPESAFE_API_KEY", "agent_simulation",
                         "model_simulation", "jev_called", "DeepSeek"):
                self.assertIn(term, text, str(path))
        self.assertTrue((ROOT / "skills/jev-setup/references/simulation.md").is_file())

    def test_new_collection_covers_all_supplied_roundups(self):
        ledger = (ROOT / "skills/jev/references/intake-2026-09-21.md").read_text()
        rows = re.findall(r"^\| (\d+) \|", ledger, re.M)
        self.assertEqual(len(rows), 39 + 15 + 22)
        for filename in ("README.md", "README.zh.md"):
            text = (ROOT / filename).read_text()
            section = text.split('<a id="projects"></a>', 1)[1].split('<a id="catalog"></a>', 1)[0]
            self.assertEqual(len(re.findall(r"^\| ", section, re.M)) - 1, 45)
            self.assertEqual(len(re.findall(r"^### \d+\.", text, re.M)), 108)

    def test_agent_first_installation_entrypoint(self):
        guide_url = "https://raw.githubusercontent.com/himetuki/neohorse_jev-skill/main/docs/install.md"
        for filename in ("README.md", "README.zh.md"):
            text = (ROOT / filename).read_text()
            first_block = re.search(r"```(\w*)\n(.*?)\n```", text, re.S)
            self.assertEqual(first_block.group(1), "text")
            self.assertIn(guide_url, first_block.group(2))
            self.assertLess(text.index(guide_url), text.index('id="agent"'))
        guide = (ROOT / "docs/install.md").read_text()
        for name in ("jev", *SCENARIOS):
            self.assertIn(f"`{name}`", guide)
        for requirement in ("OPENROUTER_API_KEY", "--dry-run", "v0.2.0"):
            self.assertIn(requirement, guide)

    def test_all_skills_teach_context_and_parallelism(self):
        for name in ("jev", *SCENARIOS):
            with self.subTest(skill=name):
                text = " ".join((ROOT / "skills" / name / "SKILL.md").read_text().lower().split())
                for requirement in ("context", "does not inherit", "independent",
                                    "bounded concurrency", "same request"):
                    self.assertIn(requirement, text)

    def test_readme_usage_explains_agent_prompts_and_manual_calls(self):
        for filename in ("README.md", "README.zh.md"):
            text = (ROOT / filename).read_text()
            self.assertTrue('<a id="usage"></a>' in text, filename)
            usage = text.split('<a id="usage"></a>', 1)[1].split('<a id="io"></a>', 1)[0]
            self.assertEqual(len(re.findall(r"```text\n", usage)), 3)
            for name in ("jev", *SCENARIOS):
                self.assertIn(f"`{name}`", usage)
            for command in ("jev-decide decide request.json --dry-run",
                            "jev-decide decide request.json > result.json"):
                self.assertIn(command, usage)
            for field in ("OPENROUTER_API_KEY", "state", "questions", "criteria",
                          "choice", "noul", "score"):
                self.assertIn(field, usage)

    def test_readme_input_can_be_saved_and_dry_run_as_documented(self):
        for filename in ("README.md", "README.zh.md"):
            text = (ROOT / filename).read_text()
            match = re.search(r"<!-- request: .*? -->\s*```json\n(.*?)\n```", text, re.S)
            with tempfile.TemporaryDirectory() as tmp:
                request = Path(tmp) / "request.json"
                request.write_text(match.group(1))
                output = io.StringIO()
                with patch.dict("os.environ", {}, clear=True), \
                        patch("urllib.request.urlopen", side_effect=AssertionError("network")), \
                        contextlib.redirect_stdout(output):
                    status = jev.main(["decide", str(request), "--dry-run"])
                self.assertEqual(status, 0)
                self.assertEqual(json.loads(output.getvalue()), json.loads(match.group(1)))

    def test_batch_example_scopes_each_independent_question(self):
        payload = json.loads((ROOT / "skills/jev/assets/batch-triage.json").read_text())
        jev.validate_request(payload)
        records = payload["state"]["records"]
        self.assertEqual(len(records), 2)
        self.assertEqual(len(payload["questions"]), 6)
        for record_id, record in records.items():
            self.assertGreater(len(record["thread"]), 1)
            scoped = {key: value for key, value in payload["questions"].items()
                      if key.startswith(record_id + "_")}
            self.assertEqual({value["type"] for value in scoped.values()},
                             {"choice", "noul", "score"})
            for question in scoped.values():
                self.assertIn(f"state.records.{record_id}", question["instructions"])
                self.assertIn("state.policy", question["instructions"])

    def test_copied_general_skill_batch_example_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "jev"
            shutil.copytree(ROOT / "skills/jev", folder)
            output = io.StringIO()
            with patch.dict("os.environ", {}, clear=True), \
                    patch("urllib.request.urlopen", side_effect=AssertionError("network")), \
                    contextlib.redirect_stdout(output):
                status = jev.main(["decide", str(folder / "assets/batch-triage.json"), "--dry-run"])
            self.assertEqual(status, 0)
            self.assertEqual(len(json.loads(output.getvalue())["questions"]), 6)
            self.assertTrue((folder / "references/context-and-throughput.md").is_file())

    def test_scenario_entrypoints_and_examples(self):
        for name in SCENARIOS:
            with self.subTest(skill=name):
                folder = ROOT / "skills" / name
                text = (folder / "SKILL.md").read_text()
                self.assertIn(f"name: {name}\n", text)
                self.assertIn("description:", text)
                self.assertIn("jev-decide", text)
                self.assertIn("OPENROUTER_API_KEY", text)
                self.assertIn("assets/example.json", text)
                payload = json.loads((folder / "assets/example.json").read_text())
                jev.validate_request(payload)

    def test_installed_scenarios_dry_run_without_sibling_skill(self):
        for name in SCENARIOS:
            with self.subTest(skill=name), tempfile.TemporaryDirectory() as tmp:
                folder = Path(tmp) / name
                shutil.copytree(ROOT / "skills" / name, folder)
                output = io.StringIO()
                with patch.dict("os.environ", {}, clear=True), \
                        patch("urllib.request.urlopen", side_effect=AssertionError("network")), \
                        contextlib.redirect_stdout(output):
                    status = jev.main(["decide", str(folder / "assets/example.json"), "--dry-run"])
                self.assertEqual(status, 0)
                self.assertIn("questions", output.getvalue())

    def test_readmes_expose_each_scenario(self):
        for filename in ("README.md", "README.zh.md"):
            text = (ROOT / filename).read_text()
            for name in SCENARIOS:
                with self.subTest(readme=filename, skill=name):
                    self.assertIn(f"skills/{name}/SKILL.md", text)
                    self.assertIn(f"skills/{name}/assets/example.json", text)

    def test_readmes_cover_the_full_researched_catalog(self):
        references = ROOT / "skills/jev/references"
        recipe_ids = set()
        for filename in ("agent-recipes.md", "human-recipes.md"):
            recipe_ids.update(re.findall(r"\*\*([AH]\d{2}) ·", (references / filename).read_text()))
        pattern_ids = {
            f"M{int(number):02d}" for number in re.findall(
                r"^## (\d+)\.", (references / "implementation-patterns.md").read_text(), re.M
            )
        }
        social_ids = {f"X{number:02d}" for number in range(1, 8)}
        readmes = [(ROOT / name).read_text() for name in ("README.md", "README.zh.md")]
        for text in readmes:
            coverage = re.findall(r"<!-- covers: (.*?) -->", text)
            covered = set(" ".join(coverage).split())
            self.assertTrue(recipe_ids | pattern_ids | social_ids <= covered)
            anchors = re.findall(r'<a id="(sc-[^"]+)"', text)
            self.assertEqual(len(anchors), len(set(anchors)))
            self.assertEqual(len(anchors), len(coverage))
            self.assertEqual(len(anchors), len(re.findall(r"^### \d+\.", text, re.M)))
        self.assertEqual(
            re.findall(r"<!-- covers: (.*?) -->", readmes[0]),
            re.findall(r"<!-- covers: (.*?) -->", readmes[1]),
        )

    def test_readme_counts_and_numbering_match_the_catalog(self):
        for filename in ("README.md", "README.zh.md"):
            text = (ROOT / filename).read_text()
            numbers = [int(n) for n in re.findall(r"^### (\d+)\.", text, re.M)]
            self.assertEqual(numbers, list(range(1, len(numbers) + 1)))
            badge = re.search(r"/badge/scenarios-(\d+)-", text)
            self.assertEqual(int(badge.group(1)), len(numbers))
            counts = re.findall(r"<br />(\d+) (?:recipes|个用法)", text)
            self.assertEqual(len(counts), 10)
            self.assertEqual(sum(map(int, counts)), len(numbers))

    def test_readmes_carry_no_measured_media_or_showcase(self):
        # The fork removed upstream's demo gallery, media files and dated run
        # notes: nothing presents a run this fork did not perform.
        for filename in ("README.md", "README.zh.md"):
            text = (ROOT / filename).read_text()
            self.assertNotIn('<a id="showcase"></a>', text)
            self.assertNotIn("docs/media", text)
        self.assertFalse((ROOT / "docs/media").exists())
        self.assertFalse((ROOT / "docs/updates").exists())
        self.assertFalse((ROOT / "evals/results").exists())

    def test_daily_additions_are_visible_in_both_languages(self):
        for filename in ("README.md", "README.zh.md"):
            text = (ROOT / filename).read_text()
            for number in range(1, 6):
                self.assertIn(f"<!-- covers: D{number:02d} -->", text)
            for anchor in ("sc-semantic-find", "sc-sponsor-skip", "sc-story-sensors",
                           "sc-midi", "sc-local-comparison"):
                self.assertIn(f'<a id="{anchor}"></a>', text)

    def test_readme_requests_are_self_contained_templates(self):
        # Upstream run receipts were removed from this fork: the READMEs show
        # editable request templates only, with no recorded outputs.
        for filename in ("README.md", "README.zh.md"):
            text = (ROOT / filename).read_text()
            self.assertNotIn("<!-- receipt:", text)
            shown = re.findall(r"<!-- request: (.*?) -->\s*```json\n(.*?)\n```", text, re.S)
            self.assertEqual(len(shown), 14)
            for key, payload in shown:
                with self.subTest(readme=filename, request=key):
                    request = json.loads(payload)
                    self.assertEqual(request.get("model"), jev.NEOHORSE_MODEL)
                    self.assertTrue(request.get("state"))
                    self.assertTrue(request.get("questions"))

    def test_readmes_do_not_quote_measured_results(self):
        banned = ("evals/results", "evals/RESULTS.md", "evals/CALIBRATION_RESULTS.md",
                  "evals/SCENARIO_EXAMPLES.md", "docs/updates", "docs/media")
        for filename in ("README.md", "README.zh.md"):
            text = (ROOT / filename).read_text()
            for target in banned:
                with self.subTest(readme=filename, target=target):
                    self.assertNotIn(target, text)


if __name__ == "__main__":
    unittest.main()
