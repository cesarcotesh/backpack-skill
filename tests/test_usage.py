"""Milestone 4 acceptance tests. Run: python -m unittest discover tests"""
import json
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path

from backpack.audit import build_audit
from backpack.inventory import build_inventory
from backpack.scanner import scan_inventory
from backpack.usage import build_usage, invocations, write_usage

FIXTURES = Path(__file__).parent / "fixtures"
HOME = FIXTURES / "home"
APP = FIXTURES / "appdata"
PRIVATE = "TEXTO-PRIVADO-1234"  # appears in every fixture log line; must never come out


class UsageTest(unittest.TestCase):
    def setUp(self):
        self.usage = build_usage(HOME, APP)

    def test_counts_names_and_dates(self):
        self.assertEqual(self.usage["skills"], {
            "pdf-helper": {"count": 2, "first_used": "2026-08-01", "last_used": "2026-09-30"},  # incl. subagent log
            "toolkit:review": {"count": 1, "first_used": "2026-09-15", "last_used": "2026-09-15"},  # typed command
            "travel:plan-trip": {"count": 1, "first_used": "2026-07-10", "last_used": "2026-07-10"},  # desktop app
        })
        self.assertEqual(self.usage["history_since"], "2026-07-10")
        self.assertEqual(self.usage["sources"]["files"], 3)

    def test_nothing_from_the_conversation_leaks(self):
        out = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, out, ignore_errors=True)
        text = write_usage(self.usage, out).read_text(encoding="utf-8")
        self.assertNotIn(PRIVATE, text)
        self.assertNotIn("contraseña", text)

    def test_only_skill_calls_and_typed_commands_count(self):
        bash = '{"timestamp":"2026-01-01T00:00:00Z","message":{"role":"assistant","content":[{"type":"tool_use","name":"Bash","input":{"command":"Skill"}}]}}'
        quoted = '{"timestamp":"2026-01-01T00:00:00Z","message":{"role":"assistant","content":[{"type":"text","text":"<command-name>/x</command-name>"}]}}'
        self.assertEqual(invocations(bash), [])
        self.assertEqual(invocations(quoted), [])  # only the user's own messages carry typed commands
        self.assertEqual(invocations("not json Skill"), [])

    def test_audit_reports_usage_and_days_unused(self):
        inventory = build_inventory(HOME, [], APP)
        audit = build_audit(inventory, scan_inventory(inventory), self.usage, today=date(2026, 10, 3))
        s = audit["skills"]
        self.assertEqual(s["personal:pdf-helper"]["usage"], {"count": 2, "last_used": "2026-09-30", "days_unused": 3})
        self.assertEqual(s["plugin:toolkit@acme/review"]["usage"]["count"], 1)
        self.assertEqual(s["personal:review"]["usage"]["count"], 0)  # /toolkit:review is not the personal one
        trip = s["plugin:travel@knowledge-work-plugins/plan-trip"]
        self.assertEqual(trip["usage"]["days_unused"], 85)
        self.assertIn("No la usas hace 85 días.", [r["text"] for r in trip["reasons"]])
        notes = [r["text"] for r in s["personal:notes"]["reasons"]]
        self.assertIn("No hay registro de uso desde el 2026-07-10 (hace 85 días).", notes)
        self.assertEqual(s["personal:notes"]["light"], "green")  # usage informs, it doesn't change the light
        t = audit["totals"]
        self.assertEqual(t["usage_history_since"], "2026-07-10")
        self.assertEqual(t["unused_skills"], sum(1 for x in s.values() if x["usage"]["count"] == 0))

    def test_audit_without_usage(self):
        inventory = build_inventory(HOME)
        audit = build_audit(inventory, scan_inventory(inventory))
        self.assertIsNone(audit["skills"]["personal:pdf-helper"]["usage"])
        self.assertEqual(audit["totals"]["unused_skills"], 0)


if __name__ == "__main__":
    unittest.main()
