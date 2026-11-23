#!/usr/bin/env python3
# Check a Verbatim passcode against the Worker without showing it, and optionally change
# it, or add another one.
#
#   python3 passcode.py               check the one you type; if it is a house passcode,
#                                     offer to change it
#   python3 passcode.py --add NAME    add a house passcode for one more teacher, as the
#                                     secret PASSCODE_<NAME>
#   --stdin                           read the passcode from stdin; no questions asked
#
# A house passcode is a Worker secret, PASSCODE or PASSCODE_<NAME>, on the Worker's own
# key. The Worker says which secret matched, so a change touches that one and nobody
# else's. A class a teacher made on activities/teacher.html is checked the same way but
# can only be changed there. POST /check calls no AI and counts no turns.
#
# To remove one: npx wrangler secret delete PASSCODE_<NAME>
import argparse, getpass, json, os, re, subprocess, sys, time, urllib.request, urllib.error

URL = "https://verbatim-class.ohiomathteacher.workers.dev/check"
WORKER_DIR = os.path.dirname(os.path.abspath(__file__))
WRANGLER = os.path.join(WORKER_DIR, "node_modules/.bin/wrangler")

def check(code):
    """None if refused; otherwise the secret's name, or "" for a teacher's own class."""
    body = json.dumps({"passcode": code}).encode()
    req = urllib.request.Request(URL, data=body, headers={"content-type": "application/json",
                                                         "user-agent": "verbatim-passcode-check/1"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read()).get("secret", "")
    except urllib.error.HTTPError as e:
        reply = e.read().decode()
        err = json.loads(reply).get("error") if reply.startswith("{") else reply
        if e.code == 401 and err == "passcode":
            return None
        if e.code == 403 and err == "off":
            return ""
        sys.exit(f"Unexpected answer from the Worker: {e.code} {err}")

def fit(new):
    # The Worker trims what a student types, keeps the first 80 characters, and ignores
    # case, spaces and dashes.
    if not new or new != new.strip() or len(new) > 80 or len(re.sub(r"[\s_-]", "", new)) < 6:
        sys.exit("Not changed: the passcode needs 6 letters or digits, at most 80 characters, "
                 "and no space at either end.")
    if check(new) is not None:
        sys.exit("Not changed: that passcode is already in use.")

def put(secret, new):
    r = subprocess.run([WRANGLER, "secret", "put", secret], cwd=WORKER_DIR,
                       input=new + "\n", text=True, capture_output=True)
    if r.returncode != 0:
        sys.exit("wrangler failed; nothing changed:\n" + (r.stderr or r.stdout))

def settle(new, secret, old=None):
    # A new secret can take a few seconds to reach the Worker.
    for _ in range(10):
        if check(new) == secret and (old is None or check(old) is None):
            return True
        time.sleep(6)          # slower than the Worker's wait after repeated misses
    sys.exit("wrangler reported success, but after a minute the Worker does not yet agree. "
             "Run this script again to check.")

def ask_new():
    new = getpass.getpass("New passcode (hidden): ")
    if getpass.getpass("Type it again (hidden): ") != new:
        sys.exit("Not changed: the two did not match.")
    return new

ap = argparse.ArgumentParser()
ap.add_argument("--add", metavar="NAME")
ap.add_argument("--stdin", action="store_true")
a = ap.parse_args()

if a.add:
    if not re.fullmatch(r"[A-Za-z0-9_]+", a.add):
        sys.exit("NAME may use letters, digits and _ only.")
    secret = "PASSCODE_" + a.add.upper()
    r = subprocess.run([WRANGLER, "secret", "list"], cwd=WORKER_DIR, text=True, capture_output=True)
    if r.returncode != 0:
        sys.exit("Could not list the Worker's secrets:\n" + (r.stderr or r.stdout))
    if any(x["name"] == secret for x in json.loads(r.stdout)):
        sys.exit(f"Not added: {secret} already exists. Run this without --add and type it to change it.")
    new = sys.stdin.readline().rstrip("\n") if a.stdin else ask_new()
    fit(new)
    put(secret, new)
    settle(new, secret)
    print(f"ADDED: the Worker accepts the new passcode ({secret}).")
    sys.exit()

code = sys.stdin.readline().rstrip("\n") if a.stdin else getpass.getpass("Passcode (hidden): ")
secret = check(code)
if secret is None:
    sys.exit("NO MATCH: the Worker did not accept that passcode.")
if not secret:
    print("MATCH: that is a class a teacher made. Change it on activities/teacher.html.")
    sys.exit()
print(f"MATCH: that is the house passcode {secret}.")
if a.stdin or input("Change it? [y/N] ").strip().lower() != "y":
    sys.exit()
new = ask_new()
fit(new)
print("The old passcode stops working at once, for every activity and everyone who has it.")
if input("Type CHANGE to go ahead: ").strip() != "CHANGE":
    sys.exit("Not changed.")
put(secret, new)
settle(new, secret, old=code)
print("CHANGED: the Worker accepts the new passcode and refuses the old one.")
