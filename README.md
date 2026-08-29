# verbatim

A single HTML file that records a student's conversation with an AI, exactly as it
happens, and hands back one JSON file per student ready for analysis.

**[Try it →](https://ohiomathteacher.github.io/verbatim-app/)** — nothing is uploaded, nothing
is stored anywhere but your own browser.

Three pages, each a single self-contained file:

| | |
|---|---|
| [the activity](https://ohiomathteacher.github.io/verbatim-app/) | what a student opens |
| [setup](https://ohiomathteacher.github.io/verbatim-app/setup.html) | build your own activity, without installing anything |
| [reader](https://ohiomathteacher.github.io/verbatim-app/reader.html) | drop a session file in and read it as a transcript |

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

The schema is `tea-taylor-session/2`. A `/2` file may contain tombstones, so anything
reading one must expect a turn with no `text` — see below.

## Taking an exchange back

A student can delete an exchange before handing the file in: the bin at the corner of a
turn removes it and the reply that belongs with it. This is narrower than it sounds, and
the shape of it is the point.

**What is deleted is the words. What survives is the shape.** A deleted turn keeps its
position, its speaker, its length and the moment it was removed, and loses its `text`:

```json
{ "i": 6, "role": "ai", "ts": "…", "deleted_utc": "…", "word_count": 47, "char_count": 260 }
```

Both halves matter. A file that dropped the turns outright would stop being evidence of
its own completeness — turn counts and the words-per-speaker ratio, which are measurements
this instrument exists to make, would quietly become wrong, and nobody reading the file
could tell a short session from an edited one. A file that kept the text would hand back
the very sentence the student was trying to withdraw, which on a page that insists on codes
rather than names is the worse failure. So: counted, but gone.

There is still no "start over", and the difference is exactly the trace. Discarding a whole
session would leave nothing behind; this leaves the outline of what was removed. The reader
draws deleted exchanges in place, as an outline rather than a gap, for the same reason.


## How a turn is drawn

Replies arrive as Markdown with mathematics in them, whether or not anything asks for
that. The page draws both, so a Taylor series appears as a Taylor series instead of as
`x^3x^3x^3`, and a step appears as **Step 2** instead of `**Step 2**`.

Mathematics is TeX between dollars — `$…$` inline, `$$…$$` set apart — and the activity
prompts ask for it explicitly. Markdown is bold, italics, headings, lists, tables, inline
code and rules.

Two decisions worth knowing about, because both trade a feature for not being wrong:

- **Mathematics is lifted out before Markdown is looked for.** The two languages collide:
  `x_1` is a subscript, not an underline, and `\frac{a}{b}` is full of braces Markdown
  would rather not see. Taking the TeX out first means the Markdown pass only ever sees
  prose.
- **Italics are stricter than CommonMark.** CommonMark reads `2*3*4` as an emphasised 3,
  which in a mathematics transcript quietly eats two multiplication signs. Here an opening
  `*` must begin a line or follow a space, so `*Hint:*` is emphasis and `2*3*4` is a
  product. `_` is never emphasis — outside the dollars it is a subscript. A lone `$5` in a
  sentence about money is left alone for the same reason.

**The recorded turn is never touched.** Rendering builds a view of the text; the JSON the
student hands in still holds the characters the model actually sent, asterisks and dollars
and all. What was said and how it was displayed stay separate, which is the same reason
`role` is recorded at creation rather than inferred later.

The reply rules still tell the model not to use headings, bold or lists. That rule is about
reading load and the sixty-word cap, and it stands. The renderer is what happens when the
model ignores it, which it does.

`richtext.js` and `richtext.css` hold all of this, in one copy, inlined into both the
activity and the reader at build time — so a transcript read afterwards cannot come to look
different from the conversation it recorded. Drawing the mathematics is
[Temml](https://temml.org) (MIT), vendored in `vendor/`, converting TeX to MathML that the
browser draws itself. Nothing is fetched: a page opened from `file://` on a classroom
machine with no network still shows mathematics. Anything Temml cannot parse falls back to
the raw characters rather than vanishing.

## Light or dark

The activity follows the machine, and the ☾ button in the corner overrides it either way.
The choice is remembered in that browser, beside the language, and is deliberately never
written into the session file: what a student found comfortable to read is not data about
what they did. The reader is light only.

## Making your own activity — without installing anything

**[Open the setup page →](https://ohiomathteacher.github.io/verbatim-app/setup.html)**

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
was built from, and `reader.html`, so the reader carries the same maths renderer the activity
does. Both are generated — edit `setup.src.html` and `reader.src.html`, not the built files.

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
