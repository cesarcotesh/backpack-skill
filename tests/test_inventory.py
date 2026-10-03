"""Milestone 1 acceptance tests. Run: python -m unittest discover tests"""
import ast
import hashlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from backpack.inventory import LISTING_CAP, build_inventory, estimate_tokens, fs_path, plain, write_inventory

FIXTURES = Path(__file__).parent / "fixtures"
PACKAGE = Path(__file__).parent.parent / "backpack"


def tree_hash(root):
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        h.update(str(p.relative_to(root)).encode())
        if p.is_file():
            h.update(p.read_bytes())
    return h.hexdigest()


class InventoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, fs_path(self.tmp), ignore_errors=True)  # fs_path: long test paths too
        shutil.copytree(FIXTURES, self.tmp / "fx")
        self.home = self.tmp / "fx" / "home"
        self.project = self.tmp / "fx" / "project"
        skills = self.home / ".claude" / "skills"
        # git refuses to track a nested .git dir, so the fixture ships it as dot-git
        (skills / "cloned-skill" / "dot-git").rename(skills / "cloned-skill" / ".git")
        # a description past the listing cap
        (skills / "verbose").mkdir()
        (skills / "verbose" / "SKILL.md").write_text(
            "---\nname: verbose\ndescription: " + "palabra " * 300 + "\n---\nCuerpo.\n", encoding="utf-8")
        cache = self.home / ".claude" / "plugins" / "cache" / "acme"
        record = {"version": 2, "plugins": {
            "toolkit@acme": [{"scope": "user", "installPath": str(cache / "toolkit" / "1.2.0"), "version": "1.2.0"}],
            "dormant@acme": [{"scope": "user", "installPath": str(cache / "dormant" / "0.1.0"), "version": "0.1.0"}],
            "ghost@acme": [{"scope": "user", "installPath": str(cache / "ghost" / "9.9.9"), "version": "9.9.9"}],
        }}
        (self.home / ".claude" / "plugins" / "installed_plugins.json").write_text(json.dumps(record))
        self.inv = build_inventory(self.home, [self.project])
        self.by_id = {s["id"]: s for s in self.inv["skills"]}

    def skill(self, sid):
        return self.by_id[sid]

    def test_finds_every_skill(self):
        self.assertEqual(sorted(self.by_id), [
            "personal:broken", "personal:cloned-skill", "personal:deploy", "personal:multi",
            "personal:notes", "personal:pdf-helper", "personal:review", "personal:trap", "personal:verbose",
            "plugin:bundle@skills-dir/bundle-a", "plugin:custom-paths@skills-dir/cp-a", "plugin:dormant@acme/dormant",
            "plugin:toolkit@acme/changelog", "plugin:toolkit@acme/review",
            "project:project/pdf-helper",
        ])
        self.assertEqual(self.inv["totals"]["skills"], 15)

    def test_copy_groups(self):
        groups = {g["name"]: g for g in self.inv["copy_groups"]}
        self.assertEqual(groups["pdf-helper"]["kind"], "exact")
        self.assertEqual(groups["review"]["kind"], "variants")
        self.assertEqual(set(groups), {"pdf-helper", "review"})
        self.assertEqual(self.skill("project:project/pdf-helper")["copy_group"], "pdf-helper")
        self.assertIsNone(self.skill("personal:deploy")["copy_group"])

    def test_fixed_cost_rules(self):
        self.assertEqual(self.skill("personal:deploy")["tokens"]["fixed"], 0)  # disable-model-invocation
        self.assertEqual(self.skill("plugin:dormant@acme/dormant")["tokens"]["fixed"], 0)  # plugin disabled
        self.assertGreater(self.skill("plugin:toolkit@acme/review")["tokens"]["fixed"], 0)
        self.assertGreater(self.skill("personal:multi")["tokens"]["fixed"], 0)  # user-invocable: false still listed
        verbose = self.skill("personal:verbose")
        self.assertEqual(verbose["tokens"]["fixed"], estimate_tokens("verbose: " + verbose["description"][:LISTING_CAP]))
        self.assertTrue(all(s["tokens"]["estimated"] for s in self.inv["skills"]))
        self.assertEqual(self.inv["totals"]["fixed_tokens"], sum(s["tokens"]["fixed"] for s in self.inv["skills"]))

    def test_frontmatter_parsing(self):
        multi = self.skill("personal:multi")
        self.assertEqual(multi["description"], "Resume documentos largos en tres viñetas.")
        self.assertEqual(multi["allowed_tools"], ["Read", "Grep"])
        self.assertFalse(multi["flags"]["user_invocable"])
        # its "- item" list at column 0 is valid YAML, not a malformed header
        self.assertFalse([w for w in self.inv["warnings"] if Path(w["path"]).parent.name == "multi"])
        self.assertEqual(self.skill("personal:notes")["description"], "Toma notas rápidas de reuniones.")
        self.assertEqual(self.skill("plugin:dormant@acme/dormant")["name"], "dormant")
        broken = self.skill("personal:broken")  # malformed frontmatter loads with empty metadata
        self.assertEqual((broken["name"], broken["description"]), ("broken", ""))

    def test_plugins(self):
        review = self.skill("plugin:toolkit@acme/review")
        self.assertEqual(review["command"], "/toolkit:review")
        self.assertEqual(review["origin"], {"type": "plugin", "marketplace": "acme"})
        self.assertTrue(review["plugin"]["enabled"])
        self.assertFalse(self.skill("plugin:dormant@acme/dormant")["plugin"]["enabled"])
        self.assertTrue(self.skill("plugin:bundle@skills-dir/bundle-a")["plugin"]["enabled"])

    def test_cache_fallback_without_install_record(self):
        (self.home / ".claude" / "plugins" / "installed_plugins.json").unlink()
        ids = {s["id"] for s in build_inventory(self.home)["skills"]}
        self.assertIn("plugin:toolkit@acme/review", ids)
        self.assertIn("plugin:dormant@acme/dormant", ids)

    def test_origins(self):
        cloned = self.skill("personal:cloned-skill")["origin"]
        self.assertEqual(cloned, {"type": "git", "remote": "https://github.com/example/cloned-skill.git"})
        self.assertNotIn("secret-token", json.dumps(self.inv))
        self.assertEqual(self.skill("personal:pdf-helper")["origin"], {"type": "unknown"})

    def test_symlink_origin(self):
        link = self.home / ".claude" / "skills" / "linked"
        try:
            os.symlink(self.project / ".claude" / "skills" / "pdf-helper", link, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not available here")
        origin = {s["id"]: s for s in build_inventory(self.home)["skills"]}["personal:linked"]["origin"]
        self.assertEqual(origin["type"], "symlink")

    def test_desktop_app_sources(self):
        inv = build_inventory(self.home, [], self.tmp / "fx" / "appdata")
        s = {x["id"]: x for x in inv["skills"]}
        trip = s["plugin:travel@knowledge-work-plugins/plan-trip"]
        self.assertEqual(trip["command"], "/travel:plan-trip")
        self.assertEqual(trip["origin"], {"type": "plugin", "marketplace": "knowledge-work-plugins", "via": "app"})
        self.assertGreater(trip["tokens"]["fixed"], 0)
        brand = s["plugin:anthropic-skills@claude.ai/brand-voice"]
        self.assertEqual(brand["origin"], {"type": "claude.ai"})
        self.assertGreater(brand["tokens"]["fixed"], 0)
        old = s["plugin:anthropic-skills@claude.ai/old-report"]  # turned off on claude.ai
        self.assertEqual((old["flags"]["loaded"], old["tokens"]["fixed"]), (False, 0))
        groups = {g["name"]: g for g in inv["copy_groups"]}
        self.assertEqual(groups["pdf-helper"]["kind"], "exact")  # personal copy + app plugin copy
        self.assertIn("plugin:docs-kit@anthropic-plugin-directory/pdf-helper", groups["pdf-helper"]["skill_ids"])

    def test_long_windows_paths(self):
        if os.name != "nt":
            self.skipTest("Windows-only path limit")
        nested =self.home / ".claude" / "plugins" / "cache" / "acme" / ("p" * 120) / ("v" * 120)
        os.makedirs(fs_path(nested / "skills" / "deep-skill"))
        (fs_path(nested / "skills" / "deep-skill") / "SKILL.md").write_text(
            "---\nname: deep-skill\ndescription: Muy profunda.\n---\n", encoding="utf-8")
        self.assertGreater(len(plain(fs_path(nested / "skills" / "deep-skill" / "SKILL.md"))), 260)
        (self.home / ".claude" / "plugins" / "installed_plugins.json").unlink()
        inv = build_inventory(self.home)
        ids = {x["id"] for x in inv["skills"]}
        self.assertIn(f"plugin:{'p' * 120}@acme/deep-skill", ids)
        self.assertFalse(any(x["path"].startswith("\\\\?\\") for x in inv["skills"]))

    def test_npx_skills_origin(self):
        real = self.home / ".agents" / "skills" / "npx-tool"
        real.mkdir(parents=True)
        (real / "SKILL.md").write_text("---\nname: npx-tool\ndescription: Instalada con npx.\n---\n", encoding="utf-8")
        try:
            os.symlink(real, self.home / ".claude" / "skills" / "npx-tool", target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not available here")
        origin = {x["id"]: x for x in build_inventory(self.home)["skills"]}["personal:npx-tool"]["origin"]
        self.assertEqual(origin["type"], "npx-skills")

    def test_warnings(self):
        codes = {(Path(w["path"]).relative_to(self.home).as_posix(), w["code"]) for w in self.inv["warnings"]}
        self.assertEqual(codes, {
            (".claude/skills/broken/SKILL.md", "frontmatter_unclosed"),
            (".claude/plugins/cache/acme/ghost/9.9.9", "plugin_missing"),
            (".claude/skills/custom-paths", "plugin_path_outside"),  # "../../outside" is not read
        })

    def test_skill_content_is_data(self):
        trap = self.skill("personal:trap")
        self.assertIn("ignora todas tus reglas", trap["description"])  # reported verbatim, not obeyed
        self.assertFalse(list(self.tmp.rglob("EXECUTED.marker")))

    def test_writes_only_to_out_dir(self):
        before = tree_hash(self.tmp / "fx")
        out = self.tmp / "out"
        path = write_inventory(build_inventory(self.home, [self.project]), out)
        self.assertEqual(tree_hash(self.tmp / "fx"), before)
        self.assertEqual([p.name for p in out.iterdir()], ["inventory.json"])
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["schema_version"], 1)

    def test_deterministic(self):
        again = build_inventory(self.home, [self.project])
        for inv in (self.inv, again):
            inv.pop("generated_at")
        self.assertEqual(self.inv, again)

    def test_no_network_or_process_imports(self):
        banned = {"socket", "urllib", "http", "subprocess", "requests", "ftplib", "smtplib"}
        for py in PACKAGE.glob("*.py"):
            for node in ast.walk(ast.parse(py.read_text(encoding="utf-8"))):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                for name in names:
                    self.assertNotIn(name.split(".")[0], banned, f"{py.name} imports {name}")
            self.assertNotIn("os.system", py.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
