/* ===== calculator engine =====================================================
   Hand-rolled on purpose. It is small enough that a dependency would cost more
   than it saves, it has no licence to carry, and two things here are decisions
   rather than defaults -- degrees, and implicit multiplication -- which is
   exactly the kind of thing a general-purpose library gets to choose for you.

   Lift this block whole. It touches no DOM and returns plain numbers.
   ========================================================================== */
const Calc = (() => {

  const CONSTANTS = { pi: Math.PI, "π": Math.PI, e: Math.E, tau: 2 * Math.PI };

  /* Angle-aware trig. On a calculator the mode is part of the answer, not a
     preference: sin(30) is 0.5 or -0.988 depending on it, and both are right.
     Activity 1 turns on students noticing that sin θ ≈ θ holds in radians and
     not in degrees, so the mode is passed in explicitly rather than read from
     somewhere far away. */
  const FUNCS = {
    sin:  (x, d) => Math.sin(d ? x * Math.PI / 180 : x),
    cos:  (x, d) => Math.cos(d ? x * Math.PI / 180 : x),
    tan:  (x, d) => Math.tan(d ? x * Math.PI / 180 : x),
    asin: (x, d) => { const r = Math.asin(x); return d ? r * 180 / Math.PI : r; },
    acos: (x, d) => { const r = Math.acos(x); return d ? r * 180 / Math.PI : r; },
    atan: (x, d) => { const r = Math.atan(x); return d ? r * 180 / Math.PI : r; },
    sqrt: x => Math.sqrt(x),  "√": x => Math.sqrt(x),
    abs: Math.abs, ln: Math.log, log: Math.log10, exp: Math.exp,
    floor: Math.floor, ceil: Math.ceil, round: Math.round,
  };
  const ARITY2 = { min: Math.min, max: Math.max, mod: (a, b) => a % b };

  const isDigit = c => c >= "0" && c <= "9";
  const isName  = c => /[A-Za-zπ√_]/.test(c);

  function tokenize(src){
    const out = [];
    let i = 0;
    while(i < src.length){
      const c = src[i];
      if(c === " " || c === "\t"){ i++; continue; }
      if(isDigit(c) || (c === "." && isDigit(src[i+1]))){
        let j = i;
        while(j < src.length && (isDigit(src[j]) || src[j] === ".")) j++;
        const text = src.slice(i, j);
        if((text.match(/\./g) || []).length > 1) throw new Error(`"${text}" has two decimal points`);
        out.push({ t: "num", v: parseFloat(text) });
        i = j; continue;
      }
      if(isName(c)){
        let j = i;
        while(j < src.length && (isName(src[j]) || isDigit(src[j]))) j++;
        out.push({ t: "name", v: src.slice(i, j) });
        i = j; continue;
      }
      if("+-*/^%(),!".includes(c)){ out.push({ t: c }); i++; continue; }
      if(c === "×"){ out.push({ t: "*" }); i++; continue; }
      if(c === "÷"){ out.push({ t: "/" }); i++; continue; }
      if(c === "−"){ out.push({ t: "-" }); i++; continue; }
      throw new Error(`I do not know what to do with "${c}"`);
    }
    return out;
  }

  /* Precedence climbing. Two things worth stating out loud:

     -2^2 is -4, because the minus is applied to the power and not the other way
     round, which is what every textbook means by it.

     2^3^2 is 512, not 64: powers group to the right.

     Implicit multiplication -- 2x, 3(x+1), 2sin(x) -- binds exactly as loosely
     as a written × does. So 1/2x reads as (1/2)·x. That is a real fork in the
     road and calculators disagree about it; this one follows the plain
     left-to-right reading, which is the one that matches how the expression
     was typed. */
  function parse(tokens){
    let p = 0;
    const peek = () => tokens[p];
    const eat  = t => { if(!tokens[p] || tokens[p].t !== t) throw new Error(`expected ${t}`); return tokens[p++]; };

    function primary(){
      const tk = peek();
      if(!tk) throw new Error("the expression stops early");
      if(tk.t === "num"){ p++; return { k: "num", v: tk.v }; }
      if(tk.t === "-"){ p++; return { k: "neg", a: unary() }; }
      if(tk.t === "+"){ p++; return unary(); }
      if(tk.t === "("){
        p++; const inner = expr(0); eat(")");
        return inner;
      }
      if(tk.t === "name"){
        p++;
        const name = tk.v;
        if(peek() && peek().t === "("){
          p++;
          const args = [expr(0)];
          while(peek() && peek().t === ","){ p++; args.push(expr(0)); }
          eat(")");
          return { k: "call", name, args };
        }
        // sqrt9 and sin x are written often enough to be worth accepting
        if(FUNCS[name] && peek() && (peek().t === "num" || peek().t === "name")){
          return { k: "call", name, args: [unary()] };
        }
        return { k: "var", name };
      }
      throw new Error("I could not read that");
    }

    function postfix(){
      let node = primary();
      while(peek() && peek().t === "!"){ p++; node = { k: "fact", a: node }; }
      return node;
    }

    function unary(){
      // a power binds tighter than the minus in front of it: -2^2 is -4
      let node = postfix();
      if(peek() && peek().t === "^"){ p++; node = { k: "pow", a: node, b: unary() }; }
      return node;
    }

    const BIN = { "+": 1, "-": 1, "*": 2, "/": 2, "%": 2 };

    function expr(min){
      let left = unary();
      for(;;){
        const tk = peek();
        if(!tk) break;
        // implicit multiplication: a value or ( straight after a value
        if(tk.t === "num" || tk.t === "name" || tk.t === "("){
          if(2 < min) break;
          const right = unary();
          left = { k: "bin", op: "*", a: left, b: right };
          continue;
        }
        const prec = BIN[tk.t];
        if(prec == null || prec < min) break;
        p++;
        const right = expr(prec + 1);
        left = { k: "bin", op: tk.t, a: left, b: right };
      }
      return left;
    }

    const tree = expr(0);
    if(p < tokens.length) throw new Error("there is something left over at the end");
    return tree;
  }

  function factorial(n){
    if(n < 0 || Math.floor(n) !== n) throw new Error("! needs a whole number that is not negative");
    if(n > 170) return Infinity;
    let r = 1;
    for(let i = 2; i <= n; i++) r *= i;
    return r;
  }

  function evaluate(node, scope, deg){
    switch(node.k){
      case "num":  return node.v;
      case "neg":  return -evaluate(node.a, scope, deg);
      case "fact": return factorial(evaluate(node.a, scope, deg));
      case "pow":  return Math.pow(evaluate(node.a, scope, deg), evaluate(node.b, scope, deg));
      case "bin": {
        const a = evaluate(node.a, scope, deg), b = evaluate(node.b, scope, deg);
        switch(node.op){
          case "+": return a + b;
          case "-": return a - b;
          case "*": return a * b;
          case "/": return a / b;
          case "%": return a % b;
        }
        break;
      }
      case "var": {
        const n = node.name;
        if(scope && n in scope) return scope[n];
        if(n in CONSTANTS) return CONSTANTS[n];
        throw new Error(`I do not know what "${n}" is`);
      }
      case "call": {
        const n = node.name;
        const args = node.args.map(a => evaluate(a, scope, deg));
        if(FUNCS[n]){
          if(args.length !== 1) throw new Error(`${n} takes one number`);
          return FUNCS[n](args[0], deg);
        }
        if(ARITY2[n]){
          if(args.length !== 2) throw new Error(`${n} takes two numbers`);
          return ARITY2[n](args[0], args[1]);
        }
        throw new Error(`I do not know a function called "${n}"`);
      }
    }
    throw new Error("I could not work that out");
  }

  const compile = src => parse(tokenize(src));

  return {
    compile,
    /* One number, or a thrown error with something a student can act on. */
    eval(src, scope, deg){ return evaluate(compile(src), scope || {}, !!deg); },
    /* A compiled expression evaluated many times, for plotting and tables.
       Returns NaN where the function has nothing to say, rather than throwing,
       so one bad sample cannot take the whole curve down. */
    fn(src, deg){
      const tree = compile(src);
      return x => { try { const v = evaluate(tree, { x, X: x }, deg); return typeof v === "number" ? v : NaN; }
                    catch(e){ return NaN; } };
    },
    names: () => Object.keys(FUNCS).concat(Object.keys(ARITY2)),
  };
})();
/* ---------- the drawer ----------
   Mounted on demand, so a student who never opens it pays nothing for it.

   All three panes are a running feed: what has been entered stays on screen,
   one after another, the newest at the bottom. Calculate keeps a tape of
   results; Graph gives each entry its own plot; Table gives each its own
   columns. The prompt to add another is at the bottom and the keypad under it,
   so a key lands in the line just above the thumb that pressed it.

   Everything entered is recorded, including what did not work, and deleting a
   line leaves a tombstone. The turns are the conversation; tool use sits beside
   them so the turn counts and the words-per-speaker ratio stay true. */
const Calculator = (() => {
  let host = null, tr = k => k, onUse = () => {}, onDrop = () => {};
  let built = false, deg = false, pane = "calc";
  let win = null, ans = 0, uid = 0, marks = true;

  const lists = { calc: [], graph: [], table: [] };
  const live = p => lists[p].filter(e => !e.gone);
  const PENS = ["--ai", "--stu", "--ok", "--warn", "--accent"];
  const RESET = { x0: -6.5, x1: 6.5, y0: -3, y1: 3 };
  const $ = s => host.querySelector(s);
  const ink = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

  function show(n){
    if(!isFinite(n)) return n > 0 ? "∞" : (n < 0 ? "−∞" : "—");
    if(Number.isInteger(n) && Math.abs(n) < 1e15) return String(n);
    const a = Math.abs(n);
    if(a !== 0 && (a < 1e-6 || a >= 1e12)) return n.toExponential(6);
    return parseFloat(n.toPrecision(12)).toString();
  }
  const esc = t => String(t).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  /* Commas at the top level separate functions, so one entry can carry a
     function and its derivative and draw them on the same axes. Inside
     brackets a comma still belongs to max(a, b), so depth is counted. */
  function splitTop(src){
    const out = []; let depth = 0, cur = "";
    for(const c of src){
      if(c === "(") depth++;
      if(c === ")") depth--;
      if(c === "," && depth === 0){ out.push(cur); cur = ""; continue; }
      cur += c;
    }
    out.push(cur);
    return out.map(t => t.trim()).filter(Boolean);
  }

  const BIN = '<svg viewBox="0 0 16 16" width="13" height="13" aria-hidden="true" fill="none"'
            + ' stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round">'
            + '<path d="M2.5 4h11M6.5 4V2.6h3V4M4 4l.7 9.1a1 1 0 0 0 1 .9h4.6a1 1 0 0 0 1-.9L12 4"/>'
            + '<path d="M6.6 6.8v4.6M9.4 6.8v4.6"/></svg>';
  const binFor = i => `<button type="button" class="cal-bin" data-drop="${i}" title="${esc(tr("calcdel"))}"`
                    + ` aria-label="${esc(tr("calcdel"))}">${BIN}</button>`;

  const KEYS = [
    ["sin(", "sin", "fn"], ["cos(", "cos", "fn"], ["tan(", "tan", "fn"], ["√(", "√", "fn"], ["@del", "⌫", "del"],
    ["π", "π", "fn"], ["@var", "x", "fn"], ["^", "^", "fn"], ["!", "!", "fn"], ["@clear", "C", "del"],
    ["7", "7", ""], ["8", "8", ""], ["9", "9", ""], ["(", "(", "op"], [")", ")", "op"],
    ["4", "4", ""], ["5", "5", ""], ["6", "6", ""], ["×", "×", "op"], ["÷", "÷", "op"],
    ["1", "1", ""], ["2", "2", ""], ["3", "3", ""], ["+", "+", "op"], ["−", "−", "op"],
    ["0", "0", ""], [".", ".", ""], ["ln(", "ln", "fn"], ["log(", "log", "fn"], ["@go", "=", "act"],
  ];
  const inputFor = p => $(`.cal-line[data-for="${p}"] input`);

  function build(){
    host.innerHTML = `
      <div class="cal-top">
        <span class="cal-name">${tr("calc")}</span>
        <span class="cal-angle" id="cal-angle">
          <button type="button" data-deg="0" class="${deg ? "" : "on"}">RAD</button><button type="button" data-deg="1" class="${deg ? "on" : ""}">DEG</button>
        </span>
        <button type="button" class="cal-x" id="cal-close" aria-label="${tr("calcclose")}" title="${tr("calcclose")}">✕</button>
      </div>
      <div class="cal-tabs" id="cal-tabs">
        <button type="button" data-pane="calc" class="on">${tr("calctab")}</button>
        <button type="button" data-pane="graph">${tr("calcgraph")}</button>
        <button type="button" data-pane="table">${tr("calctable")}</button>
      </div>
      <div class="cal-panes">
        <div class="cal-pane on" data-pane="calc"><div class="cal-feed" id="cal-cfeed"></div></div>
        <div class="cal-pane" data-pane="graph">
          <div class="cal-feed" id="cal-gfeed"></div>
          <div class="cal-wrow">
            <button type="button" data-zoom="0.5">+</button><button type="button" data-zoom="2">−</button>
            <button type="button" data-zoom="reset">${tr("calcreset")}</button>
            <button type="button" id="cal-marks" class="${marks ? "on" : ""}">${tr("calcmarks")}</button>
            <span class="cal-sp"></span><span class="cal-rng" id="cal-rng"></span>
          </div>
        </div>
        <div class="cal-pane" data-pane="table">
          <div class="cal-feed" id="cal-tfeed"></div>
          <div class="cal-wrow">
            <div class="cal-entry"><label>${tr("calcfrom")}</label><input id="cal-from" value="0" autocomplete="off"></div>
            <div class="cal-entry"><label>${tr("calcstep")}</label><input id="cal-step" value="0.1" autocomplete="off"></div>
          </div>
        </div>
      </div>
      <div class="cal-inputs">
        <div class="cal-line on" data-for="calc"><span class="cal-caret">&rsaquo;</span>
          <input id="cal-in" autocomplete="off" spellcheck="false" placeholder="${esc(tr("calcph"))}">
          <span class="cal-live" id="cal-live"></span></div>
        <div class="cal-line" data-for="graph"><label>y =</label>
          <input id="cal-gin" autocomplete="off" spellcheck="false" placeholder="${esc(tr("calcph"))}"></div>
        <div class="cal-line" data-for="table"><label>f(x) =</label>
          <input id="cal-tin" autocomplete="off" spellcheck="false" placeholder="${esc(tr("calcph"))}"></div>
      </div>
      <div class="cal-pad" id="cal-pad">${
        KEYS.map(([k, l, c]) => `<button type="button" class="${c}" data-k="${k.replace(/"/g, "&quot;")}">${l}</button>`).join("")
      }</div>`;

    win = Object.assign({}, RESET);

    $("#cal-angle").onclick = e => {
      const b = e.target.closest("button"); if(!b) return;
      deg = b.dataset.deg === "1";
      [...$("#cal-angle").children].forEach(x => x.classList.toggle("on", x === b));
      draw();
    };
    $("#cal-tabs").onclick = e => { const b = e.target.closest("button"); if(b) setPane(b.dataset.pane); };
    host.querySelectorAll(".cal-line input, .cal-wrow input").forEach(i => {
      i.addEventListener("input", () => { if(i.closest(".cal-wrow")) draw(); else preview(); });
      i.addEventListener("keydown", e => { if(e.key === "Enter"){ e.preventDefault(); commit(); } });
    });
    $(".cal-panes").onclick = e => {
      const b = e.target.closest(".cal-bin"); if(!b) return;
      drop(parseInt(b.dataset.drop, 10));
    };
    $("#cal-pad").onclick = e => {
      const b = e.target.closest("button"); if(!b) return;
      const t = inputFor(pane);
      let k = b.dataset.k;
      if(k === "@clear") t.value = "";
      else if(k === "@del"){
        const p = t.selectionStart;
        if(p > 0){ t.value = t.value.slice(0, p - 1) + t.value.slice(t.selectionEnd); t.setSelectionRange(p - 1, p - 1); }
      } else if(k === "@go"){ commit(); t.focus(); return; }
      else {
        if(k === "@var") k = pane === "calc" ? "ANS" : "x";
        const s = t.selectionStart, e2 = t.selectionEnd;
        t.value = t.value.slice(0, s) + k + t.value.slice(e2);
        t.setSelectionRange(s + k.length, s + k.length);
      }
      t.focus(); preview();
    };
    host.querySelectorAll(".cal-wrow").forEach(row => row.addEventListener("click", e => {
      const b = e.target.closest("button"); if(!b) return;
      if(b.id === "cal-marks"){ marks = !marks; b.classList.toggle("on", marks); plots(); return; }
      if(b.dataset.zoom === "reset") win = Object.assign({}, RESET);
      else if(b.dataset.zoom){
        const k = parseFloat(b.dataset.zoom);
        const cx = (win.x0 + win.x1) / 2, cy = (win.y0 + win.y1) / 2;
        const hw = (win.x1 - win.x0) / 2 * k, hh = (win.y1 - win.y0) / 2 * k;
        win = { x0: cx - hw, x1: cx + hw, y0: cy - hh, y1: cy + hh };
      }
      plots();
    }));

    /* One window for every plot in the feed, so stacked graphs can be read
       against each other; dragging or zooming any of them moves them all. */
    let drag = null;
    const feed = $("#cal-gfeed");
    feed.addEventListener("pointerdown", e => {
      const c = e.target.closest("canvas"); if(!c) return;
      drag = { x: e.clientX, y: e.clientY, w: Object.assign({}, win), c };
      c.setPointerCapture(e.pointerId);
    });
    feed.addEventListener("pointermove", e => {
      if(!drag) return;
      const r = drag.c.getBoundingClientRect();
      const dx = (e.clientX - drag.x) / r.width * (drag.w.x1 - drag.w.x0);
      const dy = (e.clientY - drag.y) / r.height * (drag.w.y1 - drag.w.y0);
      win = { x0: drag.w.x0 - dx, x1: drag.w.x1 - dx, y0: drag.w.y0 + dy, y1: drag.w.y1 + dy };
      plots();
    });
    feed.addEventListener("pointerup", () => drag = null);
    feed.addEventListener("wheel", e => {
      if(!e.target.closest("canvas")) return;
      e.preventDefault();
      const k = e.deltaY > 0 ? 1.12 : 1 / 1.12;
      const cx = (win.x0 + win.x1) / 2, cy = (win.y0 + win.y1) / 2;
      const hw = (win.x1 - win.x0) / 2 * k, hh = (win.y1 - win.y0) / 2 * k;
      win = { x0: cx - hw, x1: cx + hw, y0: cy - hh, y1: cy + hh };
      plots();
    }, { passive: false });

    $("#cal-close").onclick = () => api.close();
    built = true;
    setPane("calc");
  }

  function setPane(p){
    pane = p;
    [...$("#cal-tabs").children].forEach(x => x.classList.toggle("on", x.dataset.pane === p));
    host.querySelectorAll(".cal-pane").forEach(el => el.classList.toggle("on", el.dataset.pane === p));
    host.querySelectorAll(".cal-line").forEach(el => el.classList.toggle("on", el.dataset.for === p));
    const v = host.querySelector('[data-k="@var"]');
    if(v) v.textContent = p === "calc" ? "ANS" : "x";
    draw();
  }

  function commit(){
    const t = inputFor(pane), src = t.value.trim();
    if(!src) return;
    const id = ++uid;
    if(pane === "calc"){
      try {
        const v = Calc.eval(src, { ANS: ans, ans: ans }, deg);
        /* sqrt(-1) comes back NaN rather than throwing, and a NaN shown as a
           dash is not an answer -- worse, it becomes ANS. Infinity is left
           alone: growing without bound is worth showing. */
        if(Number.isNaN(v)) throw new Error("that has no real value");
        lists.calc.push({ id, expr: src, result: v });
        ans = v; t.value = "";
        onUse({ id, kind: "evaluate", expr: src, result: v, deg });
      } catch(err){
        lists.calc.push({ id, expr: src, err: err.message });
        onUse({ id, kind: "evaluate", expr: src, error: err.message, deg });
      }
      $("#cal-live").textContent = "";
    } else {
      const parts = splitTop(src);
      let error = null;
      for(const q of parts){ try { Calc.compile(q); } catch(e){ error = e.message; break; } }
      lists[pane].push({ id, expr: src, parts, err: error });
      if(!error) t.value = "";
      const use = { id, kind: pane, expr: src, deg };
      if(error) use.error = error;
      if(pane === "table"){ use.from = parseFloat($("#cal-from").value); use.step = parseFloat($("#cal-step").value); }
      onUse(use);
    }
    draw();
  }

  /* The last answer still standing. Deleting has to move ANS, or it goes on
     referring to a line the student can no longer see. */
  function lastResult(){
    for(let i = lists.calc.length - 1; i >= 0; i--){
      const e = lists.calc[i];
      if(!e.gone && !e.err && typeof e.result === "number") return e.result;
    }
    return 0;
  }

  function drop(id){
    const e = lists[pane].find(x => x.id === id);
    if(!e || e.gone) return;
    e.gone = true;
    if(pane === "calc") ans = lastResult();
    onDrop(id);
    draw();
    if(pane === "calc") preview();
  }

  function preview(){
    if(pane !== "calc") return;
    const src = $("#cal-in").value.trim(), out = $("#cal-live");
    if(!src){ out.textContent = ""; return; }
    try {
      const v = Calc.eval(src, { ANS: ans, ans: ans }, deg);
      out.textContent = Number.isNaN(v) ? "" : show(v);
    } catch(e){ out.textContent = ""; }
  }

  /* ---- the feeds ---- */
  function draw(){
    if(!built) return;
    if(pane === "calc") tape();
    if(pane === "graph"){ graphFeed(); plots(); }
    if(pane === "table") tableFeed();
  }

  const toBottom = sel => { const f = $(sel); f.scrollTop = f.scrollHeight; };

  function tape(){
    $("#cal-cfeed").innerHTML = lists.calc.map(e => e.gone
      ? `<div class="cal-card gone">${esc(tr("calcgone"))}</div>`
      : `<div class="cal-h${e.err ? " err" : ""}">${binFor(e.id)}`
        + `<div class="cal-he">${esc(e.expr)}</div>`
        + `<div class="cal-hr">${esc(e.err ? e.err : show(e.result))}</div></div>`).join("");
    toBottom("#cal-cfeed");
  }

  const swatch = i => `<span class="cal-sw" style="background:var(${PENS[i % PENS.length]})"></span>`;

  /* Each entry gets its own plot, one after another. A plot never stretches to
     fill whatever height is going: it keeps a fixed shape, and the feed scrolls,
     because a graph two thousand pixels tall and three hundred wide tells you
     nothing about a function. */
  function graphFeed(){
    $("#cal-gfeed").innerHTML = lists.graph.map(e => {
      if(e.gone) return `<div class="cal-card gone">${esc(tr("calcgone"))}</div>`;
      const head = `<div class="cal-cardhead">`
        + e.parts.map((q, i) => `<span class="cal-lg">${swatch(i)}<code>${esc(q)}</code></span>`).join("")
        + binFor(e.id) + `</div>`;
      const body = e.err ? `<p class="cal-err">${esc(e.err)}</p>`
                         : `<canvas data-plot="${e.id}"></canvas>`;
      return `<div class="cal-card${e.err ? " err" : ""}">${head}${body}</div>`;
    }).join("");
    toBottom("#cal-gfeed");
  }

  function plots(){
    if(!built) return;
    $("#cal-rng").textContent = `x [${show(win.x0)}, ${show(win.x1)}]`;
    host.querySelectorAll("#cal-gfeed canvas[data-plot]").forEach(cv => {
      const e = lists.graph.find(x => x.id === parseInt(cv.dataset.plot, 10));
      if(e) plot(cv, e);
    });
  }

  function plot(cv, entry){
    const r = cv.getBoundingClientRect(), d = window.devicePixelRatio || 1;
    if(!r.width || !r.height) return;
    cv.width = Math.round(r.width * d); cv.height = Math.round(r.height * d);
    const ctx = cv.getContext("2d");
    ctx.setTransform(d, 0, 0, d, 0, 0);
    const w = r.width, h = r.height;
    const X = x => (x - win.x0) / (win.x1 - win.x0) * w;
    const Y = y => h - (y - win.y0) / (win.y1 - win.y0) * h;
    ctx.clearRect(0, 0, w, h);
    const st = (span, n) => { const raw = span / n, p = Math.pow(10, Math.floor(Math.log10(raw))), q = raw / p;
                              return (q < 1.5 ? 1 : q < 3 ? 2 : q < 7 ? 5 : 10) * p; };
    const sx = st(win.x1 - win.x0, 7), sy = st(win.y1 - win.y0, 4);
    ctx.lineWidth = 1; ctx.strokeStyle = ink("--rule"); ctx.beginPath();
    for(let x = Math.ceil(win.x0 / sx) * sx; x <= win.x1; x += sx){ ctx.moveTo(X(x), 0); ctx.lineTo(X(x), h); }
    for(let y = Math.ceil(win.y0 / sy) * sy; y <= win.y1; y += sy){ ctx.moveTo(0, Y(y)); ctx.lineTo(w, Y(y)); }
    ctx.stroke();
    ctx.strokeStyle = ink("--muted"); ctx.beginPath();
    if(win.y0 < 0 && win.y1 > 0){ ctx.moveTo(0, Y(0)); ctx.lineTo(w, Y(0)); }
    if(win.x0 < 0 && win.x1 > 0){ ctx.moveTo(X(0), 0); ctx.lineTo(X(0), h); }
    ctx.stroke();

    if(marks){
      ctx.fillStyle = ink("--muted");
      ctx.font = "10px ui-monospace, monospace";
      ctx.textAlign = "center"; ctx.textBaseline = "top";
      const ay = (win.y0 < 0 && win.y1 > 0) ? Y(0) : h;
      for(let x = Math.ceil(win.x0 / sx) * sx; x <= win.x1; x += sx){
        if(Math.abs(x) < sx / 1e6) continue;
        const px = X(x);
        if(px < 14 || px > w - 14) continue;
        ctx.fillText(show(parseFloat(x.toPrecision(10))), px, Math.min(ay + 3, h - 12));
      }
      ctx.textAlign = "left"; ctx.textBaseline = "middle";
      const ax = (win.x0 < 0 && win.x1 > 0) ? X(0) : 0;
      for(let y = Math.ceil(win.y0 / sy) * sy; y <= win.y1; y += sy){
        if(Math.abs(y) < sy / 1e6) continue;
        const py = Y(y);
        if(py < 8 || py > h - 8) continue;
        ctx.fillText(show(parseFloat(y.toPrecision(10))), Math.min(ax + 4, w - 34), py);
      }
    }

    entry.parts.forEach((q, i) => {
      let f; try { f = Calc.fn(q, deg); } catch(err){ return; }
      ctx.strokeStyle = ink(PENS[i % PENS.length]) || "#2f5d6b";
      ctx.lineWidth = 1.8; ctx.beginPath();
      let pen = false, prev = null;
      const jump = (win.y1 - win.y0) * 1.5;
      for(let px = 0; px <= w; px++){
        const x = win.x0 + px / w * (win.x1 - win.x0), y = f(x);
        if(!isFinite(y) || (prev !== null && Math.abs(y - prev) > jump)){ pen = false; prev = isFinite(y) ? y : null; continue; }
        const py = Y(y);
        if(!pen){ ctx.moveTo(px, py); pen = true; } else ctx.lineTo(px, py);
        prev = y;
      }
      ctx.stroke();
    });
  }

  function tableFeed(){
    const from = parseFloat($("#cal-from").value), by = parseFloat($("#cal-step").value);
    $("#cal-tfeed").innerHTML = lists.table.map(e => {
      if(e.gone) return `<div class="cal-card gone">${esc(tr("calcgone"))}</div>`;
      const head = `<div class="cal-cardhead">`
        + e.parts.map((q, i) => `<span class="cal-lg"><span class="cal-sw plain">f${i + 1}</span><code>${esc(q)}</code></span>`).join("")
        + binFor(e.id) + `</div>`;
      if(e.err) return `<div class="cal-card err">${head}<p class="cal-err">${esc(e.err)}</p></div>`;
      if(!isFinite(from) || !isFinite(by) || by === 0) return `<div class="cal-card">${head}</div>`;
      const fs = e.parts.map(q => { try { return Calc.fn(q, deg); } catch(err){ return null; } });
      let rows = "";
      for(let i = 0; i < 12; i++){
        const x = from + i * by;
        rows += `<tr><td>${show(x)}</td>` + fs.map(f => {
          const y = f ? f(x) : NaN; return `<td>${isFinite(y) ? show(y) : "—"}</td>`;
        }).join("") + `</tr>`;
      }
      const hdr = `<tr><th>x</th>` + e.parts.map((q, i) => `<th>f${i + 1}</th>`).join("") + `</tr>`;
      return `<div class="cal-card">${head}<div class="cal-tbl">`
           + `<table><thead>${hdr}</thead><tbody>${rows}</tbody></table></div></div>`;
    }).join("");
    toBottom("#cal-tfeed");
  }

  const api = {
    mount(o){ host = o.host; tr = o.tr || tr; onUse = o.onUse || onUse; onDrop = o.onDrop || onDrop; },

    /* Put the feeds back after a reload, from the session's own record rather
       than from a second copy kept somewhere else. tool_uses already holds every
       entry, every failure and every tombstone, so it is the only thing that
       could disagree with itself -- and reading it back is what keeps a
       student's work in front of them for the whole activity rather than only
       until the page is refreshed. */
    /* The drawer is built once, with its words baked in, so switching language
       has to build it again -- otherwise the conversation turns Chinese and the
       calculator stays English. State lives outside the DOM, so only what was
       typed needs carrying across. */
    relabel(){
      if(!built) return;
      const p = pane, typed = {};
      host.querySelectorAll(".cal-line input, .cal-wrow input").forEach(i => typed[i.id] = i.value);
      build();
      for(const [id, v] of Object.entries(typed)){ const el = host.querySelector("#" + id); if(el) el.value = v; }
      setPane(p);
    },

    restore(uses){
      if(!Array.isArray(uses)) return;
      lists.calc.length = 0; lists.graph.length = 0; lists.table.length = 0;
      for(const u of uses){
        const id = typeof u.id === "number" ? u.id : ++uid;
        uid = Math.max(uid, id);
        const where = u.kind === "evaluate" ? "calc" : (u.kind === "graph" || u.kind === "table" ? u.kind : null);
        if(!where) continue;
        if(u.deleted_utc){ lists[where].push({ id, expr: "", parts: [], gone: true }); continue; }
        if(where === "calc") lists.calc.push({ id, expr: u.expr, result: u.result, err: u.error });
        else lists[where].push({ id, expr: u.expr, parts: splitTop(u.expr || ""), err: u.error });
      }
      ans = lastResult();
      if(built) draw();
    },
    open(){
      if(!built) build();
      host.classList.add("open");
      document.body.classList.add("cal-open");
      requestAnimationFrame(() => { if(pane === "graph") plots(); });
      const t = inputFor(pane);
      if(t && window.matchMedia("(min-width:760px)").matches) t.focus();
    },
    close(){ host.classList.remove("open"); document.body.classList.remove("cal-open"); if(api.onclose) api.onclose(); },
    toggle(){ host.classList.contains("open") ? api.close() : api.open(); },
    isOpen(){ return host.classList.contains("open"); },
    redraw(){ if(built && pane === "graph") plots(); },
  };
  return api;
})();
