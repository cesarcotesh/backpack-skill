"""Plugin agents and commands, folder-named plugin skills, agent usage. Run: python -m unittest"""
import json
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path

from backpack.app import build_payload
from backpack.audit import build_audit
from backpack.inventory import build_inventory
from backpack.manual import build_manual
from backpack.scanner import scan_inventory
from backpack.usage import invocations


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class ExtrasTest(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)
        cache = self.home / ".claude" / "plugins" / "cache" / "mkt"
        crew = cache / "crew" / "1.0.0"  # skills + agents + commands (one from a declared path)
        write(crew / ".claude-plugin" / "plugin.json", json.dumps({"name": "crew", "commands": ["./more", "../../outside"]}))
        write(crew / "skills" / "folder-name" / "SKILL.md", "---\nname: header-name\ndescription: Planifica sprints.\n---\n")
        write(crew / "agents" / "reviewer.md", "---\nname: reviewer\ndescription: Revisa código con ojo crítico.\n---\nCuerpo.\n")
        write(crew / "agents" / "README.md", "Not an agent.\n")
        write(crew / "commands" / "ship.md", "---\ndescription: Publica la versión.\n---\n")
        write(crew / "more" / "hotfix.md", "Arregla un error urgente.\n")
        bots = cache / "bots" / "2.0.0"  # agents only, no skills
        write(bots / ".claude-plugin" / "plugin.json", json.dumps({"name": "bots"}))
        write(bots / "agents" / "helper.md", "---\nname: helper\ndescription: Ayuda con tareas sueltas.\n---\n")
        self.inv = build_inventory(self.home)

    def test_plugin_skills_answer_to_their_folder_name(self):
        (skill,) = self.inv["skills"]
        self.assertEqual((skill["name"], skill["command"]), ("folder-name", "/crew:folder-name"))

    def test_agents_and_commands_weigh(self):
        extras = self.inv["plugin_extras"]
        crew = {(i["kind"], i["name"]) for i in extras["crew@mkt"]["items"]}
        self.assertEqual(crew, {("agent", "reviewer"), ("command", "ship"), ("command", "hotfix")})  # no README, no ../
        self.assertIn("bots@mkt", extras)  # a plugin with no skills still counts
        self.assertTrue(all(i["fixed"] > 0 for e in extras.values() for i in e["items"]))
        skills_fixed = sum(s["tokens"]["fixed"] for s in self.inv["skills"])
        self.assertEqual(self.inv["totals"]["fixed_tokens"], skills_fixed + self.inv["totals"]["extras_fixed_tokens"])

    def test_disabled_plugin_extras_weigh_nothing(self):
        write(self.home / ".claude" / "settings.json", json.dumps({"enabledPlugins": {"bots@mkt": False}}))
        inv = build_inventory(self.home)
        self.assertEqual(inv["plugin_extras"]["bots@mkt"]["fixed"], 0)

    def audit(self, usage):
        return build_audit(self.inv, scan_inventory(self.inv), usage, today=date(2026, 10, 3))

    def test_unused_plugin_counts_its_agents(self):
        audit = self.audit({"history_since": "2026-07-01", "skills": {}})
        bots = audit["plugins"]["bots@mkt"]
        self.assertEqual((bots["recommendation"], bots["extras"]["agents"]), ("remove", 1))
        self.assertIn("(1 agente)", bots["reasons"][0]["text"])
        self.assertEqual(audit["totals"]["savings"], audit["totals"]["fixed_tokens"])  # everything here is unused
        self.assertIn("bots@mkt", {p["id"] for p in build_payload(self.inv, scan_inventory(self.inv), audit,
                                                                  build_manual(self.inv, scan_inventory(self.inv), audit))["plugins"]})

    def test_using_an_agent_keeps_its_plugin(self):
        audit = self.audit({"history_since": "2026-07-01", "skills": {"crew:reviewer": {"count": 1, "first_used": "2026-09-01", "last_used": "2026-09-01"}}})
        self.assertEqual(audit["plugins"]["crew@mkt"]["recommendation"], "keep")
        self.assertEqual(audit["plugins"]["bots@mkt"]["recommendation"], "remove")

    def test_agent_calls_are_read_from_logs(self):
        line = '{"timestamp":"2026-09-01T10:00:00Z","message":{"role":"assistant","content":[{"type":"tool_use","name":"Agent","input":{"subagent_type":"crew:reviewer","prompt":"secreto"}}]}}'
        self.assertEqual(invocations(line), [("crew:reviewer", "2026-09-01T10:00:00Z")])
        builtin = line.replace("crew:reviewer", "Explore")  # built-in agents are not plugins
        self.assertEqual(invocations(builtin), [])


if __name__ == "__main__":
    unittest.main()
