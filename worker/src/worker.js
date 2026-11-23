// Verbatim class AI — a Cloudflare Worker between a Verbatim page and Claude.
//
// The student types the class passcode their teacher gives them; the page POSTs it here
// with the conversation so far; this Worker finds whose key the passcode stands for, checks
// the daily caps, calls Claude, and returns the reply. A student who uses their own key
// never comes here: the page calls that provider directly.
//
// Two kinds of passcode:
//   house    a Worker secret, PASSCODE or PASSCODE_<NAME>, on ANTHROPIC_API_KEY. Any number
//            of them, so each teacher's can be changed or removed without the others'.
//   teacher  a class a teacher made on activities/teacher.html with their own Claude key.
//            One row in D1: the key and the passcode encrypted (AES-GCM, secret CLASS_KEY),
//            the passcode and teacher code as keyed hashes for lookup, a name, on/off, and
//            a count of turns. No browser ever gets a key back, the teacher's included.
// The teacher classes follow Matrix Explorer's Worker (matrix-explorer/worker/index.js).
//
// What it keeps besides: a count of turns per session per day, and per day in all, so the
// caps work. What it does not keep: any message text, student names, codes, or an IP
// address. There is no log table and no console.log of a request, and Workers Logs is
// switched off in wrangler.toml. The conversation is recorded in one place only -- the
// student's own session file -- exactly as when the page calls a provider directly.
//
// Routes:  POST /check         {passcode}                 ->  {ok, name, secret?} or 401; no AI call
//          POST /chat          {passcode, sid, messages}  ->  {text, model}
//          POST /class/create  {key, passcode, name}      ->  {ok, teacherCode, passcode, name}
//          POST /class/manage  {teacherCode, action, ...} ->  class status, after the action
//          GET  /health                                   ->  {ok, model, classes}

import Anthropic from "@anthropic-ai/sdk";

// The page sends the whole conversation each turn, because that is how it calls every
// provider. These bound what one request can carry. A 40-minute activity is a few dozen
// turns of a few hundred words; the ceilings are far above that and only stop misuse.
const MAX_MESSAGES = 200;
const MAX_MESSAGE_CHARS = 20000;
const MAX_TOTAL_CHARS = 300000;

const json = (obj, status = 200, extra = {}) =>
  new Response(JSON.stringify(obj), { status, headers: { "content-type": "application/json", "cache-control": "no-store", ...extra } });

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

const enc = new TextEncoder(), dec = new TextDecoder();
const b64 = buf => btoa(String.fromCharCode(...new Uint8Array(buf)));
const unb64 = s => Uint8Array.from(atob(s), c => c.charCodeAt(0));

/* ---------- secrets ---------- */
// CLASS_KEY yields two keys: one encrypts teachers' keys and passcodes, the other hashes
// passcodes and teacher codes, so a copy of the database alone reveals neither.
let keysFor = null, keys = null;
async function cryptoKeys(env) {
  if (keysFor === env.CLASS_KEY && keys) return keys;
  const raw = await crypto.subtle.digest("SHA-256", enc.encode("verbatim|" + env.CLASS_KEY));
  const aes = await crypto.subtle.importKey("raw", raw, "AES-GCM", false, ["encrypt", "decrypt"]);
  const hraw = await crypto.subtle.digest("SHA-256", enc.encode("verbatim-hash|" + env.CLASS_KEY));
  const hmac = await crypto.subtle.importKey("raw", hraw, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  keysFor = env.CLASS_KEY; keys = { aes, hmac };
  return keys;
}
async function seal(env, text) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, (await cryptoKeys(env)).aes, enc.encode(text));
  return b64(iv) + "." + b64(ct);
}
async function open(env, sealed) {
  const [iv, ct] = String(sealed).split(".");
  return dec.decode(await crypto.subtle.decrypt({ name: "AES-GCM", iv: unb64(iv) }, (await cryptoKeys(env)).aes, unb64(ct)));
}
async function keyedHash(env, kind, text) {
  return b64(await crypto.subtle.sign("HMAC", (await cryptoKeys(env)).hmac, enc.encode(kind + "|" + text)));
}
// Passcodes are matched without regard to case, spaces or dashes, so "Orbit Tiger 42" and
// "orbit-tiger-42" on a board both work; teacher codes are matched exactly.
const normPass = s => clip(s, 80).toLowerCase().replace(/[\s_-]+/g, "");
const passHash = (env, p) => keyedHash(env, "pass", normPass(p));
const teacherHash = (env, t) => keyedHash(env, "teacher", clip(t, 80).toUpperCase());
function newTeacherCode() {
  const A = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789", r = crypto.getRandomValues(new Uint8Array(12));
  let s = "T";
  for (let i = 0; i < 12; i++) { if (i % 4 === 0) s += "-"; s += A[r[i] % A.length]; }
  return s;                                                    // T-XXXX-XXXX-XXXX, about 60 bits
}

/* ---------- throttles ---------- */
// After 5 misses from one address each further try waits a little, measured from the last
// miss. In memory, so per Worker instance, and gentle: a school room shares one address.
// Each route counts its own misses. A page checks the passcode (/check) before it ever
// chats, so students mistyping at the start of class cannot hold up the ones already talking.
const misses = new Map();
const missKey = (kind, req) => kind + "|" + (req.headers.get("CF-Connecting-IP") || "");
function throttled(k) {
  const m = misses.get(k);
  return m && m.n >= 5 && Date.now() - m.t < Math.min(5000, 1000 * (m.n - 4));
}
function missed(k) {
  const m = misses.get(k) || { n: 0, t: 0 };
  misses.set(k, { n: m.n + 1, t: Date.now() });
  if (misses.size > 5000) misses.clear();
}
// Creating classes: a few per address per hour is plenty for a teacher.
const creates = new Map();
function createdLately(ip) {
  const now = Date.now(), list = (creates.get(ip) || []).filter(t => now - t < 3600e3);
  creates.set(ip, list);
  if (creates.size > 5000) creates.clear();
  return list;
}

/* ---------- whose key a passcode stands for ---------- */
const classesOn = env => !!(env.DB && env.CLASS_KEY);
function housePass(env, pass) {
  const n = normPass(pass);
  if (!n) return null;
  for (const k of Object.keys(env))
    if (/^PASSCODE(_[A-Z0-9_]+)?$/.test(k) && typeof env[k] === "string" && normPass(env[k]) === n) return k;
  return null;
}
async function classByPass(env, pass) {
  if (!classesOn(env) || !normPass(pass)) return null;
  return env.DB.prepare("SELECT * FROM classes WHERE pass_hash = ?").bind(await passHash(env, pass)).first();
}

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
  const body = await readBody(req); if (!body) return json({ error: "bad json" }, 400);
  const mk = missKey("chat", req);
  if (throttled(mk)) return json({ error: "slow" }, 429);
  const house = housePass(env, body.passcode);
  const row = house ? null : await classByPass(env, body.passcode);
  if (!house && !row) { missed(mk); return json({ error: "passcode" }, 401); }
  misses.delete(mk);
  if (row && !row.active) return json({ error: "off" }, 403);
  const sid = clip(body.sid, 64);
  if (!/^[0-9a-f]{8,64}$/.test(sid)) return json({ error: "sid" }, 400);
  const messages = checkMessages(body.messages);
  if (!messages) return json({ error: "messages" }, 400);

  // Per session: what one student's conversation may use in a day. Per day: the ceiling on
  // one key, which is what bounds the bill -- every house passcode shares one, and each
  // teacher's class has its own. A school puts a whole room behind one address, so there is
  // no per-network cap; it would lock the class out at once.
  const day = localDay();
  if (await bump(env, day, row ? "class:" + row.id : "all") > dailyCap(env)) return json({ error: "cap-class" }, 429);
  if (await bump(env, day, (row ? "sid:" + row.id + ":" : "sid:") + sid) > sessionCap(env)) return json({ error: "cap" }, 429);
  if (row) await env.DB.prepare("UPDATE classes SET uses = uses + 1 WHERE id = ?").bind(row.id).run();

  let resp;
  try {
    const key = row ? await open(env, row.key_enc) : env.ANTHROPIC_API_KEY;
    // A class presses Send at about the same time, so retries are spread further than the
    // SDK's default. A 429 from Anthropic is not a billable call.
    // The same request the page makes when a student uses their own Claude key, effort
    // pinned "low" for the same reason (see askAnthropic in make_session_capture.py).
    resp = await claude(env, key, 4).messages.create({
      model: env.MODEL, max_tokens: 16000,
      output_config: { effort: "low" }, messages,
    });
  } catch (e) {
    return json({ error: upstreamError(e), status: e?.status || 0 }, 502);
  }
  if (resp.stop_reason === "refusal") return json({ error: "refusal" }, 200);
  const text = resp.content.filter(b => b.type === "text").map(b => b.text).join("");
  if (!text) return json({ error: "empty" }, 502);
  return json({ text, model: resp.model });
}

// Whether the passcode is right, without calling the AI, so a student knows at once.
// `secret` names the house secret that matched; worker/passcode.py changes that one.
async function check(req, env) {
  const mk = missKey("check", req);
  if (throttled(mk)) return json({ error: "slow" }, 429);
  const body = await readBody(req); if (!body) return json({ error: "bad json" }, 400);
  const house = housePass(env, body.passcode);
  const row = house ? null : await classByPass(env, body.passcode);
  if (!house && !row) { missed(mk); return json({ error: "passcode" }, 401); }
  misses.delete(mk);
  if (row && !row.active) return json({ error: "off" }, 403);
  return json(house ? { ok: true, name: "", secret: house } : { ok: true, name: row.name || "" });
}

/* ---------- Claude ---------- */
const claude = (env, apiKey, maxRetries) =>
  new Anthropic({ apiKey, maxRetries, ...(env.ANTHROPIC_BASE_URL ? { baseURL: env.ANTHROPIC_BASE_URL } : {}) });
function upstreamError(e) {
  if (e?.status === 402 || /credit balance/i.test(e?.message || "")) return "credit";
  if (e?.status === 401 || e?.status === 403) return "key";
  return "upstream";
}
// Looking up the model costs nothing, so it is how a teacher's key is tested: it proves the
// key works and may use the model this site records. Returns "" or an error code.
async function testKey(env, key) {
  try { await claude(env, key, 1).models.retrieve(env.MODEL); return ""; }
  catch (e) {
    if (e?.status === 401 || e?.status === 403) return "key-rejected";
    if (e?.status === 404) return "key-model";
    return "key-unchecked";
  }
}
const KEY_SHAPE = /^sk-ant-(?!admin)[\w-]{10,}$/;

/* ---------- teacher classes ---------- */
async function readBody(req) {
  try { const b = await req.json(); return b && typeof b === "object" ? b : null; } catch { return null; }
}
const dailyCap = env => parseInt(env.DAILY_CAP || "1500", 10);
const sessionCap = env => parseInt(env.SESSION_CAP || "80", 10);
// "" when the passcode may be used by the class `id` (or by a new class, id null).
async function passProblem(env, p, id) {
  if (normPass(p).length < 6) return "passcode-short";
  if (housePass(env, p)) return "passcode-taken";
  const other = await classByPass(env, p);
  return other && other.id !== id ? "passcode-taken" : "";
}

async function createClass(req, env) {
  const ip = req.headers.get("CF-Connecting-IP") || "";
  if (createdLately(ip).length >= 10) return json({ error: "slow" }, 429);
  const mk = missKey("create", req);
  if (throttled(mk)) return json({ error: "slow" }, 429);
  const body = await readBody(req); if (!body) return json({ error: "bad json" }, 400);
  const key = clip(body.key, 300), passcode = clip(body.passcode, 80), name = clip(body.name, 80);
  if (!KEY_SHAPE.test(key)) return json({ error: "key-format" }, 400);
  const bad = await passProblem(env, passcode, null);
  if (bad) { missed(mk); return json({ error: bad }, bad === "passcode-taken" ? 409 : 400); }
  const keyBad = await testKey(env, key);
  if (keyBad) { missed(mk); return json({ error: keyBad }, 400); }
  createdLately(ip).push(Date.now());
  const code = newTeacherCode(), id = crypto.randomUUID();
  try {
    await env.DB.prepare(
      "INSERT INTO classes (id, pass_hash, teacher_hash, pass_enc, key_enc, name, active, uses, created) VALUES (?, ?, ?, ?, ?, ?, 1, 0, ?)"
    ).bind(id, await passHash(env, passcode), await teacherHash(env, code), await seal(env, passcode),
           await seal(env, key), name, new Date().toISOString()).run();
  } catch { return json({ error: "passcode-taken" }, 409); }
  return json({ ok: true, teacherCode: code, passcode, name });
}

async function manageClass(req, env) {
  const mk = missKey("manage", req);
  if (throttled(mk)) return json({ error: "slow" }, 429);
  const body = await readBody(req); if (!body) return json({ error: "bad json" }, 400);
  const row = await env.DB.prepare("SELECT * FROM classes WHERE teacher_hash = ?").bind(await teacherHash(env, body.teacherCode)).first();
  if (!row) { missed(mk); return json({ error: "teacher-code" }, 401); }
  misses.delete(mk);
  const a = body.action;
  if (a === "on" || a === "off") {
    await env.DB.prepare("UPDATE classes SET active = ? WHERE id = ?").bind(a === "on" ? 1 : 0, row.id).run();
  } else if (a === "passcode") {
    const p = clip(body.passcode, 80), bad = await passProblem(env, p, row.id);
    if (bad) return json({ error: bad }, bad === "passcode-taken" ? 409 : 400);
    await env.DB.prepare("UPDATE classes SET pass_hash = ?, pass_enc = ? WHERE id = ?").bind(await passHash(env, p), await seal(env, p), row.id).run();
  } else if (a === "key") {
    const key = clip(body.key, 300);
    if (!KEY_SHAPE.test(key)) return json({ error: "key-format" }, 400);
    const keyBad = await testKey(env, key); if (keyBad) return json({ error: keyBad }, 400);
    await env.DB.prepare("UPDATE classes SET key_enc = ? WHERE id = ?").bind(await seal(env, key), row.id).run();
  } else if (a === "delete") {
    await env.DB.prepare("DELETE FROM classes WHERE id = ?").bind(row.id).run();
    return json({ ok: true, deleted: true });
  } else if (a !== "status") return json({ error: "action" }, 400);
  const now = await env.DB.prepare("SELECT * FROM classes WHERE id = ?").bind(row.id).first();
  const today = await env.DB.prepare("SELECT n FROM counts WHERE day = ? AND k = ?").bind(localDay(), "class:" + row.id).first();
  return json({ ok: true, name: now.name, passcode: await open(env, now.pass_enc), active: !!now.active,
                questions: now.uses || 0, today: today ? today.n : 0, dailyCap: dailyCap(env) });
}

export default {
  async fetch(req, env) {
    const h = cors(env, req);
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: h });
    const path = new URL(req.url).pathname;
    let r;
    if (req.method === "POST" && path === "/chat") r = await chat(req, env);
    else if (req.method === "POST" && path === "/check") r = await check(req, env);
    else if (req.method === "POST" && path.startsWith("/class/") && !classesOn(env)) r = json({ error: "classes-off" }, 503);
    else if (req.method === "POST" && path === "/class/create") r = await createClass(req, env);
    else if (req.method === "POST" && path === "/class/manage") r = await manageClass(req, env);
    else if (req.method === "GET" && path === "/health") r = json({ ok: true, model: env.MODEL, classes: classesOn(env) });
    else r = json({ error: "not found" }, 404);
    for (const [k, v] of Object.entries(h)) r.headers.set(k, v);
    return r;
  },
};
