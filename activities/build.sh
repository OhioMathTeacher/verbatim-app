#!/usr/bin/env bash
# Rebuild the fifteen draft activities and the root page. Run from the repository root:
#     bash activities/build.sh          demonstrations: no codes asked, no hand-in
#     bash activities/build.sh class    a class runs them: codes asked, hand-in and
#                                       research wording back
#
# Why this exists: the three were built by hand with only --prompt/--out/--title,
# so all three inherited the generator's DEFAULT subtitle -- which welcomes the
# reader to "explore Taylor Series", a topic none of them is about. Keeping the
# real invocation in a file means the next rebuild cannot quietly lose the
# per-activity wording again.
#
# Each has its own --accent so a set of them can be told apart at a glance
# rather than looking like three copies of one page.
set -euo pipefail
cd "$(dirname "$0")/.."

# Shared closing sentences. NOTE the honesty fix: the old default said "Nothing
# is uploaded to the internet", which is false -- the page calls the provider's
# API from the student's browser. What is true is that no copy comes to us until
# the student hands the file in, and that it is posted to no website.
TAIL_CLASS="Type the class passcode and your codes below to begin. Your conversation is saved on this device as you go, and the words you send go through the class's server to Claude, Anthropic's AI, to get replies, and nowhere else. The server keeps no copy of them. When you have finished, download the file and submit it to me for class credit. This conversation is your coursework. With your permission it may also be used for research: a small number of records, with names removed, may be studied by a collaborating researcher at Miami University in the United States. You may say no to research use, on the survey or by telling me, and it will make no difference to your grade."
# What the pages say while they are demonstrations: no codes to enter, nothing
# handed in, no research use.
TAIL="Type the class passcode below to begin. Your conversation is saved on this device as you go, and the words you send go through the class's server to Claude, Anthropic's AI, to get replies, and nowhere else. The server keeps no copy of them. When you have finished, you can download the conversation as a file."

# The one switch. Demo (the default) builds with --no-codes and the demo TAIL;
# "class" asks for codes again and uses the TAIL_CLASS wording.
MODE="${1:-demo}"

# The eight activities call Claude through the class's Worker (worker/README.md):
# students type the class passcode and never see a key, and AI Setup is in the
# page but not shown (decided 29 Oct 2026). Each links back to the activities
# page. Set VERBATIM_CLASS_AI to try a build against a Worker on 127.0.0.1.
CLASS_AI="${VERBATIM_CLASS_AI:-https://verbatim-class.ohiomathteacher.workers.dev}"
case "$MODE" in
  demo)  CODES="--no-codes" ;;
  class) CODES=""; TAIL="$TAIL_CLASS" ;;
  *)     echo "usage: bash activities/build.sh [demo|class]" >&2; exit 2 ;;
esac

# The seven calculus pages key everything to the last five digits of the student
# number (decided 15 Sep 2026): pre-survey, the activities, post-survey all
# carry the same digits, and only Zheng can resolve them.
CODEHINT="Your participant code is the last five digits of your student number — the same digits you gave on the survey. Do not type your name anywhere on this page."

# The one content item in survey.json, helped_learn, asks whether the activity
# "helped me learn calculus concepts better" -- wrong for the spider (no
# calculus), and too vague for the rest. Each page gets
# survey.json with that item reworded to name what its activity is about;
# every other question stays as written. The id is kept, so the answers still
# line up across pages.
SURVEYS="$(mktemp -d)"
trap 'rm -rf "$SURVEYS"' EXIT
learn_survey() {  # name, en -> path of a survey.json with helped_learn reworded
  python3 -I - "$SURVEYS/$1.json" "$2" <<'EOF'
import json, sys
out, en = sys.argv[1:]
spec = json.load(open("survey.json", encoding="utf-8"))
qs = spec["questions"] if isinstance(spec, dict) else spec
hit = [q for q in qs if q["id"] == "helped_learn"]
assert len(hit) == 1, "survey.json no longer has exactly one helped_learn item"
hit[0]["en"] = en
json.dump(spec, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
EOF
  echo "$SURVEYS/$1.json"
}

# Activities 5-8 are alternatives for the same slot, so they share one wording.
CHAIN_EN="This assignment helped me understand how one rate of change can be built from two others (the chain rule)."

python3 make_session_capture.py \
  --prompt activities/prompts/1-pendulum-approximation.txt \
  --out activities/activity-1-pendulum.html \
  --survey "$(learn_survey pendulum "This assignment helped me understand how to decide when an approximation is good enough.")" \
  $CODES --class-ai "$CLASS_AI" --home-url index.html --voice \
  --codehint "$CODEHINT" \
  --accent '#9a5734' \
  --title    "How small is small enough?" \
  --subtitle "Welcome! Today you will work out how far a pendulum can be pulled aside before the usual formula stops being good enough — and find that the answer depends entirely on what the pendulum is for. $TAIL"

python3 make_session_capture.py \
  --prompt activities/prompts/2-scaling-square-cube.txt \
  --out activities/activity-2-scaling.html \
  --survey "$(learn_survey scaling "This assignment helped me understand how weight and strength change when something is made bigger.")" \
  $CODES --class-ai "$CLASS_AI" --home-url index.html --voice \
  --codehint "$CODEHINT" \
  --accent '#7a5c1f' \
  --title    "Why can't a spider be the size of a horse?" \
  --subtitle "Welcome! Today you will work out why a spider the size of a horse would collapse under its own weight — no calculus, just what happens to weight and to leg thickness when you make something bigger. $TAIL"

python3 make_session_capture.py \
  --prompt activities/prompts/3-speedometer-limits.txt \
  --out activities/activity-3-speedometer.html \
  --survey "$(learn_survey speedometer "This assignment helped me understand what speed at a single instant means.")" \
  $CODES --class-ai "$CLASS_AI" --home-url index.html --voice \
  --codehint "$CODEHINT" \
  --accent '#3f5f7a' \
  --title    "What does the speedometer mean?" \
  --subtitle "Welcome! Today you will work out how you would check that a speedometer really does read 60 km/h, using only a stopwatch and distance markers — and what happens as the interval you measure over gets shorter and shorter. $TAIL"

python3 make_session_capture.py \
  --prompt activities/prompts/5-record-chain-rule.txt \
  --out activities/activity-5-record.html \
  --survey "$(learn_survey record "$CHAIN_EN")" \
  $CODES --class-ai "$CLASS_AI" --home-url index.html --voice \
  --codehint "$CODEHINT" \
  --accent '#6b4a6e' \
  --title    "Why was the last song the worst?" \
  --subtitle "Welcome! Today you will work out why the last song on a vinyl record sounded worse than the first one. Then you will find out why the engineers who designed the compact disc made it change speed as it plays. $TAIL"

# The three below are chain-rule alternatives to the record activity rather than
# three more slots in the term: Zheng's set runs about a month apart and activity
# 4 is already the record. They are built so the choice can be made by trying
# them, and they carry the same codehint because they would run in the same set.

python3 make_session_capture.py \
  --prompt activities/prompts/6-gears-chain-rule.txt \
  --out activities/activity-6-gears.html \
  --survey "$(learn_survey gears "$CHAIN_EN")" \
  $CODES --class-ai "$CLASS_AI" --home-url index.html --voice \
  --codehint "$CODEHINT" \
  --accent '#2f6f6a' \
  --title    "Why does the same pedalling give you different speeds?" \
  --subtitle "Welcome! Today you will work out how far one turn of the pedals takes you, and how fast that makes you go. Then you will decide what to change when the hill gets too steep to pedal at all. $TAIL"

python3 make_session_capture.py \
  --prompt activities/prompts/7-uphill-chain-rule.txt \
  --out activities/activity-7-uphill.html \
  --survey "$(learn_survey uphill "$CHAIN_EN")" \
  $CODES --class-ai "$CLASS_AI" --home-url index.html --voice \
  --codehint "$CODEHINT" \
  --accent '#6a7a2f' \
  --title    "How much colder does it get when you walk uphill?" \
  --subtitle "Welcome! Today you will work out how much colder it is at the top of a trail, and then how much colder it gets for every kilometre you walk. Those are two different numbers, and working out why is today's task. $TAIL"

python3 make_session_capture.py \
  --prompt activities/prompts/8-clock-chain-rule.txt \
  --out activities/activity-8-clock.html \
  --survey "$(learn_survey clock "$CHAIN_EN")" \
  $CODES --class-ai "$CLASS_AI" --home-url index.html --voice \
  --codehint "$CODEHINT" \
  --accent '#8a3f52' \
  --title    "How does one swing of a pendulum become an hour?" \
  --subtitle "Welcome! Today you will work out how a clock turns one swing of a pendulum, about one a second, into a hand that goes round once in twelve hours. Then you will find out what happens to the clock if the pendulum runs slightly fast. $TAIL"

# Rates in context, and maxima, minima and shape: eight activities added on
# 29 Oct 2026. Each survey's topic question names that activity's own topic.

python3 make_session_capture.py \
  --prompt activities/prompts/9-growth-races-lhopital.txt \
  --out activities/activity-9-growth.html \
  --survey "$(learn_survey growth "This assignment helped me understand how to compare two quantities that both grow without bound (L'Hôpital's rule).")" \
  $CODES --class-ai "$CLASS_AI" --home-url index.html --voice \
  --codehint "$CODEHINT" \
  --accent '#3d6b8f' \
  --title    "Which grows faster in the end?" \
  --subtitle "Welcome! Today you will race two quantities that both grow without bound and work out which one wins in the end. Their sizes will not settle it, but how fast each one grows will. $TAIL"

python3 make_session_capture.py \
  --prompt activities/prompts/10-sprinter-splits.txt \
  --out activities/activity-10-sprinter.html \
  --survey "$(learn_survey sprinter "This assignment helped me understand what a derivative means in context, with its units.")" \
  $CODES --class-ai "$CLASS_AI" --home-url index.html --voice \
  --codehint "$CODEHINT" \
  --accent '#8a5a2b' \
  --title    "When was the sprinter fastest?" \
  --subtitle "Welcome! Today you will use the times a sprinter passed each 10-metre mark to work out when they were fastest, and what a table of times can and cannot tell you about speed. $TAIL"

python3 make_session_capture.py \
  --prompt activities/prompts/11-streetlight-shadow.txt \
  --out activities/activity-11-shadow.html \
  --survey "$(learn_survey shadow "This assignment helped me understand how the speed of one thing can follow from the speed of another (related rates).")" \
  $CODES --class-ai "$CLASS_AI" --home-url index.html --voice \
  --codehint "$CODEHINT" \
  --accent '#556b2f' \
  --title    "How fast does your shadow move?" \
  --subtitle "Welcome! Today you will walk away from a streetlight, on paper, and work out how fast the tip of your shadow moves. The answer may surprise you. $TAIL"

python3 make_session_capture.py \
  --prompt activities/prompts/12-cone-cup.txt \
  --out activities/activity-12-cup.html \
  --survey "$(learn_survey cup "This assignment helped me understand how a steady rate of filling can give a changing rate of rise (related rates).")" \
  $CODES --class-ai "$CLASS_AI" --home-url index.html --voice \
  --codehint "$CODEHINT" \
  --accent '#7b3f7a' \
  --title    "Why does the cup fill fast, then slowly?" \
  --subtitle "Welcome! Today you will pour water into a cone-shaped cup at a steady rate and work out why the level rises quickly at first and then slows down. $TAIL"

python3 make_session_capture.py \
  --prompt activities/prompts/13-speed-camera-mvt.txt \
  --out activities/activity-13-camera.html \
  --survey "$(learn_survey camera "This assignment helped me understand what the Mean Value Theorem guarantees, and what it does not.")" \
  $CODES --class-ai "$CLASS_AI" --home-url index.html --voice \
  --codehint "$CODEHINT" \
  --accent '#2f5e8a' \
  --title    "Can a camera prove you were speeding?" \
  --subtitle "Welcome! Today you will decide whether two cameras that only time a car can prove it broke the speed limit, and what has to be true for that proof to work. $TAIL"

python3 make_session_capture.py \
  --prompt activities/prompts/14-launch-angle.txt \
  --out activities/activity-14-launch.html \
  --survey "$(learn_survey launch "This assignment helped me understand how to find and check the largest value of a function.")" \
  $CODES --class-ai "$CLASS_AI" --home-url index.html --voice \
  --codehint "$CODEHINT" \
  --accent '#9a4a3a' \
  --title    "What is the best angle to throw?" \
  --subtitle "Welcome! Today you will find the angle that throws a ball furthest, and then find out why a shot-putter should not use it. $TAIL"

python3 make_session_capture.py \
  --prompt activities/prompts/15-still-rising.txt \
  --out activities/activity-15-rising.html \
  --survey "$(learn_survey rising "This assignment helped me understand what the first and second derivatives say about how something is changing.")" \
  $CODES --class-ai "$CLASS_AI" --home-url index.html --voice \
  --codehint "$CODEHINT" \
  --accent '#4a6a5a' \
  --title    "Still rising, but more slowly" \
  --subtitle "Welcome! Today you will take a sentence from the news about prices and work out exactly what it says about a function and its derivatives. $TAIL"

python3 make_session_capture.py \
  --prompt activities/prompts/16-soup-can.txt \
  --out activities/activity-16-can.html \
  --survey "$(learn_survey can "This assignment helped me understand how to set up and solve an optimization problem, and what a model leaves out.")" \
  $CODES --class-ai "$CLASS_AI" --home-url index.html --voice \
  --codehint "$CODEHINT" \
  --accent '#6a5a8a' \
  --title    "Why are soup cans that shape?" \
  --subtitle "Welcome! Today you will design a can that holds a fixed amount using as little metal as possible, and then work out why real cans are not that shape. $TAIL"

# The Taylor series page at the root of the site, the one linked as "Try it".
# Built here so its wording is written down too; --section S4 is what it has
# always carried. Run last only because it rewrites the root setup.html, not
# activities/setup.html.
python3 make_session_capture.py \
  --out index.html \
  --section S4 $CODES \
  --subtitle "Welcome! In this activity, you'll explore Taylor series with generative AI. You'll need to set up an AI below to get started. Your conversation is saved as you go. Your messages go to the AI provider to get replies, and nowhere else. When you've finished, you can download your conversation as a file."

echo
echo "Rebuilt fifteen activities and the root page ($MODE). Note that each run also rewrites activities/setup.html"
echo "(the browser builder ships beside the activity), so the last one wins there."
