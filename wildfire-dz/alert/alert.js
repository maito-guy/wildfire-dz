// Simulated emergency alert (UK-style). Listens to GET /alerts/stream (SSE).
// Optional URL params: ?village=<id> to receive one village only (default: every alert).
const params = new URLSearchParams(location.search);
const VILLAGE = params.get("village");
const ORDER = ["ary", "kab", "ar", "fr", "en"];        // display order on the phone
const $ = (id) => document.getElementById(id);
let texts = null, audioCtx = null, siren = null, current = null, wakeLock = null;

fetch("texts.json").then((r) => r.json()).then((t) => { texts = t; });
if (VILLAGE) $("areaInfo").textContent = `Receives alerts for village ${VILLAGE} only.`;

$("armBtn").onclick = async () => {
  audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  beep(0.15);                                           // unlocks audio on iOS/Android
  try { await document.documentElement.requestFullscreen?.(); } catch (_) { /* optional */ }
  try { wakeLock = await navigator.wakeLock?.request("screen"); } catch (_) { /* optional */ }
  show("idle");
  connect();
};

function show(id) { ["arm", "idle", "alert"].forEach((s) => $(s).classList.toggle("hidden", s !== id)); }

function connect() {
  const url = "/alerts/stream" + (VILLAGE ? `?village_id=${encodeURIComponent(VILLAGE)}` : "");
  const es = new EventSource(url);                      // auto-reconnects on drop
  es.addEventListener("hello", () => { $("conn").classList.add("ok"); $("idleText").textContent = "Armed. Connected. Waiting for alerts…"; });
  es.addEventListener("alert", (e) => onAlert(JSON.parse(e.data)));
  es.addEventListener("cancel", (e) => onCancel(JSON.parse(e.data)));
  es.onerror = () => { $("conn").classList.remove("ok"); $("idleText").textContent = "Reconnecting…"; };
}

function onAlert(a) {
  current = a;
  const box = $("alert");
  box.className = `screen alert ${a.level}`;
  const head = texts?.headline?.[a.level] || {};
  $("headline").textContent = head.en || "Emergency alert";
  $("meta").textContent = `${a.village_name} · ${ageText(a)} · simulated cell broadcast`;
  $("texts").innerHTML = "";
  ORDER.filter((l) => a.texts[l]).forEach((lang) => {
    const p = document.createElement("p");
    const rtl = texts?.rtl?.includes(lang);
    p.dir = rtl ? "rtl" : "ltr";
    p.lang = lang;
    p.innerHTML = `<span class="lang">${texts?.language_names?.[lang] || lang}</span>`;
    p.appendChild(document.createTextNode(a.texts[lang]));
    $("texts").appendChild(p);
  });
  show("alert");
  startSiren(a.level === "update" ? 2 : 10);
  navigator.vibrate?.([800, 300, 800, 300, 800, 300, 800]);
}

function onCancel(a) {
  if (!current || current.id !== a.id) return;
  stopSiren();
  $("alert").className = "screen alert cancelled";
  $("headline").textContent = "Alert cancelled";
  $("meta").textContent = `${a.village_name} · the previous alert was sent in error`;
}

$("ack").onclick = () => { stopSiren(); current = null; show("idle"); };

function ageText(a) {
  const m = a.data_age_min;
  return m < 60 ? `satellite pass ${m} min ago` : `satellite pass ${Math.floor(m / 60)} h ${m % 60} min ago`;
}

// ---------------------------------------------------------------- sound (no audio file needed)
function beep(sec) {
  if (!audioCtx) return;
  const o = audioCtx.createOscillator(), g = audioCtx.createGain();
  o.frequency.value = 880; g.gain.value = 0.05; o.connect(g).connect(audioCtx.destination);
  o.start(); o.stop(audioCtx.currentTime + sec);
}

function startSiren(seconds) {
  stopSiren();
  if (!audioCtx) return;
  const o = audioCtx.createOscillator(), g = audioCtx.createGain();
  o.type = "square"; g.gain.value = 0.6; o.connect(g).connect(audioCtx.destination);
  const t0 = audioCtx.currentTime;
  for (let t = 0; t < seconds; t += 0.5) {             // two-tone, like emergency alerts
    o.frequency.setValueAtTime(t % 1 < 0.5 ? 853 : 960, t0 + t);
  }
  o.start(); o.stop(t0 + seconds);
  siren = o;
}

function stopSiren() { try { siren?.stop(); } catch (_) { /* already stopped */ } siren = null; }
