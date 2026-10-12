#!/usr/bin/env python3
"""
Convert Alkimi chat exports into session files the reader can open.

Usage
-----
    python3 convert_alkimi.py FILE_OR_FOLDER [...] [-o OUT_DIR]

Give it any mix of .json files and folders. Every Alkimi export it finds becomes
`<name>.verbatim.json`, written to OUT_DIR (default: next to the original).
Anything that is not an Alkimi export is skipped and named. Nothing is
overwritten unless --force is given.

What a converted file is, and is not
------------------------------------
An Alkimi export is a copy made after the fact, not a capture made as it
happened. The roles carry over (Alkimi tags each message itself), but the export
has no system prompt, no typing time, and no deleted turns. So the converted file
says so in its `schema` field, and leaves those fields out instead of guessing.

The student's name is in every Alkimi message. It is dropped: participant, group
and section are left blank, because this instrument works in codes, not names.
"""
import argparse, json, re, sys
from pathlib import Path

SCHEMA = "converted from alkimi.chat-export/1 (not a verbatim capture)"


def word_count(s):
    # Each CJK ideograph one word, each other run one word -- as the page counts.
    return len(re.findall(r"[一-鿿]|[^\s一-鿿]+", s or ""))


def convert(d):
    turns = []
    for i, m in enumerate(d.get("messages") or []):
        text = m.get("content") or ""
        role = "student" if m.get("role") == "user" else "ai"
        t = {"i": i, "role": role, "ts": m.get("created_at"), "text": text,
             "word_count": word_count(text), "char_count": len(text)}
        if role == "ai" and m.get("response_duration_ms") is not None:
            t["latency_ms"] = m["response_duration_ms"]
        turns.append(t)
    chat = d.get("chat") or {}
    return {
        "schema": SCHEMA,
        "participant": None, "group": None, "section": None,
        "provider": "Alkimi", "model": chat.get("agent_name"),
        "title": chat.get("title"),
        "started_utc": chat.get("created_at"), "exported_utc": d.get("exported_at"),
        "activity_prompt": {"source": "not in the export"},
        "turns": turns,
    }


def inputs(paths):
    for p in map(Path, paths):
        if p.is_dir():
            yield from sorted(f for f in p.rglob("*.json") if not f.name.endswith(".verbatim.json"))
        else:
            yield p


def main():
    ap = argparse.ArgumentParser(description="Convert Alkimi chat exports for the verbatim reader.")
    ap.add_argument("paths", nargs="+", help="export files or folders of them")
    ap.add_argument("-o", "--out", help="folder for converted files (default: beside each original)")
    ap.add_argument("--force", action="store_true", help="overwrite existing converted files")
    a = ap.parse_args()

    out_dir = Path(a.out) if a.out else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    done = skipped = 0
    for src in inputs(a.paths):
        try:
            d = json.loads(src.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            print(f"skip  {src}  (not readable JSON: {e})"); skipped += 1; continue
        if not (isinstance(d, dict) and d.get("format") == "alkimi.chat-export"):
            print(f"skip  {src}  (not an Alkimi export)"); skipped += 1; continue
        dst = (out_dir or src.parent) / (src.stem + ".verbatim.json")
        if dst.exists() and not a.force:
            print(f"skip  {src}  ({dst.name} already exists; --force to replace)"); skipped += 1; continue
        dst.write_text(json.dumps(convert(d), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"ok    {src}  ->  {dst}"); done += 1

    print(f"\n{done} converted, {skipped} skipped.")
    return 0 if done or not skipped else 1


if __name__ == "__main__":
    sys.exit(main())
