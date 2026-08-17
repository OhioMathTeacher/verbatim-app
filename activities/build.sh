#!/usr/bin/env bash
# Rebuild the three draft activities. Run from the repository root:
#     bash activities/build.sh
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
TAIL="Set up an AI and enter your codes below to begin. Your conversation is saved on this device as you go, and the words you send go to the AI provider you chose and nowhere else — this page posts to no website. When you have finished, download the file and submit it to me for class credit."
TAIL_ZH="开始前请先设置 AI，并在下方填写你的编号。你的对话会随时保存在本机；你发送的内容只会发给你所选择的 AI 服务商，不会发往任何其他网站。结束后请下载文件并提交给我，作为本次课的成绩。"

python3 make_session_capture.py \
  --prompt activities/prompts/1-pendulum-approximation.txt \
  --out activities/activity-1-pendulum.html \
  --accent '#9a5734' \
  --title    "How small is small enough?" \
  --title-zh "多小才算足够小？" \
  --subtitle "Welcome! Today you will work out how far a pendulum can be pulled aside before the usual formula stops being good enough — and find that the answer depends entirely on what the pendulum is for. $TAIL" \
  --subtitle-zh "欢迎！今天你将探究：把摆锤拉开多大的角度，常用的公式才会开始失准——你会发现答案完全取决于这个摆是用来做什么的。$TAIL_ZH"

python3 make_session_capture.py \
  --prompt activities/prompts/2-scaling-square-cube.txt \
  --out activities/activity-2-scaling.html \
  --accent '#7a5c1f' \
  --title    "Why can't a spider be the size of a horse?" \
  --title-zh "蜘蛛为什么不能长到马那么大？" \
  --subtitle "Welcome! Today you will work out why a spider the size of a horse would collapse under its own weight — no calculus, just what happens to weight and to leg thickness when you make something bigger. $TAIL" \
  --subtitle-zh "欢迎！今天你将弄清楚：为什么一只马那么大的蜘蛛会被自己的体重压垮。不需要微积分，只要想清楚把一个物体放大时，体重和腿的粗细各自会怎样变化。$TAIL_ZH"

python3 make_session_capture.py \
  --prompt activities/prompts/3-speedometer-limits.txt \
  --out activities/activity-3-speedometer.html \
  --accent '#3f5f7a' \
  --title    "What does the speedometer mean?" \
  --title-zh "速度表到底表示什么？" \
  --subtitle "Welcome! Today you will work out how you would check that a speedometer really does read 60 km/h, using only a stopwatch and distance markers — and what happens as the interval you measure over gets shorter and shorter. $TAIL" \
  --subtitle-zh "欢迎！今天你将思考：只用一只秒表和路边的距离标记，你要怎样验证速度表上的 60 km/h 是真的——以及当你测量的时间间隔越来越短时，会发生什么。$TAIL_ZH"

echo
echo "Rebuilt three activities. Note that each run also rewrites activities/setup.html"
echo "(the browser builder ships beside the activity), so the last one wins there."
