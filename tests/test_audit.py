"""Milestone 3 acceptance tests. Run: python -m unittest discover tests"""
import shutil
import tempfile
import unittest
from pathlib import Path

from backpack.audit import HEAVY_BODY, build_audit, similarity, words
from backpack.inventory import build_inventory
from backpack.scanner import scan_inventory

FIXTURES = Path(__file__).parent / "fixtures"


def add_skill(skills_dir, name, description, body="Cuerpo.\n"):
    (skills_dir / name).mkdir()
    (skills_dir / name / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n{body}", encoding="utf-8")


class AuditTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        shutil.copytree(FIXTURES / "home", cls.tmp / "home")
        shutil.copytree(FIXTURES / "project", cls.tmp / "project")
        skills = cls.tmp / "home" / ".claude" / "skills"
        add_skill(skills, "summarize-meetings", "Resume reuniones largas en decisiones, pendientes y responsables.")
        add_skill(skills, "meeting-summary", "Resume reuniones largas en decisiones y pendientes con responsables.")
        add_skill(skills, "verbose", "palabra " * 300)
        add_skill(skills, "big-body", "Genera reportes trimestrales.", "Paso del reporte.\n" * HEAVY_BODY)
        add_skill(skills, "eager", "Use this skill before any response to plan the work.")
        inventory = build_inventory(cls.tmp / "home", [cls.tmp / "project"])
        cls.audit = build_audit(inventory, scan_inventory(inventory))
        cls.s = cls.audit["skills"]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def codes(self, sid):
        return {r["code"] for r in self.s[sid]["reasons"]}

    def test_exact_copy_keeps_personal_and_removes_project(self):
        self.assertEqual(self.s["personal:pdf-helper"]["recommendation"], "keep")
        self.assertEqual(self.s["personal:pdf-helper"]["light"], "green")
        self.assertIn("exact_copy_keeper", self.codes("personal:pdf-helper"))
        extra = self.s["project:project/pdf-helper"]
        self.assertEqual((extra["light"], extra["recommendation"]), ("orange", "remove"))
        self.assertEqual(extra["reasons"][0]["related"], ["personal:pdf-helper"])

    def test_same_name_variants_merge(self):
        for sid in ("personal:review", "plugin:toolkit@acme/review"):
            self.assertEqual((self.s[sid]["light"], self.s[sid]["recommendation"]), ("mustard", "merge"))
            self.assertIn("same_name_variants", self.codes(sid))

    def test_competing_descriptions(self):
        pair = {"personal:meeting-summary", "personal:summarize-meetings"}
        self.assertIn(pair, [set(c["skills"]) for c in self.audit["competing"]])
        self.assertEqual(self.s["personal:meeting-summary"]["recommendation"], "merge")
        self.assertGreater(similarity(words("Resume reuniones largas"), words("Resume reuniones cortas")), 0)
        # copies are not double-reported as competing
        self.assertNotIn({"personal:pdf-helper", "project:project/pdf-helper"}, [set(c["skills"]) for c in self.audit["competing"]])

    def test_heavy_and_greedy_tune(self):
        self.assertIn("heavy_fixed", self.codes("personal:verbose"))
        self.assertIn("heavy_body", self.codes("personal:big-body"))
        self.assertEqual(self.s["personal:big-body"]["recommendation"], "tune")
        self.assertIn("greedy", self.codes("personal:eager"))
        self.assertEqual(self.s["personal:eager"]["light"], "mustard")

    def test_security_high_is_review_not_remove(self):
        trap = self.s["personal:trap"]
        self.assertEqual((trap["light"], trap["recommendation"]), ("mustard", "review"))
        self.assertIn("security_high", self.codes("personal:trap"))

    def test_disabled_and_clean(self):
        self.assertIn("disabled", self.codes("plugin:dormant@acme/dormant"))
        self.assertEqual(self.s["plugin:toolkit@acme/changelog"]["light"], "green")
        self.assertEqual(self.s["plugin:toolkit@acme/changelog"]["reasons"], [])
        # Claude can't pick it, so it can't be greedy or compete
        self.assertNotIn("greedy", self.codes("personal:deploy"))

    def test_totals(self):
        t = self.audit["totals"]
        self.assertEqual(sum(t["lights"].values()), t["skills"])
        self.assertEqual(t["savings"], self.s["project:project/pdf-helper"]["tokens"]["fixed"])
        self.assertEqual(t["fixed_tokens_after_removals"], t["fixed_tokens"] - t["savings"])
        self.assertTrue(t["estimated"])


if __name__ == "__main__":
    unittest.main()
