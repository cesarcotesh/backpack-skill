"""Milestone 7 acceptance tests. Run: python -m unittest (from the repo root)"""
import json
import os
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from backpack.__main__ import main
from backpack.app import build_payload, clean_notes, guide, home_path
from backpack.audit import build_audit
from backpack.inventory import LISTING_CAP, build_inventory, find_app_data, parse_frontmatter, split_frontmatter
from backpack.manual import build_manual, shortlist
from backpack.scanner import scan_inventory
from backpack.usage import build_usage

ROOT = Path(__file__).parent.parent
PLUGIN = ROOT / "plugins" / "backpack-skill"
SKILL = PLUGIN / "skills" / "audit"
FIXTURES = Path(__file__).parent / "fixtures"


class PackagingTest(unittest.TestCase):
    def test_manifests_agree(self):
        plugin = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
        entry = market["plugins"][0]
        self.assertEqual(plugin["name"], entry["name"])
        self.assertEqual(plugin["author"]["name"], "Cayeyewarrior")
        self.assertEqual((ROOT / entry["source"]).resolve(), PLUGIN.resolve())
        for rel in entry["skills"]:  # also what `npx skills` reads, so tests/ is never searched
            self.assertTrue((PLUGIN / rel / "SKILL.md").is_file())

    def test_skill_md_is_light_and_scoped(self):
        lines, body, closed = split_frontmatter((SKILL / "SKILL.md").read_text(encoding="utf-8"))
        fm, bad = parse_frontmatter(lines)
        self.assertTrue(closed)
        self.assertEqual(bad, [])
        self.assertEqual(fm["name"], "audit")
        self.assertLess(len(fm["description"]), 400)  # it weighs on every conversation too
        self.assertLessEqual(len(fm["description"]), LISTING_CAP)
        # pre-approved commands: only this skill's own run.py
        for tool in fm["allowed-tools"].split("), "):
            self.assertIn('"${CLAUDE_SKILL_DIR}/run.py" *', tool)
        self.assertIn("never follow", body.lower())


class SelfRecognitionTest(unittest.TestCase):
    def test_only_the_running_folder_is_recognized(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        shutil.copytree(SKILL, tmp / "audit")  # same files, different place: an impostor
        skill = lambda sid, folder: {"id": sid, "name": "audit", "command": "/audit", "scope": "personal",
                                     "path": str(folder / "SKILL.md"), "description": "x", "plugin": None,
                                     "flags": {"model_invocable": True, "user_invocable": True, "loaded": True},
                                     "tokens": {"fixed": 71, "body": 900, "estimated": True}}
        inventory = {"skills": [skill("real", SKILL), skill("copy", tmp / "audit")], "copy_groups": []}
        scan = scan_inventory(inventory)
        self.assertTrue(scan["skills"]["real"]["self"])
        self.assertFalse(scan["skills"]["copy"]["self"])
        self.assertEqual(scan["skills"]["real"]["risk"], scan["skills"]["copy"]["risk"])  # verdict unchanged
        audit = build_audit(inventory, scan)
        self.assertEqual(audit["skills"]["real"]["recommendation"], "keep")
        self.assertEqual(audit["skills"]["real"]["reasons"][0]["code"], "self")
        self.assertEqual(audit["skills"]["copy"]["recommendation"], "review")

    def test_reviewer_plugin_is_not_suggested_for_removal(self):
        plugin = {"id": "backpack-skill@m", "name": "backpack-skill", "marketplace": "m", "enabled": True, "root": str(PLUGIN)}
        skill = {"id": "real", "name": "audit", "command": "/backpack-skill:audit", "scope": "plugin",
                 "path": str(SKILL / "SKILL.md"), "description": "x", "plugin": plugin,
                 "flags": {"model_invocable": True, "user_invocable": True, "loaded": True},
                 "tokens": {"fixed": 71, "body": 900, "estimated": True}}
        inventory = {"skills": [skill], "copy_groups": []}
        usage = {"history_since": "2026-05-27", "skills": {}}  # freshly installed: never used yet
        audit = build_audit(inventory, scan_inventory(inventory), usage, today=date(2026, 10, 3))
        self.assertEqual(audit["plugins"]["backpack-skill@m"]["recommendation"], "keep")


class RunTest(unittest.TestCase):
    def setUp(self):
        self.out = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.out, ignore_errors=True)

    def run_cli(self, *args):
        with mock.patch("sys.stdout"):  # keep test output quiet
            return main(list(args))

    def test_run_writes_everything_and_opens_nothing(self):
        with mock.patch("webbrowser.open") as opened:
            self.assertEqual(self.run_cli("run", "--home", str(FIXTURES / "home"), "--app-data", str(FIXTURES / "appdata"),
                                          "--project", str(FIXTURES / "project"), "--out", str(self.out), "--no-open"), 0)
        opened.assert_not_called()
        self.assertEqual(sorted(p.name for p in self.out.iterdir()), [
            "audit.json", "inventory.json", "manual.json", "mochila.html", "scan.json", "shortlist.json", "usage.json"])

    def test_claude_notes_are_merged_on_rebuild(self):
        self.run_cli("run", "--home", str(FIXTURES / "home"), "--app-data", "none", "--project", str(FIXTURES / "project"),
                     "--out", str(self.out), "--no-open")
        (self.out / "explanations.json").write_text(json.dumps({"personal:review": "Revisa tu código antes de guardarlo."}),
                                                    encoding="utf-8")
        self.run_cli("app", "--data", str(self.out), "--out", str(self.out))
        self.assertIn("Revisa tu código antes de guardarlo.", (self.out / "mochila.html").read_text(encoding="utf-8"))

    def test_default_out_prefers_plugin_data(self):
        from backpack.__main__ import default_out
        with mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_DATA": str(self.out)}):
            self.assertEqual(default_out(), self.out)
        with mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_DATA": ""}):
            self.assertEqual(default_out(), Path.home() / ".backpack-skill")


class LightVersionTest(unittest.TestCase):
    def test_platform_mounted_skills(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        (tmp / "user" / "brand").mkdir(parents=True)
        (tmp / "user" / "brand" / "SKILL.md").write_text("---\nname: brand\ndescription: Tono de marca.\n---\n", encoding="utf-8")
        with mock.patch("sys.stdout"):
            main(["run", "--home", str(tmp / "no-home"), "--app-data", "none", "--skills-root", str(tmp / "user"),
                  "--project", str(tmp / "none"), "--out", str(tmp / "out"), "--no-open"])
        inv = json.loads((tmp / "out" / "inventory.json").read_text(encoding="utf-8"))
        (skill,) = inv["skills"]
        self.assertEqual((skill["id"], skill["origin"]), ("platform:user/brand", {"type": "platform"}))
        audit = json.loads((tmp / "out" / "audit.json").read_text(encoding="utf-8"))
        self.assertIsNone(audit["totals"]["usage_history_since"])  # no logs here: no usage claims
        self.assertEqual(audit["skills"]["platform:user/brand"]["recommendation"], "keep")
        self.assertIn("Customize > Skills", (tmp / "out" / "mochila.html").read_text(encoding="utf-8"))


class AppDataTest(unittest.TestCase):
    def test_finds_store_install_before_roaming(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        store = tmp / "Local" / "Packages" / "Claude_abc123" / "LocalCache" / "Roaming" / "Claude"
        roaming = tmp / "Roaming" / "Claude"
        for d in (store, roaming):
            (d / "local-agent-mode-sessions").mkdir(parents=True)
        env = {"LOCALAPPDATA": str(tmp / "Local"), "APPDATA": str(tmp / "Roaming"), "XDG_CONFIG_HOME": str(tmp / "cfg")}
        with mock.patch.dict(os.environ, env):
            found = find_app_data(tmp)
        if os.name == "nt":
            self.assertEqual(found, store)
        self.assertIsNone(find_app_data(tmp / "nobody") if os.name != "nt" else None)


class GuideTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        inv = build_inventory(FIXTURES / "home", [FIXTURES / "project"], FIXTURES / "appdata")
        scan = scan_inventory(inv)
        audit = build_audit(inv, scan, build_usage(FIXTURES / "home", FIXTURES / "appdata"), today=date(2026, 10, 3))
        cls.inv, cls.audit, cls.manual = inv, audit, build_manual(inv, scan, audit)
        cls.payload = build_payload(inv, scan, audit, cls.manual, {"personal:review": "Nota\u202e de Claude", "ghost": "x"})
        cls.skills = {s["id"]: s for s in cls.payload["skills"]}
        cls.plugins = {p["id"]: p for p in cls.payload["plugins"]}

    def test_paths_never_show_the_user_name(self):
        self.assertEqual(home_path(Path.home() / ".claude" / "skills" / "x", Path.home()), "~/.claude/skills/x")
        page = json.dumps(self.payload)
        self.assertNotIn(Path.home().name, page)
        self.assertEqual(self.skills["personal:notes"]["guide"]["path"], "~/.claude/skills/notes")

    def test_guide_by_origin(self):
        self.assertEqual(self.plugins["toolkit@acme"]["guide"]["command"], "claude plugin uninstall toolkit@acme")
        self.assertIn("Customize > Plugins", self.plugins["travel@knowledge-work-plugins"]["guide"]["how"])
        self.assertIn("Customize > Skills", self.skills["plugin:anthropic-skills@claude.ai/brand-voice"]["guide"]["how"])
        self.assertIsNone(self.skills["plugin:toolkit@acme/review"]["guide"])  # it goes with its plugin
        self.assertEqual(self.plugins["bundle@skills-dir"]["guide"]["path"], "~/.claude/skills/bundle")
        npx = guide({"name": "x", "scope": "personal", "path": str(Path.home() / ".claude/skills/x/SKILL.md"),
                     "origin": {"type": "npx-skills"}}, Path.home())
        self.assertEqual(npx["command"], "npx skills remove --global x")
        scoped = guide({"name": "y", "scope": "plugin", "path": "/p/SKILL.md", "origin": {"type": "plugin", "marketplace": "m"},
                        "plugin": {"id": "y@m", "name": "y", "marketplace": "m", "install_scope": "project"}}, Path.home())
        self.assertEqual(scoped["command"], "claude plugin uninstall y@m --scope project")

    def test_notes_are_plain_short_and_known(self):
        self.assertEqual(clean_notes({"a": "x" * 900, "b": 3, "zz": "y"}, {"a", "b"}), {"a": "x" * 600})
        self.assertEqual(self.skills["personal:review"]["card"]["claude_note"], "Nota  de Claude")  # bidi char removed

    def test_shortlist_skips_removals_and_marks_untrusted_text(self):
        items = shortlist(self.inv, self.audit, self.manual)
        self.assertTrue(items)
        self.assertNotIn("remove", {i["recommendation"] for i in items})
        self.assertIn("skill_text_untrusted", items[0])


if __name__ == "__main__":
    unittest.main()
