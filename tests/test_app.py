"""Milestone 6 acceptance tests. Run: python -m unittest discover tests"""
import json
import re
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path

from backpack.app import TEMPLATE, build_app, build_payload, font_css
from backpack.audit import build_audit
from backpack.inventory import build_inventory
from backpack.manual import build_manual
from backpack.scanner import scan_inventory
from backpack.usage import build_usage

FIXTURES = Path(__file__).parent / "fixtures"
EVIL = "</script><img src=x onerror=alert(1)><!--"


class AppTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        shutil.copytree(FIXTURES / "home", cls.tmp / "home")
        evil = cls.tmp / "home" / ".claude" / "skills" / "evil"
        evil.mkdir()
        (evil / "SKILL.md").write_text(f"---\nname: evil\ndescription: '{EVIL}'\n---\n", encoding="utf-8")
        inv = build_inventory(cls.tmp / "home", [], FIXTURES / "appdata")
        scan = scan_inventory(inv)
        audit = build_audit(inv, scan, build_usage(cls.tmp / "home", FIXTURES / "appdata"), today=date(2026, 10, 3))
        cls.parts = (inv, scan, audit, build_manual(inv, scan, audit))
        cls.html = build_app(*cls.parts, fonts_dir=cls.tmp / "no-fonts")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def data_block(self):
        m = re.search(r'<script type="application/json" id="data">(.*?)</script>', self.html, re.S)
        return m.group(1)

    def test_skill_text_cannot_break_out_of_the_data_block(self):
        self.assertNotIn(EVIL, self.html)
        self.assertEqual(self.html.count("</script>"), 2)  # the data block and the app script, nothing injected
        data = json.loads(self.data_block())
        evil = next(s for s in data["skills"] if s["name"] == "evil")
        self.assertEqual(evil["description"], EVIL)  # same text, shown later as plain text

    def test_page_never_reaches_the_network(self):
        self.assertIn("default-src 'none'", self.html)
        page = self.html.replace(self.data_block(), "")
        self.assertNotRegex(page, r"<script[^>]+src=|<link\b|@import|url\(\s*['\"]?https?:")
        urls = set(re.findall(r"https?://[^\s\"')]+", page))
        self.assertEqual(urls, {"http://www.w3.org/2000/svg"})  # an SVG namespace name, not a request

    def test_template_never_parses_strings_as_markup(self):
        script = TEMPLATE.read_text(encoding="utf-8")
        for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"):
            self.assertNotIn(sink, script)

    def test_payload_units(self):
        payload = build_payload(*self.parts)
        skills = {s["id"]: s for s in payload["skills"]}
        # claude.ai skills are switched off one by one; a real plugin goes as a whole
        self.assertIsNone(skills["plugin:anthropic-skills@claude.ai/brand-voice"]["plugin"])
        self.assertEqual(skills["plugin:travel@knowledge-work-plugins/plan-trip"]["plugin"], "travel@knowledge-work-plugins")
        self.assertNotIn("anthropic-skills@claude.ai", {p["id"] for p in payload["plugins"]})
        self.assertEqual(skills["plugin:travel@knowledge-work-plugins/plan-trip"]["origin"], "Plugin de la app · travel")
        self.assertEqual(skills["personal:pdf-helper"]["origin"], "Carpeta personal, origen desconocido")
        self.assertNotIn("path", skills["personal:pdf-helper"])  # no file paths in the page

    def test_fonts_are_embedded_when_present(self):
        self.assertEqual(font_css(self.tmp / "no-fonts"), "")
        fonts = self.tmp / "fonts"
        fonts.mkdir()
        (fonts / "atkinson-hyperlegible-400.woff2").write_bytes(b"wOF2fake")
        css = font_css(fonts)
        self.assertIn("font-family:'Atkinson Hyperlegible';font-weight:400", css)
        self.assertIn("data:font/woff2;base64,d09GMmZha2U=", css)


if __name__ == "__main__":
    unittest.main()
