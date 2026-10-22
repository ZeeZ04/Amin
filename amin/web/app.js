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
  greet(); renderSpace(); renderTargets(); renderLibrary(); renderProjects();
  await loadHistory();
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
  busy = true; q.value = ""; fit(); $("welcome").hidden = true;
  addQuestion(text);
  const a = addAnswer();
  a.scrollIntoView({ behavior: "smooth", block: "end" });
  try {
    const r = await post("/ask", { question: text, project: SPACE || null, conversation_id: CONV });
    const isNew = CONV !== r.conversation_id;
    CONV = r.conversation_id;
    renderAnswer(a, r, true);
    if (isNew) loadHistory(); else { const c = CONVS.find(c => c.id === CONV); if (c) { c.updated = Date.now() / 1000; CONVS.sort((x, y) => y.updated - x.updated); renderHistory(); } }
  } catch (err) {
    a.querySelector(".body").innerHTML = `<div class="basis clash"><svg class="i"><use href="#i-alert"/></svg>Something went wrong</div><div class="prose refused" dir="auto">${esc(err.message)}</div>`;
  } finally { busy = false; if (wide()) q.focus(); }
}

/* Answers are a list of checked claims. Each claim keeps its own citations;
   a source is numbered by first appearance so the numbers read 1, 2, 3. */
function renderAnswer(a, r, live) {
  const body = a.querySelector(".body");
  const secs = `${(r.latency_ms / 1000).toFixed(1)} s`;
  if (!r.claims.length) {
    body.innerHTML = `<div class="basis"><svg class="i"><use href="#i-shield"/></svg>No answer</div><div class="prose refused" dir="auto">${esc(r.refusal_reason || "Your documents don't cover this.")}</div>`;
    return;
  }
  const text = r.claims.map(c => c.text).join(" ");
  const tools = `<div class="a-tools"><button class="icon-btn" data-copy aria-label="Copy answer" title="Copy"><svg class="i"><use href="#i-copy"/></svg></button><span class="time">${secs}</span></div>`;
  if (r.basis === "general") {
    body.innerHTML = `<div class="basis"><svg class="i"><use href="#i-globe"/></svg>General knowledge · not from your documents</div><div class="prose" dir="auto">${paras(r.claims.map(c => esc(c.text)).join(" "))}</div>${tools}`;
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
    body.innerHTML = `${label}<div class="prose" dir="auto">${paras(html)}</div><div class="sources">${chips}</div>${tools}`;
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
  if (docId.startsWith("h.")) return ["Household", docId.slice(2)];
  if (docId.startsWith("p.")) return ["Only me", docId.slice(2)];
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

/* -- settings ------------------------------------------------------------------ */
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
function signedOut() { CONV = null; SPACE = ""; $("thread").innerHTML = ""; $("welcome").hidden = false; go("chat"); showAuth(); }
$("signOut").onclick = async () => { await post("/logout").catch(() => {}); signedOut(); };
$("signOutAll").onclick = async () => {
  if (!await dialog({ title: "Sign out everywhere?", text: "Every phone, tablet and computer signed in to your account is signed out, including this one.", ok: "Sign out", danger: true })) return;
  await post("/logout-all").catch(() => {}); signedOut();
};

boot();
