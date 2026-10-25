"""The Behavior tab's With it and Without bars (correlationRow in dashboard/stats.html) draw the
conversion rates the API returns, which are fractions: 0.574 is 57.4% (conversion/views.py, and
StatsApp.utils.formatRate, which multiplies by 100 to print them). Until 2026-10-25 the bar used
the fraction as the percentage, so every bar sat at its 1.5% minimum whatever the rate; found while
photographing the dashboard at phone width for the homepage.
"""

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

STATS = Path(settings.BASE_DIR) / "dashboard/templates/dashboard/stats.html"
UTILS = Path(settings.BASE_DIR) / "dashboard/static/js/stats/utils.js"


class BehaviorBarScaleTests(SimpleTestCase):
    def correlation_row(self) -> str:
        source = STATS.read_text()
        start = source.index("function correlationRow(")
        return source[start : source.index("\nfunction ", start + 1)]

    def test_the_rates_are_fractions_where_they_are_printed(self):
        self.assertRegex(
            UTILS.read_text(),
            r"formatRate: function\(rate\) \{\s*const pct = \(rate \|\| 0\) \* 100;",
        )

    def test_the_bars_turn_the_fraction_into_a_percentage(self):
        bar = re.search(r"const bar = \(value, tone\) => (.*?);\n", self.correlation_row(), re.S)
        self.assertIsNotNone(bar)
        self.assertIn("value * 100", bar.group(1))
        self.assertIn("Math.min(100, pct)", bar.group(1))
