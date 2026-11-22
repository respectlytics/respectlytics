"""Every package is installed at the version the lock holds, with its hash checked.

Here that is uv.lock, made from pyproject.toml: every package in it carries hashes, and no
dependency pyproject.toml names is held below its newest release by an upper bound, unless a
line `# versions-due: hold <name> <reason>` names the concrete failure that forces it (the
loheden-security skill, "Newest versions, proved compatible"). The lock, not a bound, decides
what is installed. `uv sync --locked` installs from it, and fails when the two files
disagree. The community edition's repository has no uv.lock, only the requirements.txt
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

# An upper bound: <N, <=N or <N.M.
UPPER = re.compile(r"<=?\s*[0-9]")
HOLD = re.compile(r"#\s*versions-due:\s*hold\s+(\S+)\s+\S")


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

    def test_no_upper_bound_without_a_recorded_hold(self):
        if not os.path.exists(PYPROJECT):
            self.skipTest("the community edition, which has requirements.txt instead")
        with open(PYPROJECT, "rb") as f:
            project = tomllib.load(f)
        with open(PYPROJECT, encoding="utf-8") as f:
            held = {m.group(1).lower() for m in HOLD.finditer(f.read())}
        named = list(project["project"]["dependencies"])
        for group in project["dependency-groups"].values():
            named += [d for d in group if isinstance(d, str)]
        capped = [
            d
            for d in named
            if UPPER.search(d) and re.match(r"[A-Za-z0-9_.\-]+", d).group(0).lower() not in held
        ]
        self.assertEqual(
            capped, [], "an upper bound needs `# versions-due: hold <name> <reason>` beside it"
        )


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
