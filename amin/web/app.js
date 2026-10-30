/* Amin — app logic. No framework, no build step: the page is served by the
   same Python process that answers, and must work with no network beyond it. */
"use strict";

const $ = id => document.getElementById(id);
const $$ = sel => [...document.querySelectorAll(sel)];
const esc = s => { const d = document.createElement("div"); d.textContent = s ?? ""; return d.innerHTML; };
const wide = () => matchMedia("(min-width: 760px)").matches;

async function call(path, opts = {}) {
  const res = await fetch(path, { credentials: "same-origin", ...opts });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (res.status === 401 && ME) { showAuth(); }
    const d = data.detail;
    throw new Error(typeof d === "string" ? d
      : Array.isArray(d) ? d.map(e => `${e.loc?.at(-1) ?? "input"}: ${e.msg}`).join("; ")
      : res.status >= 500 ? "Amin hit a problem on the computer it runs on. Try again in a moment." : `${res.status} ${res.statusText}`);
  }
  return data;
}
const json = method => (path, body) => call(path, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body ?? {}) });
const post = json("POST"), patch = json("PATCH");

let ME = null;

/* -- toasts & dialogs ------------------------------------------------------ */
function toast(text, bad = false) {
  const t = document.createElement("div");
  t.className = "toast" + (bad ? " bad" : ""); t.textContent = text; t.setAttribute("role", bad ? "alert" : "status");
  $("toasts").append(t);
  setTimeout(() => { t.classList.add("out"); setTimeout(() => t.remove(), 250); }, bad ? 5200 : 3200);
}
function dialog({ title, text = "", input = null, ok = "OK", danger = false, cancel = "Cancel" }) {
  const d = $("dialog");
  $("dlgTitle").textContent = title; $("dlgText").textContent = text; $("dlgText").hidden = !text;
  $("dlgInput").hidden = input === null; $("dlgInput").value = input ?? "";
  $("dlgOk").textContent = ok; $("dlgOk").className = "btn" + (danger ? " danger solid" : "");
  $("dlgCancel").textContent = cancel;
  return new Promise(resolve => {
    d.onclose = () => resolve(d.returnValue === "ok" ? (input === null ? true : $("dlgInput").value.trim()) : null);
    d.returnValue = ""; d.showModal();
    if (input !== null) { $("dlgInput").focus(); $("dlgInput").select(); }
  });
}
$("dlgInput").addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); $("dialog").close("ok"); } });

/* -- theme --------------------------------------------------------------- */
function setTheme(t) {
  if (t === "system") delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = t;
  try { t === "system" ? localStorage.removeItem("amin.theme") : localStorage.setItem("amin.theme", t); } catch {}
  $$("[data-theme-set]").forEach(b => b.setAttribute("aria-pressed", b.dataset.themeSet === t));
}
$$("[data-theme-set]").forEach(b => b.onclick = () => setTheme(b.dataset.themeSet));
setTheme(document.documentElement.dataset.theme || "system");

/* -- boot: splash on a fresh launch, then route ------------------------------- */
async function boot() {
  let first = true;
  try { first = !sessionStorage.getItem("amin.opened"); sessionStorage.setItem("amin.opened", "1"); } catch {}
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (first) $("splash").hidden = false;
  const wait = new Promise(r => setTimeout(r, !first ? 0 : reduce ? 300 : 2000));
  const [me] = await Promise.all([call("/me").catch(() => null), wait]);
  if (me) await showApp(me); else await showAuth();
  $("splash").classList.add("gone");
  setTimeout(() => $("splash").hidden = true, 500);
  call("/health").then(h => $("version").textContent = `Version ${h.version} · model ${h.answer_model}`).catch(() => {});
}

/* -- auth ------------------------------------------------------------------ */
let mode = "in", firstAccount = false;
async function showAuth() {
  ME = null; $("app").hidden = true; $("auth").hidden = false;
  const s = await call("/setup").catch(() => ({}));
  firstAccount = !!s.first_account;
  setMode(firstAccount ? "up" : "in");
  if (firstAccount) {
    $("authHeadline").textContent = "Welcome to Amin.";
    $("authLead").textContent = "Create the first account. It becomes the admin, who can invite the rest of the household.";
  }
}
function setMode(m) {
  mode = m;
  $("modeIn").setAttribute("aria-pressed", m === "in"); $("modeUp").setAttribute("aria-pressed", m === "up");
  $("authTitle").textContent = $("authGo").textContent = m === "in" ? "Sign in" : "Create account";
  $("inviteBox").hidden = m === "in" || firstAccount;
  $("nameHint").hidden = m === "in";
  $("pass").autocomplete = m === "in" ? "current-password" : "new-password";
  $("authNote").textContent = "";
}
$("modeIn").onclick = () => setMode("in");
$("modeUp").onclick = () => setMode("up");
$("authForm").onsubmit = async e => {
  e.preventDefault();
  const name = $("name").value.trim().toLowerCase(), password = $("pass").value;
  if (!name || !password) { $("authNote").textContent = "Enter your name and password."; return; }
  $("authGo").disabled = true;
  try {
    await post(mode === "in" ? "/login" : "/signup", { name, password, invite: $("invite").value.trim() || null });
    $("pass").value = ""; $("invite").value = "";
    await showApp(await call("/me"));
  } catch (err) { $("authNote").textContent = err.message; }
  finally { $("authGo").disabled = false; }
};

/* -- shell ------------------------------------------------------------------ */
const VIEWS = ["chat", "add", "projects", "settings"];
let VIEW = "chat";
async function showApp(me) {
  ME = me; $("auth").hidden = true; $("app").hidden = false;
  const initial = me.name[0].toUpperCase();
  $("avatar").textContent = $("sideAvatar").textContent = initial;
  $("meName").textContent = $("sideName").textContent = me.name;
  $("sideRole").textContent = me.admin ? "Admin" : "Member";
  $("meRole").textContent = me.admin ? "Admin · can invite people and remove household documents" : "Household member";
  $("adminBox").hidden = !me.admin;
  $("prefPrivate").checked = me.prefs.chat_private; $("prefHousehold").checked = me.prefs.chat_household;
  greet(); renderSpace(); renderTargets(); renderLibrary(); renderProjects(); loadPacks();
  await loadHistory();
  if (W.want) startWake();
}
function greet() {
  const h = new Date().getHours();
  $("greeting").textContent = `${h < 5 ? "Good evening" : h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening"}, ${ME.name}.`;
}
function go(view) {
  VIEW = view;
  for (const v of VIEWS) $(`view-${v}`).hidden = v !== view;
  $$("[data-go]").forEach(b => b.toggleAttribute("aria-current", b.dataset.go === view));
  $$("[data-go][aria-current]").forEach(b => b.setAttribute("aria-current", "page"));
  closeDrawer(); closeSource();
  if (view !== "chat") refreshMe();
  if (view === "settings") renderMemory();
  if (view === "chat" && wide()) $("question").focus({ preventScroll: true });
}
$$("[data-go]").forEach(b => b.onclick = () => go(b.dataset.go));
async function refreshMe() {
  try { ME = await call("/me"); renderSpace(); renderTargets(); renderLibrary(); renderProjects(); } catch {}
}
function openDrawer() { $("sidebar").classList.add("open"); $("drawerScrim").classList.add("open"); }
function closeDrawer() { $("sidebar").classList.remove("open"); $("drawerScrim").classList.remove("open"); }
$("openDrawer").onclick = openDrawer;
$$("[data-drawer]").forEach(b => b.onclick = openDrawer);
$("drawerScrim").onclick = closeDrawer;
$("meChip").onclick = () => go("settings");

/* -- spaces: general chat or a project ---------------------------------------- */
let SPACE = "";  // "" = general chat, else a project id
const projectById = id => (ME?.projects || []).find(p => p.id === id);
function renderSpace() {
  if (SPACE && !projectById(SPACE)) SPACE = "";
  const p = projectById(SPACE);
  $("spaceName").textContent = p ? p.name : "General chat";
  $("spaceBtn").querySelector("use").setAttribute("href", p ? "#i-folder" : "#i-globe");
  $("welcomeLead").textContent = p
    ? `Asking in “${p.name}”. Answers come from its ${p.documents.length} document${p.documents.length === 1 ? "" : "s"} first, with the passage shown.`
    : "Ask anything. When your documents hold the answer, Amin shows you the passage it came from.";
}
function menu(anchor, items) {
  closeMenu();
  const m = document.createElement("div");
  m.className = "menu"; m.setAttribute("role", "menu"); m.id = "menu";
  m.innerHTML = items.map((it, i) => it === "-" ? "<hr>" :
    `<button role="menuitemradio" aria-checked="${!!it.checked}" data-i="${i}"><svg class="i"><use href="${it.icon}"/></svg><span class="text">${esc(it.label)}${it.sub ? `<small>${esc(it.sub)}</small>` : ""}</span><svg class="i tick"><use href="#i-check"/></svg></button>`).join("");
  document.body.append(m);
  const r = anchor.getBoundingClientRect();
  m.style.top = `${r.bottom + 6}px`;
  m.style.left = `${Math.max(12, Math.min(r.left, innerWidth - m.offsetWidth - 12))}px`;
  m.querySelectorAll("button").forEach(b => b.onclick = () => { closeMenu(); items[b.dataset.i].run(); });
  m.querySelector("button")?.focus();
  setTimeout(() => document.addEventListener("pointerdown", outside), 0);
}
function outside(e) { if (!e.target.closest("#menu")) closeMenu(); }
function closeMenu() { $("menu")?.remove(); document.removeEventListener("pointerdown", outside); }
$("spaceBtn").onclick = () => menu($("spaceBtn"), [
  { icon: "#i-globe", label: "General chat", sub: "Everyday questions, plus your libraries", checked: !SPACE, run: () => switchSpace("") },
  ...(ME.projects.length ? ["-"] : []),
  ...ME.projects.map(p => ({ icon: "#i-folder", label: p.name, sub: p.role === "member" ? `Shared by ${p.owner}` : `${p.documents.length} document${p.documents.length === 1 ? "" : "s"}`, checked: SPACE === p.id, run: () => switchSpace(p.id) })),
]);
function switchSpace(id) { if (id !== SPACE) { SPACE = id; newChat(); } renderSpace(); }

/* -- history ------------------------------------------------------------------ */
let CONV = null;  // current conversation id
let CONVS = [];
async function loadHistory() {
  try { CONVS = await call("/conversations"); } catch { CONVS = []; }
  renderHistory();
}
function when(ts) {
  const d = new Date(ts * 1000), now = new Date();
  const days = Math.floor((new Date(now.toDateString()) - new Date(d.toDateString())) / 864e5);
  return days === 0 ? d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : days === 1 ? "Yesterday" : days < 7 ? d.toLocaleDateString([], { weekday: "long" }) : d.toLocaleDateString([], { day: "numeric", month: "short" });
}
function renderHistory() {
  $("history").innerHTML = CONVS.length ? CONVS.map(c => {
    const p = c.project && projectById(c.project);
    return `<button data-c="${esc(c.id)}" ${c.id === CONV ? 'aria-current="true"' : ""} dir="auto">${esc(c.title)}<small>${p ? esc(p.name) + " · " : ""}${when(c.updated)}</small></button>`;
  }).join("") : `<div class="none">Your conversations will appear here.</div>`;
  $("history").querySelectorAll("[data-c]").forEach(b => {
    b.onclick = () => openConversation(b.dataset.c);
    b.oncontextmenu = e => { e.preventDefault(); deleteConversation(b.dataset.c); };
  });
}
async function openConversation(id) {
  try {
    const c = await call(`/conversations/${encodeURIComponent(id)}`);
    CONV = c.id; SPACE = c.project && projectById(c.project) ? c.project : "";
    renderSpace(); go("chat");
    $("thread").innerHTML = ""; $("welcome").hidden = true;
    for (const m of c.messages) { addQuestion(m.question); renderAnswer(addAnswer(), m.answer, false); }
    addConversationTools();
    renderHistory();
    requestAnimationFrame(() => $("chatScroll").scrollTop = $("chatScroll").scrollHeight);
  } catch (err) { toast(err.message, true); }
}
function addConversationTools() {
  const row = document.createElement("div");
  row.className = "a-tools"; row.style.justifyContent = "center"; row.id = "convTools";
  row.innerHTML = `<button class="btn sm ghost" type="button"><svg class="i"><use href="#i-trash"/></svg>Delete conversation</button>`;
  row.querySelector("button").onclick = () => deleteConversation(CONV);
  $("thread").append(row);
}
async function deleteConversation(id) {
  if (!await dialog({ title: "Delete this conversation?", text: "It is removed from this computer. Your documents are not affected.", ok: "Delete", danger: true })) return;
  try {
    await call(`/conversations/${encodeURIComponent(id)}`, { method: "DELETE" });
    if (id === CONV) newChat();
    await loadHistory(); toast("Conversation deleted.");
  } catch (err) { toast(err.message, true); }
}
function newChat() {
  CONV = null; $("thread").innerHTML = ""; $("welcome").hidden = false; renderHistory(); closeSource();
  go("chat");
}
$("newChat").onclick = newChat;
$("newChatPhone").onclick = newChat;

/* -- asking ------------------------------------------------------------------- */
const q = $("question");
function fit() { q.style.height = "auto"; q.style.height = Math.min(q.scrollHeight, 200) + "px"; $("send").disabled = !q.value.trim(); }
q.addEventListener("input", fit);
q.addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing && (wide() || e.metaKey || e.ctrlKey)) { e.preventDefault(); ask(); }
});
$("askForm").onsubmit = e => { e.preventDefault(); ask(); };
$("attach").onclick = () => go("add");
$$("#starters button").forEach(b => b.onclick = () => { q.value = b.lastChild.textContent.trim(); ask(); });

function addQuestion(text) {
  $("convTools")?.remove();
  $("thread").insertAdjacentHTML("beforeend", `<div class="q" dir="auto">${esc(text)}</div>`);
}
function addAnswer() {
  const a = document.createElement("div");
  a.className = "a";
  a.innerHTML = `<span class="who" aria-hidden="true"><svg><use href="#logo"/></svg></span><div class="body"><div class="thinking"><i></i><i></i><i></i><span>${SPACE || ME.prefs.chat_private || ME.prefs.chat_household ? "Reading your documents…" : "Thinking…"}</span></div></div>`;
  $("thread").append(a);
  return a;
}
let busy = false;
async function ask() {
  const text = q.value.trim(); if (!text || busy) return;
  q.value = ""; fit();
  await send(text);
  if (wide()) q.focus();
}
/* One path for typed and spoken questions. Returns the /ask response, or null. */
async function send(text) {
  if (busy) return null;
  busy = true; $("welcome").hidden = true;
  addQuestion(text);
  const a = addAnswer();
  a.scrollIntoView({ behavior: "smooth", block: "end" });
  try {
    const r = await post("/ask", { question: text, project: SPACE || null, conversation_id: CONV });
    const isNew = CONV !== r.conversation_id;
    CONV = r.conversation_id;
    renderAnswer(a, r, true);
    if (isNew) loadHistory(); else { const c = CONVS.find(c => c.id === CONV); if (c) { c.updated = Date.now() / 1000; CONVS.sort((x, y) => y.updated - x.updated); renderHistory(); } }
    return r;
  } catch (err) {
    a.querySelector(".body").innerHTML = `<div class="basis clash"><svg class="i"><use href="#i-alert"/></svg>Something went wrong</div><div class="prose refused" dir="auto">${esc(err.message)}</div>`;
    return null;
  } finally { busy = false; }
}

/* Answers are a list of checked claims. Each claim keeps its own citations;
   a source is numbered by first appearance so the numbers read 1, 2, 3. */
function renderAnswer(a, r, live) {
  const body = a.querySelector(".body");
  const asked = r.asked_as ? `<div class="asked-as" dir="auto">Understood as: ${esc(r.asked_as)}</div>` : "";
  const secs = `${(r.latency_ms / 1000).toFixed(1)} s`;
  if (r.outcome === "remembered") {
    body.innerHTML = `<div class="basis docs"><svg class="i"><use href="#i-brain"/></svg>Saved to your memory</div>
      <div class="prose" dir="auto">${esc(r.refusal_reason.replace(/^Saved to your memory: /, ""))}</div>
      <div class="a-tools"><button class="btn sm ghost" type="button" data-undo>Undo</button><span class="time">Ask about it any time. Delete it under Settings › Memory.</span></div>`;
    body.querySelector("[data-undo]").onclick = async e => {
      try { await call(`/memory/${encodeURIComponent(r.fact_id)}`, { method: "DELETE" }); e.target.closest(".a-tools").innerHTML = `<span class="time">Forgotten.</span>`; renderMemory(); }
      catch (err) { toast(err.message, true); }
    };
    renderMemory();
    return;
  }
  if (!r.claims.length) {
    body.innerHTML = `${asked}<div class="basis"><svg class="i"><use href="#i-shield"/></svg>${r.routed_to ? "Better asked elsewhere" : "No answer"}</div><div class="prose refused" dir="auto">${esc(r.refusal_reason || "Your documents don't cover this.")}</div>`;
    return;
  }
  const text = r.claims.map(c => c.text).join(" ");
  const tools = `<div class="a-tools"><button class="icon-btn" data-copy aria-label="Copy answer" title="Copy"><svg class="i"><use href="#i-copy"/></svg></button><span class="time">${secs}</span></div>`;
  if (r.basis === "general") {
    body.innerHTML = `${asked}<div class="basis"><svg class="i"><use href="#i-globe"/></svg>General knowledge · not from your documents</div><div class="prose" dir="auto">${paras(r.claims.map(c => esc(c.text)).join(" "))}</div>${tools}`;
  } else {
    const num = new Map();
    const html = r.claims.map(c => esc(c.text) + c.citations.map(id => {
      if (!num.has(id)) num.set(id, num.size + 1);
      return `<button class="cite" data-id="${esc(id)}" aria-label="Source ${num.get(id)}">${num.get(id)}</button>`;
    }).join("")).join(" ");
    const n = num.size;
    const label = r.outcome === "conflict"
      ? `<div class="basis clash"><svg class="i"><use href="#i-alert"/></svg>Your documents disagree on this</div>`
      : `<div class="basis docs"><svg class="i"><use href="#i-doc"/></svg>From your documents · ${n} source${n === 1 ? "" : "s"}</div>`;
    const chips = [...num].map(([id, k]) => {
      const s = r.sources?.[id], head = s?.heading ? ` · ${s.heading}` : "";
      return `<button class="source-chip" data-id="${esc(id)}"><b>${k}</b><span dir="auto">${esc(docLabel(id) + head)}</span></button>`;
    }).join("");
    body.innerHTML = `${asked}${label}<div class="prose" dir="auto">${paras(html)}</div><div class="sources">${chips}</div>${tools}`;
    body.querySelectorAll("[data-id]").forEach(b => b.onclick = () => openSource(b.dataset.id, b));
  }
  body.querySelector("[data-copy]").onclick = async () => {
    try { await navigator.clipboard.writeText(text); toast("Copied."); } catch { toast("Couldn't copy on this device.", true); }
  };
  if (live) a.scrollIntoView({ behavior: "smooth", block: "nearest" });
}
const paras = html => html.split(/\n{2,}/).map(p => `<p>${p.replace(/\n/g, "<br>")}</p>`).join("");

/* chunk ids look like "<doc_id>#<n>"; doc ids carry their library prefix */
function docParts(docId) {
  if (docId === "p.memory.md") return ["Only me", "Your memory"];
  if (docId.startsWith("h.")) return ["Household", docId.slice(2)];
  if (docId.startsWith("p.")) return ["Only me", docId.slice(2)];
  const k = /^k\.([a-z0-9-]+)\.(.*)$/.exec(docId);
  if (k) return [PACKS.find(p => p.name === k[1])?.title ?? "Reference", k[2]];
  const m = /^j\.([a-z0-9]+)\.(.*)$/.exec(docId);
  if (m) return [`Project · ${projectById(m[1])?.name ?? "project"}`, m[2]];
  return ["Library", docId];
}
const docLabel = chunkId => docParts(chunkId.split("#")[0])[1];
const ext = f => (f.split(".").pop() || "").slice(0, 4).toUpperCase();

/* -- source inspector --------------------------------------------------------- */
let srcFrom = null;
async function openSource(id, from) {
  try {
    const c = await call(`/chunks/${encodeURIComponent(id)}` + (SPACE ? `?project=${encodeURIComponent(SPACE)}` : ""));
    const [lib, file] = docParts(c.doc_id);
    $("srcType").textContent = ext(file) || "DOC";
    $("srcTitle").textContent = file;
    $("srcSub").textContent = c.heading ? `${lib} · ${c.heading}` : lib;
    $("srcText").textContent = c.text;
    $$(".cite[aria-expanded]").forEach(b => b.removeAttribute("aria-expanded"));
    $$(`.cite[data-id="${CSS.escape(id)}"]`).forEach(b => b.setAttribute("aria-expanded", "true"));
    srcFrom = from;
    $("inspector").classList.add("open"); $("inspector").setAttribute("aria-hidden", "false");
    $("app").classList.add("inspecting");
    if (!matchMedia("(min-width: 1180px)").matches) $("sheetScrim").classList.add("open");
    $("closeSrc").focus({ preventScroll: true });
  } catch (err) {
    toast(err.message === "no such chunk" ? "That source is no longer in your documents." : err.message, true);
  }
}
function closeSource() {
  if (!$("inspector").classList.contains("open")) return;
  $("inspector").classList.remove("open"); $("inspector").setAttribute("aria-hidden", "true");
  $("app").classList.remove("inspecting"); $("sheetScrim").classList.remove("open");
  $$(".cite[aria-expanded]").forEach(b => b.removeAttribute("aria-expanded"));
  srcFrom?.focus?.({ preventScroll: true }); srcFrom = null;
}
$("closeSrc").onclick = closeSource;
$("sheetScrim").onclick = closeSource;
document.addEventListener("keydown", e => {
  if (e.key === "Escape") { closeMenu(); closeSource(); closeDrawer(); }
  if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === "o") { e.preventDefault(); newChat(); }
});

/* -- add documents ------------------------------------------------------------ */
let pending = null;
function renderTargets() {
  const keep = $("target").value;
  $("target").innerHTML = [`<option value="private">Only me</option>`, `<option value="household">Household (everyone)</option>`]
    .concat((ME.projects || []).map(p => `<option value="project:${esc(p.id)}">Project · ${esc(p.name)}</option>`)).join("");
  if ([...$("target").options].some(o => o.value === keep)) $("target").value = keep;
}
const size = n => n < 1024 * 1024 ? `${Math.max(1, Math.round(n / 1024))} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`;
function choose(f) {
  if (!f) return;
  pending = f;
  $("pending").hidden = false; $("pendingName").textContent = f.name; $("pendingSize").textContent = size(f.size);
  const img = f.type.startsWith("image/");
  $("preview").hidden = !img; $("pendingType").hidden = img;
  if (img) $("preview").src = URL.createObjectURL(f); else $("pendingType").textContent = ext(f.name);
  $("save").disabled = false; $("saveNote").textContent = "";
}
function clearPending() { pending = null; $("pending").hidden = true; $("save").disabled = true; }
$("takePhoto").onclick = () => $("camera").click();
$("chooseFile").onclick = () => $("picker").click();
for (const input of [$("camera"), $("picker")]) input.onchange = () => { choose(input.files[0]); input.value = ""; };
$("clearPending").onclick = clearPending;
const dz = $("dropzone");
dz.addEventListener("dragover", e => { e.preventDefault(); dz.classList.add("over"); });
dz.addEventListener("dragleave", () => dz.classList.remove("over"));
dz.addEventListener("drop", e => { e.preventDefault(); dz.classList.remove("over"); choose(e.dataTransfer.files[0]); });

function uploadUrl(name, target) {
  const [lib, pid] = target.split(":");
  return `/upload?filename=${encodeURIComponent(name)}&library=${lib}` + (pid ? `&project=${encodeURIComponent(pid)}` : "");
}
function targetName(target) {
  const [lib, pid] = target.split(":");
  return lib === "project" ? `“${projectById(pid)?.name}”` : lib === "household" ? "the household library" : "your library";
}
// Phone cameras name every photo image.jpg; give each scan its own name.
const scanName = f => /^image\.(jpe?g|heic|png)$/i.test(f.name)
  ? `scan-${new Date().toISOString().slice(0, 16).replace(/[:T]/g, "-")}.${f.name.split(".").pop()}` : f.name;
$("save").onclick = async () => {
  if (!pending) return;
  const target = $("target").value, name = scanName(pending);
  $("save").disabled = true; $("saving").hidden = false;
  $("saveNote").textContent = pending.type.startsWith("image/") || /\.pdf$/i.test(name) ? "Reading the text. Photos and scans take a little longer." : "Reading…";
  try {
    const r = await call(uploadUrl(name, target), { method: "POST", body: pending });
    $("saveNote").textContent = "";
    toast(`Saved ${r.document} to ${targetName(target)}. You can ask about it now.`);
    clearPending(); refreshMe();
  } catch (err) { $("saveNote").textContent = ""; toast(err.message, true); $("save").disabled = false; }
  finally { $("saving").hidden = true; }
};

let LIB = "private";
$$("[data-lib]").forEach(b => b.onclick = () => {
  LIB = b.dataset.lib;
  $$("[data-lib]").forEach(x => x.setAttribute("aria-pressed", x === b));
  renderLibrary();
});
function docRows(files, canDelete) {
  return files.map(f => `<div class="item"><span class="filetype">${esc(ext(f))}</span><span class="text"><span class="title" dir="auto">${esc(f)}</span></span>
    ${canDelete ? `<button class="icon-btn" data-del="${esc(f)}" aria-label="Delete ${esc(f)}" title="Delete"><svg class="i"><use href="#i-trash"/></svg></button>` : ""}</div>`).join("");
}
function renderLibrary() {
  if (!ME) return;
  const files = ME[LIB] || [];
  const canDelete = LIB === "private" || ME.admin;
  $("libHint").textContent = LIB === "private" ? "Only you can see and ask about these." : "Everyone in the household can ask about these.";
  $("docList").innerHTML = files.length ? docRows(files, canDelete)
    : `<div class="empty"><b>No documents yet</b>Add one above and ask about it straight away.</div>`;
  $("docList").querySelectorAll("[data-del]").forEach(b => b.onclick = async () => {
    const f = b.dataset.del;
    if (!await dialog({ title: `Delete ${f}?`, text: "Amin stops answering from it on every device. This can't be undone.", ok: "Delete", danger: true })) return;
    try { await call(`/documents?filename=${encodeURIComponent(f)}&library=${LIB}`, { method: "DELETE" }); toast(`Deleted ${f}.`); refreshMe(); }
    catch (err) { toast(err.message, true); }
  });
}

/* -- projects ----------------------------------------------------------------- */
let OPEN = null;
function renderProjects() {
  if (!ME) return;
  const ps = ME.projects || [];
  $("projects").innerHTML = ps.length ? ps.map(p => `
    <button class="item" data-p="${esc(p.id)}"><span class="filetype" style="place-items:center;padding:0"><svg class="i"><use href="#i-folder"/></svg></span>
      <span class="text"><span class="title" dir="auto">${esc(p.name)}</span>
      <span class="sub">${p.documents.length} document${p.documents.length === 1 ? "" : "s"}${p.role === "member" ? ` · shared by ${esc(p.owner)}` : p.members.length ? ` · shared with ${p.members.length}` : ""}</span></span>
      <svg class="i chev"><use href="#i-chev"/></svg></button>`).join("")
    : `<div class="empty"><b>No projects yet</b>Make one for a flat, a car or a school year, and keep its papers together.</div>`;
  $("projects").querySelectorAll("[data-p]").forEach(b => b.onclick = () => openProject(b.dataset.p));
  if (OPEN) openProject(OPEN);
}
function showProjectList() { OPEN = null; $("projList").hidden = false; $("projDetail").hidden = true; }
$("projBack").onclick = showProjectList;
$("newProject").onclick = async () => {
  const name = await dialog({ title: "New project", text: "For example “Flat in Marina” or “Car”.", input: "", ok: "Create" });
  if (!name) return;
  try { const p = await post("/projects", { name }); OPEN = p.id; await refreshMe(); toast(`Created “${p.name}”.`); }
  catch (err) { toast(err.message, true); }
};
function openProject(id) {
  const p = projectById(id); if (!p) return showProjectList();
  OPEN = id; $("projList").hidden = true; $("projDetail").hidden = false;
  const owner = p.role === "owner";
  $("projName").textContent = p.name;
  $("projLead").textContent = owner ? (p.members.length ? `Shared with ${p.members.join(", ")}.` : "Only you can see this project.") : `Shared with you by ${p.owner}.`;
  $("projAdd").hidden = false;
  $("projDocs").innerHTML = p.documents.length ? docRows(p.documents, owner) : `<div class="empty"><b>No documents yet</b>Add the papers this project is about.</div>`;
  $("projDocs").querySelectorAll("[data-del]").forEach(b => b.onclick = async () => {
    const f = b.dataset.del;
    if (!await dialog({ title: `Delete ${f}?`, text: `It is removed from “${p.name}”.`, ok: "Delete", danger: true })) return;
    try { await call(`/documents?filename=${encodeURIComponent(f)}&library=project&project=${p.id}`, { method: "DELETE" }); refreshMe(); }
    catch (err) { toast(err.message, true); }
  });
  $("projOwner").hidden = !owner;
  if (!owner) return;
  const perm = (key, title, sub) => `<label class="toggle-row"><span class="text"><span class="title">${title}</span><span class="sub">${sub}</span></span>
    <span class="switch"><input type="checkbox" data-perm="${key}" ${p[key] ? "checked" : ""}><span></span></span></label>`;
  $("projPerms").innerHTML =
      perm("general_chat", "General chat may use this project", "Its documents also answer outside the project, for everyone who can open it.")
    + perm("grant_private", "This project may read my library", p.members.length ? "Everyone you share this project with could get answers from your private documents." : "Your “Only me” documents answer questions here too.")
    + perm("grant_household", "This project may read the household library", "Shared household documents answer questions here too.");
  $("projPerms").querySelectorAll("[data-perm]").forEach(i => i.onchange = async () => {
    if (i.checked && i.dataset.perm === "grant_private" && p.members.length
        && !await dialog({ title: "Share your private library?", text: "People you've shared this project with will be able to get answers from your private documents.", ok: "Allow" })) { i.checked = false; return; }
    try { await patch(`/projects/${p.id}`, { [i.dataset.perm]: i.checked }); refreshMe(); }
    catch (err) { i.checked = !i.checked; toast(err.message, true); }
  });
  const others = (ME.people || []).filter(n => n !== ME.name);
  $("projMembers").innerHTML = others.length ? others.map(n => `<label class="toggle-row"><span class="avatar">${esc(n[0].toUpperCase())}</span><span class="text"><span class="title">${esc(n)}</span></span>
    <span class="switch"><input type="checkbox" data-m="${esc(n)}" ${p.members.includes(n) ? "checked" : ""}><span></span></span></label>`).join("")
    : `<div class="empty">No one else here yet. Invite people from Settings.</div>`;
  $("projMembers").querySelectorAll("[data-m]").forEach(i => i.onchange = async () => {
    if (i.checked && p.grant_private && !await dialog({ title: `Share with ${i.dataset.m}?`, text: "This project reads your private library, so they will be able to get answers from it.", ok: "Share" })) { i.checked = false; return; }
    const members = [...$("projMembers").querySelectorAll("[data-m]:checked")].map(x => x.dataset.m);
    try { await patch(`/projects/${p.id}`, { members }); refreshMe(); }
    catch (err) { i.checked = !i.checked; toast(err.message, true); }
  });
}
$("askProject").onclick = () => { if (OPEN) { SPACE = OPEN; newChat(); renderSpace(); } };
$("projAdd").onclick = () => $("projPicker").click();
$("projPicker").onchange = async () => {
  const f = $("projPicker").files[0]; $("projPicker").value = ""; if (!f || !OPEN) return;
  toast(`Reading ${f.name}…`);
  try { await call(uploadUrl(scanName(f), `project:${OPEN}`), { method: "POST", body: f }); toast(`Added ${f.name}.`); refreshMe(); }
  catch (err) { toast(err.message, true); }
};
$("projRename").onclick = async () => {
  const p = projectById(OPEN); if (!p) return;
  const name = await dialog({ title: "Rename project", input: p.name, ok: "Rename" });
  if (!name || name === p.name) return;
  try { await patch(`/projects/${p.id}`, { name }); refreshMe(); } catch (err) { toast(err.message, true); }
};
$("projDelete").onclick = async () => {
  const p = projectById(OPEN);
  if (!p || !await dialog({ title: `Delete “${p.name}”?`, text: "Its documents and conversations are removed from this computer. This can't be undone.", ok: "Delete project", danger: true })) return;
  try {
    await call(`/projects/${p.id}`, { method: "DELETE" });
    if (SPACE === p.id) { SPACE = ""; newChat(); go("projects"); }
    showProjectList(); await refreshMe(); loadHistory(); toast(`Deleted “${p.name}”.`);
  } catch (err) { toast(err.message, true); }
};

/* -- memory (Teach Amin) --------------------------------------------------------- */
async function renderMemory() {
  let facts = [];
  try { facts = await call("/memory"); } catch { return; }
  $("memoryList").innerHTML = facts.length ? facts.slice().reverse().map(f => `
    <div class="item"><svg class="i" style="color:var(--teal-ink)"><use href="#i-brain"/></svg>
      <span class="text"><span class="title wrap" dir="auto" style="white-space:normal">${esc(f.text)}</span>
      <span class="sub">${new Date(f.created * 1000).toLocaleDateString([], { day: "numeric", month: "short", year: "numeric" })}</span></span>
      <button class="icon-btn" data-forget="${esc(f.id)}" aria-label="Forget this" title="Forget"><svg class="i"><use href="#i-trash"/></svg></button></div>`).join("")
    : `<div class="empty">Nothing yet. Tell Amin something worth remembering.</div>`;
  $("memoryList").querySelectorAll("[data-forget]").forEach(b => b.onclick = async () => {
    try { await call(`/memory/${encodeURIComponent(b.dataset.forget)}`, { method: "DELETE" }); toast("Forgotten."); renderMemory(); }
    catch (err) { toast(err.message, true); }
  });
}
$("teachForm").onsubmit = async e => {
  e.preventDefault();
  const text = $("teachText").value.trim(); if (!text) return;
  try { await post("/memory", { text }); $("teachText").value = ""; toast("Amin will remember that."); renderMemory(); }
  catch (err) { toast(err.message, true); }
};

/* -- settings ------------------------------------------------------------------ */
let PACKS = [];
async function loadPacks() {
  try { PACKS = await call("/packs"); } catch { PACKS = []; }
  if (!PACKS.length) return;
  $("packList").innerHTML = PACKS.map(p => `<label class="toggle-row"><span class="text"><span class="title">${esc(p.title)}</span><span class="sub">${esc(p.licence)} · ${p.documents} pages</span></span><span class="switch"><input type="checkbox" data-pack="${esc(p.name)}"${p.enabled ? " checked" : ""}><span></span></span></label>`).join("");
  $("packList").querySelectorAll("[data-pack]").forEach(box => box.onchange = async () => {
    const on = [...$("packList").querySelectorAll("[data-pack]:checked")].map(b => b.dataset.pack);
    try { ME.prefs = await patch("/me/prefs", { packs: on }); }
    catch (err) { box.checked = !box.checked; toast(err.message, true); }
  });
}
for (const [id, key] of [["prefPrivate", "chat_private"], ["prefHousehold", "chat_household"]]) $(id).onchange = async () => {
  try { ME.prefs = await patch("/me/prefs", { [key]: $(id).checked }); }
  catch (err) { $(id).checked = !$(id).checked; toast(err.message, true); }
};
$("newInvite").onclick = async () => {
  try { $("inviteCode").textContent = (await post("/invites")).code; $("inviteRow").hidden = false; }
  catch (err) { toast(err.message, true); }
};
$("copyInvite").onclick = async () => {
  try { await navigator.clipboard.writeText($("inviteCode").textContent); toast("Invite code copied."); } catch { toast("Couldn't copy on this device.", true); }
};
function signedOut() {
  stopWake(); if (V.on) stopVoice(); CONV = null; SPACE = ""; $("thread").innerHTML = ""; $("welcome").hidden = false; go("chat"); showAuth(); }
$("signOut").onclick = async () => { await post("/logout").catch(() => {}); signedOut(); };
$("signOutAll").onclick = async () => {
  if (!await dialog({ title: "Sign out everywhere?", text: "Every phone, tablet and computer signed in to your account is signed out, including this one.", ok: "Sign out", danger: true })) return;
  await post("/logout-all").catch(() => {}); signedOut();
};

/* -- voice mode -------------------------------------------------------------------
   A conversation loop: listen → (pause detected) → transcribe on this computer →
   ask → read the answer aloud → listen again. Tap the orb to interrupt or to
   talk; it ends after two quiet turns or with "End conversation".
   iPhone note: only Siri may listen for a wake word in the background, so
   "Hey Amin" works while the app is open; on iOS, "Hey Siri, ask Amin" comes
   with the native app. */
const V = { on: false, state: "idle", stream: null, ctx: null, analyser: null, rec: null, raf: 0,
  quiet: 0, mute: false, lang: "auto" };
try { V.lang = localStorage.getItem("amin.voice.lang") || "auto"; V.mute = localStorage.getItem("amin.voice.mute") === "1"; } catch {}
const SPEECH_RMS = 0.035, END_SILENCE_MS = 1300, NO_SPEECH_MS = 7000, MAX_TURN_MS = 30000;

function vstate(state, label) {
  V.state = state; $("voice").dataset.state = state; $("voiceState").textContent = label;
}
function vlangUI() {
  $$("[data-vlang]").forEach(b => b.setAttribute("aria-pressed", b.dataset.vlang === V.lang));
  $("voiceMute").setAttribute("aria-pressed", V.mute);
  $("voiceMute").querySelector("use").setAttribute("href", V.mute ? "#i-speaker-off" : "#i-speaker");
  $("voiceMute").setAttribute("aria-label", V.mute ? "Read answers aloud" : "Don't read answers aloud");
}
$$("[data-vlang]").forEach(b => b.onclick = () => { V.lang = b.dataset.vlang; try { localStorage.setItem("amin.voice.lang", V.lang); } catch {} vlangUI(); });
$("voiceMute").onclick = () => { V.mute = !V.mute; try { localStorage.setItem("amin.voice.mute", V.mute ? "1" : "0"); } catch {} if (V.mute) speechSynthesis.cancel(); vlangUI(); };

async function startVoice(opening = null) {
  stopWake();
  if (!navigator.mediaDevices?.getUserMedia) {
    toast(location.protocol === "https:" || location.hostname === "localhost" ? "This browser can't record audio." : "Voice needs a secure connection. Open Amin over https (run make certs).", true);
    return;
  }
  try { V.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } }); }
  catch { toast("Amin needs microphone permission for voice mode.", true); return; }
  // iOS only lets speech play after a tap; an empty utterance now unlocks it for the whole session.
  try { speechSynthesis.speak(new SpeechSynthesisUtterance("")); } catch {}
  V.ctx = new (window.AudioContext || window.webkitAudioContext)();
  V.analyser = V.ctx.createAnalyser(); V.analyser.fftSize = 1024;
  V.ctx.createMediaStreamSource(V.stream).connect(V.analyser);
  V.on = true; V.quiet = 0; $("voiceSaid").textContent = ""; $("voiceReply").textContent = "";
  $("voice").hidden = false; vlangUI(); go("chat");
  if (opening === null) return listen();
  if (opening) return askSpoken(opening);  // "Hey Amin, when does my lease end?"
  speak("How can I help?", () => V.on && listen());  // just "Hey Amin"
}
function stopVoice() {
  V.on = false; cancelAnimationFrame(V.raf);
  try { V.rec?.state === "recording" && V.rec.stop(); } catch {}
  speechSynthesis.cancel();
  V.stream?.getTracks().forEach(t => t.stop()); V.ctx?.close().catch(() => {});
  V.stream = V.ctx = V.rec = null;
  $("voice").hidden = true; $("orb").style.setProperty("--level", 0);
  if (W.want) setTimeout(startWake, 400);
}
function level() {
  const buf = new Float32Array(V.analyser.fftSize);
  V.analyser.getFloatTimeDomainData(buf);
  let sum = 0; for (const x of buf) sum += x * x;
  return Math.sqrt(sum / buf.length);
}
function pickType() {
  for (const t of ["audio/webm;codecs=opus", "audio/mp4", "audio/webm", "audio/ogg;codecs=opus"])
    if (window.MediaRecorder?.isTypeSupported?.(t)) return t;
  return "";
}
function listen() {
  if (!V.on) return;
  vstate("listening", "Listening…");
  const type = pickType(), chunks = [];
  V.rec = new MediaRecorder(V.stream, type ? { mimeType: type } : undefined);
  V.rec.ondataavailable = e => e.data.size && chunks.push(e.data);
  let spoke = false, lastVoice = 0;
  const started = performance.now();
  V.rec.onstop = () => {
    cancelAnimationFrame(V.raf); $("orb").style.setProperty("--level", 0);
    if (!V.on) return;
    if (!spoke) {
      if (++V.quiet >= 2) { vstate("idle", "Tap the orb to talk"); return; }
      return listen();
    }
    V.quiet = 0;
    heard(new Blob(chunks, { type: V.rec.mimeType || type || "audio/webm" }));
  };
  V.rec.start(250);
  const tick = () => {
    if (!V.on || V.rec?.state !== "recording") return;
    const l = level(), now = performance.now();
    $("orb").style.setProperty("--level", Math.min(1, l * 9).toFixed(3));
    if (l > SPEECH_RMS) { spoke = true; lastVoice = now; }
    if ((spoke && now - lastVoice > END_SILENCE_MS) || (!spoke && now - started > NO_SPEECH_MS) || now - started > MAX_TURN_MS) {
      V.rec.stop(); return;
    }
    V.raf = requestAnimationFrame(tick);
  };
  V.raf = requestAnimationFrame(tick);
}
async function heard(blob) {
  vstate("transcribing", "Transcribing…");
  let said;
  try {
    const hint = V.lang === "auto" ? "" : `?lang=${V.lang}`;
    said = await call(`/transcribe${hint}`, { method: "POST", headers: { "Content-Type": blob.type || "audio/webm" }, body: blob });
  } catch (err) { toast(err.message, true); return V.on && listen(); }
  if (!V.on) return;
  if (!said.text) return listen();
  askSpoken(said.text);
}
async function askSpoken(text) {
  $("voiceSaid").textContent = text; $("voiceReply").textContent = "";
  vstate("thinking", "Thinking…");
  const r = await send(text);
  if (!V.on) return;
  if (!r) return listen();
  const reply = r.claims.length ? r.claims.map(c => c.text).join(" ") : (r.refusal_reason || "");
  $("voiceReply").textContent = reply;
  speak(reply, () => V.on && listen());
}
const scriptLang = t => /[ഀ-ൿ]/.test(t) ? "ml" : /[؀-ۿ]/.test(t) ? "ar" : "en";
function speak(text, done) {
  if (V.mute || !text || !("speechSynthesis" in window)) return done();
  const lang = scriptLang(text);
  const voice = speechSynthesis.getVoices().find(v => v.lang.toLowerCase().startsWith(lang));
  if (!voice) {
    vstate("speaking", lang === "ml" ? "No Malayalam voice on this device yet — reading is on screen" : "No voice for this language on this device");
    return setTimeout(done, 2500);
  }
  const u = new SpeechSynthesisUtterance(text.replace(/\s*\[S\d+\]/g, ""));
  u.voice = voice; u.lang = voice.lang; u.rate = 1;
  u.onend = u.onerror = () => done();
  vstate("speaking", "Speaking…");
  speechSynthesis.speak(u);
}
$("orb").onclick = () => {
  if (V.state === "speaking") { speechSynthesis.cancel(); return; }  // interrupt; onend → listen
  if (V.state === "idle") { V.quiet = 0; listen(); }
  else if (V.state === "listening") { V.rec?.stop(); }  // done talking
};
$("voiceEnd").onclick = stopVoice;
$("micBtn").onclick = () => startVoice();

/* -- "Hey Amin" -------------------------------------------------------------------
   Only bursts of speech leave the page, each to this computer's /wake, which
   checks whether it starts with Amin's name. Silence sends nothing. */
const W = { want: false, on: false, stream: null, ctx: null, analyser: null, raf: 0, rec: null, busy: false };
try { W.want = localStorage.getItem("amin.wake") === "1"; } catch {}
$("prefWake").checked = W.want;
$("prefWake").onchange = () => {
  W.want = $("prefWake").checked;
  try { localStorage.setItem("amin.wake", W.want ? "1" : "0"); } catch {}
  W.want ? startWake() : stopWake();
};
async function startWake() {
  if (W.on || V.on || !W.want || !ME) return;
  try { W.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } }); }
  catch { W.want = false; $("prefWake").checked = false; toast("“Hey Amin” needs microphone permission.", true); return; }
  W.ctx = new (window.AudioContext || window.webkitAudioContext)();
  W.analyser = W.ctx.createAnalyser(); W.analyser.fftSize = 1024;
  W.ctx.createMediaStreamSource(W.stream).connect(W.analyser);
  W.on = true; $("wakePill").hidden = false;
  const buf = new Float32Array(W.analyser.fftSize), type = pickType();
  let chunks = [], since = 0, lastVoice = 0;
  const tick = () => {
    if (!W.on) return;
    W.analyser.getFloatTimeDomainData(buf);
    let sum = 0; for (const x of buf) sum += x * x;
    const loud = Math.sqrt(sum / buf.length) > SPEECH_RMS, now = performance.now();
    if (loud && !W.rec && !W.busy) {  // a burst starts
      chunks = []; since = now;
      W.rec = new MediaRecorder(W.stream, type ? { mimeType: type } : undefined);
      W.rec.ondataavailable = e => e.data.size && chunks.push(e.data);
      W.rec.onstop = () => check(new Blob(chunks, { type: W.rec?.mimeType || type || "audio/webm" }));
      W.rec.start(200);
    }
    if (loud) lastVoice = now;
    // a burst ends at a 0.7 s pause, or at 5 s: a wake phrase plus a short question
    if (W.rec && W.rec.state === "recording" && (now - lastVoice > 700 || now - since > 5000)) W.rec.stop();
    W.raf = requestAnimationFrame(tick);
  };
  W.raf = requestAnimationFrame(tick);
}
async function check(blob) {
  W.rec = null;
  if (!W.on || blob.size < 2000) return;
  W.busy = true;
  try {
    const r = await call("/wake", { method: "POST", headers: { "Content-Type": blob.type || "audio/webm" }, body: blob });
    if (r.wake && W.on) startVoice(r.rest || "");
  } catch {} finally { W.busy = false; }
}
function stopWake() {
  W.on = false; cancelAnimationFrame(W.raf);
  try { W.rec?.state === "recording" && W.rec.stop(); } catch {}
  W.stream?.getTracks().forEach(t => t.stop()); W.ctx?.close().catch(() => {});
  W.stream = W.ctx = W.rec = null; $("wakePill").hidden = true;
}
$("wakePill").onclick = () => go("settings");
document.addEventListener("visibilitychange", () => { if (document.hidden) stopWake(); else if (W.want && !V.on) startWake(); });
document.addEventListener("keydown", e => { if (e.key === "Escape" && V.on) stopVoice(); });
speechSynthesis?.getVoices();  // voices load asynchronously; ask early

boot();
