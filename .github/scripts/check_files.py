"""Checks the pack's files before they're merged: every .json, .bbmodel and .mcmeta file the repository
tracks reads as JSON, and no text file holds a merge's conflict markers (a stash popped over changes, or a
merge, committed as it stood). Prints a line a problem and exits 1 if there are any."""
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
JSON_LIKE = (".json", ".bbmodel", ".mcmeta")
MARKER = re.compile(rb"^(<<<<<<< |>>>>>>> |=======\r?$)", re.M)


def tracked():
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    return [p for p in out.decode("utf-8").split("\0") if p]


def main():
    problems = []
    for path in tracked():
        full = os.path.join(ROOT, path)
        if not os.path.isfile(full):
            continue
        data = open(full, "rb").read()
        if b"\0" in data[:8000]:
            continue  # binary: an image, a sound
        marker = MARKER.search(data)
        if marker and (b"<<<<<<< " in data and b">>>>>>> " in data):
            line = data[:marker.start()].count(b"\n") + 1
            problems.append("%s:%d: merge conflict markers (%s)" % (path, line, marker.group(0).decode().strip()))
            continue
        if path.lower().endswith(JSON_LIKE):
            try:
                json.loads(data.decode("utf-8-sig"))
            except UnicodeDecodeError as e:
                problems.append("%s: not UTF-8 (%s)" % (path, e))
            except json.JSONDecodeError as e:
                problems.append("%s:%d:%d: not valid JSON: %s" % (path, e.lineno, e.colno, e.msg))
    for problem in problems:
        print(problem)
    if problems:
        print("%d file problem%s" % (len(problems), "" if len(problems) == 1 else "s"))
        sys.exit(1)
    print("files ok")


if __name__ == "__main__":
    main()
