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

   Everything worked out here is recorded. A calculator whose use went
   unrecorded would make the session file quietly incomplete again -- the page
   would know the student computed something and the file would not -- which is
   the failure this whole instrument is built against. It is kept out of
   S.turns on purpose: the turns are the conversation, and dropping tool use
   among them would put the turn counts and the words-per-speaker ratio wrong
   in exactly the way tombstones were designed to avoid. */
const Calculator = (() => {
  let host = null, tr = k => k, onUse = () => {}, built = false, deg = false;
  let pane = "calc", win = null, cv = null, ctx = null;
  let history = [], ans = 0;
  const RESET = { x0: -6.5, x1: 6.5, y0: -3, y1: 3 };
  const $ = s => host.querySelector(s);

  function show(n){
    if(!isFinite(n)) return n > 0 ? "∞" : (n < 0 ? "−∞" : "—");
    if(Number.isInteger(n) && Math.abs(n) < 1e15) return String(n);
    const a = Math.abs(n);
    if(a !== 0 && (a < 1e-6 || a >= 1e12)) return n.toExponential(6);
    return parseFloat(n.toPrecision(12)).toString();
  }
  const esc = t => String(t).replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

  /* One key changes with the pane. In Calculate the useful thing is the last
     answer; in Graph and Table it is the variable. Neither means anything in
     the other place, so the key says whichever one applies. */
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
          <button type="button" data-deg="0" class="on">RAD</button><button type="button" data-deg="1">DEG</button>
        </span>
        <button type="button" class="cal-x" id="cal-close" aria-label="${tr("calcclose")}" title="${tr("calcclose")}">✕</button>
      </div>
      <div class="cal-tabs" id="cal-tabs">
        <button type="button" data-pane="calc" class="on">${tr("calctab")}</button>
        <button type="button" data-pane="graph">${tr("calcgraph")}</button>
        <button type="button" data-pane="table">${tr("calctable")}</button>
      </div>

      <div class="cal-body" id="cal-body">
        <div class="cal-pane on" data-pane="calc">
          <div class="cal-hist" id="cal-hist"></div>
        </div>
        <div class="cal-pane" data-pane="graph">
          <canvas id="cal-cv"></canvas>
          <div class="cal-wrow">
            <button type="button" data-zoom="0.5">+</button><button type="button" data-zoom="2">−</button>
            <button type="button" data-zoom="reset">${tr("calcreset")}</button>
            <span class="cal-sp"></span><span class="cal-rng" id="cal-rng"></span>
          </div>
        </div>
        <div class="cal-pane" data-pane="table">
          <div class="cal-two">
            <div class="cal-entry"><label>${tr("calcfrom")}</label><input id="cal-from" value="0" autocomplete="off"></div>
            <div class="cal-entry"><label>${tr("calcstep")}</label><input id="cal-step" value="0.1" autocomplete="off"></div>
          </div>
          <div class="cal-tbl" id="cal-tbl"></div>
        </div>
      </div>

      <div class="cal-inputs">
        <div class="cal-line on" data-for="calc"><span class="cal-caret">&rsaquo;</span>
          <input id="cal-in" autocomplete="off" spellcheck="false" placeholder="0.2 - 0.2^3/3!">
          <span class="cal-live" id="cal-live"></span></div>
        <div class="cal-line" data-for="graph"><label>y =</label>
          <input id="cal-gin" autocomplete="off" spellcheck="false" placeholder="sin(x)"></div>
        <div class="cal-line" data-for="table"><label>f(x) =</label>
          <input id="cal-tin" autocomplete="off" spellcheck="false" placeholder="sin(x) - x"></div>
      </div>

      <div class="cal-pad" id="cal-pad">${
        KEYS.map(([k, label, cls]) =>
          `<button type="button" class="${cls}" data-k="${k.replace(/"/g, "&quot;")}">${label}</button>`).join("")
      }</div>`;

    win = Object.assign({}, RESET);
    cv = $("#cal-cv"); ctx = cv.getContext("2d");

    $("#cal-angle").onclick = e => {
      const b = e.target.closest("button"); if(!b) return;
      deg = b.dataset.deg === "1";
      [...$("#cal-angle").children].forEach(x => x.classList.toggle("on", x === b));
      if(pane === "graph") graph();
      if(pane === "table") table();
    };
    $("#cal-tabs").onclick = e => {
      const b = e.target.closest("button"); if(!b) return;
      setPane(b.dataset.pane);
    };
    host.querySelectorAll(".cal-line input, .cal-two input").forEach(i => {
      i.addEventListener("input", () => live());
      i.addEventListener("keydown", e => { if(e.key === "Enter"){ e.preventDefault(); commit(); } });
    });
    $("#cal-pad").onclick = e => {
      const b = e.target.closest("button"); if(!b) return;
      const t = inputFor(pane);
      let k = b.dataset.k;
      if(k === "@clear"){ t.value = ""; }
      else if(k === "@del"){
        const p = t.selectionStart;
        if(p > 0){ t.value = t.value.slice(0, p - 1) + t.value.slice(t.selectionEnd); t.setSelectionRange(p - 1, p - 1); }
      }
      else if(k === "@go"){ commit(); t.focus(); return; }
      else {
        if(k === "@var") k = pane === "calc" ? "ANS" : "x";
        const s = t.selectionStart, e2 = t.selectionEnd;
        t.value = t.value.slice(0, s) + k + t.value.slice(e2);
        t.setSelectionRange(s + k.length, s + k.length);
      }
      t.focus(); live();
    };
    $(".cal-wrow").onclick = e => {
      const b = e.target.closest("button"); if(!b) return;
      if(b.dataset.zoom === "reset") win = Object.assign({}, RESET);
      else {
        const k = parseFloat(b.dataset.zoom);
        const cx = (win.x0 + win.x1) / 2, cy = (win.y0 + win.y1) / 2;
        const hw = (win.x1 - win.x0) / 2 * k, hh = (win.y1 - win.y0) / 2 * k;
        win = { x0: cx - hw, x1: cx + hw, y0: cy - hh, y1: cy + hh };
      }
      graph();
    };
    let drag = null;
    cv.addEventListener("pointerdown", e => { drag = { x: e.clientX, y: e.clientY, w: Object.assign({}, win) }; cv.setPointerCapture(e.pointerId); });
    cv.addEventListener("pointermove", e => {
      if(!drag) return;
      const r = cv.getBoundingClientRect();
      const dx = (e.clientX - drag.x) / r.width * (drag.w.x1 - drag.w.x0);
      const dy = (e.clientY - drag.y) / r.height * (drag.w.y1 - drag.w.y0);
      win = { x0: drag.w.x0 - dx, x1: drag.w.x1 - dx, y0: drag.w.y0 + dy, y1: drag.w.y1 + dy };
      graph();
    });
    cv.addEventListener("pointerup", () => drag = null);
    $("#cal-close").onclick = () => api.close();
    built = true;
    setPane("calc");
  }

  function setPane(p){
    pane = p;
    [...$("#cal-tabs").children].forEach(x => x.classList.toggle("on", x.dataset.pane === p));
    host.querySelectorAll(".cal-pane").forEach(el => el.classList.toggle("on", el.dataset.pane === p));
    host.querySelectorAll(".cal-line").forEach(el => el.classList.toggle("on", el.dataset.for === p));
    const varKey = host.querySelector('[data-k="@var"]');
    if(varKey) varKey.textContent = p === "calc" ? "ANS" : "x";
    if(p === "graph") requestAnimationFrame(graph);
    if(p === "table") table();
  }

  const ink = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

  /* ---- calculate, as a running tape ----
     Entries stay on screen and ANS carries the last result forward, so a
     student can build on what they just worked out instead of copying a number
     back in by hand -- the way the calculator they already know behaves. */
  function drawHistory(){
    const h = $("#cal-hist");
    h.innerHTML = history.map(e => e.err
      ? `<div class="cal-h err"><div class="cal-he">${esc(e.expr)}</div><div class="cal-hr">${esc(e.err)}</div></div>`
      : `<div class="cal-h"><div class="cal-he">${esc(e.expr)}</div><div class="cal-hr">${esc(show(e.result))}</div></div>`
    ).join("");
    $("#cal-body").scrollTop = $("#cal-body").scrollHeight;
  }

  function commit(){
    const t = inputFor(pane), src = t.value.trim();
    if(!src) return;
    if(pane === "calc"){
      try {
        const v = Calc.eval(src, { ANS: ans, ans: ans }, deg);
        history.push({ expr: src, result: v });
        ans = v;
        t.value = "";
        onUse({ kind: "evaluate", expr: src, result: v, deg });
      } catch(err){
        /* An attempt that did not parse is still an attempt. Recording only the
           ones that worked would make the file a record of what succeeded
           rather than of what the student did, and where a student got stuck is
           worth as much as where they did not. The input is left alone so it
           can be corrected and tried again. */
        history.push({ expr: src, err: err.message });
        onUse({ kind: "evaluate", expr: src, error: err.message, deg });
      }
      drawHistory();
      $("#cal-live").textContent = "";
      return;
    }
    /* Same for a function that will not compile: it is recorded as attempted,
       with what went wrong, rather than as though nothing was asked for. */
    let error = null;
    try { Calc.compile(src); } catch(e){ error = e.message; }
    const note = error ? { error } : {};
    if(pane === "graph"){ graph(); onUse(Object.assign({ kind: "graph", expr: src, deg }, note)); }
    if(pane === "table"){ table(); onUse(Object.assign({ kind: "table", expr: src, deg,
                            from: parseFloat($("#cal-from").value),
                            step: parseFloat($("#cal-step").value) }, note)); }
  }

  /* A quiet preview under the input while typing, so the tape only ever holds
     things the student meant to keep. */
  function live(){
    if(pane === "graph"){ graph(); return; }
    if(pane === "table"){ table(); return; }
    const src = $("#cal-in").value.trim(), out = $("#cal-live");
    if(!src){ out.textContent = ""; return; }
    try { out.textContent = show(Calc.eval(src, { ANS: ans, ans: ans }, deg)); out.classList.remove("err"); }
    catch(e){ out.textContent = ""; }
  }

  function graph(){
    const r = cv.getBoundingClientRect(), d = window.devicePixelRatio || 1;
    if(!r.width) return;
    cv.width = Math.round(r.width * d); cv.height = Math.round(r.height * d);
    ctx.setTransform(d, 0, 0, d, 0, 0);
    const w = r.width, h = r.height;
    const X = x => (x - win.x0) / (win.x1 - win.x0) * w;
    const Y = y => h - (y - win.y0) / (win.y1 - win.y0) * h;
    ctx.clearRect(0, 0, w, h);
    const st = (span, n) => { const raw = span / n, p = Math.pow(10, Math.floor(Math.log10(raw))), q = raw / p;
                              return (q < 1.5 ? 1 : q < 3 ? 2 : q < 7 ? 5 : 10) * p; };
    const sx = st(win.x1 - win.x0, 8), sy = st(win.y1 - win.y0, 5);
    ctx.lineWidth = 1; ctx.strokeStyle = ink("--rule"); ctx.beginPath();
    for(let x = Math.ceil(win.x0 / sx) * sx; x <= win.x1; x += sx){ ctx.moveTo(X(x), 0); ctx.lineTo(X(x), h); }
    for(let y = Math.ceil(win.y0 / sy) * sy; y <= win.y1; y += sy){ ctx.moveTo(0, Y(y)); ctx.lineTo(w, Y(y)); }
    ctx.stroke();
    ctx.strokeStyle = ink("--muted"); ctx.beginPath();
    if(win.y0 < 0 && win.y1 > 0){ ctx.moveTo(0, Y(0)); ctx.lineTo(w, Y(0)); }
    if(win.x0 < 0 && win.x1 > 0){ ctx.moveTo(X(0), 0); ctx.lineTo(X(0), h); }
    ctx.stroke();
    $("#cal-rng").textContent = `x [${show(win.x0)}, ${show(win.x1)}]`;
    const src = ($("#cal-gin").value || "").trim();
    if(!src) return;
    let f; try { f = Calc.fn(src, deg); } catch(e){ return; }
    ctx.strokeStyle = ink("--ai") || "#2f5d6b"; ctx.lineWidth = 1.8; ctx.beginPath();
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
  }

  function table(){
    const src = ($("#cal-tin").value || "").trim(), h = $("#cal-tbl");
    if(!src){ h.innerHTML = ""; return; }
    const from = parseFloat($("#cal-from").value), by = parseFloat($("#cal-step").value);
    if(!isFinite(from) || !isFinite(by) || by === 0){ h.innerHTML = ""; return; }
    let f;
    try { f = Calc.fn(src, deg); }
    catch(e){ h.innerHTML = `<p class="cal-err">${esc(e.message)}</p>`; return; }
    let rows = "";
    for(let i = 0; i < 20; i++){
      const x = from + i * by, y = f(x);
      rows += `<tr><td>${show(x)}</td><td>${isFinite(y) ? show(y) : "—"}</td></tr>`;
    }
    h.innerHTML = `<table><thead><tr><th>x</th><th>f(x)</th></tr></thead><tbody>${rows}</tbody></table>`;
  }

  const api = {
    mount(opts){ host = opts.host; tr = opts.tr || tr; onUse = opts.onUse || onUse; },
    open(){
      if(!built) build();
      host.classList.add("open");
      document.body.classList.add("cal-open");
      if(pane === "graph") requestAnimationFrame(graph);
      const t = inputFor(pane);
      if(t && window.matchMedia("(min-width:760px)").matches) t.focus();
    },
    close(){ host.classList.remove("open"); document.body.classList.remove("cal-open"); if(api.onclose) api.onclose(); },
    toggle(){ host.classList.contains("open") ? api.close() : api.open(); },
    isOpen(){ return host.classList.contains("open"); },
    redraw(){ if(built && pane === "graph") graph(); },
  };
  return api;
})();
