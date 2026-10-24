"""Every package is installed at the version the lock holds, with its hash checked.

Here that is uv.lock, made from pyproject.toml: every package in it carries hashes, and every
dependency pyproject.toml names is bounded above, so a new lock cannot take a breaking release
by itself. CI and the deploy gate install with `uv sync --locked`, which fails when the two
files disagree. The community edition's repository has no uv.lock, only the requirements.txt
scripts/sync_to_oss.py exports from it, so there this test checks that file instead: every
line pinned to one version and hashed.
"""

import os
import re
import tomllib

from django.test import SimpleTestCase

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCK = os.path.join(REPO, "uv.lock")
PYPROJECT = os.path.join(REPO, "pyproject.toml")
REQUIREMENTS = os.path.join(REPO, "requirements.txt")

# A bound written as <N or <N.M; an exact == pin needs none.
UPPER = re.compile(r"(<[0-9]|==[0-9])")


class LockTest(SimpleTestCase):
    def test_every_locked_package_has_a_hash(self):
        if not os.path.exists(LOCK):
            self.skipTest("the community edition, which has requirements.txt instead")
        with open(LOCK, "rb") as f:
            packages = tomllib.load(f)["package"]
        unhashed = sorted(
            p["name"]
            for p in packages
            if p.get("source", {}).get("virtual") is None
            and not (
                p.get("sdist", {}).get("hash") or any(w.get("hash") for w in p.get("wheels", []))
            )
        )
        self.assertEqual(unhashed, [], "every locked package needs its hashes")
        self.assertGreater(len(packages), 1)

    def test_every_direct_dependency_is_bounded(self):
        if not os.path.exists(PYPROJECT):
            self.skipTest("the community edition, which has requirements.txt instead")
        with open(PYPROJECT, "rb") as f:
            project = tomllib.load(f)
        named = list(project["project"]["dependencies"])
        named += [d for d in project["dependency-groups"]["dev"] if isinstance(d, str)]
        unbounded = [d for d in named if not UPPER.search(d)]
        self.assertEqual(unbounded, [], "bound each range by the major version it is tested on")


class CommunityRequirementsTest(SimpleTestCase):
    def test_every_requirement_is_pinned_and_hashed(self):
        if not os.path.exists(REQUIREMENTS):
            self.skipTest("respectlytics.com, where uv.lock is the lock")
        problems, current = [], None
        with open(REQUIREMENTS, encoding="utf-8") as f:
            for raw in f:
                line = raw.split("#", 1)[0].rstrip()
                if not line.strip():
                    continue
                if raw.startswith(" "):
                    if current and line.strip().startswith("--hash=sha256:"):
                        current[1] = True
                    continue
                if current and not current[1]:
                    problems.append(f"{current[0]}: no hash")
                spec = line.split(";", 1)[0].rstrip(" \\")
                if not re.fullmatch(r"[A-Za-z0-9_.\-\[\],]+==[^=\s]+", spec):
                    problems.append(f"{spec}: not pinned to one version")
                current = [spec, False]
        if current and not current[1]:
            problems.append(f"{current[0]}: no hash")
        self.assertEqual(problems, [], "requirements.txt is exported from uv.lock; edit nothing")
