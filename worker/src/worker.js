// Verbatim class AI — a Cloudflare Worker between a Verbatim page and Claude.
//
// A page built with --class-ai never holds an API key and never asks a student for one.
// The student types the class passcode their teacher gives them; the page POSTs it here
// with the conversation so far; this Worker checks the passcode and the daily caps, calls
// Claude with the instructor's key, and returns the reply.
//
// What it keeps: a count of turns per session per day, and per day in all, so the caps
// work. What it does not keep: any message text, the passcode, codes, or an IP address.
// There is no log table and no console.log of a request, and Workers Logs is switched
// off in wrangler.toml. The conversation is recorded in one place only -- the student's
// own session file -- exactly as it is when the page calls a provider directly.
//
// Routes:  POST /chat   {passcode, sid, messages}  ->  {text, model}
//          GET  /health                            ->  {ok, model}

import Anthropic from "@anthropic-ai/sdk";

// The page sends the whole conversation each turn, because that is how it calls every
// provider. These bound what one request can carry. A 40-minute activity is a few dozen
// turns of a few hundred words; the ceilings are far above that and only stop misuse.
const MAX_MESSAGES = 200;
const MAX_MESSAGE_CHARS = 20000;
const MAX_TOTAL_CHARS = 300000;

const json = (obj, status = 200, extra = {}) =>
  new Response(JSON.stringify(obj), { status, headers: { "content-type": "application/json", ...extra } });

function cors(env, req) {
  const origin = req.headers.get("Origin") || "";
  const allowed = (env.ALLOWED_ORIGINS || "").split(",").map(s => s.trim());
  const ok = allowed.includes(origin);
  return {
    "Access-Control-Allow-Origin": ok ? origin : allowed[0] || "",
    "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
    "Access-Control-Allow-Headers": "content-type",
    "Vary": "Origin",
  };
}

function localDay(d = new Date()) {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit" }).format(d);
}

const clip = (s, n) => (typeof s === "string" ? s : "").trim().slice(0, n);

// The same shape the page builds for every provider: the activity prompt as the first
// user turn, then the conversation. Anything else is refused rather than repaired, so
// what Claude was sent is always what the student's file says was sent.
function checkMessages(m) {
  if (!Array.isArray(m) || !m.length || m.length > MAX_MESSAGES) return null;
  let total = 0;
  for (const x of m) {
    if (!x || (x.role !== "user" && x.role !== "assistant")) return null;
    if (typeof x.content !== "string" || !x.content || x.content.length > MAX_MESSAGE_CHARS) return null;
    total += x.content.length;
  }
  if (m[0].role !== "user" || total > MAX_TOTAL_CHARS) return null;
  return m.map(x => ({ role: x.role, content: x.content }));
}

// One row per (day, key) holding a number. The key is "all" or "sid:<session id>"; the
// session id is the random one in the student's file, so a count is never tied to a
// person. Counted before the call, so a burst cannot all slip under the cap at once.
async function bump(env, day, key) {
  const r = await env.DB.prepare(
    "INSERT INTO counts (day, k, n) VALUES (?, ?, 1) ON CONFLICT (day, k) DO UPDATE SET n = n + 1 RETURNING n"
  ).bind(day, key).first();
  return r ? r.n : 0;
}

async function chat(req, env) {
  let body;
  try { body = await req.json(); } catch { return json({ error: "bad json" }, 400); }

  if (!env.PASSCODE || clip(body.passcode, 80) !== env.PASSCODE) return json({ error: "passcode" }, 401);
  const sid = clip(body.sid, 64);
  if (!/^[0-9a-f]{8,64}$/.test(sid)) return json({ error: "sid" }, 400);
  const messages = checkMessages(body.messages);
  if (!messages) return json({ error: "messages" }, 400);

  // Per session: what one student's conversation may use in a day. Per day: the class
  // ceiling, which is what bounds the bill. A school puts a whole room behind one
  // address, so there is no per-network cap; it would lock the class out at once.
  const day = localDay();
  const sessionCap = parseInt(env.SESSION_CAP || "80", 10);
  const dayCap = parseInt(env.DAILY_CAP || "1500", 10);
  if (await bump(env, day, "all") > dayCap) return json({ error: "cap-class" }, 429);
  if (await bump(env, day, "sid:" + sid) > sessionCap) return json({ error: "cap" }, 429);

  // A class presses Send at about the same time, so retries are spread further than the
  // SDK's default. A 429 from Anthropic is not a billable call.
  const client = new Anthropic({ apiKey: env.ANTHROPIC_API_KEY, maxRetries: 4,
                                 ...(env.ANTHROPIC_BASE_URL ? { baseURL: env.ANTHROPIC_BASE_URL } : {}) });
  let resp;
  try {
    // The same request the page makes when a student uses their own Claude key, effort
    // pinned "low" for the same reason (see askAnthropic in make_session_capture.py).
    resp = await client.messages.create({
      model: env.MODEL, max_tokens: 16000,
      output_config: { effort: "low" }, messages,
    });
  } catch (e) {
    return json({ error: "upstream", status: e?.status || 0 }, 502);
  }
  if (resp.stop_reason === "refusal") return json({ error: "refusal" }, 200);
  const text = resp.content.filter(b => b.type === "text").map(b => b.text).join("");
  if (!text) return json({ error: "empty" }, 502);
  return json({ text, model: resp.model });
}

export default {
  async fetch(req, env) {
    const h = cors(env, req);
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: h });
    const path = new URL(req.url).pathname;
    let r;
    if (req.method === "POST" && path === "/chat") r = await chat(req, env);
    else if (req.method === "GET" && path === "/health") r = json({ ok: true, model: env.MODEL });
    else r = json({ error: "not found" }, 404);
    for (const [k, v] of Object.entries(h)) r.headers.set(k, v);
    return r;
  },
};
