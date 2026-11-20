// Simulated cell-broadcast emergency alert. Listens to GET /alerts/stream (SSE): events hello, alert, cancel.
// Only sent alerts and cancels arrive there (the operator approved them on the dashboard).
// Optional URL param: ?village=<id> to receive one village only (default: every alert).
const params = new URLSearchParams(location.search);
const VILLAGE = params.get("village");
const ORDER = ["ary", "kab", "ar", "fr", "en"];          // display order after the phone's chosen language
const RTL = ["ar", "ary"];
const NAMES = { ary: "Darija", kab: "Taqbaylit", ar: "العربية", fr: "Français", en: "English" };
const LEVEL_WORDS = {
  leave_now: ["EXTREME ALERT", "LEAVE NOW"],
  get_ready: ["SEVERE ALERT", "GET READY"],
  preventive: ["FIRE RISK TODAY"],
  update: ["UPDATE"],
};
const COMPASS = {
  N: [0, "north"], NE: [45, "north-east"], E: [90, "east"], SE: [135, "south-east"],
  S: [180, "south"], SW: [225, "south-west"], W: [270, "west"], NW: [315, "north-west"],
};
const VIBRATE = [500, 200, 500, 200, 500, 200, 500];    // 2.6 s, repeated every 3 s until Dismiss
const LANG_KEY = "alertLang";

const $ = (id) => document.getElementById(id);
let texts = null, audioCtx = null, siren = null, vibrateTimer = null, wakeLock = null;
let armed = false, last = null;                          // last = {alert, cancelled}
const received = new Set();                              // alert ids this phone has shown

// ---------------------------------------------------------------- language choice
function storedLang() {
  try { return localStorage.getItem(LANG_KEY); } catch (_) { return null; }
}
function saveLang(l) {
  try { localStorage.setItem(LANG_KEY, l); } catch (_) { /* private mode: keep it for this visit only */ }
}
function defaultLang() {
  const nav = (navigator.language || "en").slice(0, 2).toLowerCase();
  return ORDER.includes(nav) ? nav : "en";
}
let lang = ORDER.includes(storedLang()) ? storedLang() : defaultLang();

function buildPicker() {
  const names = texts?.language_names || NAMES;
  const box = $("langPicker");
  box.textContent = "";
  ORDER.forEach((l) => {
    const label = document.createElement("label");
    const input = document.createElement("input");
    input.type = "radio"; input.name = "lang"; input.value = l; input.checked = l === lang;
    input.onchange = () => { lang = l; saveLang(l); };
    const span = document.createElement("span");
    span.textContent = names[l] || l;
    span.lang = l;
    if (RTL.includes(l)) span.dir = "rtl";
    label.append(input, span);
    box.appendChild(label);
  });
}
buildPicker();

fetch("texts.json")
  .then((r) => r.json())
  .then((t) => { texts = t; buildPicker(); if (last && !$("alert").classList.contains("hidden")) render(last); })
  .catch(() => { /* headlines fall back to the level word only */ });

if (VILLAGE) $("areaInfo").textContent = `Receives alerts for village ${VILLAGE} only.`;

// ---------------------------------------------------------------- arm
$("armBtn").onclick = async () => {
  try {
    audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
    await audioCtx.resume?.();
  } catch (_) { audioCtx = null; }
  tone(0.15, 880, 0.2);                                  // a tap-started sound unlocks audio on iOS/Android
  navigator.vibrate?.(100);
  try { await document.documentElement.requestFullscreen?.({ navigationUI: "hide" }); } catch (_) { /* optional */ }
  await requestWakeLock();
  armed = true;
  show("idle");
};

async function requestWakeLock() {
  try { wakeLock = await navigator.wakeLock?.request("screen"); } catch (_) { /* needs HTTPS; set auto-lock to never */ }
}
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState !== "visible" || !armed) return;
  audioCtx?.resume?.();
  if (!wakeLock || wakeLock.released) requestWakeLock();
});

function show(id) { ["arm", "idle", "alert"].forEach((s) => $(s).classList.toggle("hidden", s !== id)); window.scrollTo(0, 0); }

// ---------------------------------------------------------------- stream
function setConn(ok) {
  document.body.classList.toggle("online", ok);
  document.querySelectorAll(".connText").forEach((el) => { el.textContent = ok ? "Connected" : "Reconnecting…"; });
}

function connect() {
  const url = "/alerts/stream" + (VILLAGE ? `?village_id=${encodeURIComponent(VILLAGE)}` : "");
  const es = new EventSource(url);                        // reconnects by itself after a drop
  es.addEventListener("hello", () => setConn(true));
  es.addEventListener("alert", (e) => onAlert(JSON.parse(e.data)));
  es.addEventListener("cancel", (e) => onCancel(JSON.parse(e.data)));
  es.onopen = () => setConn(true);
  es.onerror = () => setConn(false);
}
connect();                                                // connect before arming, so the arm screen shows the state

// ---------------------------------------------------------------- alert / cancel
function onAlert(a) {
  received.add(a.id);
  last = { alert: a, cancelled: false };
  render(last);
  show("alert");
  startAlarm();                                           // a new alert or an escalation restarts the alarm
}

function onCancel(a) {
  if (!received.has(a.id)) return;                        // never saw it: nothing to cancel on this phone
  stopAlarm();
  last = { alert: a, cancelled: true };
  render(last);
  show("alert");
  tone(0.6, 660, 0.4);
}

$("dismissBtn").onclick = () => { stopAlarm(); show(armed ? "idle" : "arm"); $("lastBtn").classList.toggle("hidden", !last); };
$("lastBtn").onclick = () => { if (last) { render(last); show("alert"); } };

function render({ alert: a, cancelled }) {
  const level = cancelled ? "cancelled" : a.level;
  $("alert").className = `screen alert ${level}`;

  const word = $("levelWord");
  word.textContent = "";
  const parts = cancelled ? ["Alert cancelled by Civil Protection"] : (LEVEL_WORDS[a.level] || ["EMERGENCY ALERT"]);
  parts.forEach((p, i) => {
    if (i) word.appendChild(Object.assign(document.createElement("span"), { className: "sep", textContent: " · " }));
    word.appendChild(Object.assign(document.createElement("span"), { textContent: p }));
  });

  const head = texts?.headline?.[a.level] || {};
  const h = $("headline");
  if (cancelled) {
    const was = (LEVEL_WORDS[a.level] || ["alert"]).join(" · ");
    h.textContent = `The earlier "${was}" message was cancelled. Follow instructions from Civil Protection.`;
    h.removeAttribute("dir"); h.lang = "en";
  } else {
    const hl = head[lang] ? lang : "en";
    h.textContent = head[hl] || "";
    h.lang = hl; h.dir = RTL.includes(hl) ? "rtl" : "ltr";
  }
  $("village").textContent = a.village_name || "";

  const urgent = !cancelled && (a.level === "leave_now" || a.level === "get_ready");
  const hasMinutes = urgent && a.minutes_left !== null && a.minutes_left !== undefined;
  $("minutesBox").classList.toggle("hidden", !hasMinutes);
  if (hasMinutes) $("minutes").textContent = a.minutes_left;

  const fireDir = COMPASS[a.fire_direction];
  const showFire = !cancelled && a.level !== "preventive" && fireDir && a.distance_km != null;
  $("fireLine").classList.toggle("hidden", !showFire);
  if (showFire) $("fireLine").textContent = `Fire ${Number(a.distance_km).toFixed(1)} km to the ${fireDir[1]} (${a.fire_direction})`;

  const leave = COMPASS[a.leave_toward];
  const showLeave = urgent && leave;
  $("leaveBox").classList.toggle("hidden", !showLeave);
  if (showLeave) {
    $("arrow").style.transform = `rotate(${leave[0]}deg)`;
    $("leaveWord").textContent = `${leave[1]} (${a.leave_toward})`;
  }

  $("age").classList.toggle("hidden", cancelled || a.data_age_min == null);
  $("age").textContent = ageText(a.data_age_min);

  const box = $("texts");
  box.textContent = "";
  if (!cancelled) {
    const names = texts?.language_names || NAMES;
    const langs = Object.keys(a.texts || {}).filter((l) => a.texts[l]);
    langs.sort((x, y) => rank(x) - rank(y));
    langs.forEach((l) => {
      const p = document.createElement("p");
      p.className = "msg"; p.lang = l; p.dir = RTL.includes(l) ? "rtl" : "ltr";
      const tag = document.createElement("span");
      tag.className = "lang"; tag.textContent = names[l] || l;
      p.append(tag, document.createTextNode(a.texts[l]));
      box.appendChild(p);
    });
  }
  $("dismissBtn").textContent = cancelled ? "OK" : "Dismiss";
}

function rank(l) { return l === lang ? -1 : (ORDER.indexOf(l) + 1 || ORDER.length + 1); }

function ageText(m) {
  if (m == null) return "";
  return m < 60 ? `Satellite pass ${m} min ago` : `Satellite pass ${Math.floor(m / 60)} h ${m % 60} min ago`;
}

// ---------------------------------------------------------------- sound and vibration (no audio file needed)
function tone(sec, freq, gain) {
  if (!audioCtx) return;
  const o = audioCtx.createOscillator(), g = audioCtx.createGain();
  o.frequency.value = freq; g.gain.value = gain;
  o.connect(g).connect(audioCtx.destination);
  o.start(); o.stop(audioCtx.currentTime + sec);
}

// Two-tone siren (853 / 960 Hz, the cell-broadcast attention tones), alternating every 0.5 s.
// A 1 Hz square LFO swings the carrier frequency, so it loops forever without timers until stopAlarm().
function startAlarm() {
  stopAlarm();
  if (VIBRATE && navigator.vibrate) {
    navigator.vibrate(VIBRATE);
    vibrateTimer = setInterval(() => navigator.vibrate(VIBRATE), 3000);
  }
  if (!audioCtx) return;                                  // not armed: browsers block sound without a tap
  audioCtx.resume?.();
  const o = audioCtx.createOscillator(), lfo = audioCtx.createOscillator();
  const depth = audioCtx.createGain(), g = audioCtx.createGain();
  o.type = "square"; o.frequency.value = (853 + 960) / 2;
  lfo.type = "square"; lfo.frequency.value = 1;
  depth.gain.value = (960 - 853) / 2;
  g.gain.value = 0.5;
  lfo.connect(depth).connect(o.frequency);
  o.connect(g).connect(audioCtx.destination);
  o.start(); lfo.start();
  siren = { o, lfo, g };
}

function stopAlarm() {
  if (siren) {
    try { siren.o.stop(); siren.lfo.stop(); siren.g.disconnect(); } catch (_) { /* already stopped */ }
    siren = null;
  }
  if (vibrateTimer) { clearInterval(vibrateTimer); vibrateTimer = null; }
  navigator.vibrate?.(0);
}
