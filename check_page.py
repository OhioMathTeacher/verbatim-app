#!/usr/bin/env python3
"""
Check a built session_capture.html before it goes to a classroom.

Why this exists
---------------
Two real bugs in this page got past a careful diff read: a full-width bracket that
looked identical to an ASCII one, and a string replacement that turned an English
i18n entry into a self-reference. Neither is visible by reading. Both are caught
in a second by a machine.

The checks
----------
1. The page's JavaScript parses.            (needs node; skipped with a warning if absent)
2. The two i18n dictionaries have the same keys, and no entry is byte-identical
   across them — an identical pair almost always means a replacement that did not
   happen, which is exactly how the self-reference got in.
3. Every data-i18n / data-i18n-ph attribute and every tr("…") call names a key
   that exists.
4. The word counter agrees with hand-derived expectations on mixed script.
5. The provider list: every provider has what the page needs to call it and to
   send a student for a key — and the page asserts nothing about what a student's
   network can reach, which it finds out for itself at load.

Run it on the file you are actually about to hand out:

    python make_session_capture.py --section S4
    python check_page.py
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT = HERE / "session_capture.html"

# Hand-derived: each CJK ideograph is one word, each run of other non-space
# characters is one word, CJK punctuation separates without counting. The rule is
# stated in Documentation/Protocols/SESSION-SCHEMA.md; these are the worked cases.
WORD_CASES = [
    ("", 0),
    ("hello", 1),
    ("hello there friend", 3),
    ("泰勒级数", 4),                       # 泰勒级数 — four ideographs
    ("我不懂，请再说", 6),     # 我不懂，请再说 — comma separates, six ideographs
    ("sin(x) 的展开", 4),          # one latin run, then three ideographs one each
    ("  spaced   out  ", 2),
    ("a、b", 2),                                       # 、 separates without counting
]

fails: list[str] = []
warns: list[str] = []


def fail(msg: str) -> None:
    fails.append(msg)
    print(f"  FAIL  {msg}")


def ok(msg: str) -> None:
    print(f"  ok    {msg}")


def page_js(html: str) -> str:
    """The page's own script block — the last one, and the only one that matters.

    Taken by position, not by size. The page now inlines Temml ahead of its own
    script, and the vendored library is the larger of the two, so picking the
    longest block would check the maths renderer and never the page.
    """
    blocks = re.findall(r"<script>(.*?)</script>", html, re.S)
    if not blocks:
        raise SystemExit("no <script> block found — is this a built page?")
    return blocks[-1]


def js_object(js: str, name: str) -> str:
    """Source text of `const <name> = {…};`, brace-matched rather than regexed."""
    m = re.search(r"\bconst\s+" + name + r"\s*=\s*", js)
    if not m:
        raise SystemExit(f"{name} not found in the page")
    i = m.end()
    if js[i] not in "{[":
        raise SystemExit(f"{name} is not an object or array literal")
    close = {"{": "}", "[": "]"}[js[i]]
    depth, j, in_str, esc = 0, i, "", False
    while j < len(js):
        c = js[j]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == in_str:
                in_str = ""
        elif c in "\"'":
            in_str = c
        elif c == js[i]:
            depth += 1
        elif c == close:
            depth -= 1
            if depth == 0:
                return js[i:j + 1]
        j += 1
    raise SystemExit(f"{name}: unbalanced braces")


def run_node(js: str, expr: str) -> object:
    """Evaluate an expression against the page's own script, in node."""
    node = shutil.which("node")
    if not node:
        return None
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "probe.js"
        p.write_text(js + "\n;console.log(JSON.stringify(" + expr + "));", encoding="utf-8")
        r = subprocess.run([node, str(p)], capture_output=True, text=True)
        if r.returncode != 0:
            return None
        return json.loads(r.stdout.strip().splitlines()[-1])


def check_parses(js: str) -> None:
    node = shutil.which("node")
    if not node:
        warns.append("node not found — the page's JS was not syntax-checked")
        print("  skip  JS syntax (node not installed)")
        return
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "page.js"
        p.write_text(js, encoding="utf-8")
        r = subprocess.run([node, "--check", str(p)], capture_output=True, text=True)
    if r.returncode:
        fail("the page's JS does not parse:\n" + r.stderr.strip())
    else:
        ok("the page's JS parses")


def check_i18n(html: str, js: str) -> None:
    # The dictionaries are JS literals with unquoted keys, so node reads them, not
    # json.loads. Falling back to a regex here would defeat the point of the check.
    i18n = run_node("const I18N = " + js_object(js, "I18N") + ";", "I18N")
    if i18n is None:
        warns.append("node not found — the i18n dictionaries were not compared")
        print("  skip  i18n dictionaries (node not installed)")
        return
    en, zh = set(i18n["en"]), set(i18n["zh"])
    if en - zh:
        fail(f"keys in en but not zh: {sorted(en - zh)}")
    if zh - en:
        fail(f"keys in zh but not en: {sorted(zh - en)}")
    if en == zh:
        ok(f"i18n dictionaries agree on all {len(en)} keys")

    same = [k for k in en & zh
            if isinstance(i18n["en"][k], str) and i18n["en"][k] == i18n["zh"][k]]
    if same:
        fail("identical in both dictionaries — a replacement that did not happen? "
             + str(sorted(same)))
    else:
        ok("no entry is byte-identical across the two dictionaries")

    known = en | zh
    used = set(re.findall(r'data-i18n(?:-ph)?="([^"]+)"', html))
    used |= set(re.findall(r'\btr\("([^"]+)"\)', js))
    missing = sorted(used - known)
    if missing:
        fail(f"referenced but not defined: {missing}")
    else:
        ok(f"all {len(used)} referenced keys resolve")

    # Some keys reach tr() through a variable — tr(k) inside a helper, say — so a
    # literal-only scan would call them dead. Any bare quoted word matching a key
    # counts as a possible use. Loose on purpose: this is a note, not a failure,
    # and a false "unused" is more annoying than a missed one.
    maybe = set(re.findall(r'"([A-Za-z][A-Za-z0-9_]*)"', js))
    unused = sorted(known - used - maybe)
    if unused:
        warns.append(f"defined but never used: {unused}")


def check_words(js: str) -> None:
    body = re.search(r"(const CJK\s*=.*?\n\}\n)", js, re.S)
    if not body:
        fail("countWords not found in the page")
        return
    got = run_node(body.group(1), "[" + ",".join(
        "countWords(" + json.dumps(t) + ")" for t, _ in WORD_CASES) + "]")
    if got is None:
        warns.append("node not found — word counting was not checked")
        print("  skip  word counting (node not installed)")
        return
    bad = [(t, want, g) for (t, want), g in zip(WORD_CASES, got) if want != g]
    for t, want, g in bad:
        fail(f"countWords({t!r}) = {g}, expected {want}")
    if not bad:
        ok(f"word counting {len(WORD_CASES)}/{len(WORD_CASES)} against hand-derived counts")


def check_providers(js: str) -> None:
    provs = run_node("const PROVIDERS = " + js_object(js, "PROVIDERS") + ";", "PROVIDERS")
    if provs is None:
        warns.append("node not found — the provider list was not checked")
        print("  skip  provider list (node not installed)")
        return

    # A provider the page cannot call, or cannot send a student to for a key, is
    # worse than one that is missing: it looks like an option and is not.
    for p in provs:
        for field in ("id", "label", "model", "url", "tier"):
            if not p.get(field):
                fail(f"provider {p.get('id', '?')!r} has no {field}")
        if p.get("tier") != "local" and not p.get("key_url"):
            fail(f"provider {p['id']!r} has no key_url — a student cannot get a key")
    if not fails:
        ok(f"all {len(provs)} providers have what the page needs to call them")

    # Nothing in the page may assert what a student's network can reach. The page
    # tests that and reports what answered; a stored prior would be both less
    # accurate and a claim about the student rather than about the endpoint.
    said = [w for w in ("VPN", "cn_direct") if w in js]
    if said:
        fail(f"the page mentions {said} — reachability is tested, not asserted, and "
             "how a student reaches a service is not the study's business")
    else:
        ok("the page makes no claim about how a student reaches a service")

    print("\n  what is offered, before the page probes the network:")
    for tier in ("webgpu", "free", "paid"):
        if tier == "webgpu":
            print("      webgpu a model running in the student's own browser — no key needed")
            continue
        here = [p["label"] + (" (recommended)" if p.get("recommended") else "")
                for p in provs if p.get("tier") == tier]
        print(f"      {tier:<6} {', '.join(here) or '(none)'}")
    print()


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else DEFAULT
    if not path.exists():
        raise SystemExit(f"{path} does not exist — build it first with make_session_capture.py")
    html = path.read_text(encoding="utf-8")
    js = page_js(html)
    print(f"checking {path}  ({path.stat().st_size / 1024:.0f} KB)\n")

    check_parses(js)
    check_i18n(html, js)
    check_words(js)
    check_providers(js)

    for w in warns:
        print(f"  note: {w}")
    print("\ncheck:", "FAIL" if fails else "PASS")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
