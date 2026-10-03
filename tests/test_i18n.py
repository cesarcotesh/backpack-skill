"""Spanish and English carry the same texts. Run: python -m unittest (from the repo root)"""
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backpack import i18n
from backpack.__main__ import main
from backpack.app import TEMPLATE

FIXTURES = Path(__file__).parent / "fixtures"


def ui_keys(block):
    return set(re.findall(r"(?:^|[{,]\s*)([A-Za-z]\w*|\"[\w-]+\"):", block, re.M))


class I18nTest(unittest.TestCase):
    def tearDown(self):
        i18n.set_lang("es")

    def test_python_texts_match(self):
        es, en = i18n.MESSAGES["es"], i18n.MESSAGES["en"]
        self.assertEqual(set(es), set(en))
        for key in es:  # same placeholders in both languages
            self.assertEqual(set(re.findall(r"{(\w+)}", es[key])), set(re.findall(r"{(\w+)}", en[key])), key)

    def test_interface_texts_match(self):
        page = TEMPLATE.read_text(encoding="utf-8")
        es = page[page.index("  es: {"):page.index("  en: {")]
        en = page[page.index("  en: {"):page.index("const T = TEXT[LANG];")]
        self.assertEqual(ui_keys(es), ui_keys(en))
        self.assertNotIn("T.", es + en)  # the dictionary can't use itself: T doesn't exist yet there

    def test_numbers_by_language(self):
        self.assertEqual(i18n.n(9394), "9.394")
        i18n.set_lang("en")
        self.assertEqual(i18n.n(9394), "9,394")
        i18n.set_lang("xx")  # unknown falls back to Spanish
        self.assertEqual(i18n.lang(), "es")

    def test_english_run(self):
        out = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, out, ignore_errors=True)
        with mock.patch("sys.stdout"):
            main(["run", "--home", str(FIXTURES / "home"), "--app-data", str(FIXTURES / "appdata"),
                  "--project", str(FIXTURES / "project"), "--out", str(out), "--no-open", "--lang", "en"])
            main(["app", "--data", str(out), "--out", str(out)])  # rebuild keeps the review's language
        page = (out / "mochila.html").read_text(encoding="utf-8")
        self.assertIn('"lang":"en"', page)
        self.assertIn("It's an exact copy of /pdf-helper.", page)
        self.assertIn("Move this folder to the trash", page)
        self.assertNotIn("Mueve esta carpeta", page)


if __name__ == "__main__":
    unittest.main()
