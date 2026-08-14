# verbatim

A single HTML file that records a student's conversation with an AI, exactly as it
happens, and hands back one JSON file per student ready for analysis.

**[Try it →](https://ohiomathteacher.github.io/verbatim/)** — nothing is uploaded, nothing
is stored anywhere but your own browser.

## What it is for

Research on how students talk with AI usually collects *what the student produced* — a
conversation copied into a document, reformatted, and handed in. Everything about who said
what then has to be inferred from the text, and it cannot always be recovered. In the study
this was built for, two researchers annotating the same transcripts reached Krippendorff's
α between 0.21 and 0.66 on speaker attribution alone: below the threshold for even a
tentative claim.

This captures the conversation as it happens instead, so `role` is a fact about where the
text came from rather than an inference about what it looks like.

**The activity is whatever you make it.** The prompt the AI receives and the questions
asked at the end are both yours — swap them and the same instrument runs a different study.
The Taylor Series activity in `examples/` is simply the one it was first built for.

## What it records

One JSON file per student, conforming to a written schema:

- **Every turn tagged `student` or `ai` at creation.** No inference, no `unknown`.
- **The prompt as its own field with a SHA-256** — never as a turn — so which activity a
  session ran is verifiable, and nothing downstream has to decide whether the opening block
  was the prompt or the AI speaking.
- **Timing, never shown on screen**: how long before a reply, and how much of that was
  typing. The difference is reading and thinking. A visible clock would make students hurry.
- **Word counts that work in mixed script**: each CJK ideograph one word, each other run
  one word. Splitting on spaces under-reports Chinese badly.
- **The exit survey, in the same file** as the conversation it describes, so nothing has to
  be matched up afterwards.
- **Codes, never names.** The filename carries participant, group and section only.

## Making your own activity — without installing anything

**[Open the setup page →](https://ohiomathteacher.github.io/verbatim/setup.html)**

Fill in the title, the prompt, the questions at the end, a thumbnail and a footer, then press
**Download the activity**. You get a single HTML file with all of it baked in — that file is
what you give your students. Nothing to install, no command line.

It is the same generator as below, running in the browser: it fills in the same template
through the same fields, so the two cannot produce different pages from the same answers.

## Running it from the command line

```bash
# build the page for a class
python3 make_session_capture.py --prompt my-activity.txt --survey my-questions.json \
                                --section S4 --title "Sequences and series"

# check what you just built, before it goes anywhere
python3 check_page.py

# look at the interface with canned replies — no key, no network
python3 make_session_capture.py --demo
```

Hand out the resulting file, or serve it. Both work: a page opened directly from a file
sends `Origin: null`, and every provider offered accepts that.

`--help` lists the rest: branding, language, submission, provider selection. Every build also
writes `setup.html` beside the activity, so the browser builder always carries the template it
was built from.

## Changing the activity without rebuilding

Two unlinked addresses open an editor for whoever is running the session:

    …/index.html?reset-teacher-prompt
    …/index.html?reset-survey-questions

Use `#` instead of `?` when the page was opened as a local file — a local address will not
carry a query string.

A change made there applies **to that browser only**. It is the right tool for trying a
prompt before class or showing a colleague what a change would look like. To change the
activity for a whole class, rebuild and hand out that file, so every student is
demonstrably working from the same one. Either way `activity_prompt.source` records which
it was, so no session file is ambiguous about what produced it.

## Where the AI comes from

Students bring their own key, or use one the instructor reads out, or run a model on their
own machine with no key at all. The page tries each service when it loads and lists only
the ones that answer from that network — so nobody is offered an option that cannot work
for them, and nothing is asked about their connection or where they are.

A key is checked the moment it is entered: its shape first, then a real call. Nothing is
baked into the built file, and no key ever leaves the student's browser.

## Requirements

Python 3.9+ to build. Nothing to install. Node is optional and only used by
`check_page.py`, which will say so and skip those checks if it is absent.

## Licence

MIT. If you use it in research, a citation is welcome — see `CITATION.cff` in the study
repository.
