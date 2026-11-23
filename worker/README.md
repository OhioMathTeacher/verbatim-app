# Verbatim class AI (Cloudflare Worker)

On a page built with `--class-ai`, students type the class passcode their teacher gives
them at the top of the page. They never see, type or hold an API key. The Worker finds whose
key the passcode stands for, checks two daily caps, calls Claude, and returns the reply.
Built with `--own-key` as well, the page also shows AI Setup. A student who uses their own
key there talks to that provider directly, and this Worker is not involved.

There are two kinds of passcode:

- **House passcodes** are the Worker secrets `PASSCODE` and `PASSCODE_<NAME>`, all on the
  Worker's own key. Add one per teacher, so each can be changed or removed alone.
- **Teacher classes** are made on
  https://ohiomathteacher.github.io/verbatim-app/activities/teacher.html. A teacher pastes
  their own Claude key, picks a passcode and gets a teacher code, which can turn the class on
  or off, change the passcode, replace the key, show counts, or delete the class.

It keeps turn counts, and for each teacher class its name, its key and passcode (encrypted
with the secret `CLASS_KEY`), and keyed hashes to look them up by. No message text, student
name, participant code or IP address is written anywhere, and Workers Logs is off
(`wrangler.toml`). The conversation is recorded in one place: the student's own session file,
as with every other provider.

The activities in `activities/build.sh` are built this way. The browser builder
(`setup.html`) still makes pages that set up their own AI.

## First deploy (once)

```bash
cd worker
npm install                                  # pinned: @anthropic-ai/sdk 0.127.0, wrangler 4.153.0
npx wrangler d1 create verbatim-class-counts # paste the printed database_id into wrangler.toml
npx wrangler d1 execute verbatim-class-counts --remote --command "$(grep -v '^ *--' schema.sql | sed 's/--.*//')"
npx wrangler deploy                          # https://verbatim-class.ohiomathteacher.workers.dev
npx wrangler secret put ANTHROPIC_API_KEY    # a key made for Verbatim, with its own spend limit
npx wrangler secret put PASSCODE             # the phrase the teacher gives the class
openssl rand -base64 32 | tr -d '\n' | npx wrangler secret put CLASS_KEY   # once, never replaced
```

Until the first two secrets are set, every request is refused. Without `CLASS_KEY`, only house
passcodes work.

## Another house passcode

```bash
python3 passcode.py --add NAME    # sets PASSCODE_NAME; the passcode is typed hidden
python3 passcode.py               # check one, and change it
npx wrangler secret delete PASSCODE_NAME
```

## Every later change

```bash
npx wrangler deploy
```

Pushing the repository publishes the pages; it does not deploy the Worker.

## Check it's up

```bash
curl https://verbatim-class.ohiomathteacher.workers.dev/health
```

## Knobs (`wrangler.toml` → `[vars]`)

- `MODEL`: `claude-opus-5-5`. The generator reads this value into each page it builds,
  and a page refuses a reply from any other model, because the session file records the
  model. Change it, then rebuild and push the pages, or the live pages will refuse every
  reply.
- `SESSION_CAP`: turns per session per day. 80.
- `DAILY_CAP`: turns per day on one key. 1500 across all house passcodes together, and 1500
  for each teacher class. This is what bounds the bill; the key's own spend limit in Console
  is the backstop.
- `ALLOWED_ORIGINS`: the Pages site, plus localhost for testing.

## Testing locally

Put `ANTHROPIC_API_KEY`, `PASSCODE` and (for a stand-in upstream) `ANTHROPIC_BASE_URL` in
`worker/.dev.vars` (ignored by git), then `npx wrangler dev --ip 127.0.0.1`. Build pages
against it with `VERBATIM_CLASS_AI=http://127.0.0.1:8787 bash activities/build.sh`, and
rebuild without the variable before committing.
