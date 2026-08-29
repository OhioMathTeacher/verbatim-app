/* ---------- drawing a turn ----------
   Inlined into both the activity and the reader by make_session_capture.py, so
   a transcript read afterwards looks like what the student saw. Returns HTML.

   The recorded turn is never touched. This builds a view of the text; the JSON
   the student hands in still holds the characters the model actually sent.

   Two passes, mathematics first. TeX is lifted out and replaced by a sentinel
   before any Markdown is looked for, because the two languages collide badly:
   `x_1` is a subscript, not an underline, and `\frac{a}{b}` is full of braces
   Markdown would rather not see. Putting the mathematics beyond reach first
   means the Markdown pass only ever sees prose. */

const RT_OPEN = "", RT_CLOSE = "";

const RT_MATH = /\$\$([\s\S]+?)\$\$|\\\[([\s\S]+?)\\\]|\$(?!\s)([^\n$]+?)(?<!\s)\$|\\\(([\s\S]+?)\\\)/g;

function rtEsc(s){
  return String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
}

/* Mathematics out, sentinels in. Returns the prose and the drawn expressions
   separately so nothing downstream can mistake one for the other. */
function rtLiftMath(text){
  const drawn = [];
  let work = "", last = 0, m;
  RT_MATH.lastIndex = 0;
  while((m = RT_MATH.exec(text))){
    work += text.slice(last, m.index);
    const display = m[1] != null || m[2] != null;
    const tex = m[1] ?? m[2] ?? m[3] ?? m[4];
    let html;
    try {
      if(typeof temml === "undefined") throw new Error("no renderer");
      html = `<span class="math${display ? " math-display" : ""}">`
           + temml.renderToString(tex, { displayMode: display, throwOnError: true })
           + `</span>`;
    } catch(e){
      /* Unparseable TeX is shown as the characters that were recorded. A student
         reading back their session should never find something simply gone. */
      html = rtEsc(m[0]);
    }
    work += RT_OPEN + drawn.push(html) + RT_CLOSE;   // push returns the new length, so ids start at 1
    last = m.index + m[0].length;
  }
  return { work: work + text.slice(last), drawn };
}

/* Inline Markdown, on prose that has already had its mathematics removed.

   Italics are stricter than CommonMark on purpose. CommonMark reads `2*3*4` as
   an emphasised 3, which in a mathematics transcript quietly eats two
   multiplication signs. So an opening `*` must begin the line or follow a
   space or an opening bracket, and the closing `*` must end the line or be
   followed by a space or punctuation. `*Hint:*` is emphasis; `2*3*4` is a
   product and is left alone.

   `_` is not an emphasis marker here at all -- outside the dollars it is far
   more often a subscript someone forgot to wrap. */
function rtInline(s, drawn){
  return rtEsc(s)
    .replace(/\*\*(?=\S)([\s\S]*?\S)\*\*/g, (_, t) => `<strong>${t}</strong>`)
    .replace(/(^|[\s(\[{"'\u2014\u2013])\*(?=\S)([^*\n]*?\S)\*(?=$|[\s.,;:!?)\]}"'\u2014\u2013])/g,
             (_, pre, t) => `${pre}<em>${t}</em>`)
    .replace(/`([^`\n]+)`/g, (_, t) => `<code>${t}</code>`)
    .replace(new RegExp(RT_OPEN + "(\\d+)" + RT_CLOSE, "g"), (_, i) => drawn[i - 1]);
}

const RT_RULE   = /^\s{0,3}(?:[-*_]\s*){3,}$/;
const RT_HEAD   = /^\s{0,3}(#{1,6})\s+(.*)$/;
const RT_UL     = /^\s{0,3}[-*+]\s+(.*)$/;
const RT_OL     = /^\s{0,3}\d+[.)]\s+(.*)$/;
const RT_QUOTE  = /^\s{0,3}>\s?(.*)$/;
const RT_ROW    = /\|/;
const RT_DIVIDE = /^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$/;

const rtCells = line => line.replace(/^\s*\|/, "").replace(/\|\s*$/, "").split("|").map(c => c.trim());

/* Block structure. Deliberately flat -- no nested lists, no fenced code. The
   reply rules cap a turn at sixty words; anything needing more structure than
   this is a turn that broke the rules, and it is still readable as prose. */
function renderRich(text){
  const { work, drawn } = rtLiftMath(String(text ?? ""));
  const lines = work.split("\n");
  const md = s => rtInline(s, drawn);
  let out = "", para = [];

  const flush = () => {
    if(para.length) out += `<p>${para.map(md).join("<br>")}</p>`;
    para = [];
  };

  for(let i = 0; i < lines.length; i++){
    const line = lines[i];

    if(!line.trim()){ flush(); continue; }

    if(RT_RULE.test(line)){ flush(); out += "<hr>"; continue; }

    const h = RT_HEAD.exec(line);
    if(h){ flush(); out += `<p class="mdh">${md(h[2])}</p>`; continue; }

    // A table is a row followed by a divider. Checked before lists, because a
    // divider row is also three dashes and would otherwise read as a rule.
    if(RT_ROW.test(line) && i + 1 < lines.length && RT_DIVIDE.test(lines[i + 1]) && RT_ROW.test(lines[i + 1])){
      flush();
      const head = rtCells(line);
      let body = [], j = i + 2;
      while(j < lines.length && lines[j].trim() && RT_ROW.test(lines[j])) body.push(rtCells(lines[j++]));
      out += `<div class="mdtw"><table class="mdt"><thead><tr>`
           + head.map(c => `<th>${md(c)}</th>`).join("")
           + `</tr></thead><tbody>`
           + body.map(r => `<tr>${r.map(c => `<td>${md(c)}</td>`).join("")}</tr>`).join("")
           + `</tbody></table></div>`;
      i = j - 1;
      continue;
    }

    for(const [re, tag] of [[RT_UL, "ul"], [RT_OL, "ol"]]){
      const first = re.exec(line);
      if(!first) continue;
      flush();
      const items = [first[1]];
      let j = i + 1, mm;
      while(j < lines.length && (mm = re.exec(lines[j]))){ items.push(mm[1]); j++; }
      out += `<${tag}>` + items.map(t => `<li>${md(t)}</li>`).join("") + `</${tag}>`;
      i = j - 1;
      break;
    }
    if(RT_UL.test(line) || RT_OL.test(line)) continue;

    const q = RT_QUOTE.exec(line);
    if(q){ flush(); out += `<blockquote>${md(q[1])}</blockquote>`; continue; }

    para.push(line);
  }
  flush();
  return out;
}

/* The activity builds its turns as DOM. This is the only place innerHTML is
   used, and only on HTML this file produced itself: prose was escaped by
   rtEsc, and the mathematics is Temml's own MathML. */
function rtBody(text){
  const b = document.createElement("div");
  b.className = "rt";
  b.innerHTML = renderRich(text);
  return b;
}
