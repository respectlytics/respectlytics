"""The dashboard's scripts escape what apps send before it reaches the page (2026-10-24).

Event names are written by every copy of an app, and anyone who pulls an app's key out of one
can send any name. The stats page puts names inside attributes (title="...", value="..."), so the
one escaper, StatsApp.utils.escapeHtml, escapes quotes as well as markup: until 2026-10-24 it
escaped markup only, and a name with a quote in it could add an attribute, a script handler among
them, to the owner's dashboard.
"""

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

ROOT = Path(settings.BASE_DIR)
UTILS = ROOT / "dashboard/static/js/stats/utils.js"


class EscapingTest(SimpleTestCase):
    def test_the_escaper_covers_quotes_and_markup(self):
        source = UTILS.read_text()
        table = re.search(r"const ESCAPES = \{(.*?)\};", source).group(1)
        for character, entity in [
            ("&", "&amp;"),
            ("<", "&lt;"),
            (">", "&gt;"),
            ('"', "&quot;"),
            ("'", "&#39;"),
        ]:
            self.assertIn(f"{entity}", table, character)
        self.assertIn("/[&<>\"']/g", source)

    def test_there_is_one_escaper(self):
        found = []
        for folder in ["dashboard", "demo", "static/js"]:
            for path in (ROOT / folder).rglob("*"):
                if path.suffix not in {".js", ".html"} or path == UTILS:
                    continue
                text = path.read_text(errors="ignore")
                if re.search(r"(function escapeHtml|escapeHtml\s*[:=]\s*(function|\())", text):
                    found.append(str(path.relative_to(ROOT)))
        self.assertEqual(found, [], "use StatsApp.utils.escapeHtml (window.escapeHtml)")
