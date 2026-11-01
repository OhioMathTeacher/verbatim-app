#!/usr/bin/env python3
# Check the Verbatim class passcode against the Worker without showing it, and
# optionally change it.
# The passcode is typed at a hidden prompt and sent with a session id the Worker
# rejects ("x"). The Worker checks the passcode first (worker/src/worker.js), so:
#   401 {"error":"passcode"}  -> wrong passcode
#   400 {"error":"sid"}       -> right passcode; stopped before Claude, nothing counted
# A change is offered only after the current passcode matches. It runs
# `wrangler secret put PASSCODE` in this folder with the new passcode on
# stdin, then checks that the new one is accepted and the old one is not.
import getpass, json, os, subprocess, sys, time, urllib.request, urllib.error

URL = "https://verbatim-class.ohiomathteacher.workers.dev/chat"
WORKER_DIR = os.path.dirname(os.path.abspath(__file__))
WRANGLER = os.path.join(WORKER_DIR, "node_modules/.bin/wrangler")

def check(code):
    body = json.dumps({"passcode": code, "sid": "x", "messages": []}).encode()
    req = urllib.request.Request(URL, data=body, headers={"content-type": "application/json",
                                                         "user-agent": "verbatim-passcode-check/1"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            status, reply = r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        status, reply = e.code, e.read().decode()
    err = json.loads(reply).get("error") if reply.startswith("{") else reply
    if status == 400 and err == "sid":
        return True
    if status == 401 and err == "passcode":
        return False
    sys.exit(f"Unexpected answer from the Worker: {status} {err}")

def change(old):
    if input("Change the class passcode? [y/N] ").strip().lower() != "y":
        return
    new = getpass.getpass("New passcode (hidden): ")
    # The Worker trims what a student types and keeps the first 80 characters, so a
    # passcode with outer spaces or over 80 characters could never be matched.
    if not new or new != new.strip() or len(new) > 80:
        sys.exit("Not changed: the passcode must be 1 to 80 characters, with no space at either end.")
    if getpass.getpass("Type it again (hidden): ") != new:
        sys.exit("Not changed: the two did not match.")
    if new == old:
        sys.exit("Not changed: that is the passcode it already has.")
    print("The old passcode stops working at once, for every activity and everyone who has it,")
    print("Mr. Phelps included. Anyone using the activities will need the new one.")
    if input("Type CHANGE to go ahead: ").strip() != "CHANGE":
        sys.exit("Not changed.")
    r = subprocess.run([WRANGLER, "secret", "put", "PASSCODE"], cwd=WORKER_DIR,
                       input=new + "\n", text=True, capture_output=True)
    if r.returncode != 0:
        sys.exit("wrangler failed; the passcode is unchanged:\n" + (r.stderr or r.stdout))
    # A new secret can take a few seconds to reach the Worker.
    for _ in range(10):
        if check(new) and not check(old):
            print("CHANGED: the Worker accepts the new passcode and refuses the old one.")
            return
        time.sleep(3)
    sys.exit("wrangler reported success, but after 30 seconds the Worker is not yet "
             "accepting only the new passcode. Run this script again to check.")

code = sys.stdin.readline().rstrip("\n") if "--stdin" in sys.argv else getpass.getpass("Class passcode (hidden): ")
if check(code):
    print("MATCH: that is the class passcode.")
    if "--stdin" not in sys.argv:
        change(code)
else:
    print("NO MATCH: the Worker did not accept that passcode.")
