# Activities

Draft activities built with Verbatim, published so they can be tried on a phone
without installing anything: <https://ohiomathteacher.github.io/verbatim-app/activities/>

Each page is self-contained. It holds no API key — the reader supplies their own
through **AI Setup** — and it posts to no server. `getting-a-key.html` is the
plain-language walkthrough for anyone who has not made one before.

`prompts/` holds the source. To rebuild a page after editing a prompt:

    python3 make_session_capture.py \
        --prompt activities/prompts/1-pendulum-approximation.txt \
        --out activities/activity-1-pendulum.html \
        --title "How small is small enough?"

Always pass `--out`. It defaults to `session_capture.html` in the repository
root, which is a different thing.

`prompts/_RULES.txt` records why all three constrain the model the same way: in
an earlier round of transcripts the AI was writing about eleven words for every
one the student wrote, so every reply is capped, may ask only one question, and
may never answer its own.

These are drafts for comment, not classroom-ready material.
