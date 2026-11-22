"""A Django comment written {# like this #} ends on its own line; one that runs onto the next is not
a comment at all and is printed on the page, as it was on the Overview on 2026-10-26. Every
template here is held to that: a longer comment uses {% comment %}."""

from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

ROOT = Path(settings.BASE_DIR)
SKIP = {"venv", "node_modules", "staticfiles", ".git"}


class TemplateCommentTest(SimpleTestCase):
    def test_no_short_comment_runs_onto_a_second_line(self):
        found = []
        for path in ROOT.rglob("*.html"):
            if SKIP & set(path.relative_to(ROOT).parts):
                continue
            for number, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
                rest = line
                while "{#" in rest:
                    rest = rest[rest.index("{#") + 2 :]
                    if "#}" not in rest:
                        found.append(f"{path.relative_to(ROOT)}:{number}")
                        break
                    rest = rest[rest.index("#}") + 2 :]
        self.assertEqual(found, [], "use {% comment %} for a comment longer than its line")
