# Verbatim class AI (Cloudflare Worker)

A page built with `--class-ai` talks to this Worker, never to an AI provider directly.
Students type the class passcode their teacher gives them. They never see, type or hold an
API key. The Worker checks the passcode and two daily caps, calls Claude with the
instructor's key, and returns the reply.

It keeps turn counts and nothing else. No message text, passcode, participant code or IP
address is written anywhere, and Workers Logs is off (`wrangler.toml`). The conversation is
recorded in one place: the student's own session file, as with every other provider.

The eight activities in `activities/build.sh` are built this way. The browser builder
(`setup.html`) still makes pages that set up their own AI.

## First deploy (once)

```bash
cd worker
npm install                                  # pinned: @anthropic-ai/sdk 0.127.0, wrangler 4.147.0
npx wrangler d1 create verbatim-class-counts # paste the printed database_id into wrangler.toml
npx wrangler d1 execute verbatim-class-counts --remote --command "CREATE TABLE IF NOT EXISTS counts (day TEXT NOT NULL, k TEXT NOT NULL, n INTEGER NOT NULL, PRIMARY KEY (day, k));"
npx wrangler deploy                          # https://verbatim-class.ohiomathteacher.workers.dev
npx wrangler secret put ANTHROPIC_API_KEY    # a key made for Verbatim, with its own spend limit
npx wrangler secret put PASSCODE             # the phrase the teacher gives the class
```

Until both secrets are set, every request is refused.

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
- `DAILY_CAP`: turns per day across everyone. 1500. This is what bounds the bill; the
  key's own spend limit in Console is the backstop.
- `ALLOWED_ORIGINS`: the Pages site, plus localhost for testing.

## Testing locally

Put `ANTHROPIC_API_KEY`, `PASSCODE` and (for a stand-in upstream) `ANTHROPIC_BASE_URL` in
`worker/.dev.vars` (ignored by git), then `npx wrangler dev --ip 127.0.0.1`. Build pages
against it with `VERBATIM_CLASS_AI=http://127.0.0.1:8787 bash activities/build.sh`, and
rebuild without the variable before committing.
