"""Fail when a forbidden character (the middle dot and look-alikes) appears
anywhere in the application sources."""

import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "common"))

from winiso.i18n import FORBIDDEN_CHARS  # noqa: E402

bad = []
for folder in ("common", "windows", "macos", "linux"):
    for dirpath, _, files in os.walk(os.path.join(ROOT, folder)):
        if os.sep + "build" in dirpath or os.sep + "dist" in dirpath:
            continue
        for name in files:
            if not name.endswith((".py", ".txt", ".desktop", ".plist", ".sh", ".ps1", ".bat")):
                continue
            path = os.path.join(dirpath, name)
            with open(path, encoding="utf-8", errors="replace") as f:
                for lineno, line in enumerate(f, 1):
                    # The list of forbidden characters itself is written as escapes.
                    if any(ch in line for ch in FORBIDDEN_CHARS):
                        bad.append("%s:%d: %s" % (os.path.relpath(path, ROOT), lineno, line.strip()))
for line in bad:
    print(line)
print("forbidden characters: %d" % len(bad))
sys.exit(1 if bad else 0)
