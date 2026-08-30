#!/usr/bin/env python3
"""
Build the self-contained session-capture page students use in class.

Why this exists
---------------
The first corpus was collected by having students paste their conversation into a
Word document — the original instructions say "press CTRL-A to select all of your
conversation, then paste into a Word document." That one step flattened the
formatting that showed who was speaking, and it could not be recovered: two
researchers annotating the same lines reached Krippendorff's alpha between 0.21
and 0.66, below the 0.667 threshold for even a tentative claim.

This page records the conversation as it happens, so `role` is a fact about where
the text came from rather than an inference about what it looks like. Speaker
attribution stops being a measurement.

The activity prompt is built in
-------------------------------
`Data/Activity Materials/.../prompts.tex` is ONE prompt given to every student —
not something they authored. It is embedded here, byte-identical for everyone,
and recorded in each file with its SHA-256. That removes a paste step from a
20-minute activity, removes a source of variance, and makes the prompt a recorded
constant rather than input.

It also removes the question that broke both model attribution runs: whether a
transcript's opening block is the pasted prompt or the AI introducing itself.

Output conforms to `Documentation/Protocols/SESSION-SCHEMA.md`.

No key is written into the page
-------------------------------
The browser calls the provider directly, using a key the student enters in AI
Setup — their own, or the one the instructor reads out on the day. Nothing is
baked into this file, so the built page is a plain static document that can be
emailed, put on the LMS, or copied to a drive. A student who views source sees a
list of provider names and endpoints and no credential.

The key is kept in the student's own browser alongside their conversation, so a
session cut short by the bell can be finished later in the same browser; losing
the key would mean losing the work. "Forget all keys" removes it deliberately.

Because the browser makes the call, CORS applies. Every endpoint offered was
preflight-verified, **including from a `file://` page**: a file sends
`Origin: null`, and all eight either reflect it or answer `*`, so opening the
built file directly works. Serving it from a URL is still the better way to run a
class — one link, one version, nothing to distribute — but it is a convenience,
not a requirement.

The picker only lists what works, and nobody is asked why
---------------------------------------------------------
Not every provider answers from every network. The page finds out for itself: at
load it sends an empty request to each endpoint and quietly drops the ones that
do not answer, so by the time a student opens AI Setup the list is simply their
options. No button, no diagnostics, no report — a student is choosing an AI
teacher, not troubleshooting a connection.

Two cases make the page ignore what it found, both protecting the rule that every
student must have a viable path: nothing answered anywhere (the probe is
unreliable then — no network yet, opened from a file — and a dialog with no
options is far worse than one listing something that might not work), and any
endpoint that has not answered yet.

The result is recorded as `network_check`: which endpoints answered and when. A
fact about the endpoints, never a claim about the student — nothing is asked or
inferred about their connection, their location, or how they reach a service.

`--section` is still fixed at build time, since thirty students in one room
should not each be asked a question with one right answer.

Deployment
----------
    # the build for the classroom
    python make_session_capture.py --section S4

    # look at the interface — no keys, no network, opens straight from disk
    python make_session_capture.py --demo

    # verify a key works before class, from the command line
    python make_session_capture.py --key groq=$GROQ_API_KEY --check

`--key` at build time only decides which providers are *offered* and is used by
`--check`; the value is never written into the page.
"""
from __future__ import annotations

import argparse
import colorsys, hashlib, json, os, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Bumped by hand, when a change is worth telling a user about.
VERSION = "1.2.1"
# The activity is whatever prompt you point this at. `examples/` holds the one
# from the Taylor Series study it was first built for.
PROMPT_DEFAULT = HERE / "examples" / "taylor-series.txt"
PROMPT_MARKER = "------- BEGIN PROMPT HERE -------"

# Endpoints verified browser-callable 2026-08-14 (OPTIONS preflight from a LAN
# origin returned access-control-allow-origin reflecting that origin, and
# access-control-allow-headers including authorization,content-type).
# All are OpenAI-compatible /chat/completions.
# Students supply the key themselves -- their own, or one the instructor reads out
# on the day. Grouped the way the other apps group them: a personal/local server,
# services with a $0 tier, and paid services.
#
# Nothing here records whether a service is reachable from a given classroom.
# The page finds that out by asking the endpoints, which is both more accurate
# than a stored guess and the only version of the question worth writing down.
#
# CORS matters again now that the browser calls the provider directly. Every
# OpenAI-compatible endpoint below was preflight-verified 2026-08-14.
PROVIDERS = [
    # Domestic services first, since they are the ones most likely to answer from
    # a Chengdu classroom. The rest are offered too: which of them a given student
    # can actually reach is a question the page answers by trying, not by guessing.
    {"id": "deepseek", "label": "DeepSeek", "tier": "paid", "api": "openai",
     "recommended": True,
     "model": "deepseek-chat",
     "url": "https://api.deepseek.com/chat/completions",
     "blurb": "\u6df1\u5ea6\u6c42\u7d22 \u00b7 the model the original study used.",
     "key_url": "https://platform.deepseek.com/api_keys", "blurb_zh": "深度求索 · 原研究使用的模型。",
     "prefix": "sk-",
     "placeholder": "sk-\u2026"},
    {"id": "moonshot", "label": "Kimi", "tier": "paid", "api": "openai",
     "model": "moonshot-v1-8k",
     "url": "https://api.moonshot.cn/v1/chat/completions",
     "blurb": "\u6708\u4e4b\u6697\u9762 Moonshot AI.",
     "key_url": "https://platform.moonshot.cn/console/api-keys", "blurb_zh": "月之暗面 Moonshot AI。",
     "prefix": "sk-",
     "placeholder": "sk-\u2026"},
    {"id": "zhipu", "label": "GLM", "tier": "paid", "api": "openai",
     "model": "glm-4-plus",
     "url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
     "blurb": "\u667a\u8c31\u6e05\u8a00 Zhipu AI.",
     "key_url": "https://open.bigmodel.cn/usercenter/apikeys", "blurb_zh": "智谱清言 Zhipu AI。",
     "prefix": "",
     "placeholder": "\u2026"},
    {"id": "qwen", "label": "Qwen", "tier": "paid", "api": "openai",
     "model": "qwen-plus",
     "url": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
     "blurb": "\u901a\u4e49\u5343\u95ee Alibaba Cloud.",
     "key_url": "https://bailian.console.aliyun.com/", "blurb_zh": "通义千问 阿里云。",
     "prefix": "sk-",
     "placeholder": "sk-\u2026"},
    {"id": "openai", "label": "OpenAI", "tier": "paid", "api": "openai",
     "model": "gpt-5",
     "url": "https://api.openai.com/v1/chat/completions",
     "blurb": "ChatGPT's models. Bring your own key.",
     "key_url": "https://platform.openai.com/api-keys", "blurb_zh": "ChatGPT 的模型。需自备密钥。",
     "prefix": "sk-",
     "placeholder": "sk-\u2026"},
    {"id": "openrouter", "label": "OpenRouter", "tier": "paid", "api": "openai",
     "model": "deepseek/deepseek-chat",
     "url": "https://openrouter.ai/api/v1/chat/completions",
     "blurb": "One key, many models.",
     "key_url": "https://openrouter.ai/keys", "blurb_zh": "一个密钥，多种模型。",
     "prefix": "sk-or-",
     "placeholder": "sk-or-\u2026"},
    # llama-3.3-70b-versatile stopped being served on 16 August 2026. It stayed
    # pinned here after the classroom apps were swept, so every published activity
    # offered Groq -- the free, any-email option, and therefore the one a student
    # without a Google account reaches for -- and returned an error on use.
    #
    # Pinned by hand, and it must stay that way: the classroom apps may chase
    # whatever model is live, but the instrument records `provider` and `model`
    # per session as covariates, and a study tool that silently changed model
    # mid-collection would produce sessions that cannot be compared with each
    # other. When this id retires, edit this line -- do not make it self-heal.
    {"id": "groq", "label": "Groq", "tier": "free", "api": "openai",
     "model": "openai/gpt-oss-120b",
     "url": "https://api.groq.com/openai/v1/chat/completions",
     "blurb": "Free, fast, open-weight models.",
     "key_url": "https://console.groq.com/keys", "blurb_zh": "免费、快速的开源模型。",
     "prefix": "gsk_",
     "placeholder": "gsk_\u2026"},
    {"id": "gemini", "label": "Gemini", "tier": "free", "api": "gemini",
     "model": "gemini-2.5-flash",
     "url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
     "blurb": "Google's free tier. No card required.",
     "key_url": "https://aistudio.google.com/apikey", "blurb_zh": "谷歌免费额度。无需信用卡。",
     "prefix": "AIza",
     "placeholder": "AIza\u2026"},
]


# Ports probed when the Local tab opens, so a student already running a model
# finds it without typing anything. Same list the other apps use.
LOCAL_PORTS = [
    {"port": 11434, "hint": "Ollama"},
    {"port": 1234,  "hint": "LM Studio"},
    {"port": 8765,  "hint": "Athena / OpenAI-compatible shim"},
]

# Extra providers live in providers.local.json beside this script, so an endpoint
# that is internal, licensed, or not yet public never has to be committed. Both
# this builder and serve_collect.py read it, so the page and the server always
# agree on what exists. Keys are NOT stored here -- they come from --key or the
# environment at run time, as with every other provider.
#
# Because serve_collect.py makes the API call rather than the browser, a provider
# does not need permissive CORS headers to be usable. Any OpenAI-compatible
# /chat/completions endpoint works.
#
#   [{"id": "alkimi", "label": "Alkimi", "blurb": "Miami pilot",
#     "url": "https://<base>/v1/chat/completions", "model": "<model>",
#     "env": "ALKIMI_API_KEY", "test_only": true}]
LOCAL_PROVIDERS = HERE / "providers.local.json"

def _local_providers() -> list[dict]:
    if not LOCAL_PROVIDERS.exists():
        return []
    try:
        extra = json.loads(LOCAL_PROVIDERS.read_text(encoding="utf-8"))
    except Exception as e:
        raise SystemExit(f"{LOCAL_PROVIDERS}: {e}")
    if not isinstance(extra, list):
        raise SystemExit(f"{LOCAL_PROVIDERS}: expected a list of provider objects")
    known = {p["id"] for p in PROVIDERS}
    out = []
    for q in extra:
        missing = [k for k in ("id", "label", "url", "model") if not q.get(k)]
        if missing:
            raise SystemExit(f"{LOCAL_PROVIDERS}: entry {q.get('id', '?')!r} missing {missing}")
        if q["id"] in known:
            raise SystemExit(f"{LOCAL_PROVIDERS}: {q['id']!r} collides with a built-in provider")
        q.setdefault("env", q["id"].upper() + "_API_KEY")
        q.setdefault("blurb", "")
        # Reachability from the classroom cannot be assumed for an endpoint we did
        # not verify, so a local provider stays out of the default picker unless
        # its file says otherwise.
        q.setdefault("test_only", True)
        out.append(q)
    return out


PROVIDERS = PROVIDERS + _local_providers()

# Token replacement rather than str.format — the CSS/JS is dense with braces, and
# doubling them all is how the apostrophe bug got in last time (see make_packet.py).
TEMPLATE = r"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
:root{
  --paper:#f6f2ea; --card:#fffdf8; --ink:#221f1a; --muted:#726a5f; --rule:#e4dccd;
  --ai:#2f5d6b; --ai-bg:#eef4f5; --ai-edge:#cfe0e3;
  --stu:__ACCENT__; --stu-bg:__ACCENT_BG__; --stu-edge:__ACCENT_EDGE__;
  --accent:__ACCENT__; --ok:#4a7a55; --warn:#a8622e;
  --shadow:0 1px 2px rgba(60,45,25,.05), 0 6px 20px -8px rgba(60,45,25,.14);
  --serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,"Songti SC","Noto Serif CJK SC","Noto Serif SC",serif;
  --sans:ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Noto Sans CJK SC","PingFang SC","Microsoft YaHei",sans-serif;
  --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,monospace;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --paper:#16150f; --card:#1e1c16; --ink:#ece6d9; --muted:#9d968a; --rule:#332f26;
  --ai:#8fc0cd; --ai-bg:#182428; --ai-edge:#26383d;
  --stu:#dda278; --stu-bg:#241a13; --stu-edge:#3d2b1e;
  --accent:#dda278; --ok:#8ab894; --warn:#d99a63;
  --shadow:0 1px 2px rgba(0,0,0,.3), 0 8px 24px -10px rgba(0,0,0,.5);
}}
/* The same values again, for a reader who asked for dark on a light machine.
   Keep the two blocks in step -- they are one palette written twice. */
:root[data-theme="dark"]{
  --paper:#16150f; --card:#1e1c16; --ink:#ece6d9; --muted:#9d968a; --rule:#332f26;
  --ai:#8fc0cd; --ai-bg:#182428; --ai-edge:#26383d;
  --stu:#dda278; --stu-bg:#241a13; --stu-edge:#3d2b1e;
  --accent:#dda278; --ok:#8ab894; --warn:#d99a63;
  --shadow:0 1px 2px rgba(0,0,0,.3), 0 8px 24px -10px rgba(0,0,0,.5);
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);
  font-size:16.5px;line-height:1.65;
  background-image:radial-gradient(circle at 12% -8%, rgba(154,87,52,.05), transparent 45%),
                   radial-gradient(circle at 92% 4%, rgba(47,93,107,.05), transparent 42%);
  background-attachment:fixed}
.wrap{max-width:780px;margin:0 auto;padding:40px 22px 130px}
.mast{display:flex;align-items:center;gap:14px;border-bottom:1px solid var(--rule);
  padding:0 0 16px;margin:0 0 30px}
.avatar{width:48px;height:48px;border-radius:50%;object-fit:cover;flex:0 0 auto;
  border:2px solid var(--card);box-shadow:0 0 0 1px var(--rule), var(--shadow)}
/* Which build this page is, said quietly. Worth having on screen because the
   page is handed out as a file and then lives on its own: by the time anyone
   asks what made it, the answer is not anywhere else. */
.ver{margin:24px 0 0;text-align:center;font-family:var(--mono);font-size:11px;
  color:var(--muted);opacity:.6;user-select:all}
.foot{margin:44px 0 0;padding:18px 0 0;border-top:1px solid var(--rule);
  display:flex;align-items:center;gap:12px;font-size:13px;line-height:1.5;color:var(--muted)}
.foot img{width:34px;height:34px;border-radius:50%;object-fit:cover;flex:0 0 auto;
  border:1px solid var(--rule)}
h1{font-family:var(--serif);font-size:27px;font-weight:600;letter-spacing:-.01em;margin:0;line-height:1.25}
.mastbtns{margin-left:auto;display:flex;gap:8px;flex:0 0 auto}
.mast .tag{font-size:11.5px;letter-spacing:.13em;text-transform:uppercase;color:var(--muted);
  margin-left:auto;white-space:nowrap;padding-bottom:3px}
.sub{color:var(--muted);font-size:15px;margin:-18px 0 30px}
.card{background:var(--card);border:1px solid var(--rule);border-radius:14px;
  padding:26px 28px;margin:0 0 20px;box-shadow:var(--shadow)}
h2{font-family:var(--serif);font-size:19px;font-weight:600;margin:0 0 6px}
label{display:block;font-size:12px;font-weight:700;letter-spacing:.07em;text-transform:uppercase;
  color:var(--muted);margin:0 0 7px}
.hint{font-size:14px;color:var(--muted);margin:8px 0 0}
input,select,textarea{width:100%;padding:11px 13px;border:1px solid var(--rule);border-radius:9px;
  background:var(--paper);color:var(--ink);font:inherit;transition:border-color .15s, box-shadow .15s}
input::placeholder,textarea::placeholder{font-style:italic;opacity:.62}
input:focus,select:focus,textarea:focus{outline:0;border-color:var(--accent);
  box-shadow:0 0 0 3px color-mix(in srgb, var(--accent) 16%, transparent)}
select{appearance:none;background-image:linear-gradient(45deg,transparent 50%,var(--muted) 50%),
  linear-gradient(135deg,var(--muted) 50%,transparent 50%);
  background-position:calc(100% - 19px) 51%, calc(100% - 14px) 51%;
  background-size:5px 5px, 5px 5px;background-repeat:no-repeat;padding-right:40px}
.row{display:flex;gap:14px;flex-wrap:wrap}
.row>div{flex:1;min-width:132px}
.field{margin:0 0 20px}

/* provider cards — click one, the way Allegory's AI settings panel does it */
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(215px,1fr));gap:11px}
.pcard{position:relative;display:block;text-align:left;font:inherit;cursor:pointer;
  background:var(--paper);color:var(--ink);border:1.5px solid var(--rule);border-radius:12px;
  padding:14px 15px 15px;box-shadow:none;transition:border-color .15s, background .15s, transform .1s}
.pcard:hover:not(:disabled){border-color:color-mix(in srgb, var(--accent) 45%, var(--rule));
  transform:translateY(-1px)}
.pcard[aria-pressed="true"]{border-color:var(--accent);background:var(--card);
  box-shadow:0 0 0 3px color-mix(in srgb, var(--accent) 14%, transparent)}
.pcard[aria-pressed="true"]::after{content:"✓";position:absolute;top:11px;right:13px;
  color:var(--accent);font-weight:700;font-size:15px}
.pcard:disabled{opacity:.42;cursor:not-allowed}
.pcard .pt{display:block;font-family:var(--serif);font-size:17px;font-weight:600;
  letter-spacing:-.005em;margin:0 0 2px;padding-right:20px}
.pcard .pm{display:block;font-family:var(--mono);font-size:11px;color:var(--muted);margin:0 0 7px}
.pcard .pd{display:block;font-size:13px;line-height:1.45;color:var(--muted)}
button{font-family:inherit;font-size:15px;font-weight:600;border:0;border-radius:9px;
  padding:11px 22px;cursor:pointer;background:var(--ink);color:var(--card);
  transition:transform .1s, opacity .15s, box-shadow .15s;box-shadow:var(--shadow)}
button:hover:not(:disabled){transform:translateY(-1px)}
button:active:not(:disabled){transform:translateY(0)}
button:disabled{opacity:.38;cursor:not-allowed;box-shadow:none}
button.ghost{background:transparent;color:var(--ink);border:1px solid var(--rule);box-shadow:none}
button.ghost:hover:not(:disabled){border-color:var(--accent);color:var(--accent)}
button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}

/* conversation */
.strip{display:flex;align-items:center;gap:9px;flex-wrap:wrap;
  padding:12px 18px;margin:0 0 22px;background:var(--card);
  border:1px solid var(--rule);border-radius:12px;box-shadow:var(--shadow)}
.pill{font-size:12px;letter-spacing:.04em;color:var(--muted);
  border:1px solid var(--rule);border-radius:99px;padding:3px 11px;white-space:nowrap}
.pill.live{color:var(--ok);border-color:color-mix(in srgb, var(--ok) 35%, var(--rule))}
.strip .sp{margin-left:auto}
.turn{position:relative;border-radius:14px;padding:15px 19px;margin:0 0 16px;
  font-family:var(--serif);font-size:16.5px;line-height:1.7;
  white-space:pre-wrap;overflow-wrap:anywhere;box-shadow:var(--shadow);
  animation:rise .22s ease-out}
@keyframes rise{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:none}}
.turn.ai{background:var(--ai-bg);border:1px solid var(--ai-edge);margin-right:11%}
.turn.student{background:var(--stu-bg);border:1px solid var(--stu-edge);margin-left:11%}
.who{display:block;font-family:var(--sans);font-size:10.5px;font-weight:700;
  letter-spacing:.15em;text-transform:uppercase;margin:0 0 8px}
.turn.ai .who{color:var(--ai)} .turn.student .who{color:var(--stu)}

/* The report. What the student just handed in, rendered from the session already
   in memory -- no file to reopen, no page to visit, so it works from a disk and
   on a network that does not reach anything. Timings appear here and nowhere in
   the activity itself: showing a clock during the work would make them hurry,
   but afterwards it is simply what the record says about them. */
#report{margin:26px 0 0;border-top:1px solid var(--rule);padding:22px 0 0}
#report .turn{animation:none}
#report .rmeta{display:block;font-family:var(--mono);font-size:11px;color:var(--muted);
  margin:9px 0 0;white-space:normal}
#report h3{font-family:var(--serif);font-size:17px;font-weight:600;margin:26px 0 10px}
#report .qa{margin:0 0 13px}
#report .qa .q{display:block;font-size:14.5px;margin:0 0 3px}
#report .qa .a{display:block;font-family:var(--mono);font-size:13px;color:var(--muted);
  overflow-wrap:anywhere}
.dots span{display:inline-block;width:6px;height:6px;margin-right:4px;border-radius:50%;
  background:var(--ai);opacity:.35;animation:blink 1.3s infinite}
.dots span:nth-child(2){animation-delay:.18s} .dots span:nth-child(3){animation-delay:.36s}
@keyframes blink{0%,60%,100%{opacity:.28} 30%{opacity:.95}}

/* composer */
.bar{position:fixed;left:0;right:0;bottom:0;background:color-mix(in srgb, var(--card) 92%, transparent);
  backdrop-filter:blur(10px);border-top:1px solid var(--rule);padding:14px 22px 16px}
.bar .inner{max-width:780px;margin:0 auto;display:flex;gap:11px;align-items:flex-end}
.bar textarea{min-height:56px;max-height:180px;border-radius:11px;background:var(--paper);
  font-family:var(--serif);font-size:16px;resize:none}
.bar button{flex:0 0 auto;padding:14px 26px}
/* Maths palette. A Calculus II student typing x\u00b3/3! into a chat box otherwise
   has to hunt for characters their keyboard does not have, and the alternative is
   ASCII that the AI teacher has to guess at. Symbols insert at the cursor;
   templates insert a skeleton with the first field selected and Tab moves through
   the rest. */
.bar .mathbtn{padding:14px 16px;font-family:var(--serif);font-size:19px;line-height:1}
.mathpal{max-width:780px;margin:0 auto 11px;background:var(--paper);border:1px solid var(--rule);
  border-radius:11px;padding:11px 13px;max-height:min(52vh,300px);overflow-y:auto}
.mathtabs{display:flex;gap:4px;border-bottom:1px solid var(--rule);margin:0 0 10px}
.mathtabs button{background:transparent;border:0;border-radius:0;box-shadow:none;cursor:pointer;
  color:var(--muted);font-family:var(--sans);font-size:12.5px;font-weight:600;
  padding:6px 11px;min-width:0;height:auto;border-bottom:2px solid transparent}
.mathtabs button:hover{color:var(--ink);background:transparent}
.mathtabs button[aria-selected="true"]{color:var(--accent);border-bottom-color:var(--accent)}
.mathgrp{display:flex;align-items:baseline;gap:9px;flex-wrap:wrap;margin:0 0 8px}
.mathgrp:last-child{margin-bottom:0}
.mathgrp b{font-size:10.5px;font-weight:700;letter-spacing:.09em;text-transform:uppercase;
  color:var(--muted);flex:0 0 84px}
.mathgrp span{display:flex;gap:5px;flex-wrap:wrap;flex:1}
.mathpal button{padding:0;box-shadow:none;background:var(--card);border:1px solid var(--rule);
  color:var(--ink);border-radius:8px;font-family:var(--serif);font-size:16px;line-height:1;
  min-width:34px;height:32px;flex:0 0 auto}
.mathpal button.tmpl{font-size:13px;font-family:var(--sans);font-weight:600;padding:0 11px}
.mathpal button:hover{border-color:var(--accent);color:var(--accent);transform:none}

.err{color:var(--warn);font-size:14.5px;margin:12px 0 0;white-space:pre-wrap;
  border-left:3px solid var(--warn);padding-left:12px}
.err:empty{display:none}
.hide{display:none !important}
.demo{background:var(--warn);color:#fff;text-align:center;font-size:13px;
  padding:8px;font-weight:600;letter-spacing:.03em}
details.prompt{margin:22px 0 0;border-top:1px solid var(--rule);padding:16px 0 0}
details.prompt summary{cursor:pointer;font-size:13.5px;color:var(--muted);font-weight:600}
details.prompt pre{font-family:var(--mono);font-size:12.5px;line-height:1.6;white-space:pre-wrap;
  color:var(--muted);max-height:280px;overflow:auto;margin:14px 0 0;
  background:var(--paper);border:1px solid var(--rule);border-radius:9px;padding:14px}

/* AI Setup — the same shape as the panel in clique / allegory / marginalia:
   three tiers (a personal server, $0 services, paid services), cards you click,
   key typed in by the person using it. */
.gear{background:transparent;border:1px solid var(--rule);color:var(--muted);
  border-radius:9px;padding:7px 11px;font-size:16px;line-height:1;box-shadow:none;flex:0 0 auto}
.gear:hover{border-color:var(--accent);color:var(--accent)}
.gear.ready{color:var(--ok);border-color:color-mix(in srgb, var(--ok) 40%, var(--rule))}
.gear.ready:hover{color:var(--ok);border-color:var(--ok)}
.ai-modal-overlay{display:none;position:fixed;inset:0;z-index:9999;padding:18px;
  background:rgba(24,18,10,.5);backdrop-filter:blur(3px);align-items:center;justify-content:center}
.ai-modal-overlay.open{display:flex}
.ai-modal{background:var(--card);border:1px solid var(--rule);border-radius:15px;padding:26px 28px;
  width:620px;max-width:100%;max-height:calc(100vh - 36px);overflow-y:auto;
  box-shadow:0 24px 60px -20px rgba(40,28,14,.45);color:var(--ink)}
.ai-modal{position:relative}
.ai-x{position:absolute;top:14px;right:16px;background:transparent;border:0;box-shadow:none;
  color:var(--muted);font-size:26px;line-height:1;padding:2px 8px;border-radius:8px}
.ai-x:hover{color:var(--ink);background:var(--paper);transform:none}
.ai-modal h2{font-family:var(--serif);font-size:22px;margin:0 0 5px;padding-right:34px}
.ai-modal-sub{margin:0 0 18px;font-size:14px;color:var(--muted);line-height:1.55}
/* Guidance, not an alarm. Nothing in this dialog gets a warning box. */
.tabnote{margin:0 0 14px;font-size:13px;line-height:1.55;color:var(--muted)}
.ai-tabs{display:flex;gap:5px;border-bottom:1px solid var(--rule);margin:0 0 16px}
.ai-tab{background:transparent;border:0;box-shadow:none;color:var(--muted);cursor:pointer;
  font-size:13.5px;font-weight:600;padding:9px 14px;border-bottom:2px solid transparent;border-radius:0}
.ai-tab:hover{color:var(--ink);transform:none}
.ai-tab[aria-selected="true"]{color:var(--accent);border-bottom-color:var(--accent)}
.ai-provider-cards{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin:0 0 6px}
@media (max-width:520px){.ai-provider-cards{grid-template-columns:1fr}}
.ai-provider-card{position:relative;background:var(--paper);border:1.5px solid var(--rule);
  border-radius:11px;padding:13px 14px;cursor:pointer;text-align:left;font-family:inherit;
  color:var(--ink);box-shadow:none;transition:background .15s,border-color .15s,transform .1s}
.ai-provider-card:hover{transform:translateY(-1px);
  border-color:color-mix(in srgb, var(--accent) 42%, var(--rule))}
.ai-provider-card.selected{border-color:var(--accent);
  background:color-mix(in srgb, var(--accent) 9%, var(--card))}
.ai-provider-card.add-server{border-style:dashed}
.ai-card-title{font-weight:600;font-size:15px;margin:0 0 3px}
.ai-card-model{font-family:var(--mono);font-size:11px;color:var(--muted);margin:0 0 5px}
.ai-card-desc{font-size:12.5px;color:var(--muted);line-height:1.45}
.ai-card-badge{display:inline-block;font-size:10px;font-weight:700;letter-spacing:.08em;
  text-transform:uppercase;padding:2px 8px;border-radius:999px;margin-top:8px}
.ai-badge-free{background:color-mix(in srgb,var(--ok) 22%,transparent);color:var(--ok)}
.ai-badge-paid{background:color-mix(in srgb,var(--warn) 20%,transparent);color:var(--warn)}
.ai-badge-local{background:color-mix(in srgb,var(--ai) 20%,transparent);color:var(--ai)}
.ai-badge-rec{background:color-mix(in srgb,var(--accent) 20%,transparent);color:var(--accent);margin-left:6px}
.localpanel{margin:14px 0 4px;background:var(--paper);border:1px solid var(--rule);
  border-radius:11px;padding:15px 17px}
.localpanel h3{font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;
  color:var(--muted);margin:0 0 9px}
.steps{display:grid;grid-template-columns:repeat(2,1fr);gap:9px}
@media (max-width:520px){.steps{grid-template-columns:1fr}}
.step{display:flex;gap:10px;align-items:center;text-align:left;cursor:pointer;
  background:var(--card);border:1px solid var(--rule);border-radius:10px;padding:11px 12px;
  box-shadow:none;font-family:inherit;color:var(--ink)}
.step:hover{border-color:var(--accent);transform:translateY(-1px)}
.step .smore{margin-left:auto;color:var(--muted);font-size:18px;line-height:1}
.step .sn{flex:0 0 22px;height:22px;border-radius:50%;background:var(--accent);color:var(--card);
  font-size:12px;font-weight:700;display:grid;place-items:center;margin-top:1px}
.step .sb{flex:1;min-width:0}
.step .st{font-size:13.5px;font-weight:600;line-height:1.35}

.sc{display:block;font-family:var(--mono);font-size:12.5px;margin:7px 0 0;padding:7px 10px;
  background:var(--card);border:1px solid var(--rule);border-radius:7px;overflow-x:auto;
  white-space:pre;color:var(--ink)}
.sl{margin:11px 0 0;font-size:14px}
.sl a{color:var(--accent);font-weight:600;text-decoration:none}
.sl a:hover{text-decoration:underline}
.snote{margin:11px 0 0;font-size:13px;color:var(--warn);line-height:1.45}
.wgpu-state{margin:11px 0 0;font-size:13px;color:var(--muted);line-height:1.5}
.wgpu-state.bad{color:var(--warn)}
.wgpu-bar{margin:9px 0 0;height:6px;border-radius:3px;background:var(--rule);overflow:hidden}
.wgpu-bar i{display:block;height:100%;background:var(--accent);width:0;
  transition:width .25s ease}
.ai-key-section{margin:14px 0 4px}
.ai-key-hint{font-size:12.5px;color:var(--muted);margin:8px 0 0;line-height:1.5}
.ai-key-hint a{color:var(--accent);font-weight:600}
.ai-modal-actions{display:flex;justify-content:flex-end;gap:10px;margin:20px 0 0;align-items:center}
button.ghost.danger{margin-right:auto;color:var(--warn);border-color:color-mix(in srgb,var(--warn) 30%,var(--rule))}
button.ghost.danger:hover:not(:disabled){border-color:var(--warn);color:var(--warn)}
.q{border-top:1px solid var(--rule);padding:20px 0 4px;margin:0}
.q:first-child{border-top:0;padding-top:6px}
.q .qt{font-size:15.5px;line-height:1.5;margin:0 0 12px;font-weight:600}
.q .qn{color:var(--muted);font-weight:400;margin-right:7px}
.opt{display:flex;align-items:flex-start;gap:10px;padding:7px 0;cursor:pointer;font-size:14.5px;line-height:1.45}
.opt input{width:auto;flex:0 0 auto;margin:3px 0 0;accent-color:var(--accent)}
.opt span{flex:1}
.q .spec{margin:6px 0 0 26px;width:calc(100% - 26px);font-size:14px;padding:8px 10px}
/* A scale reads as a scale: one row, ends labelled, so the order is visible at a
   glance instead of having to be read down a column of five radio buttons. */
.lik{display:flex;gap:4px;margin:4px 0 0}
.lik label{display:flex;flex-direction:column;align-items:center;gap:7px;flex:1;
  text-align:center;cursor:pointer;padding:11px 5px;border:1px solid var(--rule);
  border-radius:10px;background:var(--paper);text-transform:none;letter-spacing:0;
  font-size:12.5px;font-weight:500;color:var(--muted);line-height:1.3;margin:0}
.lik label:hover{border-color:var(--accent)}
.lik label:has(input:checked){border-color:var(--accent);color:var(--ink);
  background:color-mix(in srgb, var(--accent) 9%, var(--card))}
.lik input{width:auto;margin:0;accent-color:var(--accent)}
@media (max-width:560px){.lik{flex-direction:column}
  .lik label{flex-direction:row;justify-content:flex-start;gap:11px;text-align:left}}
.q textarea{min-height:92px}
.ai-status{display:flex;align-items:center;gap:10px;flex-wrap:wrap;
  background:var(--paper);border:1px solid var(--rule);border-radius:10px;padding:12px 14px}
.ai-status .dot{width:8px;height:8px;border-radius:50%;background:var(--muted);flex:0 0 auto}
.ai-status.ready .dot{background:var(--ok)}
.ai-status .txt{font-size:14px}
.ai-status button{margin-left:auto;padding:7px 14px;font-size:13.5px}
/* The bin. Quiet until the exchange is hovered or the button is focused, so it
   is reachable without sitting over the conversation asking to be pressed. */
.turn{position:relative}
.binbtn{position:absolute;top:8px;right:9px;background:transparent;border:0;cursor:pointer;
  font-size:15px;line-height:1;padding:5px 6px;border-radius:8px;color:var(--muted);
  opacity:0;transition:opacity .12s ease, color .12s ease}
.turn:hover .binbtn, .binbtn:focus-visible{opacity:.75}
.binbtn:hover{opacity:1;color:var(--warn);background:color-mix(in srgb, var(--warn) 12%, transparent)}
.rcalc{display:flex;align-items:center;gap:9px;justify-content:center;margin:0 0 14px;
  font-size:13px;color:var(--muted);flex-wrap:wrap}
.rcalc .rcw{font-style:italic}
.rcalc code{font-family:var(--mono);font-size:12.5px;color:var(--ink);background:var(--paper);
  border:1px solid var(--rule);border-radius:7px;padding:3px 9px}
.rcalc.failed code{border-style:dashed;color:var(--muted)}
.rcalc .rcn{font-size:12px;color:var(--warn)}
.gone{margin:0 0 16px;padding:9px 15px;border:1px dashed var(--rule);border-radius:12px;
  color:var(--muted);font-size:13.5px;font-style:italic;text-align:center}
__RICHTEXT_CSS__
__CALCULATOR_CSS__
__TEMML_CSS__
</style>

<script>
/* Light or dark, decided before anything is drawn. The page follows the machine
   until someone says otherwise; after that it remembers what they chose. Kept
   here, ahead of the page's own script, so the choice is applied on the first
   paint rather than a moment after it. */
try{
  var t = localStorage.getItem("tea.theme");
  document.documentElement.dataset.theme =
    (t === "light" || t === "dark") ? t
    : (matchMedia("(prefers-color-scheme:dark)").matches ? "dark" : "light");
}catch(e){}
</script>

<div id="demobar" class="demo hide">DEMO MODE — replies are canned. Nothing is sent anywhere.</div>
<div class="wrap">

<div class="mast">
  <img class="avatar hide" id="avatar" alt="">
  <h1 data-i18n="title">__TITLE__</h1>
  <span class="mastbtns">
    <button class="gear" id="theme" title="Light or dark / 浅色或深色"><span id="theme-icon" aria-hidden="true">☾</span></button>
    <button class="gear" id="lang" title="Language / 语言">中文</button>
    <button class="gear" id="gear"><span aria-hidden="true">⚙</span> <span id="gear-txt" data-i18n="aisetup">AI Setup</span></button>
  </span>
</div>

<!-- 1 · who -->
<section id="s-setup">
  <p class="sub" data-i18n="subtitle">__SUBTITLE__</p>
  <div class="card">
    <h2 data-i18n="before">Before you start</h2>
    <p class="hint" style="margin:0 0 22px" data-i18n="codehint">Your instructor gave you a participant code.</p>

    <div class="field">
      <label for="pid" data-i18n="pid">Participant code</label>
      <input id="pid" autocomplete="off" spellcheck="false" data-i18n-ph="pidph" placeholder="Enter code here (e.g., P07)">
    </div>
    <div class="row field">
      <div><label for="grp" data-i18n="group">Group</label><input id="grp" autocomplete="off" spellcheck="false" data-i18n-ph="grpph" placeholder="Enter group here (e.g., G3)"></div>
      <div id="secwrap"><label for="sec" data-i18n="section">Section</label><input id="sec" autocomplete="off" spellcheck="false" data-i18n-ph="secph" placeholder="Enter section here (e.g., S4)"></div>
    </div>
    <div class="field">
      <label data-i18n="yourai">Your AI</label>
      <div class="ai-status" id="ai-status">
        <span class="dot"></span>
        <span class="txt" id="ai-status-txt">Not set up yet</span>
        <button type="button" class="ghost" id="ai-open">Set up</button>
      </div>
      <p class="hint" style="margin-top:10px" data-i18n="aihint">Use your own API key, or the one your instructor gives you.</p>
    </div>

    <p class="err" id="setup-err"></p>
    <p style="margin:24px 0 0"><button id="go-setup" data-i18n="start">Start the activity</button></p>

    <details class="prompt">
      <summary data-i18n="whatai">What the AI has been told (the same for everyone)</summary>
      <pre id="promptview"></pre>
    </details>
  </div>
</section>

<!-- 2 · conversation -->
<section id="s-chat" class="hide">
  <div class="strip">
    <span class="pill" id="p-id"></span>
    <span class="pill" id="p-model"></span>
    <span class="pill" id="p-turns"></span>
    <span class="sp"></span>
    <button id="finish" class="ghost" style="padding:7px 16px;font-size:14px" data-i18n="finish">Finish &amp; export</button>
  </div>
  <div id="log"></div>
  <p class="err" id="chat-err"></p>
</section>

<!-- 3 · survey -->
<section id="s-survey" class="hide">
  <div class="card">
    <h2 data-i18n="surveyh">A few questions before you finish</h2>
    <p class="hint" style="margin:0 0 6px" data-i18n="surveyhint">These are saved in the same file as your conversation. Every question is optional.</p>
    <p class="hint" style="margin:0 0 4px" data-i18n="surveylater">Your work stays saved on this computer.</p>
    <div id="survey-body"></div>
    <p style="margin:26px 0 0"><button id="survey-done" data-i18n="surveydone">Finish and download</button></p>
  </div>
</section>

<!-- 4 · done -->
<section id="s-done" class="hide">
  <div class="card">
    <h2 id="done-h">Finishing…</h2>
    <p id="done-msg" style="margin:8px 0 0">Sending your session to your instructor…</p>

    <p class="hint" id="done-stats" style="margin:22px 0 0"></p>
    <p class="err" id="done-note"></p>
    <p style="margin:26px 0 0">
      <button id="to-survey" class="hide" data-i18n="answerq">Answer the questions</button>
      <button id="see-report" class="ghost" data-i18n="seereport">See what you handed in</button>
      <button id="redownload" class="ghost" data-i18n="dlcopy">Download the file again</button>
      <button id="resume" class="ghost" data-i18n="backconv">Back to the conversation</button>
    </p>

    <div id="report" class="hide"></div>
  </div>
</section>

<footer class="foot hide" id="foot"><img class="hide" id="footimg" alt=""><span id="foottext"></span></footer>
<p class="ver" title="The version of verbatim that built this page, and a digest of the code that made it">verbatim __VERSION__ · __BUILD__</p>

</div>

<aside class="cal" id="cal" aria-label="Calculator"></aside>

<div class="ai-modal-overlay" id="ai-modal-overlay">
  <div class="ai-modal" role="dialog" aria-labelledby="ai-modal-title" aria-modal="true">
    <button type="button" class="ai-x" id="ai-x" aria-label="Close" title="Close">&times;</button>
    <h2 id="ai-modal-title" data-i18n="aisetup">AI Setup</h2>
    <p class="ai-modal-sub" data-i18n="modalsub">Choose where your AI teacher runs.</p>

    <div class="ai-tabs" role="tablist">
      <button class="ai-tab" role="tab" data-tab="webgpu" aria-selected="false" data-i18n="tabwebgpu">WebGPU</button>
      <button class="ai-tab" role="tab" data-tab="free"  aria-selected="true" data-i18n="tabfree">Free ($0)</button>
      <button class="ai-tab" role="tab" data-tab="paid"  aria-selected="false" data-i18n="tabpaid">Paid</button>
    </div>

    <div id="ai-notes"></div>
    <div id="ai-provider-cards" class="ai-provider-cards"></div>
    <div id="ai-webgpu" class="localpanel hide"></div>

    <div id="ai-key-section" class="ai-key-section" hidden>
      <input type="password" id="ai-key-input" data-i18n-ph="keyph" autocomplete="off" spellcheck="false">
      <div class="ai-key-hint" id="ai-key-hint"></div>
    </div>

    <div id="ai-endpoint-section" class="ai-key-section" hidden>
      <input type="url" id="ai-endpoint-input" data-i18n-ph="endpointph" autocomplete="off" spellcheck="false">
      <div class="ai-key-hint" data-i18n="endpointhint">Connect an OpenAI-compatible model you are running yourself.</div>
    </div>

    <p class="err" id="ai-err"></p>
    <div class="ai-modal-actions">
      <button type="button" class="ghost danger" id="ai-forget" data-i18n="forgetkeys">Forget all keys</button>
      <button type="button" class="ghost" id="ai-test" data-i18n="testconn">Test connection</button>
      <button type="button" id="ai-done" data-i18n="done">Done</button>
    </div>
  </div>
</div>

<div class="ai-modal-overlay" id="tool-overlay" style="z-index:10001">
  <div class="ai-modal" style="width:760px">
    <button type="button" class="ai-x" id="tool-x" aria-label="Close">&times;</button>
    <h2 id="tool-title"></h2>
    <p class="ai-modal-sub" id="tool-sub"></p>
    <textarea id="tool-text" spellcheck="false"
      style="min-height:340px;font-family:var(--mono);font-size:13px;line-height:1.6"></textarea>
    <p class="err" id="tool-err"></p>
    <div class="ai-modal-actions">
      <button type="button" class="ghost danger" id="tool-default"></button>
      <button type="button" class="ghost" id="tool-cancel"></button>
      <button type="button" id="tool-save"></button>
    </div>
  </div>
</div>

<div class="ai-modal-overlay" id="step-overlay" style="z-index:10000">
  <div class="ai-modal" style="width:520px">
    <button type="button" class="ai-x" id="step-x" aria-label="Close">&times;</button>
    <h2 id="step-title"></h2>
    <div id="step-body"></div>
    <div class="ai-modal-actions"><button type="button" id="step-done" data-i18n="done">Done</button></div>
  </div>
</div>

<div class="bar hide" id="bar">
  <div class="mathpal hide" id="mathpal"></div>
  <div class="inner">
    <textarea id="say" rows="1" data-i18n-ph="sayph"></textarea>
    <button id="math" class="ghost mathbtn" title="Maths symbols" aria-expanded="false">&#8721;</button>
    <button id="calcbtn" class="ghost mathbtn" aria-expanded="false"><svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="1.6" width="10" height="12.8" rx="1.6"/><rect x="5.1" y="3.7" width="5.8" height="2.4" rx=".6"/><path d="M5.4 8.6h.01M8 8.6h.01M10.6 8.6h.01M5.4 11.2h.01M8 11.2h.01M10.6 11.2h.01"/></svg></button>
    <button id="send" data-i18n="send">Send</button>
  </div>
</div>

<!-- Temml (MIT), vendored from vendor/temml.min.js. Inlined rather than linked:
     the page must open from file:// with nothing to fetch. -->
<script>__TEMML_JS__</script>
<script>__RICHTEXT_JS__</script>
<script>__CALCULATOR_JS__</script>

<script>
const PROVIDERS = __PROVIDERS_JSON__;
let   PROMPT    = __PROMPT_JSON__;
const SUBMIT    = __SUBMIT_JSON__;
const CHAT_URL  = __CHAT_JSON__;
const AVATAR    = __AVATAR_JSON__;
const SECTION   = __SECTION_JSON__;
let   SURVEY    = __SURVEY_JSON__;
const FOOTER    = __FOOTER_JSON__;
const DEMO      = __DEMO_JSON__;
const SCHEMA    = "tea-taylor-session/2";
/* Recorded in the session as well as shown on the page. A file outlives the
   page that made it, and by the time a transcript raises a question the page is
   usually gone. Additive: nothing in /2 changed shape, so a reader written for
   /2 goes on working and simply has one more thing it may report. */
const APP       = { name: "verbatim", version: "__VERSION__", build: "__BUILD__" };   // /2: a turn may be a tombstone (no text)
/* Saved work is keyed per activity, not per app.
   localStorage is scoped to the origin and ignores the path, so two activities
   served from one site -- which happens the moment you publish more than one --
   shared a single slot under a fixed key. Opening the second showed the first
   one's conversation, finished screen and all. Keying on the prompt's digest
   gives each activity its own slot, and keeps that slot stable across rebuilds
   of the same prompt so a student who reloads still has their work. */
const KEY       = "tea-taylor-session-v1." + PROMPT.sha256.slice(0, 12);
/* Anyone who opened a page built before that change has one slot left under the
   bare key, which nothing reads any more. Sweep it here rather than asking a reader
   to clear site data: site data is the whole origin, so clearing it would take every
   other page published on the same site with it, and most readers will never be asked. */
try{ localStorage.removeItem("tea-taylor-session-v1"); }catch(e){}

const $ = s => document.querySelector(s);
let S = null;   // the session record — this IS the exported file

/* Mixed-script word count. Chinese does not delimit words with spaces, so a
   whitespace split under-reports Chinese turns badly. Each CJK ideograph counts
   as one word; each run of other non-space characters counts as one. Documented
   in Documentation/Protocols/SESSION-SCHEMA.md so the analysis uses the same rule. */
const CJK  = /[一-鿿㐀-䶿豈-﫿]/;
const CJKP = /[　-〿＀-･]/;
function countWords(s){
  if(!s) return 0;
  let n = 0, inRun = false;
  for(const ch of s){
    if(CJK.test(ch)){ n++; inRun = false; }
    else if(/\s/.test(ch) || CJKP.test(ch)){ inRun = false; }
    else if(!inRun){ n++; inRun = true; }
  }
  return n;
}
const meas = t => ({ word_count: countWords(t), char_count: [...(t||"")].length });
/* Twelve figures, trailing zeros gone. A report reading 0.19866666666666669 is
   showing the float rather than the answer. */
const ms0 = n => !isFinite(n) ? String(n)
  : (Number.isInteger(n) && Math.abs(n) < 1e15) ? String(n)
  : parseFloat(n.toPrecision(12)).toString();
const nowUTC = () => new Date().toISOString().replace(/\.\d+Z$/, "Z");
const rndHex = n => [...crypto.getRandomValues(new Uint8Array(n))]
                      .map(b => b.toString(16).padStart(2,"0")).join("");

function save(){ try{ localStorage.setItem(KEY, JSON.stringify(S)); }catch(e){} }
function load(){ try{ return JSON.parse(localStorage.getItem(KEY) || "null"); }catch(e){ return null; } }

function show(id){
  for(const s of ["s-setup","s-chat","s-survey","s-done"]) $("#"+s).classList.add("hide");
  $("#"+id).classList.remove("hide");
  $("#bar").classList.toggle("hide", id !== "s-chat");
}

/* ---------- setup ---------- */
$("#promptview").textContent = PROMPT.text;

/* One class cohort means the section is the same for everyone, so it is fixed at
   build time rather than typed thirty times -- one fewer field, and no chance of
   S4/s4/Section 4 all appearing in the same corpus. It is still recorded. */
if(SECTION){ $("#sec").value = SECTION; $("#secwrap").classList.add("hide"); }

/* Course branding in the masthead and footer, so a student can see at a glance
   that this page is their own instructor's activity and not something stray. */
if(AVATAR){
  for(const id of ["#avatar", "#footimg"]){
    const el = $(id); el.src = AVATAR; el.classList.remove("hide");
  }
}
if(FOOTER){ $("#foottext").textContent = FOOTER; $("#foot").classList.remove("hide"); }


/* ---------- language ----------
   A course may be taught in one language while students write in another, so the
   whole interface switches and the choice persists for the tab. It also sets the
   language the AI teacher is asked to work in; see apiMessages(). */
const I18N = {
  en: {
    title: __TITLE_JSON__, subtitle: __SUBTITLE_JSON__,
    before: "Before you start",
    codehint: "Your instructor will give you a participant code and a group code. Please use those instead of your name — your name should not appear anywhere on this page.",
    pid: "Participant code", group: "Group", section: "Section",
    yourai: "Your AI", setup: "Set up", change: "Change",
    aihint: "Use your own API key, or the one your instructor gives you. It is saved in this browser, alongside your conversation, so you can finish later on the same computer — it is never sent anywhere. On a shared computer, use Forget all keys when you are done. Whichever AI you use is recorded with your session.",
    start: "Start the activity",
    whatai: "What the AI has been told (the same for everyone)",
    finish: "Finish & export", send: "Send",
    finishconfirm: "Finish the activity and export your work?\n\nYou can come back to the conversation afterwards.",
    sayph: "Type your reply…    (Enter to send · Shift+Enter for a new line)",
    aisetup: "AI Setup",
    modalsub: "Choose where your AI teacher runs, then enter a key if it needs one. Nothing you enter here leaves this computer.",
    tabwebgpu: "WebGPU", tabfree: "Free ($0)", tabpaid: "Paid",
    notefree: "Nothing here is available on this network. Two things still work: a model running inside this page (WebGPU), or the key your instructor gives you, used with one of the services under Paid.",
    testconn: "Test connection", done: "Done",
    surveyh: "A few questions before you finish",
    surveyhint: "These are saved in the same file as your conversation. Every question is optional.",
    surveydone: "Finish and download",
    answerq: "Answer the questions",
    surveypending: "You have not answered the questions yet. Your work is saved on this computer — you can come back to this page in the same browser and finish.",
    surveylater: "Your work stays saved on this computer, so you can close this and finish later in the same browser.",
    forgetkeys: "Forget all keys",
    forgetconfirm: "Forget every API key saved in this browser?",
    resetconfirm: "Clear this session and start from an empty page?\n\nThis is a setup tool, not part of the activity.",
    forgotten: "Keys forgotten. Nothing is stored in this browser.",
    forgotnone: "There were no keys stored.",
    dlcopy: "Download the file again", backconv: "Back to the conversation",
    aiteacher: "AI teacher", you: "You",
    rcalced: "you worked out", rcalcgraph: "you graphed", rcalctable: "you tabulated",
    rcalctried: "you tried", rcalcgone: "a calculation you deleted",
    calc: "Calculator", calctab: "Calculate", calcgraph: "Graph", calctable: "Table",
    calcfrom: "from", calcstep: "step", calcreset: "reset", calcclose: "Close the calculator",
    calcdel: "Delete this line", calcgone: "deleted", calcmarks: "numbers",
    calcph: "type expressions here",
    calcworked: "worked out",
    del: "Delete this exchange",
    delask: "Delete this exchange?\n\nYour words and the reply are removed from what you hand in. The file will still record that an exchange was here, and how long it was — so what you submit stays an honest account of the session.\n\nThis cannot be undone.",
    delgone: "Exchange deleted",
    delcount: "deleted",
    notset: "Not set up yet", keyneeded: "key needed", demomode: "Demo mode — no AI needed",
    pidph: "Enter code here (e.g., P07)",
    grpph: "Enter group here (e.g., G3)",
    secph: "Enter section here (e.g., S4)",
    errfields: "Participant code, group and section are all required.",
    errcode: "The participant code should be letters and numbers only, e.g. P07. Please do not use your name.",
    errai: "Please set up your AI first.",
    errsay: "Please say something to your AI teacher first.",
    errreach: "Could not reach the AI: ",
    errsaved: "\nYour conversation is saved. Try Send again, or tell your instructor.",
    saved: "Downloaded", received: "Received",
    recvmsg: "Your instructor has your session. There is nothing else to do.",
    savedmsg: "Your conversation has downloaded as a JSON file. Hand it in the way your instructor asked \u2014 by email, on the LMS, or however else they set up \u2014 for class credit.",
    turns: "turns", turn1: "turn", wordsfrom: "words from you", wordsai: "from the AI",
    seereport: "See what you handed in", hidereport: "Hide what you handed in",
    youranswers: "Your answers", noanswers: "You did not answer the questions.",
    rreplied: "replied in", rtyped: "typed for", word1: "word", wordn: "words",
    cardlocaldesc: "Running on your own machine.",
    cardfound: "model(s) found. Click to use.",
    addserver: "Add a server", addserverdesc: "Type the address of an OpenAI-compatible model you are running.",
    badgelocal: "Local", badgefound: "Found", badgefree: "$0", badgepaid: "Paid",
    badgerec: "Recommended",
    wgpuh: "A model running inside this page",
    wgpudesc: "Runs in this browser. No key, no account.",
    badgewgpu: "In-browser",
    wgpuno: "This browser cannot run a model in the page. WebGPU is needed, and this browser does not offer it. Use one of the other tabs, or open this page in an up-to-date Chrome, Edge or Safari.",
    wgpulib: "Loading the model runner\u2026",
    wgpuliberr: "Could not load the model runner. That download needs a network the first time.",
    wgpuget: "Downloading the model \u2014 this happens once, then it is kept in this browser.",
    wgpuready: "Ready. Nothing you type will leave this computer.",
    wgpupick: "Pick a model above to download it.",
    wgpufirst: "first use downloads it",
    keyph: "Paste your key", keysaved: "Key saved — type a new one to replace it",
    keyhint1: "Your instructor may give you a key to type here. Otherwise get your own at ",
    keyhint2: ". It stays in this browser until you use Forget all keys.",
    endpointhint: "Connect an OpenAI-compatible model you are running yourself. Press Enter to add.",
    endpointph: "http://localhost:11434  (an address, NOT a key)",
    errurl: "That should start with http:// or https://",
    looking: "Looking for models…", nothinganswered: "Nothing answered at ",
    keychecking: "Checking your key\u2026",
    keyok: "That key works. You are ready to start.",
    keyshape: "That does not look like a {p} key \u2014 they normally begin {x}. Saved anyway; check it if the test below fails.",
    errkey: "That API key was not accepted \u2014 check it in AI Setup, or ask your instructor for one.",
    toolpromptt: "What the AI is told",
    toolprompts: "This replaces the prompt every student's AI teacher receives. It applies in this browser only \u2014 to change it for a class, rebuild the page with the new prompt and hand that copy out. Whichever prompt is used is recorded in every student's file.",
    toolsurveyt: "The questions at the end",
    toolsurveys: "A list of questions in JSON. Each needs id, type (single, multi or text), en and zh; the first two types also need options. Applies in this browser only.",
    toolrestore: "Restore the default", toolcancel: "Cancel", toolsave: "Save",
    toolreset: "Default restored. Reloading\u2026",
    toolerrshort: "That looks too short to be the activity prompt.",
    toolerrjson: "That is not valid JSON: ",
    toolerrlist: "Expected a list of questions.",
    toolerrfields: "Every question needs id, type, en and zh.",
    toolerrtype: "Unknown question type: ",
    toolerropts: "This question needs options: ",
  },
  zh: {
    title: __TITLE_ZH_JSON__,
    subtitle: __SUBTITLE_ZH_JSON__,
    before: "开始之前",
    codehint: "老师会给你一个参与者编号和组别编号。请使用这两个编号，不要在本页面填写你的姓名。",
    pid: "参与者编号", group: "组别", section: "班级",
    yourai: "你的 AI", setup: "设置", change: "更改",
    aihint: "可以使用你自己的 API 密钥，或老师提供的密钥。密钥与你的对话一起保存在本浏览器中，方便你稍后在同一台电脑上继续，不会发送到任何地方。如果使用公用电脑，结束后请点击“清除所有密钥”。你使用的 AI 会随会话一起记录。",
    start: "开始活动",
    whatai: "AI 收到的指令（所有人相同）",
    finish: "完成并导出", send: "发送",
    finishconfirm: "完成活动并导出你的作业吗？\n\n之后仍可以返回对话。",
    sayph: "输入你的回复……（Enter 发送 · Shift+Enter 换行）",
    aisetup: "AI 设置",
    modalsub: "选择你的 AI 老师在哪里运行，如需密钥请填写。你在这里填写的内容不会离开这台电脑。",
    tabwebgpu: "WebGPU（本机）", tabfree: "免费 ($0)", tabpaid: "付费",
    notefree: "\u5728\u5f53\u524d\u7f51\u7edc\u4e0b\uff0c\u8fd9\u91cc\u6ca1\u6709\u53ef\u7528\u7684\u670d\u52a1\u3002\u4ecd\u6709\u4e24\u4e2a\u53ef\u884c\u7684\u529e\u6cd5\uff1a\u5728\u672c\u9875\u9762\u5185\u8fd0\u884c\u6a21\u578b\uff08WebGPU\uff09\uff0c\u6216\u4f7f\u7528\u8001\u5e08\u63d0\u4f9b\u7684\u5bc6\u94a5\u8bbf\u95ee\u201c\u4ed8\u8d39\u201d\u4e2d\u7684\u670d\u52a1\u3002",
    testconn: "测试连接", done: "完成",
    surveyh: "结束前的几个问题",
    surveyhint: "这些回答会与你的对话保存在同一个文件中。所有问题均为选填。",
    surveydone: "完成并下载",
    answerq: "回答问题",
    surveypending: "你还没有回答这些问题。你的作业已保存在这台电脑上 —— 可以稍后用同一个浏览器打开本页面继续完成。",
    surveylater: "你的作业会保存在这台电脑上，可以关闭页面，稍后用同一个浏览器继续完成。",
    forgetkeys: "清除所有密钥",
    forgetconfirm: "确定要清除本浏览器中保存的所有 API 密钥吗？",
    resetconfirm: "\u6e05\u9664\u672c\u6b21\u4f1a\u8bdd\u5e76\u4ece\u7a7a\u767d\u9875\u9762\u91cd\u65b0\u5f00\u59cb\uff1f\n\n\u8fd9\u662f\u8bbe\u7f6e\u5de5\u5177\uff0c\u4e0d\u5c5e\u4e8e\u6d3b\u52a8\u5185\u5bb9\u3002",
    forgotten: "密钥已清除。浏览器中不再保存任何密钥。",
    forgotnone: "没有已保存的密钥。",
    dlcopy: "重新下载文件", backconv: "返回对话",
    aiteacher: "AI 老师", you: "你",
    rcalced: "你计算了", rcalcgraph: "你作了图", rcalctable: "你列了表",
    rcalctried: "你尝试了", rcalcgone: "你删除的一次计算",
    calc: "计算器", calctab: "计算", calcgraph: "作图", calctable: "数值表",
    calcfrom: "起点", calcstep: "步长", calcreset: "复位", calcclose: "关闭计算器",
    calcdel: "删除这一行", calcgone: "已删除", calcmarks: "刻度",
    calcph: "在此输入算式",
    calcworked: "算过",
    del: "删除这段对话",
    delask: "要删除这段对话吗？\n\n你的发言和这条回复都会从你提交的文件中移除。文件仍会记录此处曾有一段对话及其长度——这样你提交的内容依然是本次会话的如实记录。\n\n此操作无法撤销。",
    delgone: "已删除的对话",
    delcount: "已删除",
    notset: "尚未设置", keyneeded: "需要密钥", demomode: "演示模式 —— 无需 AI",
    pidph: "在此输入编号（例如 P07）",
    grpph: "在此输入组别（例如 G3）",
    secph: "在此输入班级（例如 S4）",
    errfields: "参与者编号、组别和班级都是必填项。",
    errcode: "参与者编号只能包含字母和数字，例如 P07。请不要使用姓名。",
    errai: "请先设置你的 AI。",
    errsay: "请先对 AI 老师说些什么。",
    errreach: "无法连接 AI：",
    errsaved: "\n你的对话已保存。请重试发送，或告知老师。",
    saved: "已下载", received: "已收到",
    recvmsg: "老师已收到你的会话。无需其他操作。",
    savedmsg: "\u4f60\u7684\u5bf9\u8bdd\u5df2\u4e0b\u8f7d\u4e3a JSON \u6587\u4ef6\u3002\u8bf7\u6309\u8001\u5e08\u8981\u6c42\u7684\u65b9\u5f0f\u63d0\u4ea4 \u2014\u2014 \u90ae\u4ef6\u3001\u6559\u5b66\u5e73\u53f0\u6216\u5176\u4ed6\u65b9\u5f0f \u2014\u2014 \u4f5c\u4e3a\u672c\u6b21\u8bfe\u7684\u6210\u7ee9\u3002",
    turns: "轮对话", turn1: "轮对话", wordsfrom: "个词来自你", wordsai: "来自 AI",
    seereport: "查看你提交的内容", hidereport: "收起提交的内容",
    youranswers: "你的回答", noanswers: "你没有回答这些问题。",
    rreplied: "回复用时", rtyped: "输入用时", word1: "个词", wordn: "个词",
    cardlocaldesc: "在你自己的电脑上运行。",
    cardfound: "个模型可用。点击使用。",
    addserver: "添加服务器", addserverdesc: "输入你正在运行的 OpenAI 兼容模型的地址。",
    badgelocal: "本地", badgefound: "已发现", badgefree: "免费", badgepaid: "付费",
    badgerec: "推荐",
    wgpuh: "在本页面内运行的模型",
    wgpudesc: "在浏览器中运行。无需密钥，无需账号。",
    badgewgpu: "浏览器内",
    wgpuno: "本浏览器无法在页面内运行模型。这需要 WebGPU，而本浏览器不支持。请使用其他选项卡，或用较新版本的 Chrome、Edge 或 Safari 打开本页。",
    wgpulib: "正在加载模型运行器…",
    wgpuliberr: "无法加载模型运行器。首次使用需要联网下载。",
    wgpuget: "正在下载模型 —— 只需一次，之后会保存在本浏览器中。",
    wgpuready: "已就绪。你输入的内容不会离开这台电脑。",
    wgpupick: "在上方选一个模型开始下载。",
    wgpufirst: "首次使用需下载",
    keyph: "粘贴你的密钥", keysaved: "密钥已保存 —— 输入新密钥可替换",
    keyhint1: "老师可能会给你一个密钥填在这里。也可以到这里自行获取：",
    keyhint2: "。密钥会保存在本浏览器中，直到你点击“清除所有密钥”。",
    endpointhint: "连接你自己运行的 OpenAI 兼容模型。按 Enter 添加。",
    endpointph: "http://localhost:11434 （地址，不是密钥）",
    errurl: "地址应以 http:// 或 https:// 开头",
    looking: "正在查找模型……", nothinganswered: "该地址无响应：",
    keychecking: "\u6b63\u5728\u68c0\u67e5\u4f60\u7684\u5bc6\u94a5\u2026\u2026",
    keyok: "\u5bc6\u94a5\u53ef\u7528\uff0c\u53ef\u4ee5\u5f00\u59cb\u4e86\u3002",
    keyshape: "\u8fd9\u770b\u8d77\u6765\u4e0d\u50cf {p} \u7684\u5bc6\u94a5 \u2014\u2014 \u5b83\u4eec\u901a\u5e38\u4ee5 {x} \u5f00\u5934\u3002\u5df2\u4fdd\u5b58\uff1b\u82e5\u6d4b\u8bd5\u5931\u8d25\u8bf7\u68c0\u67e5\u3002",
    errkey: "\u8be5 API \u5bc6\u94a5\u672a\u88ab\u63a5\u53d7 \u2014\u2014 \u8bf7\u5728 AI \u8bbe\u7f6e\u4e2d\u68c0\u67e5\uff0c\u6216\u5411\u8001\u5e08\u7d22\u53d6\u3002",
    toolpromptt: "\u7ed9 AI \u7684\u6307\u4ee4",
    toolprompts: "\u8fd9\u5c06\u66ff\u6362\u6bcf\u4f4d\u5b66\u751f\u7684 AI \u8001\u5e08\u6536\u5230\u7684\u6307\u4ee4\u3002\u4ec5\u5bf9\u672c\u6d4f\u89c8\u5668\u751f\u6548 \u2014\u2014 \u82e5\u8981\u5bf9\u5168\u73ed\u751f\u6548\uff0c\u8bf7\u7528\u65b0\u6307\u4ee4\u91cd\u65b0\u751f\u6210\u9875\u9762\u5e76\u5206\u53d1\u3002\u5b9e\u9645\u4f7f\u7528\u7684\u6307\u4ee4\u4f1a\u8bb0\u5f55\u5728\u6bcf\u4efd\u4f5c\u4e1a\u6587\u4ef6\u4e2d\u3002",
    toolsurveyt: "\u7ed3\u675f\u65f6\u7684\u95ee\u9898",
    toolsurveys: "JSON \u683c\u5f0f\u7684\u95ee\u9898\u5217\u8868\u3002\u6bcf\u9898\u9700\u8981 id\u3001type\uff08single\u3001multi \u6216 text\uff09\u3001en \u548c zh\uff1b\u524d\u4e24\u79cd\u7c7b\u578b\u8fd8\u9700\u8981 options\u3002\u4ec5\u5bf9\u672c\u6d4f\u89c8\u5668\u751f\u6548\u3002",
    toolrestore: "\u6062\u590d\u9ed8\u8ba4", toolcancel: "\u53d6\u6d88", toolsave: "\u4fdd\u5b58",
    toolreset: "\u5df2\u6062\u590d\u9ed8\u8ba4\u3002\u6b63\u5728\u91cd\u65b0\u52a0\u8f7d\u2026\u2026",
    toolerrshort: "\u8fd9\u6bb5\u5185\u5bb9\u592a\u77ed\uff0c\u4e0d\u50cf\u662f\u6d3b\u52a8\u6307\u4ee4\u3002",
    toolerrjson: "JSON \u683c\u5f0f\u9519\u8bef\uff1a",
    toolerrlist: "\u9700\u8981\u4e00\u4e2a\u95ee\u9898\u5217\u8868\u3002",
    toolerrfields: "\u6bcf\u9053\u95ee\u9898\u90fd\u9700\u8981 id\u3001type\u3001en \u548c zh\u3002",
    toolerrtype: "\u672a\u77e5\u7684\u95ee\u9898\u7c7b\u578b\uff1a",
    toolerropts: "\u8be5\u95ee\u9898\u9700\u8981 options\uff1a",
  }
};
let lang = (() => { try{ return localStorage.getItem("tea.lang") || __LANG_JSON__; }catch(e){ return __LANG_JSON__; } })();
const tr = k => (I18N[lang] && I18N[lang][k]) || I18N.en[k] || k;
function applyLang(){
  document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
  for(const el of document.querySelectorAll("[data-i18n]"))    el.textContent = tr(el.dataset.i18n);
  for(const el of document.querySelectorAll("[data-i18n-ph]")) el.placeholder = tr(el.dataset.i18nPh);
  document.title = tr("title");
  $("#lang").textContent = lang === "zh" ? "EN" : "中文";
  if(S) render();
  // The done screen is written once when it is reached, so switching language
  // while standing on it would otherwise leave the last thing a student reads in
  // the language they just switched away from.
  if(S && !$("#s-done").classList.contains("hide")) fillDone();
  // The report's button says what it will do next, so its label depends on state
  // rather than on a single key -- the loop above cannot know which one is right.
  if($("#report")) $("#see-report").textContent =
    tr($("#report").classList.contains("hide") ? "seereport" : "hidereport");
  // Same for the survey, whose questions come from survey.json and so are built
  // rather than translated in place. Answers already given are carried across --
  // re-rendering must not cost a student what they have filled in.
  if(!$("#s-survey").classList.contains("hide")) renderSurvey(collectSurvey());
  if(!$("#mathpal").classList.contains("hide")) renderMath();
  refreshAiStatus();
  if($("#ai-modal-overlay").classList.contains("open")){
    renderCards();
    const c = aiConfig();
    if(c && !c.local){ const pp = PROVIDERS.find(x => x.id === c.id); if(pp) showKeyEntry(pp); }
  }
}
$("#lang").onclick = () => {
  lang = lang === "zh" ? "en" : "zh";
  try{ localStorage.setItem("tea.lang", lang); }catch(e){}
  applyLang();
  /* The calculator builds its own markup once, so applyLang cannot reach it. */
  Calculator.relabel();
};

/* ---------- the calculator ----------
   Opened from the bar, beside the symbol palette, because it is wanted while a
   reply is being written and read. What it works out is recorded: see the note
   in calculator.js for why it goes beside the turns rather than among them. */
Calculator.mount({
  host: $("#cal"),
  tr,
  onUse(use){
    if(!S || !S.turns) return;
    if(!S.tool_uses) S.tool_uses = [];
    /* Where in the conversation it happened, so a transcript can put it back in
       the right place. A number worked out before the AI suggested it is a
       different thing from one worked out after. */
    S.tool_uses.push(Object.assign({ after_turn: S.turns.length - 1, ts: nowUTC() }, use));
    save();
  },
  /* Deleting a line leaves a tombstone, exactly as deleting an exchange does.
     The student's expression goes; that they reached for the calculator at that
     point in the conversation stays, so the file does not quietly become an
     account of only the work that was kept. */
  onDrop(id){
    if(!S || !Array.isArray(S.tool_uses)) return;
    const u = S.tool_uses.find(x => x.id === id);
    if(!u || u.deleted_utc) return;
    S.tool_uses[S.tool_uses.indexOf(u)] = {
      id: u.id, kind: u.kind, after_turn: u.after_turn, ts: u.ts,
      deg: u.deg, deleted_utc: nowUTC(),
    };
    save();
  },
});
Calculator.onclose = () => $("#calcbtn").setAttribute("aria-expanded", "false");
$("#calcbtn").title = tr("calc");
$("#calcbtn").onclick = () => {
  Calculator.toggle();
  $("#calcbtn").setAttribute("aria-expanded", String(Calculator.isOpen()));
};
addEventListener("resize", () => Calculator.redraw());

/* ---------- light or dark ----------
   A preference about reading, not about the activity: stored in this browser
   beside the language, and deliberately never written into the session file.
   What a student found comfortable to look at is not data about what they did.

   The glyph shows what pressing it gives you, not what you are looking at. */
function applyTheme(t){
  document.documentElement.dataset.theme = t;
  $("#theme-icon").textContent = t === "dark" ? "☀" : "☾";
}
applyTheme(document.documentElement.dataset.theme === "dark" ? "dark" : "light");
$("#theme").onclick = () => {
  const t = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  try{ localStorage.setItem("tea.theme", t); }catch(e){}
  applyTheme(t);
};

/* ---------- AI setup ----------
   The key belongs to the student -- their own, or one the instructor reads out on
   the day. It is kept on the student's own machine alongside their conversation,
   so a session cut short by the end of class can be finished later in the same
   browser -- losing the key would mean losing the work. "Forget all keys" removes
   it deliberately. Nothing is baked into this file. */
/* Persisted on the student's own machine, alongside the conversation, so a
   session interrupted by the end of class can be finished later in the same
   browser. "Forget all keys" is the deliberate way to remove it. */
const SS = {
  get(k){ try{ return localStorage.getItem(k); }catch(e){ return null; } },
  set(k,v){ try{ localStorage.setItem(k,v); }catch(e){} },
  del(k){ try{ localStorage.removeItem(k); }catch(e){} }
};
const K_PROV = "tea.ai.provider", K_ENDS = "tea.ai.endpoints";
const K_KEY  = id => "tea.ai.key." + id;

/* Which services this network can reach.
   Tested, not asked. Asking would make the student report on their own connection
   and would still be wrong for anyone whose network is not what they think it is;
   trying it is both more accurate and a fact about the endpoint rather than about
   the person. `reach[id]` is "yes", "no", or "trying" once a check has run.

   Deliberately NOT persisted: a session can be finished later at home, on a
   different network, and a stale answer would be worse than none. */
let reach = {}, reachedAt = null;
const reachRan = () => !!reachedAt;

let aiTab = (PROVIDERS.find(p => p.recommended) || PROVIDERS[0] || {}).tier || "paid";
let showAddEndpoint = false, localModels = {};

const endpoints    = () => { try{ return JSON.parse(SS.get(K_ENDS) || "[]"); }catch(e){ return []; } };
const setEndpoints = a  => SS.set(K_ENDS, JSON.stringify(a));

function aiConfig(){
  const id = SS.get(K_PROV);
  if(!id) return null;
  if(id.startsWith("webgpu:")){
    const model = id.slice(7);
    /* `local:true` is what makes this count as live without a key. The full MLC
       id stays in `model` because that is what the session file records; `short`
       exists only so the gear does not read like a filename. */
    return { id, api:"webgpu", url:"", model, short: webgpuShort(model),
             label:"WebGPU", key:"", local:true, webgpu:true };
  }
  if(id.startsWith("local:")){
    const [url, model] = id.slice(6).split("|");
    return { id, api:"openai", url: url.replace(/\/+$/,"") + "/v1/chat/completions",
             model: model || "local", key:"", label:"Local model", local:true };
  }
  const p = PROVIDERS.find(x => x.id === id);
  if(!p) return null;
  return { id, api:p.api, url:p.url, model:p.model, label:p.label, key: SS.get(K_KEY(id)) || "" };
}
const aiLive  = () => { const c = aiConfig(); return !!c && (c.local || !!c.key); };
const aiReady = () => DEMO || aiLive();
const demoActive = () => DEMO && !aiLive();

function refreshAiStatus(){
  const c = aiConfig(), el = $("#ai-status");
  // The gear says which provider is in use once one is working, without growing:
  // "AI Setup" is simply replaced by the provider's name.
  const live = aiLive();
  $("#gear-txt").textContent = live ? (c.local ? (c.short || c.model) : c.label) : tr("aisetup");
  $("#gear").classList.toggle("ready", live);
  $("#ai-open").textContent = live ? tr("change") : tr("setup");
  $("#demobar").classList.toggle("hide", !demoActive());
  if(live){
    /* A selected model counts as set up before its weights have finished
       arriving, which is what lets a returning student pick up where they left
       off. Saying only "ready" during that first download would be a lie the
       student discovers by pressing Send and waiting, so the percentage is
       carried out here, where it is visible with the dialog closed. */
    $("#ai-status-txt").textContent = c.label + " · " + (c.short || c.model)
      + (c.webgpu && wgpuPhase === "getting" ? "  " + Math.round(wgpuPct * 100) + "%" : "");
    el.classList.add("ready"); return;
  }
  if(demoActive()){ $("#ai-status-txt").textContent = tr("demomode"); el.classList.add("ready"); return; }
  $("#ai-status-txt").textContent = c ? (c.label + " — " + tr("keyneeded")) : tr("notset");
  el.classList.remove("ready");
}

/* ---- probing a locally running model ---- */
async function probe(url){
  const base = url.replace(/\/+$/,"");
  try{
    const r = await fetch(base + "/v1/models", { signal: AbortSignal.timeout(2500) });
    if(!r.ok) return null;
    const d = await r.json();
    const ids = (d.data || d.models || []).map(m => m.id || m.name).filter(Boolean);
    return ids.length ? ids : null;
  }catch(e){ return null; }
}
async function probeWellKnown(){
  const have = new Set(endpoints());
  for(const {port, hint} of LOCAL_PORTS){
    const url = "http://localhost:" + port;
    if(have.has(url)) continue;
    const models = await probe(url);
    if(models){ localModels[url] = { models, hint }; }
  }
  renderCards();
}

/* ---- cards ---- */
function card(opts){
  const b = document.createElement("button");
  b.type = "button";
  b.className = "ai-provider-card" + (opts.selected ? " selected" : "") + (opts.extra || "");
  const t = document.createElement("div"); t.className = "ai-card-title"; t.textContent = opts.title;
  b.appendChild(t);
  if(opts.model){ const m = document.createElement("div"); m.className = "ai-card-model"; m.textContent = opts.model; b.appendChild(m); }
  if(opts.desc){ const d = document.createElement("div"); d.className = "ai-card-desc"; d.textContent = opts.desc; b.appendChild(d); }
  if(opts.badge){ const g = document.createElement("div"); g.className = "ai-card-badge ai-badge-" + opts.badgeClass; g.textContent = opts.badge; b.appendChild(g); }
  if(opts.badge2){ const g = document.createElement("div"); g.className = "ai-card-badge ai-badge-rec"; g.textContent = opts.badge2; b.appendChild(g); }
  b.onclick = opts.onClick;
  $("#ai-provider-cards").appendChild(b);
}

/* A model that runs inside this page, on the student's own graphics hardware.

   This replaces the four-step Ollama setup that stood here. That flow asked a
   student to install a server, pull a model, set an environment variable and
   type an address -- four chances to give up before the activity starts, and in
   practice a path only an instructor ever walked. WebGPU asks for one click and
   a wait.

   What it costs instead: the weights come from a CDN the first time, so the very
   first run needs a network and a machine with enough graphics memory, and a 1-3B
   model is a weaker mathematician than anything under Paid. Both are recorded --
   the session file stores this model's full id like any other -- so a transcript
   is never ambiguous about what produced it.

   The library is fetched only when this tab is opened. A student who never opens
   it downloads nothing, and the page still runs from file:// with no network. */
const WEBGPU_LIB = "https://cdn.jsdelivr.net/npm/@mlc-ai/web-llm@0.2.84/+esm";

/* Ids are checked against the library's own catalogue at load rather than
   trusted. A hardcoded id that the upstream project retires would otherwise
   break every student at once, mid-class -- which is exactly what a retired
   Groq model already did to this page once. Anything no longer listed is
   dropped quietly and the rest still work. */
const WEBGPU_PICKS = [
  ["Qwen2.5-1.5B-Instruct-q4f16_1-MLC",  true ],
  ["Llama-3.2-1B-Instruct-q4f16_1-MLC",  false],
  ["Llama-3.2-3B-Instruct-q4f16_1-MLC",  false],
  ["Qwen2.5-3B-Instruct-q4f16_1-MLC",    false]
];
/* `navigator.gpu` existing is not the same as WebGPU working. A browser can
   expose the object and still hand back no adapter -- no usable card, a driver
   on the blocklist, a remote session. Asking for the adapter is the only check
   that distinguishes them, and it is the difference between a student being
   told plainly to use another tab and a student picking a model, waiting, and
   getting an opaque failure. Null means not yet asked. */
let wgpuAdapter = null;
async function webgpuProbe(){
  if(wgpuAdapter !== null) return wgpuAdapter;
  if(!(typeof navigator !== "undefined" && navigator.gpu)){ wgpuAdapter = false; return false; }
  try{ wgpuAdapter = !!(await navigator.gpu.requestAdapter()); }
  catch(e){ wgpuAdapter = false; }
  return wgpuAdapter;
}
const webgpuOK = () => wgpuAdapter !== false;
const webgpuShort = id => id.replace(/-q4f\d+(_\d+)?-MLC$/, "").replace(/-Instruct$/, "");

let wgpuLib = null, wgpuList = null, wgpuEngine = null, wgpuEngineId = null;
let wgpuPhase = "idle";     // idle | lib | liberr | listed | getting | ready | error
let wgpuNote = "", wgpuPct = 0;

/* Load the runner, then keep only the picks it still ships. */
async function webgpuLoad(){
  if(wgpuList) return wgpuList;
  wgpuPhase = "lib"; wgpuNote = ""; renderWebgpuPanel();
  if(!(await webgpuProbe())){ renderWebgpuPanel(); renderCards(); return null; }
  try{
    wgpuLib = await import(WEBGPU_LIB);
  }catch(e){
    wgpuPhase = "liberr"; renderWebgpuPanel(); return null;
  }
  const have = new Map();
  for(const m of (wgpuLib.prebuiltAppConfig || {}).model_list || []) have.set(m.model_id, m);
  wgpuList = WEBGPU_PICKS
    .filter(([id]) => have.has(id))
    .map(([id, rec]) => ({ id, rec, gb: (have.get(id).vram_required_MB || 0) / 1024 }));
  wgpuPhase = "listed"; renderWebgpuPanel(); renderCards();
  return wgpuList;
}

/* Build the engine for one model, reporting progress into the panel. Switching
   model throws the old engine away rather than holding two sets of weights. */
async function webgpuEngineFor(id){
  if(wgpuEngine && wgpuEngineId === id) return wgpuEngine;
  await webgpuLoad();
  if(!wgpuLib) throw new Error(tr("wgpuliberr"));
  if(wgpuEngine){ try{ await wgpuEngine.unload(); }catch(e){} wgpuEngine = null; wgpuEngineId = null; }
  wgpuPhase = "getting"; wgpuPct = 0; wgpuNote = ""; renderWebgpuPanel();
  try{
    wgpuEngine = await wgpuLib.CreateMLCEngine(id, { initProgressCallback: r => {
      wgpuPct = Math.max(0, Math.min(1, r.progress || 0));
      wgpuNote = r.text || "";
      renderWebgpuPanel(); refreshAiStatus();
    }});
  }catch(e){
    wgpuPhase = "error"; wgpuNote = (e && e.message) || String(e); renderWebgpuPanel();
    throw e;
  }
  wgpuEngineId = id; wgpuPhase = "ready"; wgpuPct = 1; wgpuNote = "";
  renderWebgpuPanel(); refreshAiStatus();
  return wgpuEngine;
}

/* Three things a student needs to know before waiting on a download, in the same
   numbered cards the Ollama steps used. */
const WEBGPU_STEPS = [
  { en: ["What this is", "The model runs on your own graphics hardware, inside this page. There is no key, no account, and nothing you type is sent anywhere."],
    zh: ["这是什么", "模型在你自己的显卡上运行，就在本页面内。无需密钥，无需账号，你输入的内容不会发送到任何地方。"] },
  { en: ["What it needs", "A browser with WebGPU — an up-to-date Chrome, Edge or Safari — and enough graphics memory for the model you pick. The sizes are on the cards above."],
    zh: ["需要什么", "支持 WebGPU 的浏览器 —— 较新版本的 Chrome、Edge 或 Safari —— 以及足够的显存。上方每张卡片都标有大小。"] },
  { en: ["The first run downloads it", "The model is fetched once and then kept in this browser, so later sessions start straight away. That first download is large and needs a network."],
    zh: ["首次运行需下载", "模型只下载一次，之后保存在本浏览器中，以后可直接开始。首次下载较大，需要联网。"],
    note: { en: "The weights come from the HuggingFace CDN, which may not load from mainland China. If it does not, use the key your instructor gives you under Paid instead.",
            zh: "模型权重来自 HuggingFace CDN，在中国大陆可能无法访问。若无法下载，请改用老师提供的密钥（“付费”选项卡）。" } }
];

function renderWebgpuPanel(){
  const el = $("#ai-webgpu");
  el.classList.toggle("hide", aiTab !== "webgpu");
  if(aiTab !== "webgpu") return;
  /* Progress arrives many times a second for the length of a multi-gigabyte
     download. Rebuilding the panel on each one would make the three steps
     flicker the whole time, so a repeat of the same phase only moves the bar. */
  if(el.dataset.phase === wgpuPhase && wgpuPhase === "getting"){
    const st = el.querySelector(".wgpu-state"), fill = el.querySelector(".wgpu-bar i");
    if(st)   st.textContent = tr("wgpuget") + (wgpuNote ? "  " + wgpuNote : "");
    if(fill) fill.style.width = (wgpuPct * 100).toFixed(1) + "%";
    return;
  }
  el.dataset.phase = wgpuPhase;
  el.textContent = "";
  const h = document.createElement("h3"); h.textContent = tr("wgpuh"); el.appendChild(h);

  // A browser without WebGPU is told so plainly, and sent somewhere that works,
  // rather than being shown steps it cannot follow.
  if(wgpuAdapter === false){
    const d = document.createElement("div"); d.className = "wgpu-state bad";
    d.textContent = tr("wgpuno"); el.appendChild(d);
    return;
  }

  const grid = document.createElement("div"); grid.className = "steps"; el.appendChild(grid);
  WEBGPU_STEPS.forEach((st, i) => {
    const [title] = lang === "zh" ? st.zh : st.en;
    const c = document.createElement("button");
    c.type = "button"; c.className = "step";
    const nn = document.createElement("span"); nn.className = "sn"; nn.textContent = i + 1;
    const t = document.createElement("span"); t.className = "st"; t.textContent = title;
    const more = document.createElement("span"); more.className = "smore"; more.textContent = "›";
    c.append(nn, t, more);
    c.onclick = () => openStep(i);
    grid.appendChild(c);
  });

  const msg = { lib: "wgpulib", liberr: "wgpuliberr", getting: "wgpuget",
                ready: "wgpuready", listed: "wgpupick", idle: "wgpupick" }[wgpuPhase];
  const d = document.createElement("div");
  d.className = "wgpu-state" + (wgpuPhase === "liberr" || wgpuPhase === "error" ? " bad" : "");
  d.textContent = wgpuPhase === "error" ? wgpuNote
                : (tr(msg) + (wgpuPhase === "getting" && wgpuNote ? "  " + wgpuNote : ""));
  el.appendChild(d);

  if(wgpuPhase === "getting"){
    const bar = document.createElement("div"); bar.className = "wgpu-bar";
    const fill = document.createElement("i"); fill.style.width = (wgpuPct * 100).toFixed(1) + "%";
    bar.appendChild(fill); el.appendChild(bar);
  }
}
function openStep(i){
  const st = WEBGPU_STEPS[i];
  const [title, body] = lang === "zh" ? st.zh : st.en;
  $("#step-title").textContent = (i + 1) + ". " + title;
  const el = $("#step-body"); el.textContent = "";
  const b = document.createElement("p"); b.className = "ai-modal-sub"; b.textContent = body;
  el.appendChild(b);
  if(st.code){
    const pre = document.createElement("code"); pre.className = "sc"; pre.textContent = st.code;
    el.appendChild(pre);
  }
  const links = (lang === "zh" ? st.links_zh : st.links_en) || st.links;
  if(links){
    const ln = document.createElement("div"); ln.className = "sl";
    links.forEach(([nm, url], j) => {
      if(j) ln.append(document.createTextNode(" \u00b7 "));
      const a = document.createElement("a");
      a.href = url; a.target = "_blank"; a.rel = "noopener"; a.textContent = nm;
      ln.appendChild(a);
    });
    el.appendChild(ln);
  }
  if(st.note){
    const nt = document.createElement("div"); nt.className = "snote";
    nt.textContent = lang === "zh" ? st.note.zh : st.note.en;
    el.appendChild(nt);
  }
  $("#step-overlay").classList.add("open");
}

/* Notes that depend on where the student is connecting from, or on how the page
   was opened. Both are things a student would otherwise discover by spending
   class time on a service that cannot answer them. */
function renderNotes(){
  const el = $("#ai-notes"); el.textContent = "";
  const add = k => { const d = document.createElement("div"); d.className = "tabnote";
                     d.textContent = tr(k); el.appendChild(d); };
  // A tab emptied by the probe would otherwise just be blank. One line saying
  // where to go instead, in the same muted voice as every other hint here.
  if(aiTab !== "webgpu" && !offer(aiTab).length) add("notefree");
}

/* Does this endpoint answer at all?

   `mode:"no-cors"` on purpose. We are asking about connectivity, not about the
   reply: an opaque response cannot be read, but the promise still settles, and
   that is the whole signal. It resolves whenever the server answered — 401 for
   the missing key included — and rejects when the connection failed. Reading the
   status would mean a normal CORS request, and an error response without the
   right headers would then look identical to an unreachable host.

   The body is empty, so nothing about the student goes anywhere. */
async function answers(url){
  try{
    await fetch(url, { method: "POST", mode: "no-cors",
                       headers: { "Content-Type": "text/plain" }, body: "",
                       signal: AbortSignal.timeout(8000) });
    return true;
  }catch(e){ return false; }
}
/* Runs once at load, silently. The student never asks for this and never sees it
   happen -- by the time they open AI Setup the list is simply the services that
   work here. A student is choosing an AI teacher, not diagnosing a network. */
async function probeProviders(){
  if(DEMO) return;                       // no network in a demo build
  await Promise.all(PROVIDERS.map(async p => {
    reach[p.id] = (await answers(p.url)) ? "yes" : "no";
    if($("#ai-modal-overlay").classList.contains("open")) renderCards();
  }));
  reachedAt = nowUTC();
  if($("#ai-modal-overlay").classList.contains("open")) renderCards();
  if(S){ S.network_check = networkCheck(); save(); }
}

/* Which providers to list in a tier.

   Two ways the probe is ignored, both protecting the rule that every student must
   have a viable path:

   - nothing answered anywhere. The probe itself is unreliable then -- no network
     yet, opened from a file, a browser that refuses no-cors -- and a dialog with
     no options at all is far worse than one listing something that may not work.
   - a provider not yet resolved. Absence of an answer is not an answer.

   A tier that genuinely has nothing left is allowed to be empty; renderNotes()
   says where to go instead. */
const anyAnswered = () => PROVIDERS.some(p => reach[p.id] === "yes");
function offer(tier){
  const here = PROVIDERS.filter(p => p.tier === tier);
  if(!anyAnswered()) return here;
  return here.filter(p => reach[p.id] !== "no");
}

/* Recorded as what it is: which endpoints answered, and when. No claim about
   where the student is or how they got there. Null until the probe has finished. */
function networkCheck(){
  if(!reachRan()) return null;
  return { checked_utc: reachedAt,
           answered:    PROVIDERS.filter(p => reach[p.id] === "yes").map(p => p.id),
           no_response: PROVIDERS.filter(p => reach[p.id] === "no").map(p => p.id) };
}

function renderCards(){
  const wrap = $("#ai-provider-cards"); wrap.innerHTML = "";
  renderNotes(); renderWebgpuPanel();
  $("#ai-err").textContent = "";
  const current = SS.get(K_PROV);

  if(aiTab === "webgpu"){
    for(const m of (webgpuOK() ? (wgpuList || []) : [])){
      const id = "webgpu:" + m.id;
      card({ title: webgpuShort(m.id),
             model: m.gb.toFixed(1) + " GB · " + tr("wgpufirst"),
             desc: tr("wgpudesc"), badge: tr("badgewgpu"), badgeClass: "local",
             badge2: m.rec ? tr("badgerec") : null, selected: current === id,
             /* Choosing the model is what starts the download. The failure is
                already drawn in the panel, so nothing is rethrown at the page. */
             onClick: () => { SS.set(K_PROV, id); showAddEndpoint = false;
                              $("#ai-key-section").hidden = true; $("#ai-endpoint-section").hidden = true;
                              renderCards(); refreshAiStatus();
                              webgpuEngineFor(m.id).catch(() => {}); } });
    }
    for(const url of endpoints()){
      for(const m of ((localModels[url] || {}).models || ["local"])){
        const id = "local:" + url + "|" + m;
        card({ title: m, model: url, desc: tr("cardlocaldesc"),
               badge: tr("badgelocal"), badgeClass: "local", selected: current === id,
               onClick: () => { SS.set(K_PROV, id); showAddEndpoint = false;
                                $("#ai-key-section").hidden = true; $("#ai-endpoint-section").hidden = true;
                                renderCards(); refreshAiStatus(); } });
      }
    }
    for(const [url, info] of Object.entries(localModels)){
      if(endpoints().includes(url)) continue;
      card({ title: info.hint, model: url,
             desc: info.models.length + " " + tr("cardfound"),
             badge: tr("badgefound"), badgeClass: "local",
             onClick: () => { setEndpoints([...endpoints(), url]); renderCards(); } });
    }
    card({ title: tr("addserver"), desc: tr("addserverdesc"),
           extra: " add-server",
           onClick: () => { showAddEndpoint = true; $("#ai-key-section").hidden = true;
                            $("#ai-endpoint-section").hidden = false;
                            setTimeout(() => $("#ai-endpoint-input").focus(), 0); } });
    return;
  }

  for(const p of offer(aiTab)){
    card({ title: p.label, model: p.model, desc: (lang === "zh" && p.blurb_zh) ? p.blurb_zh : p.blurb,
           badge: p.tier === "free" ? tr("badgefree") : tr("badgepaid"), badgeClass: p.tier,
           badge2: p.recommended ? tr("badgerec") : null,
           selected: current === p.id,
           onClick: () => { SS.set(K_PROV, p.id); showAddEndpoint = false;
                            $("#ai-endpoint-section").hidden = true;
                            showKeyEntry(p); renderCards(); refreshAiStatus(); } });
  }
}

function showKeyEntry(p){
  const has = !!SS.get(K_KEY(p.id));
  const inp = $("#ai-key-input");
  inp.value = ""; inp.placeholder = has ? tr("keysaved") : (tr("keyph") + "  " + (p.placeholder || ""));
  $("#ai-key-hint").textContent = "";
  $("#ai-key-hint").append(tr("keyhint1"));
  const a = document.createElement("a");
  a.href = p.key_url; a.target = "_blank"; a.rel = "noopener";
  a.textContent = p.key_url.replace(/^https?:\/\//, "");
  $("#ai-key-hint").append(a, tr("keyhint2"));
  $("#ai-key-section").hidden = false;
  setTimeout(() => inp.focus(), 0);
}
/* A key is checked twice on the way in: its shape, immediately, which catches a
   half-paste or the wrong service's key without any network at all; then a real
   call, which is the only thing that actually proves it works. Both report into
   the dialog. Neither refuses to save -- key formats change, and a student who
   knows better than this page should not be locked out. */
function keyShapeWarning(p, v){
  if(!p || !p.prefix) return "";
  if(v.startsWith(p.prefix)) return "";
  return tr("keyshape").replace("{p}", p.label).replace("{x}", p.prefix);
}
async function commitKey(opts){
  const id = SS.get(K_PROV), v = $("#ai-key-input").value.trim();
  if(!id || !v) return;
  SS.set(K_KEY(id), v); $("#ai-key-input").value = "";
  $("#ai-key-input").placeholder = tr("keysaved");
  refreshAiStatus();
  const p = PROVIDERS.find(x => x.id === id);
  const warn = keyShapeWarning(p, v);
  $("#ai-err").textContent = warn;
  if(opts && opts.quiet) return;          // closing the dialog: do not start a call
  await testKey(warn);
}
/* One real request, and the answer said plainly. The shape warning stays on
   screen alongside the result -- it is usually the explanation for it. */
async function testKey(warn){
  const c = aiConfig();
  if(!c || (!c.key && !c.local)) return;
  // Testing a model that has not been fetched yet would start the download as a
  // side effect of a button labelled "Test connection". Say what is missing.
  if(c.webgpu && wgpuPhase !== "ready"){ $("#ai-err").textContent = tr("wgpupick"); return; }
  const pre = warn ? warn + "  " : "";
  $("#ai-err").textContent = pre + tr("keychecking");
  try{
    await askModel([{ role: "user", content: "Reply with the single word: ok" }]);
    $("#ai-err").textContent = pre + tr("keyok");
  }catch(err){
    $("#ai-err").textContent = pre + err.message;
  }
}

/* ---- wiring ---- */
$("#gear").onclick = $("#ai-open").onclick = () => {
  $("#ai-modal-overlay").classList.add("open");
  const c = aiConfig();
  if(c && c.webgpu) aiTab = "webgpu";
  else if(c && !c.local){ const p = PROVIDERS.find(x => x.id === c.id); if(p){ aiTab = p.tier; showKeyEntry(p); } }
  for(const t of document.querySelectorAll(".ai-tab")) t.setAttribute("aria-selected", String(t.dataset.tab === aiTab));
  renderCards();
  if(aiTab === "webgpu"){ probeWellKnown(); webgpuLoad(); }
};
const closeAi = () => { commitKey({quiet:true}); $("#ai-modal-overlay").classList.remove("open"); refreshAiStatus(); };
$("#ai-done").onclick = closeAi;
$("#ai-x").onclick = closeAi;
const closeStep = () => $("#step-overlay").classList.remove("open");
$("#step-x").onclick = closeStep;
$("#step-done").onclick = closeStep;
$("#step-overlay").onclick = e => { if(e.target === $("#step-overlay")) closeStep(); };
document.addEventListener("keydown", e => {
  if(e.key !== "Escape") return;
  if($("#step-overlay").classList.contains("open")) return closeStep();
  if($("#ai-modal-overlay").classList.contains("open")) closeAi();
});
$("#ai-modal-overlay").onclick = e => { if(e.target === $("#ai-modal-overlay")) closeAi(); };
for(const t of document.querySelectorAll(".ai-tab")){
  t.onclick = () => {
    aiTab = t.dataset.tab;
    for(const o of document.querySelectorAll(".ai-tab")) o.setAttribute("aria-selected", String(o === t));
    $("#ai-key-section").hidden = true; $("#ai-endpoint-section").hidden = true;
    renderCards();
    if(aiTab === "webgpu"){ probeWellKnown(); webgpuLoad(); }
  };
}
$("#ai-key-input").addEventListener("keydown", e => { if(e.key === "Enter"){ e.preventDefault(); commitKey(); } });
$("#ai-key-input").addEventListener("blur", () => commitKey());
$("#ai-endpoint-input").addEventListener("keydown", async e => {
  if(e.key !== "Enter") return;
  e.preventDefault();
  const url = e.target.value.trim().replace(/\/+$/,"");
  if(!/^https?:\/\//.test(url)){ $("#ai-err").textContent = tr("errurl"); return; }
  $("#ai-err").textContent = tr("looking");
  const models = await probe(url);
  if(!models){ $("#ai-err").textContent = tr("nothinganswered") + url; return; }
  localModels[url] = { models, hint: "Your server" };
  setEndpoints([...new Set([...endpoints(), url])]);
  e.target.value = ""; $("#ai-endpoint-section").hidden = true; $("#ai-err").textContent = "";
  renderCards();
});
/* Keys already die with the tab, but a student may be on a shared machine and
   want them gone before they stand up. Endpoints and the provider choice are not
   secrets and are left alone, so the label stays literally true. */
$("#ai-forget").onclick = () => {
  const doomed = [];
  try{
    for(let i = 0; i < localStorage.length; i++){
      const k = localStorage.key(i);
      if(k && k.startsWith("tea.ai.key.")) doomed.push(k);
    }
  }catch(e){}
  if(!doomed.length){ $("#ai-err").textContent = tr("forgotnone"); return; }
  if(!confirm(tr("forgetconfirm"))) return;
  for(const k of doomed) SS.del(k);
  $("#ai-key-input").value = "";
  const c = aiConfig();
  if(c && !c.local){ const pp = PROVIDERS.find(x => x.id === c.id); if(pp) showKeyEntry(pp); }
  renderCards(); refreshAiStatus();
  $("#ai-err").textContent = tr("forgotten");
};

// Same check the key gets on entry; the button is for trying again after a fix.
$("#ai-test").onclick = () => { const c = aiConfig(); if(c && c.webgpu) testKey(""); else commitKey(); };

refreshAiStatus();
probeProviders();

$("#go-setup").onclick = async () => {
  const pid = $("#pid").value.trim().toUpperCase();
  const grp = $("#grp").value.trim().toUpperCase();
  const sec = $("#sec").value.trim().toUpperCase();
  const cfg = aiConfig();
  if(!pid || !grp || !sec){ $("#setup-err").textContent = tr("errfields"); return; }
  if(!DEMO && !aiReady()){ $("#setup-err").textContent = tr("errai"); return; }
  if(/[^A-Z0-9-]/.test(pid)){ $("#setup-err").textContent = tr("errcode"); return; }
  $("#setup-err").textContent = "";
  /* network_check is part of why a given student ended up on a given provider,
     so it travels with the session. Null when they never ran one. */
  S = { schema: SCHEMA, app: APP, tool_uses: [], participant: pid, group: grp, section: sec,
        network_check: networkCheck(),
        session_id: rndHex(8), provider: (cfg ? cfg.id : "demo"), model: (cfg ? cfg.model : "demo"),
        started_utc: nowUTC(), exported_utc: null,
        reply_directives: REPLY_DIRECTIVE,
        // `source` says whether this is the prompt the page was built with or one
        // an instructor replaced at run time, so no file is ever ambiguous about
        // which prompt produced it.
        activity_prompt: Object.assign({ id: PROMPT.id, sha256: PROMPT.sha256,
                                         source: PROMPT.source || "built-in", text: PROMPT.text },
                                       meas(PROMPT.text)),
        turns: [] };
  save(); header(); show("s-chat");
  await turnFromAI();     // the prompt is sent for everyone; the AI opens
};

/* ---------- conversation ---------- */
/* Timing is recorded, never displayed. A clock on screen would make students
   hurry, and the pause before a reply is exactly what we want to measure --
   showing it to them would turn the measurement into an artifact of itself.

   aiDoneAt      when the model's reply finished arriving, i.e. when the student
                 could begin reading it
   composeStart  first keystroke in the box after that
   so latency_ms = think + compose, compose_ms = compose alone, and reading and
   thinking time is the difference. */
let aiDoneAt = null, composeStart = null;
/* English needs the singular, Chinese does not distinguish; going through tr()
   for both means neither language has to be special-cased at the call site. */
const turnCount = n => n + " " + tr(n === 1 ? "turn1" : "turns");
function header(){
  $("#p-id").textContent    = S.participant + " · " + S.group + " · " + S.section;
  $("#p-model").textContent = S.model;
  const gone = S.turns.filter(isGone).length;
  $("#p-turns").textContent = turnCount(S.turns.length)
                            + (gone ? "  ·  " + gone + " " + tr("delcount") : "");
}

/* ---------- deleting an exchange ----------
   A student may take back what they said. The turns are grouped as they appear
   on screen -- an AI turn and the reply to it -- and removing one takes both.

   What is left behind is a tombstone: the position, the speaker, the length and
   the moment it was deleted, with the words gone. This is the whole of the
   argument. A file that silently dropped the turns would stop being evidence of
   its own completeness, and the turn counts and the words-per-speaker ratio --
   which are measurements this instrument exists to make -- would quietly become
   wrong. A file that kept the text would hand back the very sentence a student
   was trying to withdraw, which on a page that insists on codes rather than
   names is worse. Counted, but gone.

   There is still deliberately no "start over": see the note further down. This
   is the narrower thing, and it is bounded by leaving a trace. */
const isGone = t => !!t.deleted_utc;

/* Groups of turns as they are read: each AI turn opens a group, and whatever
   the student says next belongs to it. Written as a scan rather than assuming
   strict alternation, because a failed request leaves no AI turn behind. */
function exchanges(){
  const out = [];
  S.turns.forEach((t, i) => {
    if(t.role === "ai" || !out.length) out.push([i]);
    else out[out.length - 1].push(i);
  });
  return out;
}

function deleteExchange(idx){
  if(!confirm(tr("delask"))) return;
  const when = nowUTC();
  for(const i of idx){
    const t = S.turns[i];
    if(isGone(t)) continue;
    /* Keep what can be counted, drop what was said. Timing is kept: how long a
       reply took is not a thing anyone asks to have removed. */
    S.turns[i] = {
      i: t.i, role: t.role, ts: t.ts, deleted_utc: when,
      word_count: t.word_count, char_count: t.char_count,
      ...(t.latency_ms != null ? { latency_ms: t.latency_ms } : {}),
      ...(t.compose_ms != null ? { compose_ms: t.compose_ms } : {}),
    };
  }
  save(); render();
}

function render(){
  const log = $("#log"); log.innerHTML = "";
  for(const idx of exchanges()){
    const gone = idx.every(i => isGone(S.turns[i]));
    if(gone){
      /* One line where the exchange was, rather than a gap. A student who
         deletes something should be able to see that they did. */
      const g = document.createElement("div");
      g.className = "gone";
      g.textContent = tr("delgone");
      log.appendChild(g);
      continue;
    }
    for(const i of idx){
      const t = S.turns[i];
      const d = document.createElement("div");
      d.className = "turn " + t.role;
      const w = document.createElement("span");
      w.className = "who"; w.textContent = t.role === "ai" ? tr("aiteacher") : tr("you");
      d.appendChild(w);
      d.appendChild(isGone(t) ? document.createTextNode("") : rtBody(t.text));
      /* The bin sits on the first turn of the exchange and removes the whole of
         it, because half an exchange is not a thing anyone means to keep. */
      if(i === idx[0]){
        const b = document.createElement("button");
        b.className = "binbtn"; b.type = "button";
        b.title = tr("del"); b.setAttribute("aria-label", tr("del"));
        /* Drawn rather than typed. The bin emoji is missing from enough system
           fonts to come out as a blank box, and a blank box is not a thing
           anyone will press. */
        b.innerHTML = '<svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true" '
                    + 'fill="none" stroke="currentColor" stroke-width="1.3" '
                    + 'stroke-linecap="round" stroke-linejoin="round">'
                    + '<path d="M2.5 4h11M6.5 4V2.6h3V4M4 4l.7 9.1a1 1 0 0 0 1 .9h4.6a1 1 0 0 0 1-.9L12 4"/>'
                    + '<path d="M6.6 6.8v4.6M9.4 6.8v4.6"/></svg>';
        b.onclick = () => deleteExchange(idx);
        d.appendChild(b);
      }
      log.appendChild(d);
    }
  }
  header();
  window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
}
function push(role, text, extra){
  S.turns.push(Object.assign({ i: S.turns.length, role, text, ts: nowUTC() },
                             meas(text), extra || {}));
  save(); render();
}

/* Messages sent to the API: the activity prompt is the opening user message —
   which is exactly what students did by hand — followed by the conversation. It
   is stored as its own field rather than as turn 0, so nothing downstream has to
   decide whether the opening block was the prompt or the AI speaking. Both model
   attribution runs failed on precisely that question. */
/* The language toggle also says what language to be taught in.

   Without this the opening turn is whatever the model defaults to, which for an
   English prompt is English -- so a student who has set the page to 中文 is greeted
   in English before they have written a word, and the AI only follows them into
   Chinese once they have written enough of it to be read.

   Switching mid-conversation changes what comes next and never what has already
   been said. Turns are data; they are not retranslated.

   The directive is appended to the copy of the prompt SENT to the model and never
   to `activity_prompt.text`, which stays byte-identical for everyone and keeps its
   SHA-256. Which language was in force is recorded on each AI turn, and the exact
   wording is recorded once in `reply_directives`, so the instrument can be
   reconstructed from the file instead of from this source. */
const REPLY_DIRECTIVE = {
  en: "Reply in English throughout, whatever language the student writes in.",
  zh: "请全程使用简体中文回复，无论学生使用什么语言。"
};
const replyLang = () => (REPLY_DIRECTIVE[lang] ? lang : "en");
function apiMessages(){
  const m = [{ role: "user",
               content: S.activity_prompt.text + "\n\n" + REPLY_DIRECTIVE[replyLang()] }];
  for(const t of S.turns) m.push({ role: t.role === "ai" ? "assistant" : "user", content: t.text });
  return m;
}

let busy = false;
async function turnFromAI(){
  if(busy) return;
  busy = true; $("#send").disabled = true; $("#chat-err").textContent = "";
  const wait = document.createElement("div");
  wait.className = "turn ai";
  wait.innerHTML = '<span class="who">AI teacher</span><span class="dots"><span></span><span></span><span></span></span>';
  $("#log").appendChild(wait);
  window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
  const askedAt = Date.now(), askedTs = nowUTC(), askedLang = replyLang();
  try{
    const text = demoActive() ? await demoReply() : await callAPI();
    wait.remove();
    push("ai", text, { request_ts: askedTs, elapsed_ms: Date.now() - askedAt,
                       reply_lang: askedLang });
    aiDoneAt = Date.now(); composeStart = null;
  }catch(e){
    wait.remove();
    $("#chat-err").textContent = tr("errreach") + e.message + tr("errsaved");
  }finally{
    busy = false; $("#send").disabled = false; $("#say").focus();
  }
}
/* The API key is NOT in this page. The browser asks the instructor's machine,
   which holds the key and forwards the request. A student who views source sees
   a provider id and nothing else. Same-origin, so CORS does not arise either. */
/* The browser calls the provider directly, using the key the student entered.
   Nothing is baked into this file and nothing is proxied, so the page is a plain
   static file that can be handed out however suits the course.

   Two request shapes: OpenAI-compatible (everything here, plus any local server)
   and Gemini, which uses its own body and an x-goog-api-key header. Google also
   accepts ?key= in the URL; a header is used instead so the credential does not
   land in browser history or any proxy log. */
async function askModel(messages){
  const c = aiConfig();
  if(!c) throw new Error(tr("errai"));
  if(c.api === "webgpu") return askWebGPU(c, messages);
  return c.api === "gemini" ? askGemini(c, messages) : askOpenAI(c, messages);
}
/* No fetch and no key: the weights are already in this browser and the reply is
   computed here. The body is the OpenAI shape the other path uses, so the system
   prompt and the turn history are passed exactly as they are elsewhere. */
async function askWebGPU(c, messages){
  const engine = await webgpuEngineFor(c.model);
  const r = await engine.chat.completions.create({ messages, temperature: 0.7 });
  const out = r && r.choices && r.choices[0] && r.choices[0].message
              && r.choices[0].message.content;
  if(!out) throw new Error("empty reply");
  return out;
}
/* Providers answer a bad key with a page of JSON. A student does not need the
   JSON; they need to know it was the key and where to fix it. Anything that is
   not recognisably an auth problem keeps its own message, shortened. */
function providerError(status, body){
  let msg = "";
  try{ const d = JSON.parse(body); msg = (d.error && (d.error.message || d.error)) || d.message || ""; }
  catch(e){ msg = ""; }
  if(typeof msg !== "string") msg = "";
  if(status === 401 || status === 403 ||
     /api[\s_-]?key|unauthor|invalid.?argument|permission|credential/i.test(msg))
    return tr("errkey");
  return (msg || ("HTTP " + status)).slice(0, 140);
}
async function askOpenAI(c, messages){
  const headers = { "Content-Type": "application/json" };
  if(c.key) headers["Authorization"] = "Bearer " + c.key;
  const r = await fetch(c.url, { method: "POST", headers,
    body: JSON.stringify({ model: c.model, messages, temperature: 0.7 }) });
  if(!r.ok) throw new Error(providerError(r.status, await r.text()));
  const d = await r.json();
  const out = d?.choices?.[0]?.message?.content;
  if(!out) throw new Error("empty reply");
  return out;
}
async function askGemini(c, messages){
  const contents = messages.map(m => ({ role: m.role === "assistant" ? "model" : "user",
                                        parts: [{ text: m.content }] }));
  const r = await fetch(c.url, { method: "POST",
    headers: { "Content-Type": "application/json", "x-goog-api-key": c.key },
    // No maxOutputTokens is set, so this page was never at risk of the mid-word
    // truncation that gemini-2.5-flash's default thinking caused in the classroom
    // apps, where a small budget capped thinking and reply together. Thinking is
    // off anyway, and for the instrument that is the more important reason: it is
    // an unrecorded variable. The session file stores provider and model as
    // covariates, and the finding this study rests on is about reply length -- a
    // hidden setting that changes how much the model writes is exactly what must
    // not vary silently between one session and the next.
    body: JSON.stringify({ contents, generationConfig: { thinkingConfig: { thinkingBudget: 0 } } }) });
  if(!r.ok) throw new Error(providerError(r.status, await r.text()));
  const d = await r.json();
  const out = d?.candidates?.[0]?.content?.parts?.map(x => x.text).join("");
  if(!out) throw new Error("empty reply");
  return out;
}
const callAPI = () => askModel(apiMessages());
async function demoReply(){
  await new Promise(r => setTimeout(r, 800));
  const n = S.turns.filter(t => t.role === "ai").length;
  if(n === 0) return "Hi! I'm your temporary AI profiler. Before we start on Taylor series, "
    + "I'd like to ask a few short questions to work out what kind of teacher you'd learn best from.\n\n"
    + "First one: when something doesn't make sense, would you rather be given a hint, or be asked "
    + "a question that helps you find it yourself?";
  if(n === 1) return "Good — that tells me something.\n\n我明白了。Next: when you get an answer wrong, "
    + "do you want me to say so directly, or work around to it more gently?";
  return "Right. Let's begin.\n\nWithout a calculator, estimate sin(0.2) using a 3rd-degree Taylor "
    + "polynomial centred at x = 0.\n\nStart with the series for sin(x). What are its first few terms?\n\n"
    + "(Demo reply " + (n+1) + " — no API was called.)";
}

$("#send").onclick = async () => {
  const t = $("#say").value.trim();
  if(!t || busy) return;
  $("#say").value = ""; $("#say").style.height = "";
  const sentAt = Date.now();
  push("student", t, {
    latency_ms: aiDoneAt      ? sentAt - aiDoneAt     : null,
    compose_ms: composeStart  ? sentAt - composeStart : null,
    // Whether the palette was reached for at all, and how often. Cheap to record
    // and the only way to know afterwards whether it earned its place.
    math_inserts: mathInserts
  });
  composeStart = null; slots = []; mathInserts = 0;
  await turnFromAI();
};
$("#say").addEventListener("keydown", e => {
  // Tab walks the fields of a freshly inserted template and otherwise does what
  // Tab normally does, so it never traps a student who is not using one.
  if(e.key === "Tab" && !e.shiftKey && slots.length){ e.preventDefault(); nextSlot(); return; }
  if(e.key === "Enter" && !e.shiftKey){ e.preventDefault(); $("#send").click(); }
});
$("#say").addEventListener("input", e => {
  if(composeStart === null && e.target.value.length) composeStart = Date.now();
  e.target.style.height = "auto";
  e.target.style.height = Math.min(180, e.target.scrollHeight) + "px";
});

/* ---------- survey ----------
   Asked inside the activity rather than separately, so a student's answers and
   their conversation are one file. The original study could not match its 146
   survey responses to its 127 transcripts; here the link is structural.
   Name and student ID are not asked: the participant code already carries it. */
/* `prev` is the shape collectSurvey() returns. Passing it back in repaints the
   survey in the other language with everything the student has already answered
   still filled in. */
function renderSurvey(prev){
  const body = $("#survey-body"); body.innerHTML = "";
  SURVEY.forEach((q, i) => {
    const had = (prev || {})[q.id];
    const box = document.createElement("div"); box.className = "q";
    const title = document.createElement("p"); title.className = "qt";
    const num = document.createElement("span"); num.className = "qn"; num.textContent = (i + 1) + ".";
    title.append(num, document.createTextNode(lang === "zh" ? q.zh : q.en));
    box.appendChild(title);

    if(q.type === "text"){
      const ta = document.createElement("textarea");
      ta.id = "q_" + q.id; ta.rows = 3;
      if(typeof had === "string") ta.value = had;
      box.appendChild(ta);
    }else if(q.type === "likert"){
      const chosen = had ? [].concat(had.selected) : [];
      const row = document.createElement("div"); row.className = "lik";
      for(const o of q.options){
        const lab = document.createElement("label");
        const inp = document.createElement("input");
        inp.type = "radio"; inp.name = "q_" + q.id; inp.value = o.v;
        inp.checked = chosen.includes(o.v);
        const sp = document.createElement("span");
        sp.textContent = lang === "zh" ? o.zh : o.en;
        lab.append(inp, sp); row.appendChild(lab);
      }
      box.appendChild(row);
    }else{
      const chosen = had ? [].concat(had.selected) : [];
      for(const o of q.options){
        const lab = document.createElement("label"); lab.className = "opt";
        const inp = document.createElement("input");
        inp.type = q.type === "multi" ? "checkbox" : "radio";
        inp.name = "q_" + q.id; inp.value = o.v;
        inp.checked = chosen.includes(o.v);
        const sp = document.createElement("span");
        sp.textContent = lang === "zh" ? o.zh : o.en;
        lab.append(inp, sp); box.appendChild(lab);
        if(o.specify){
          const sx = document.createElement("input");
          sx.type = "text"; sx.className = "spec"; sx.id = "spec_" + q.id + "_" + o.v;
          sx.placeholder = lang === "zh" ? "请说明" : "Please specify";
          sx.disabled = !inp.checked;
          if(had && had.specify && had.specify[o.v]) sx.value = had.specify[o.v];
          inp.addEventListener("change", () => {
            const on = q.type === "multi" ? inp.checked
                     : document.querySelector('input[name="q_' + q.id + '"]:checked')?.value === o.v;
            for(const el of box.querySelectorAll(".spec")) el.disabled = true;
            sx.disabled = !on;
            if(on) sx.focus();
          });
          box.appendChild(sx);
        }
      }
      box.addEventListener("change", () => {
        if(q.type !== "single") return;
        const picked = box.querySelector('input[name="q_' + q.id + '"]:checked')?.value;
        for(const o of q.options){
          const sx = $("#spec_" + q.id + "_" + o.v);
          if(sx) sx.disabled = picked !== o.v;
        }
      });
    }
    body.appendChild(box);
  });
}
function collectSurvey(){
  const out = {};
  for(const q of SURVEY){
    if(q.type === "text"){
      const v = ($("#q_" + q.id)?.value || "").trim();
      if(v) out[q.id] = v;
      continue;
    }
    const picked = [...document.querySelectorAll('input[name="q_' + q.id + '"]:checked')].map(x => x.value);
    if(!picked.length) continue;
    const spec = {};
    for(const v of picked){
      const sx = $("#spec_" + q.id + "_" + v);
      if(sx && sx.value.trim()) spec[v] = sx.value.trim();
    }
    out[q.id] = q.type === "multi" ? { selected: picked } : { selected: picked[0] };
    if(Object.keys(spec).length) out[q.id].specify = spec;
  }
  return out;
}

/* ---------- maths palette ----------
   Typing x³/3! into a chat box means hunting for characters a keyboard does
   not have, and the usual fallback is ASCII the AI teacher has to guess at. The
   palette inserts real symbols, so what the student wrote is what the model reads
   and what a coder later reads in the transcript.

   Unicode rather than LaTeX: `x³/3!` is legible to a student, to a Pirie-Kieren
   coder reading the corpus, and to every model. `\frac{x^3}{3!}` is legible only
   to the last of those. Where Unicode has no form -- arbitrary exponents, sums
   with bounds -- the templates fall back to the plain-text conventions (`^`, `_`,
   `/`) that every model already reads.

   Templates carry fields marked ⟨like this⟩. Inserting selects the first;
   Tab moves to the next. Markers never reach the textarea. */
/* Three tabs rather than one long list: what a student needs is grouped the way
   they would think of it, and each tab fits without scrolling. Calculus opens
   first because that is the activity. Indices and the power template appear on
   more than one tab on purpose -- a palette is judged by reach, not by taxonomy. */
const MATH_TABS = [
  { en: "Calculus", zh: "微积分", rows: [
      { en: "Symbols", zh: "符号",
        keys: ["∑","∫","∂","∏","∮","∇","∞","Δ","δ","ε","θ","′","″"] },
      { en: "Indices", zh: "指数",
        keys: ["²","³","⁴","⁵","ⁿ","₀","₁","₂","ₙ","!"] },
      { en: "Templates", zh: "模板", tmpl: [
        { en: "Sum",         zh: "求和",  t: "∑_(⟨n=0⟩)^(⟨∞⟩) ⟨term⟩" },
        { en: "Integral",    zh: "积分",  t: "∫_(⟨a⟩)^(⟨b⟩) ⟨f(x)⟩ d⟨x⟩" },
        { en: "Derivative",  zh: "导数",  t: "f⁽⟨n⟩⁾(⟨x⟩)" },
        { en: "Limit",       zh: "极限",  t: "lim_(⟨x→0⟩) ⟨f(x)⟩" },
        { en: "Taylor term", zh: "泰勒项", t: "⟨x⟩^(⟨n⟩)/⟨n⟩!" }
      ] }
  ] },
  { en: "Functions", zh: "函数", rows: [
      { en: "Symbols", zh: "符号",
        keys: ["π","√","∛","≈","∘","|","e","∅"] },
      { en: "Templates", zh: "模板", tmpl: [
        { en: "sin",       zh: "sin",  t: "sin(⟨x⟩)" },
        { en: "cos",       zh: "cos",  t: "cos(⟨x⟩)" },
        { en: "tan",       zh: "tan",  t: "tan(⟨x⟩)" },
        { en: "ln",        zh: "ln",   t: "ln(⟨x⟩)" },
        { en: "log",       zh: "log",  t: "log_(⟨10⟩)(⟨x⟩)" },
        { en: "eˣ",        zh: "eˣ",   t: "e^(⟨x⟩)" },
        { en: "Root",      zh: "根式", t: "√(⟨x⟩)" },
        { en: "Power",     zh: "幂",   t: "⟨x⟩^(⟨n⟩)" },
        { en: "Factorial", zh: "阶乘", t: "⟨n⟩!" },
        { en: "|x|",       zh: "|x|",  t: "|⟨x⟩|" }
      ] }
  ] },
  { en: "Arithmetic", zh: "算术", rows: [
      { en: "Operators", zh: "运算",
        keys: ["+","−","×","÷","·","±","∓","(",")","/"] },
      { en: "Relations", zh: "关系",
        keys: ["=","≈","≠","≤","≥","<",">","≡","→","⇒"] },
      { en: "Indices", zh: "指数",
        keys: ["⁰","¹","²","³","⁴","⁵","⁶","⁷","⁸","⁹","ⁿ","₀","₁","₂","₃","ₙ"] },
      { en: "Templates", zh: "模板", tmpl: [
        { en: "Fraction", zh: "分式", t: "(⟨a⟩)/(⟨b⟩)" },
        { en: "Power",    zh: "幂",   t: "⟨x⟩^(⟨n⟩)" },
        { en: "Percent",  zh: "百分比", t: "⟨n⟩%" }
      ] }
  ] }
];
let mathTab = 0;

let slots = [], slotLen = 0, mathInserts = 0;

function renderMath(){
  const el = $("#mathpal"); el.textContent = "";

  const tabs = document.createElement("div"); tabs.className = "mathtabs";
  MATH_TABS.forEach((t, i) => {
    const b = document.createElement("button");
    b.type = "button"; b.textContent = lang === "zh" ? t.zh : t.en;
    b.setAttribute("aria-selected", String(i === mathTab));
    b.onclick = () => { mathTab = i; renderMath(); $("#say").focus(); };
    tabs.appendChild(b);
  });
  el.appendChild(tabs);

  const key = k => { const b = document.createElement("button");
                     b.type = "button"; b.textContent = k;
                     b.onclick = () => insertMath(k); return b; };
  const tmpl = t => { const b = document.createElement("button");
                      b.type = "button"; b.className = "tmpl";
                      b.textContent = lang === "zh" ? t.zh : t.en;
                      b.onclick = () => insertMath(t.t); return b; };

  for(const r of MATH_TABS[mathTab].rows){
    const g = document.createElement("div"); g.className = "mathgrp";
    const b = document.createElement("b"); b.textContent = lang === "zh" ? r.zh : r.en;
    const wrap = document.createElement("span");
    for(const it of (r.keys || [])) wrap.appendChild(key(it));
    for(const it of (r.tmpl || [])) wrap.appendChild(tmpl(it));
    g.append(b, wrap); el.appendChild(g);
  }
}

/* Insert at the cursor, keeping focus in the box so typing carries straight on. */
function insertMath(raw){
  const ta = $("#say");
  const parts = raw.split(/[⟨⟩]/);        // odd indices are the fields
  const start = ta.selectionStart, end = ta.selectionEnd;
  let plain = "", ranges = [];
  parts.forEach((part, i) => {
    if(i % 2) ranges.push([start + plain.length, start + plain.length + part.length]);
    plain += part;
  });
  ta.focus();
  ta.setRangeText(plain, start, end, "end");
  slots = ranges; slotLen = ta.value.length;
  mathInserts++;
  if(!nextSlot()) ta.setSelectionRange(start + plain.length, start + plain.length);
  ta.dispatchEvent(new Event("input"));           // keep compose timing honest
}
function nextSlot(){
  const ta = $("#say");
  slots = slots.filter(([a, b]) => a >= 0 && b <= ta.value.length && b > a);
  if(!slots.length) return false;
  const p = ta.selectionEnd;
  const s = slots.find(([a]) => a >= p) || slots[0];
  ta.setSelectionRange(s[0], s[1]);
  return true;
}
/* As the student types into a field, everything after it shifts. Tracking the
   length delta keeps the remaining fields pointing at the right characters. */
$("#say").addEventListener("input", () => {
  if(!slots.length) return;
  const ta = $("#say"), d = ta.value.length - slotLen;
  slotLen = ta.value.length;
  if(!d) return;
  const was = ta.selectionStart - d;
  slots = slots.map(([a, b]) => a >= was ? [a + d, b + d] : [a, b]);
});
$("#math").onclick = () => {
  const el = $("#mathpal"), open = el.classList.contains("hide");
  if(open) renderMath();
  el.classList.toggle("hide", !open);
  $("#math").setAttribute("aria-expanded", String(open));
  if(open) $("#say").focus();
};


/* ---------- instructor tools ----------
   Two unlinked addresses let whoever is running the activity replace what the AI
   is told, or the questions asked at the end, without rebuilding anything:

     …/session_capture.html?reset-teacher-prompt
     …/session_capture.html?reset-survey-questions

   Both accept # instead of ? -- a file:// URL will not take a query string.

   IMPORTANT, and said in the dialog too: a change made here lives in THIS browser
   only. It is the right tool for trying a different prompt before class, or for
   showing someone what a change would look like. To change the activity for a
   whole class, rebuild the page (--prompt / --survey) and hand out that file, so
   every student is demonstrably working from the same one.

   Whatever was actually used is recorded in the session either way, so a file is
   never ambiguous about which prompt produced it. */
const K_PROMPT = "tea.custom.prompt", K_SURVEY = "tea.custom.survey";

/* SHA-256 needs a secure context (https, localhost or a file). On a plain LAN
   address it is unavailable, so the hash is recorded as null rather than faked --
   the prompt text itself is stored verbatim and is the actual record. */
async function sha256(text){
  try{
    const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
    return [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, "0")).join("");
  }catch(e){ return null; }
}

function loadCustom(){
  try{
    const p = JSON.parse(SS.get(K_PROMPT) || "null");
    if(p && p.text) PROMPT = p;
    const q = JSON.parse(SS.get(K_SURVEY) || "null");
    if(Array.isArray(q)) SURVEY = q;
  }catch(e){}
}

let toolMode = null;
function openTool(mode){
  toolMode = mode;
  const isPrompt = mode === "prompt";
  $("#tool-title").textContent = tr(isPrompt ? "toolpromptt" : "toolsurveyt");
  $("#tool-sub").textContent   = tr(isPrompt ? "toolprompts" : "toolsurveys");
  $("#tool-text").value = isPrompt ? PROMPT.text : JSON.stringify(SURVEY, null, 2);
  $("#tool-err").textContent = "";
  $("#tool-default").textContent = tr("toolrestore");
  $("#tool-cancel").textContent  = tr("toolcancel");
  $("#tool-save").textContent    = tr("toolsave");
  $("#tool-overlay").classList.add("open");
  setTimeout(() => $("#tool-text").focus(), 0);
}
const closeTool = () => $("#tool-overlay").classList.remove("open");

/* Validated before it is accepted, because a broken survey would only show itself
   at the end of the activity, when the student can least afford it. */
const SURVEY_TYPES = ["single", "multi", "likert", "text"];
function validateSurvey(v){
  if(!Array.isArray(v) || !v.length) return tr("toolerrlist");
  for(const q of v){
    if(!q || !q.id || !q.en || !q.zh || !q.type) return tr("toolerrfields");
    if(!SURVEY_TYPES.includes(q.type)) return tr("toolerrtype") + q.type;
    if(q.type !== "text" && !(Array.isArray(q.options) && q.options.length))
      return tr("toolerropts") + q.id;
  }
  return "";
}

$("#tool-save").onclick = async () => {
  const v = $("#tool-text").value;
  if(toolMode === "prompt"){
    const text = v.trim();
    if(text.length < 200){ $("#tool-err").textContent = tr("toolerrshort"); return; }
    const rec = { id: "instructor", source: "instructor",
                  sha256: await sha256(text), text };
    SS.set(K_PROMPT, JSON.stringify(rec));
    PROMPT = rec;
    $("#promptview").textContent = PROMPT.text;
  }else{
    let parsed;
    try{ parsed = JSON.parse(v); }
    catch(e){ $("#tool-err").textContent = tr("toolerrjson") + e.message; return; }
    if(parsed && parsed.questions) parsed = parsed.questions;   // accept survey.json whole
    const bad = validateSurvey(parsed);
    if(bad){ $("#tool-err").textContent = bad; return; }
    SS.set(K_SURVEY, JSON.stringify(parsed));
    SURVEY = parsed;
  }
  closeTool();
};
$("#tool-default").onclick = () => {
  SS.del(toolMode === "prompt" ? K_PROMPT : K_SURVEY);
  $("#tool-err").textContent = tr("toolreset");
  setTimeout(() => location.reload(), 700);
};
$("#tool-cancel").onclick = closeTool;
$("#tool-x").onclick = closeTool;
$("#tool-overlay").onclick = e => { if(e.target === $("#tool-overlay")) closeTool(); };

/* ---------- export ---------- */
function download(){
  const blob = new Blob([JSON.stringify(S, null, 2)], { type: "application/json;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "session_" + S.participant + "_" + S.group + "_" + S.section + ".json";
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 4000);
}
function surveyDone(){ return !!(S && S.survey && Object.keys(S.survey.answers || {}).length); }
function fillDone(){
  const pending = SURVEY.length && !surveyDone();
  $("#to-survey").classList.toggle("hide", !pending);
  $("#done-note").textContent = pending ? tr("surveypending") : "";
  const sw = S.turns.filter(t => t.role === "student").reduce((a, t) => a + t.word_count, 0);
  const aw = S.turns.filter(t => t.role === "ai").reduce((a, t) => a + t.word_count, 0);
  $("#done-stats").textContent = turnCount(S.turns.length) + " · "
                               + sw + " " + tr("wordsfrom") + " · " + aw + " " + tr("wordsai");
  if(!$("#report").classList.contains("hide")) fillReport();
}

/* The report, drawn from S rather than from the file that was just written.

   The file and this view are the same session by construction -- S is what was
   serialised -- so there is nothing to load and nothing that can go stale, and
   it works with no network at all. That matters more than it sounds: a student
   handed a single HTML file on a disk has no other page to open, and the class
   this was built for may not reach anything outside it.

   The survey is shown as questions, not as ids. reader.html cannot do that,
   because a session file records answers and not the wording; this page still
   has SURVEY, so it can say what was asked. */
const ms1 = n => n == null ? null : (n >= 10000 ? Math.round(n / 1000) + "s"
                                                : (n / 1000).toFixed(1) + "s");
function answerText(q, v){
  if(v == null || v === "") return null;
  if(typeof v === "string") return v;
  const label = id => {
    const o = (q.options || []).find(x => x.v === id);
    return o ? ((lang === "zh" && o.zh) ? o.zh : o.en) : id;
  };
  const sel = Array.isArray(v.selected) ? v.selected
            : (v.selected == null ? [] : [v.selected]);
  let out = sel.map(label).join(lang === "zh" ? "、" : ", ");
  if(v.specify && typeof v.specify === "object"){
    const extra = Object.entries(v.specify).filter(([, t]) => t !== "" && t != null)
                                           .map(([, t]) => t);
    if(extra.length) out += (out ? " — " : "") + extra.join("; ");
  }
  return out || null;
}
function fillReport(){
  const box = $("#report");
  box.innerHTML = "";
  const add = (tag, cls, text) => {
    const e = document.createElement(tag);
    if(cls) e.className = cls;
    if(text != null) e.textContent = text;
    box.appendChild(e); return e;
  };

  /* Calculations belong in the report for the same reason they belong in the
     file: a student checking what they are about to hand in should see all of
     it. Placed where they happened, as the reader places them. */
  const uses = Array.isArray(S.tool_uses) ? S.tool_uses : [];
  const KINDWORD = { evaluate: "rcalced", graph: "rcalcgraph", table: "rcalctable" };
  const calcAt = i => {
    for(const u of uses.filter(u => (u.after_turn == null ? -1 : u.after_turn) === i)){
      const d = document.createElement("div");
      d.className = "rcalc";
      const w = document.createElement("span"); w.className = "rcw";
      /* An attempt that failed is named as an attempt. Calling it "you worked
         out" and printing "= undefined" would report the opposite of what
         happened. */
      if(u.deleted_utc){
        d.classList.add("failed");
        w.textContent = tr("rcalcgone");
        d.appendChild(w);
        box.appendChild(d);
        continue;
      }
      w.textContent = tr(u.error ? "rcalctried" : (KINDWORD[u.kind] || "rcalced"));
      const c = document.createElement("code");
      c.textContent = (!u.error && u.kind === "evaluate" && u.result != null)
        ? u.expr + " = " + ms0(u.result) : (u.expr || "");
      d.append(w, c);
      if(u.error){
        d.classList.add("failed");
        const n = document.createElement("span"); n.className = "rcn";
        n.textContent = u.error;
        d.appendChild(n);
      }
      box.appendChild(d);
    }
  };
  calcAt(-1);
  for(const [ti, t] of S.turns.entries()){
    if(isGone(t)){
      const g = document.createElement("div");
      g.className = "gone";
      g.textContent = tr("delgone") + "  ·  " + t.word_count + " "
                    + tr(t.word_count === 1 ? "word1" : "wordn");
      box.appendChild(g);
      continue;
    }
    const d = document.createElement("div");
    d.className = "turn " + t.role;
    const w = document.createElement("span");
    w.className = "who";
    w.textContent = t.role === "ai" ? tr("aiteacher") : tr("you");
    d.appendChild(w);
    d.appendChild(rtBody(t.text));
    const bits = [];
    if(t.role === "ai" && t.latency_ms != null) bits.push(tr("rreplied") + " " + ms1(t.latency_ms));
    if(t.role === "student" && t.compose_ms != null) bits.push(tr("rtyped") + " " + ms1(t.compose_ms));
    if(t.word_count != null) bits.push(t.word_count + " " + tr(t.word_count === 1 ? "word1" : "wordn"));
    if(bits.length){
      const m = document.createElement("span");
      m.className = "rmeta"; m.textContent = bits.join("  ·  ");
      d.appendChild(m);
    }
    calcAt(ti);
    box.appendChild(d);
  }

  const answers = (S.survey && S.survey.answers) || null;
  if(SURVEY.length){
    add("h3", null, tr("youranswers"));
    const asked = SURVEY.filter(q => answers && answerText(q, answers[q.id]) != null);
    if(!asked.length){
      add("p", "hint", tr("noanswers"));
    } else {
      for(const q of asked){
        const wrap = document.createElement("div"); wrap.className = "qa";
        const qq = document.createElement("span"); qq.className = "q";
        qq.textContent = (lang === "zh" && q.zh) ? q.zh : q.en;
        const aa = document.createElement("span"); aa.className = "a";
        aa.textContent = answerText(q, answers[q.id]);
        wrap.appendChild(qq); wrap.appendChild(aa); box.appendChild(wrap);
      }
    }
  }

  const det = document.createElement("details");
  const sum = document.createElement("summary");
  sum.textContent = tr("whatai");
  const pre = document.createElement("pre");
  pre.textContent = S.activity_prompt.text;
  det.appendChild(sum); det.appendChild(pre); box.appendChild(det);
}
$("#see-report").onclick = () => {
  const box = $("#report"), showing = box.classList.contains("hide");
  if(showing) fillReport();
  box.classList.toggle("hide", !showing);
  $("#see-report").textContent = tr(showing ? "hidereport" : "seereport");
  if(showing) box.scrollIntoView({ behavior: "smooth", block: "start" });
};

/* Submission. The page is served from the instructor's machine on the classroom
   LAN, so it posts straight back there and the file never leaves the room. If
   that fails for any reason — page opened from disk, server not running, network
   hiccup — it falls back to downloading the file and opening a pre-addressed
   email. One class session with no second chance is the wrong place to rely on a
   single mechanism. */
async function submitSession(){
  // No submit URL means the student hands the work in themselves, which is the
  // normal case: it is their work, and it is going to their instructor for
  // credit. Downloading is the destination, not a fallback from a failure.
  if(!SUBMIT.url) return failover("");
  if(DEMO) return failover("");
  if(location.protocol === "file:")
    return failover("This page was opened from a file, so it cannot send by itself.");
  try{
    const r = await fetch(SUBMIT.url, { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(S) });
    const d = await r.json().catch(() => ({}));
    if(!r.ok || !d.ok) throw new Error(d.error || ("HTTP " + r.status));
    S.submitted = true;
    // The instructor has it, so drop it from this browser: classroom machines are
    // shared, and the next student should not find the last one's conversation.
    // S stays in memory, so "Download a copy" still works until the tab closes.
    try{ localStorage.removeItem(KEY); }catch(e){}
    $("#done-h").textContent  = tr("received");
    $("#done-msg").textContent = tr("recvmsg");
  }catch(e){
    failover("Could not send automatically (" + e.message + ").");
  }
}
function failover(why){
  download();
  $("#done-h").textContent   = tr("saved");
  $("#done-msg").textContent = (why ? why + " " : "") + tr("savedmsg");
}
/* Finish sits a couple of centimetres below the language toggle, and both are in
   the top-right corner. One stray click should not end the activity, so it asks.
   Nothing is lost either way -- the conversation is still there afterwards -- but
   being bounced out of it mid-thought is disorienting enough to be worth a step. */
$("#finish").onclick = () => {
  if(!S.turns.some(t => t.role === "student")){
    $("#chat-err").textContent = tr("errsay"); return;
  }
  if(!confirm(tr("finishconfirm"))) return;
  if(SURVEY.length){ renderSurvey(); show("s-survey"); window.scrollTo(0, 0); return; }
  finalise();
};
$("#survey-done").onclick = () => {
  const answers = collectSurvey();
  S.survey = Object.keys(answers).length ? { answered_utc: nowUTC(), answers } : null;
  save(); finalise();
};
async function finalise(){
  S.exported_utc = nowUTC();
  save();
  fillDone(); show("s-done"); window.scrollTo(0, 0);
  await submitSession();
}
$("#to-survey").onclick = () => { renderSurvey(); show("s-survey"); window.scrollTo(0, 0); };
$("#redownload").onclick  = download;
$("#resume").onclick = () => { render(); show("s-chat"); };

/* There is deliberately no "start over" in the interface.

   A student who could discard a conversation and begin again would be selecting
   the corpus one session at a time, and the discarded one would leave no trace --
   the same silent, unrecorded variation the whole re-collection exists to remove.
   A student who wants to change direction can say so to the AI teacher, which is
   itself worth recording.

   Deleting a single exchange is allowed, and the difference is the trace. A
   deleted exchange leaves a tombstone: the position, the speaker and the length
   stay in the file, so the turn counts and the words-per-speaker ratio remain
   true and the session is still evidence of its own completeness. Starting over
   would leave nothing at all, which is the thing being refused. See
   deleteExchange() above.

   ?reset is for whoever is building the activity. Nothing links to it, nothing
   shows it, and it asks before it does anything. It clears the session only:
   stored keys are left alone, since "Forget all keys" is the thing for those.

   It runs before the resume block below, so clearing the stored session is all it
   takes -- the page carries on loading and finds nothing to restore. No reload,
   so nothing can loop on a parameter still sitting in the address bar.
   Both ?reset and #reset work. A file:// URL will not take a query string --
   the browser looks for a file called "session_capture.html?reset" and fails to
   load anything at all -- so the hash is the one that works from disk. */
const flag = n => new URLSearchParams(location.search).has(n) || location.hash === "#" + n;
loadCustom();
$("#promptview").textContent = PROMPT.text;
if(flag("reset-teacher-prompt"))   openTool("prompt");
if(flag("reset-survey-questions")) openTool("survey");
if(flag("reset")){
  if(confirm(tr("resetconfirm"))){ try{ localStorage.removeItem(KEY); }catch(e){} }
  try{ history.replaceState(null, "", location.pathname); }catch(e){}
}

/* The static HTML carries English, so nothing had translated it on a zh build or
   for a student whose saved choice was zh. Runs last, after any restored screen
   is on show, so it repaints whichever one that is. */
applyLang();

/* ---------- resume after a reload ---------- */
(function(){
  const prev = load();
  const READABLE = [SCHEMA, "tea-taylor-session/1"];
  if(prev && READABLE.includes(prev.schema) && prev.activity_prompt){
    prev.schema = SCHEMA;   // saved before tombstones; nothing about it is wrong
    S = prev; render();
    /* The calculator comes back with the session. A student who reloads should
       find their working where they left it, not an empty tape beside a
       conversation that survived. */
    Calculator.restore(S.tool_uses);
    if(prev.exported_utc && SURVEY.length && !surveyDone()){
      renderSurvey(); show("s-survey");
    }else if(prev.exported_utc){
      fillDone(); show("s-done");
      if(prev.submitted){
        $("#done-h").textContent   = tr("received");
        $("#done-msg").textContent = tr("recvmsg");
      }else{
        $("#done-h").textContent   = tr("saved");
        $("#done-msg").textContent = tr("savedmsg");
      }
    }else{
      show("s-chat");
    }
  }
})();
</script>
"""


VENDOR = HERE / "vendor"

def _asset(name: str) -> str:
    """A vendored file, or a clear failure. A page that silently lost its maths
    renderer would look fine until an expression appeared in front of a class."""
    p = VENDOR / name
    if not p.is_file():
        raise SystemExit(f"missing {p} -- the maths renderer is vendored, not fetched")
    return p.read_text(encoding="utf-8")


# Temml's stylesheet names a woff2 for script capitals that we do not ship. Drop
# the rule rather than let a built page reach for a file that is not beside it.
TEMML_CSS = re.sub(r"@font-face\s*\{[^}]*\}", "", _asset("temml.css")).strip()
# MIT asks that the notice travel with the code, and the code travels into every
# built page. The minified file carries no banner of its own, so one is added here
# rather than left to the repository, which a handed-out HTML file is not part of.
TEMML_JS  = ("/*\n" + _asset("temml.LICENSE").strip()
             + "\n\nTemml 0.11.11 -- https://temml.org\n*/\n"
             + _asset("temml.min.js").strip())

# How a turn is drawn. One copy, inlined into the activity and the reader alike,
# so a transcript cannot come to look different from the conversation it records.
RICHTEXT_JS  = (HERE / "richtext.js").read_text(encoding="utf-8").strip()
RICHTEXT_CSS = (HERE / "richtext.css").read_text(encoding="utf-8").strip()
CALCULATOR_JS  = (HERE / "calculator.js").read_text(encoding="utf-8").strip()
CALCULATOR_CSS = (HERE / "calculator.css").read_text(encoding="utf-8").strip()


def with_assets(page: str) -> str:
    return (page
            .replace("__CALCULATOR_CSS__", CALCULATOR_CSS)
            .replace("__CALCULATOR_JS__", CALCULATOR_JS)
            .replace("__RICHTEXT_CSS__", RICHTEXT_CSS)
            .replace("__RICHTEXT_JS__", RICHTEXT_JS)
            .replace("__TEMML_CSS__", TEMML_CSS)
            .replace("__TEMML_JS__", TEMML_JS))


TEMPLATE = with_assets(TEMPLATE)
READER_TEXT = (HERE / "reader.src.html").read_text(encoding="utf-8")

# A build id, derived rather than typed. It is a digest of everything that makes
# a page -- the assembled template with its libraries, and the reader source --
# taken while the version marks are still tokens, so hashing cannot depend on
# its own result. It changes when, and only when, the thing it identifies does:
# no timestamp, so a rebuild of unchanged sources is still byte-identical, which
# is what lets the built pages be committed and diffed.
BUILD = hashlib.sha256((TEMPLATE + READER_TEXT).encode("utf-8")).hexdigest()[:8]


def stamp(page: str) -> str:
    return page.replace("__VERSION__", VERSION).replace("__BUILD__", BUILD)


TEMPLATE = stamp(TEMPLATE)

SETUP_SRC  = HERE / "setup.src.html"
READER_SRC = HERE / "reader.src.html"


def build_reader() -> str:
    """The transcript reader, carrying the same maths renderer as the activity.

    A transcript that showed dollar signs where the student saw an expression
    would misreport the session, so the reader takes its delimiters, its
    fallback and its library from the same place the activity does.
    """
    return stamp(with_assets(READER_TEXT))


def build_setup(defaults: dict) -> str:
    """The same generator, in the browser.

    A teacher who wants a different prompt, different questions, their own title
    and their own thumbnail should not need Python to get them. setup.html embeds
    the student template with its tokens still in place and fills them in exactly
    as build() does -- same template, same tokens, so the two cannot disagree.

    It ships beside the activity rather than inside it, so the page students open
    carries no teacher controls at all.
    """
    def js(obj):
        # </script> inside a JS string literal would close the block it sits in
        return json.dumps(obj, ensure_ascii=False).replace("</script", "<\\/script")

    return (SETUP_SRC.read_text(encoding="utf-8")
            .replace("__TEMPLATE_JSON__", js(TEMPLATE))
            .replace("__DEFAULTS_JSON__", js(defaults)))


def load_prompt(path: Path) -> dict:
    """Read the activity prompt, dropping the instructions addressed to students.

    Everything before PROMPT_MARKER tells students how to paste into DeepSeek and
    then into Word — the procedure this tool replaces. Only what follows is sent
    to the model.
    """
    raw = path.read_text(encoding="utf-8")
    text = raw.split(PROMPT_MARKER, 1)[1].strip() if PROMPT_MARKER in raw else raw.strip()
    if len(text) < 200:
        raise SystemExit(f"prompt at {path} looks too short ({len(text)} chars) — check the marker")
    return {"id": path.name,
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "text": text}


def check(provs: list[dict]) -> int:
    """Make one real call per keyed provider, verifying body and response parsing."""
    import urllib.error, urllib.request
    ok = True
    print("checking providers with a real call:\n")
    for p in provs:
        gemini = p.get("api") == "gemini"
        if gemini:
            # Same body shape the page sends, thinking included -- a check that
            # exercises a different request from the students' is not a check.
            body = json.dumps({"contents": [{"role": "user",
                               "parts": [{"text": "Reply with exactly: ok"}]}],
                               "generationConfig": {"thinkingConfig": {"thinkingBudget": 0}}}).encode("utf-8")
            headers = {"Content-Type": "application/json", "x-goog-api-key": p["key"]}
        else:
            body = json.dumps({"model": p["model"],
                               "messages": [{"role": "user", "content": "Reply with exactly: ok"}],
                               "max_tokens": 16}).encode("utf-8")
            headers = {"Content-Type": "application/json", "Authorization": "Bearer " + p["key"]}
        req = urllib.request.Request(p["url"], data=body, method="POST", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.loads(r.read().decode("utf-8"))
            reply = (d["candidates"][0]["content"]["parts"][0]["text"] if gemini
                     else d["choices"][0]["message"]["content"]).strip()
            print(f"  ok    {p['id']:<9} {p['model']:<26} -> {reply[:40]!r}")
        except Exception as e:
            ok = False
            extra = ""
            if isinstance(e, urllib.error.HTTPError):
                extra = "\n          " + e.read().decode("utf-8", "replace")[:240]
            print(f"  FAIL  {p['id']:<9} {p['model']:<26} {type(e).__name__}: {e}{extra}")
    print("\ncheck:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def pub_providers(providers: list[dict]) -> list[dict]:
    """What the page is allowed to know about a provider: never a key."""
    return [{"id": p["id"], "label": p["label"], "model": p["model"],
            "blurb": p.get("blurb", ""), "blurb_zh": p.get("blurb_zh", ""),
            "recommended": bool(p.get("recommended")),
            "tier": p.get("tier", "paid"), "api": p.get("api", "openai"),
            "url": p["url"], "key_url": p.get("key_url", ""),
            "prefix": p.get("prefix", ""),
            "placeholder": p.get("placeholder", "")} for p in providers]


def tint(hex_colour: str, s: float, l: float) -> str:
    """Take the accent's HUE and restate it at a fixed lightness and saturation.

    The student's turns are tinted with the accent, so an accent needs a very
    pale background and a light edge to go with it. Deriving them means a new
    activity colour is one flag, not three hand-picked hexes that may or may not
    sit together.

    Hue only, rather than mixing the accent towards white: a straight mix
    desaturates, and the pair that was hand-picked for the original accent
    (#fbf0e7 / #eed7c3) is *more* saturated in HSL terms than the accent itself,
    because saturation inflates as lightness approaches 1. Fixing s and l and
    carrying only the hue reproduces those two almost exactly for the default
    accent, so existing pages keep the look they have.
    """
    c = hex_colour.lstrip("#")
    r, g, b = (int(c[i:i+2], 16) / 255 for i in (0, 2, 4))
    h, _, _ = colorsys.rgb_to_hls(r, g, b)
    rr, gg, bb = colorsys.hls_to_rgb(h, l, s)
    return "#%02x%02x%02x" % (round(rr * 255), round(gg * 255), round(bb * 255))


def build(providers: list[dict], prompt: dict, submit: dict, chat_url: str,
          avatar: str, footer: str, lang: str, section: str, title_zh: str,
          subtitle_zh: str, survey: list, demo: bool, title: str, subtitle: str,
          accent: str) -> str:
    # Deliberately NOT published to the page: url and key. The page names a
    # provider; the student supplies the credential.
    pub = pub_providers(providers)
    return (TEMPLATE
            .replace("__PROVIDERS_JSON__", json.dumps(pub, ensure_ascii=False))
            .replace("__PROMPT_JSON__", json.dumps(prompt, ensure_ascii=False))
            .replace("__SUBMIT_JSON__", json.dumps(submit, ensure_ascii=False))
            .replace("__CHAT_JSON__", json.dumps(chat_url))
            .replace("__AVATAR_JSON__", json.dumps(avatar))
            .replace("__FOOTER_JSON__", json.dumps(footer, ensure_ascii=False))
            .replace("__TITLE_JSON__", json.dumps(title, ensure_ascii=False))
            .replace("__SUBTITLE_JSON__", json.dumps(subtitle, ensure_ascii=False))
            .replace("__LANG_JSON__", json.dumps(lang))
            .replace("__SECTION_JSON__", json.dumps(section))
            .replace("__SURVEY_JSON__", json.dumps(survey, ensure_ascii=False))
            .replace("__TITLE_ZH_JSON__", json.dumps(title_zh, ensure_ascii=False))
            .replace("__SUBTITLE_ZH_JSON__", json.dumps(subtitle_zh, ensure_ascii=False))
            .replace("__DEMO_JSON__", "true" if demo else "false")
            .replace("__ACCENT_BG__", tint(accent, 0.71, 0.945))
            .replace("__ACCENT_EDGE__", tint(accent, 0.56, 0.849))
            .replace("__ACCENT__", accent)
            .replace("__TITLE__", title)
            .replace("__SUBTITLE__", subtitle))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--key", action="append", default=[], metavar="ID=KEY",
                    help="API key, e.g. --key deepseek=sk-... (repeatable). "
                         "Falls back to the provider's environment variable.")
    ap.add_argument("--only", help="comma-separated provider ids to offer; default is "
                                   "all of them. Which ones actually answer depends on "
                                   "the student's network, which the page tests in AI "
                                   "Setup rather than assuming.")
    ap.add_argument("--model", action="append", default=[], metavar="ID=MODEL",
                    help="override a provider's model, e.g. --model groq=llama-3.1-8b-instant")
    ap.add_argument("--prompt", type=Path, default=PROMPT_DEFAULT,
                    help="activity prompt to embed (default: the original prompts.tex)")
    ap.add_argument("--avatar", type=Path, default=HERE / "instructor.jpg",
                    help="course branding image, inlined as a data URI so the page stays "
                         "self-contained (default: instructor.jpg beside this script)")
    ap.add_argument("--no-avatar", action="store_true")
    ap.add_argument("--footer", default="",
                    help="footer line identifying the course, e.g. "
                         "'Riverside College \u00b7 Calculus II \u00b7 Dr Ada Shah'")
    ap.add_argument("--chat-url", default="chat",
                    help="where the page asks the instructor's machine to call the model, "
                         "relative to the page (default: chat, i.e. serve_collect.py). "
                         "API keys stay on that machine and are never written into the page.")
    ap.add_argument("--submit-url", default="",
                    help="optional: POST the finished session to this path instead of relying on "
                         "the student to hand the file in. Empty (the default) means the student "
                         "downloads the file and submits it themselves. Set to 'submit' to post "
                         "back to serve_collect.py on a classroom LAN.")
    ap.add_argument("--check", action="store_true",
                    help="make one real API call per keyed provider and report, verifying "
                         "the request body and response parsing before the browser sees it")
    ap.add_argument("--demo", action="store_true",
                    help="canned replies, no keys, no network — for looking at the interface")
    ap.add_argument("--out", type=Path, default=HERE / "session_capture.html")
    ap.add_argument("--survey", type=Path, default=HERE / "survey.json",
                    help="survey shown after the conversation and saved into the same file")
    ap.add_argument("--no-survey", action="store_true", help="skip the survey entirely")
    ap.add_argument("--section", default="",
                    help="fixed section code recorded with every session, e.g. S4. "
                         "When set, students are not asked for it.")
    ap.add_argument("--title-zh", default="AI 活动",
                    help="Chinese title shown when the page is switched to 中文")
    ap.add_argument("--subtitle-zh", default='欢迎！在今天的课上，你将有机会借助生成式 AI 探索泰勒级数。这个应用是我为收集大家的作业而搭建的。开始之前，请先设置 AI，并在下方填写你的编号。你的对话会随时保存。你发送的消息会传给 AI 服务商以获取回复，除此之外不会上传到任何其他地方。结束后请下载 JSON 文件并提交给我，作为本次课的成绩。',
                    help="Chinese opening paragraph")
    ap.add_argument("--lang", choices=("en", "zh"), default="en",
                    help="language the page opens in; students can switch either way")
    ap.add_argument("--accent", default="#9a5734", metavar="HEX",
                    help="accent colour, e.g. --accent '#3f5f7a'. Tints the student's "
                         "turns, the buttons and the links, so a set of activities can "
                         "be told apart at a glance instead of looking identical. The "
                         "pale background and edge tones are derived from it.")
    ap.add_argument("--title", default="AI activity")
    ap.add_argument("--minutes", type=int, default=0,
                    help="suggested duration shown to students; 0 says nothing. "
                         "NOTE: prompts.tex says 'no more than 20 minutes' while methods.tex "
                         "says students had 'approximately 50 minutes' — resolve before class.")
    ap.add_argument("--subtitle", default="Welcome! In today's class, you'll have the opportunity to explore Taylor Series with genAI. I've set up this app to collect your work. You'll need to set up an AI and enter your codes in the dialog below to get started. Your conversation is saved as you go. Your messages go to the AI provider to get replies, and nowhere else. You'll download your conversation as a JSON file and submit it to me for class credit.")
    a = ap.parse_args()

    def pairs(items, flag):
        out = {}
        for kv in items:
            if "=" not in kv:
                ap.error(f"{flag} needs ID=VALUE, got {kv!r}")
            k, v = kv.split("=", 1)
            out[k.strip()] = v.strip()
        return out

    keys = pairs(a.key, "--key")
    models = pairs(a.model, "--model")

    known = {p["id"] for p in PROVIDERS}
    if a.only:
        chosen = [s.strip() for s in a.only.split(",") if s.strip()]
        unknown = [c for c in chosen if c not in known]
        if unknown:
            ap.error(f"unknown provider(s): {', '.join(unknown)}. known: {', '.join(sorted(known))}")
    else:
        # Test-only providers stay out of the default picker so they cannot reach
        # the classroom by accident. Naming one in --only or --key is explicit intent.
        chosen = [p["id"] for p in PROVIDERS
                  if a.demo or not p.get("test_only") or p["id"] in keys]

    provs = []
    for p in PROVIDERS:
        if p["id"] not in chosen:
            continue
        q = dict(p)
        q["model"] = models.get(p["id"], p["model"])
        # only used by --check; the page never receives a key
        env = p.get("env", p["id"].upper() + "_API_KEY")
        q["key"] = keys.get(p["id"]) or os.environ.get(env, "")
        if q.get("test_only"):
            q["label"] += "  — testing only"
        provs.append(q)

    live = [p for p in provs if p["key"]]

    if a.check:
        return check(live)

    subtitle = a.subtitle + (f" Please spend about {a.minutes} minutes." if a.minutes else "")

    avatar = ""
    if not a.no_avatar and a.avatar and a.avatar.exists():
        import base64, mimetypes
        mime = mimetypes.guess_type(a.avatar.name)[0] or "image/jpeg"
        avatar = f"data:{mime};base64," + base64.b64encode(a.avatar.read_bytes()).decode()
    elif not a.no_avatar and a.avatar:
        print(f"  note: no branding image at {a.avatar} — building without it", file=sys.stderr)

    survey = []
    if not a.no_survey and a.survey.exists():
        spec = json.loads(a.survey.read_text(encoding="utf-8"))
        survey = spec.get("questions", [])

    prompt = load_prompt(a.prompt)
    submit = {"url": a.submit_url}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(build(provs, prompt, submit, a.chat_url, avatar, a.footer, a.lang, a.section.strip().upper(),
                           a.title_zh, a.subtitle_zh, survey, a.demo, a.title, subtitle,
                           a.accent), encoding="utf-8")

    # The builder ships with the activity so a teacher can make their own without
    # Python. It embeds this exact template, so the two stay in step by construction.
    setup_out = a.out.parent / "setup.html"
    if SETUP_SRC.exists() and not a.demo:
        setup_out.write_text(build_setup({
            "providers": pub_providers(provs), "submit": submit, "chat_url": a.chat_url,
            "avatar": avatar, "footer": a.footer, "title": a.title, "title_zh": a.title_zh,
            "subtitle": subtitle, "subtitle_zh": a.subtitle_zh, "lang": a.lang,
            "section": a.section.strip().upper(), "prompt": prompt, "survey": survey,
            "accent": a.accent,
            "built": prompt["sha256"][:12],
        }), encoding="utf-8")

    reader_out = a.out.parent / "reader.html"
    if READER_SRC.exists() and not a.demo:
        reader_out.write_text(build_reader(), encoding="utf-8")

    print(f"wrote {a.out}  ({a.out.stat().st_size/1024:.0f} KB)")
    if SETUP_SRC.exists() and not a.demo:
        print(f"wrote {setup_out}  ({setup_out.stat().st_size/1024:.0f} KB)  "
              f"— the browser builder, for making an activity without Python")
    if READER_SRC.exists() and not a.demo:
        print(f"wrote {reader_out}  ({reader_out.stat().st_size/1024:.0f} KB)  "
              f"— the transcript reader")
    print(f"  prompt            : {prompt['id']}  sha256 {prompt['sha256'][:12]}…  "
          f"{len(prompt['text'])} chars")
    print(f"  survey            : {len(survey)} question(s)" if survey else "  survey            : (none)")
    print(f"  section           : {a.section.strip().upper() or '(students are asked)'}")
    print("  reachability      : probed silently at load; the picker lists what answered")
    print(f"  branding          : {'inlined, %.0f KB' % (len(avatar)/1024) if avatar else '(none)'}")
    print(f"  footer            : {a.footer or '(none)'}")
    print(f"  submits to        : {a.submit_url or '(disabled)'}")
    if a.demo:
        print("\nDEMO build — canned replies, no keys, no network. Open it directly:")
        print(f"  xdg-open {a.out}")
        return 0

    print(f"  providers offered : {', '.join(p['id'] for p in provs)}")
    print("  keys              : entered by the student in AI Setup; none in this file")
    if any(p.get("test_only") for p in provs):
        print("\n  NOTE: a testing-only provider is in this build. Groq is not reachable\n"
              "  from mainland China — do not send this build to the classroom.")
    print("\nSelf-contained: no server, no keys inside. Hand it out however suits you —")
    print("email it, put it on the LMS, or copy it to a shared drive.")
    # Said to the person who can act on it. The student sees none of this: a page
    # that cannot reach anything simply offers the local option and the note.
    print("\nOpening this file directly works: every provider above allows a null")
    print("origin, which is what a file:// page sends (re-checked by preflight).")
    print("A URL is still easier for a class -- one link, one version, nothing to")
    print("hand round, and it can be demonstrated over a call:")
    print(f"  python3 -m http.server 8000   # then http://<your-ip>:8000/{a.out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
