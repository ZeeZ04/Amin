/* Amin, Jarvis mode: one full-screen voice window for the computer Amin runs on.
   Always listening for "Hey Amin" (bursts of speech go to this computer's /wake,
   silence sends nothing), then a conversation loop: listen → /transcribe (Whisper,
   Malayalam-tuned for Malayalam) → /ask (the full pipeline: documents, memory,
   knowledge packs, citations) → speak → listen. Nothing leaves this computer.
   The orb is the native Majlis Orb (apple/Sources/App/MajlisOrb.swift), on a canvas. */
"use strict";
const $ = id => document.getElementById(id);
const S = { phase: "idle", level: 0, lang: "auto", mute: false, conv: null, quiet: 0,
  stream: null, ctx: null, analyser: null, rec: null, raf: 0, mode: "off", busy: false };
try { S.lang = localStorage.getItem("amin.voice.lang") || "auto"; S.mute = localStorage.getItem("amin.voice.mute") === "1"; } catch {}
const SPEECH_RMS = 0.035, END_SILENCE_MS = 1300, NO_SPEECH_MS = 7000, MAX_TURN_MS = 30000;
const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

async function call(path, opts = {}) {
  const res = await fetch(path, { credentials: "same-origin", ...opts });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401) { $("gate").classList.add("show"); throw new Error("sign in first"); }
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : `Amin hit a problem (${res.status})`);
  return data;
}
const scriptOf = t => /[ഀ-ൿ]/.test(t) ? "ml" : /[؀-ۿ]/.test(t) ? "ar" : "en";

/* -- clock and status ------------------------------------------------------------ */
function clock() {
  const d = new Date();
  $("clock").textContent = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  $("date").textContent = d.toLocaleDateString([], { weekday: "long", day: "numeric", month: "long" });
}
setInterval(clock, 15000); clock();
function setPhase(phase, label) { S.phase = phase; $("state").textContent = label; }
function wakeUI(text, live) { $("wakeText").textContent = text; $("wakePill").classList.toggle("live", live); }

/* -- the orb ------------------------------------------------------------------------ */
const cv = $("orb"), g = cv.getContext("2d");
function drawOrb(t) {
  const w = cv.width, c = w / 2, r = w / 2;
  const active = S.phase !== "idle";
  const breathe = 0.5 + 0.5 * Math.sin(t * 2 * Math.PI / 4.0);
  const lvl = S.phase === "listening" ? S.level : 0;
  const pulse = S.phase === "speaking" ? 0.5 + 0.5 * Math.sin(t * 2 * Math.PI * 2.2) : 0;
  g.clearRect(0, 0, w, w);
  // 1. glow
  const glowR = r * (0.62 + 0.10 * lvl + 0.04 * breathe);
  const glowCol = S.phase === "speaking" ? "143,211,201" : "255,231,174";
  let grd = g.createRadialGradient(c, c, 0, c, c, glowR * 1.5);
  grd.addColorStop(0, `rgba(${glowCol},${active ? 0.28 + 0.3 * lvl : 0.12})`); grd.addColorStop(1, "rgba(0,0,0,0)");
  g.fillStyle = grd; g.fillRect(0, 0, w, w);
  // 2. the 60-tick astrolabe dial; thinking sweeps a bright arc
  for (let i = 0; i < 60; i++) {
    const a = i / 60 * 2 * Math.PI - Math.PI / 2, major = i % 5 === 0;
    let sweep = 0;
    if (S.phase === "thinking") {
      const head = ((t * 0.6) % 1) * 2 * Math.PI;
      const d = Math.abs(Math.atan2(Math.sin(a + Math.PI / 2 - head), Math.cos(a + Math.PI / 2 - head)));
      sweep = Math.max(0, 1 - d / 0.9);
    }
    const wave = S.phase === "listening" ? lvl * (0.5 + 0.5 * Math.sin(i * 0.7 + t * 6)) : 0;
    const inner = r * (major ? 0.86 : 0.89), outer = r * 0.95 + r * 0.05 * wave;
    g.strokeStyle = sweep > 0.05 ? `rgba(255,231,174,${Math.min(1, 0.45 + 0.5 * sweep)})`
      : `rgba(243,239,228,${Math.min(1, (active ? 0.45 : 0.18) + 0.4 * wave)})`;
    g.lineWidth = (major ? 2.2 : 1.2) * (w / 440);
    g.beginPath(); g.moveTo(c + Math.cos(a) * inner, c + Math.sin(a) * inner);
    g.lineTo(c + Math.cos(a) * outer, c + Math.sin(a) * outer); g.stroke();
  }
  // 3. two counter-rotating rings
  [[0.74, 0.25, [0.18, 0.06]], [0.80, -0.18, [0.02, 0.05]]].forEach(([rr, speed, dash]) => {
    g.save(); g.translate(c, c); g.rotate(active ? t * speed : 0);
    g.setLineDash(dash.map(x => x * r)); g.strokeStyle = `rgba(243,239,228,${active ? 0.55 : 0.2})`;
    g.lineWidth = 1.4 * (w / 440); g.beginPath(); g.arc(0, 0, r * rr, 0, 2 * Math.PI); g.stroke(); g.restore();
  });
  // 4. the lantern core: saffron listening, teal speaking; dims (not fades) when idle
  const coreR = r * (0.46 + 0.10 * lvl + 0.03 * breathe + 0.05 * pulse);
  const cols = S.phase === "speaking" ? ["#E8F5F2", "#8FD3C9", "#2A8C84"] : ["#FFE7AE", "#E3A72F", "#996B12"];
  grd = g.createRadialGradient(c - coreR * 0.2, c - coreR * 0.3, 2, c, c, coreR * 1.2);
  cols.forEach((col, i) => grd.addColorStop(i / 2, col));
  g.globalAlpha = active ? 1 : 0.72; g.fillStyle = grd;
  g.beginPath(); g.arc(c, c, coreR, 0, 2 * Math.PI); g.fill(); g.globalAlpha = 1;
  // 5. the door, faint, at the heart
  const d = coreR * 0.42;
  g.strokeStyle = "rgba(10,63,60,0.35)"; g.lineWidth = Math.max(1.5, d * 0.08);
  g.beginPath(); g.moveTo(c - d * 0.6, c + d); g.lineTo(c - d * 0.6, c - d * 0.1);
  g.arc(c, c - d * 0.1, d * 0.6, Math.PI, 0); g.lineTo(c + d * 0.6, c + d); g.stroke();
}
(function frame(now) { drawOrb(reduceMotion ? 0 : now / 1000); requestAnimationFrame(frame); })(0);

/* -- microphone ------------------------------------------------------------------- */
async function mic() {
  if (S.stream) return true;
  try { S.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } }); }
  catch { setPhase("idle", "Amin needs microphone permission. Allow it in the browser, then click the orb."); return false; }
  S.ctx = new AudioContext(); S.analyser = S.ctx.createAnalyser(); S.analyser.fftSize = 1024;
  S.ctx.createMediaStreamSource(S.stream).connect(S.analyser);
  return true;
}
function rms() {
  const buf = new Float32Array(S.analyser.fftSize); S.analyser.getFloatTimeDomainData(buf);
  let s = 0; for (const x of buf) s += x * x; return Math.sqrt(s / buf.length);
}
const pickType = () => ["audio/webm;codecs=opus", "audio/mp4", "audio/webm"].find(t => MediaRecorder.isTypeSupported?.(t)) || "";
function stopRec() { cancelAnimationFrame(S.raf); try { S.rec?.state === "recording" && S.rec.stop(); } catch {} }

/* -- "Hey Amin" ------------------------------------------------------------------ */
async function waitForWake() {
  if (!(await mic())) return;
  S.mode = "wake"; S.quiet = 0; S.level = 0;
  setPhase("idle", "Say “Hey Amin”"); wakeUI("Listening for “Hey Amin”", true);
  const type = pickType(); let chunks = [], since = 0, last = 0;
  const tick = () => {
    if (S.mode !== "wake") return;
    const loud = rms() > SPEECH_RMS, now = performance.now();
    if (loud && !S.rec && !S.busy) {
      chunks = []; since = now;
      S.rec = new MediaRecorder(S.stream, type ? { mimeType: type } : undefined);
      S.rec.ondataavailable = e => e.data.size && chunks.push(e.data);
      S.rec.onstop = () => checkWake(new Blob(chunks, { type: S.rec?.mimeType || type || "audio/webm" }));
      S.rec.start(200);
    }
    if (loud) last = now;
    if (S.rec?.state === "recording" && (now - last > 700 || now - since > 5000)) S.rec.stop();
    S.raf = requestAnimationFrame(tick);
  };
  S.raf = requestAnimationFrame(tick);
}
async function checkWake(blob) {
  S.rec = null;
  if (S.mode !== "wake" || blob.size < 2000) return;
  S.busy = true;
  try {
    const r = await call("/wake", { method: "POST", headers: { "Content-Type": blob.type }, body: blob });
    if (r.wake && S.mode === "wake") { stopRec(); converse(r.rest || ""); }
  } catch {} finally { S.busy = false; }
}

/* -- the conversation -------------------------------------------------------------- */
async function converse(opening = null) {
  if (!(await mic())) return;
  stopRec(); S.mode = "talk"; S.quiet = 0;
  wakeUI("In conversation", true);
  if (opening) return ask(opening);
  if (opening === "") return speak("How can I help?", listen);
  listen();
}
function listen() {
  if (S.mode !== "talk") return;
  setPhase("listening", "Listening…");
  const type = pickType(), chunks = [];
  S.rec = new MediaRecorder(S.stream, type ? { mimeType: type } : undefined);
  S.rec.ondataavailable = e => e.data.size && chunks.push(e.data);
  let spoke = false, last = 0; const started = performance.now();
  S.rec.onstop = () => {
    cancelAnimationFrame(S.raf); S.level = 0;
    if (S.mode !== "talk") return;
    if (!spoke) { if (++S.quiet >= 2) return waitForWake(); return listen(); }
    S.quiet = 0; transcribe(new Blob(chunks, { type: S.rec.mimeType || type || "audio/webm" }));
  };
  S.rec.start(250);
  const tick = () => {
    if (S.mode !== "talk" || S.rec?.state !== "recording") return;
    const l = rms(), now = performance.now();
    S.level = 0.65 * S.level + 0.35 * Math.min(1, l * 9);
    if (l > SPEECH_RMS) { spoke = true; last = now; }
    if ((spoke && now - last > END_SILENCE_MS) || (!spoke && now - started > NO_SPEECH_MS) || now - started > MAX_TURN_MS) return S.rec.stop();
    S.raf = requestAnimationFrame(tick);
  };
  S.raf = requestAnimationFrame(tick);
}
async function transcribe(blob) {
  setPhase("thinking", "Transcribing…");
  try {
    const hint = S.lang === "auto" ? "" : `?lang=${S.lang}`;
    const said = await call(`/transcribe${hint}`, { method: "POST", headers: { "Content-Type": blob.type }, body: blob });
    if (S.mode !== "talk") return;
    if (!said.text) return listen();
    ask(said.text);
  } catch (e) { setPhase("idle", e.message); setTimeout(() => S.mode === "talk" && listen(), 1500); }
}
async function ask(text) {
  $("said").textContent = text; $("said").className = scriptOf(text) === "ml" ? "ml" : "";
  $("reply").textContent = "";
  setPhase("thinking", "Thinking…");
  addHistory(text);
  let r;
  try { r = await call("/ask", { method: "POST", headers: { "Content-Type": "application/json" },
                                 body: JSON.stringify({ question: text, project: null, conversation_id: S.conv }) }); }
  catch (e) { setPhase("idle", e.message); return S.mode === "talk" ? setTimeout(listen, 1500) : null; }
  S.conv = r.conversation_id || S.conv;
  const reply = r.claims?.length ? r.claims.map(c => c.text).join(" ") : (r.refusal_reason || "");
  const clean = reply.replace(/\s*\[S\d+\]/g, "");
  $("reply").textContent = clean; $("reply").className = scriptOf(clean) === "ml" ? "ml" : "";
  showSources(r);
  speak(clean, () => (S.mode === "talk" ? listen() : null));
}
function showSources(r) {
  const order = [];
  for (const c of r.claims || []) for (const id of c.citations || []) if (!order.includes(id)) order.push(id);
  const box = $("sources");
  if (r.basis === "general" || !order.length) {
    box.innerHTML = `<span class="hint">${r.basis === "general" ? "General knowledge · not from your documents." : "No sources for this answer."}</span>`;
    return;
  }
  box.innerHTML = "";
  order.forEach((id, i) => {
    const s = r.sources?.[id] || {}; const doc = (s.doc_id || id.split("#")[0]).replace(/^(p|h|k\.[a-z0-9-]+|j\.[a-z0-9]+)\./, "");
    const row = document.createElement("div"); row.className = "src";
    row.innerHTML = `<b>${i + 1}</b><span></span>`;
    row.querySelector("span").textContent = doc;
    if (s.heading) { const sm = document.createElement("small"); sm.textContent = s.heading; row.querySelector("span").append(sm); }
    box.append(row);
  });
}
function addHistory(q) {
  const h = $("history"); if (h.querySelector(".hint")) h.innerHTML = "";
  const d = document.createElement("div"); d.className = "q" + (scriptOf(q) === "ml" ? " ml" : ""); d.textContent = q;
  h.prepend(d);
}
/* The best installed voice for the reply's language; macOS "Premium"/"Enhanced" voices first. */
function voiceFor(lang) {
  const all = speechSynthesis.getVoices().filter(v => v.lang.toLowerCase().startsWith(lang));
  return all.find(v => /premium|enhanced|neural/i.test(v.name)) || all[0];
}
function speak(text, done) {
  if (S.mute || !text) return done();
  const lang = scriptOf(text), voice = voiceFor(lang);
  if (!voice) {
    setPhase("speaking", lang === "ml" ? "No Malayalam voice on this computer yet · the answer is on screen" : "Answer on screen");
    return setTimeout(done, 3000 + text.length * 25);
  }
  const u = new SpeechSynthesisUtterance(text); u.voice = voice; u.lang = voice.lang;
  u.onend = u.onerror = () => done();
  setPhase("speaking", "Speaking…"); speechSynthesis.speak(u);
}
function stopAll() {
  speechSynthesis.cancel(); stopRec(); S.rec = null;
  if (S.mode === "talk") waitForWake();
}

/* -- controls ------------------------------------------------------------------- */
cv.onclick = () => {
  if (S.phase === "speaking") { speechSynthesis.cancel(); return; }  // interrupt; onend → listen
  if (S.mode === "talk" && S.phase === "listening") { S.rec?.stop(); return; }  // done talking
  converse();
};
document.addEventListener("keydown", e => {
  if (e.target === $("type")) return;
  if (e.code === "Space") { e.preventDefault(); cv.onclick(); }
  if (e.key === "Escape") stopAll();
});
$("type").addEventListener("keydown", e => {
  if (e.key !== "Enter" || !e.target.value.trim()) return;
  const q = e.target.value.trim(); e.target.value = "";
  stopRec(); S.mode = S.stream ? "talk" : "off"; ask(q);
});
document.querySelectorAll("[data-lang]").forEach(b => b.onclick = () => {
  S.lang = b.dataset.lang; try { localStorage.setItem("amin.voice.lang", S.lang); } catch {}
  document.querySelectorAll("[data-lang]").forEach(x => x.setAttribute("aria-pressed", x === b));
});
document.querySelectorAll("[data-lang]").forEach(x => x.setAttribute("aria-pressed", x.dataset.lang === S.lang));
function muteUI() { $("mute").setAttribute("aria-pressed", S.mute); $("mute").textContent = S.mute ? "Voice off" : "Voice on"; }
$("mute").onclick = () => { S.mute = !S.mute; try { localStorage.setItem("amin.voice.mute", S.mute ? "1" : "0"); } catch {} if (S.mute) speechSynthesis.cancel(); muteUI(); };
muteUI();
speechSynthesis.getVoices();

/* -- start: signed in? then listen for the wake word straight away -------------------- */
call("/me").then(me => {
  setPhase("idle", `Hello ${me.name}. Click the orb, or say “Hey Amin”`);
  waitForWake();
}).catch(() => {});
