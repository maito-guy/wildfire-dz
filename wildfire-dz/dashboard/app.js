// Civil Protection dashboard. Vanilla JS + Leaflet, no build step. Talks only to the API contract (docs/contracts.md).
const API = "";            // same origin: the API serves this page
const POLL_MS = 3000;      // refresh villages/alerts while a fire is active

const map = L.map("map").setView([36.6, 4.1], 10);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 17, attribution: "© OpenStreetMap contributors · fire data NASA FIRMS",
}).addTo(map);

const layers = {
  zones: L.layerGroup().addTo(map),
  burning: L.layerGroup().addTo(map),
  truth: L.layerGroup().addTo(map),
  villages: L.layerGroup().addTo(map),
};
const $ = (id) => document.getElementById(id);
const state = { fireId: null, replay: null, pass: 0, timer: null, startMode: false };

async function api(path, opts = {}) {
  const r = await fetch(API + path, { headers: { "Content-Type": "application/json" }, ...opts });
  if (!r.ok) throw new Error(`${path}: ${r.status} ${await r.text()}`);
  return r.json();
}

function wind() { return { speed_kmh: +$("windKmh").value, from_deg: +$("windFrom").value % 360 }; }

function fmtAge(min) {
  if (min == null) return "no data yet";
  return min < 60 ? `satellite pass ${min} min ago` : `satellite pass ${Math.floor(min / 60)} h ${min % 60} min ago`;
}

async function predict(burning, time, observedAt, fireId) {
  const body = { burning, wind: wind(), model: "auto" };
  if (time) body.time = time;
  if (observedAt) body.observed_at = observedAt;
  if (fireId) body.fire_id = fireId;
  const p = await api("/predict", { method: "POST", body: JSON.stringify(body) });
  state.fireId = p.fire_id;
  drawPrediction(p, burning);
  await refresh();
  return p;
}

function drawPrediction(p, burning) {
  layers.zones.clearLayers();
  layers.burning.clearLayers();
  const colors = { 60: "#b00020", 120: "#e07000" };
  [...p.zones.features].sort((a, b) => b.properties.horizon_min - a.properties.horizon_min).forEach((f) => {
    const h = f.properties.horizon_min;
    L.geoJSON(f, { style: { color: colors[h], weight: 2, fillOpacity: h === 60 ? 0.35 : 0.2 } })
      .bindTooltip(`${h / 60} h zone`).addTo(layers.zones);
  });
  burning.forEach((b) => L.circleMarker([b.lat, b.lon], { radius: 3, color: "#000", fillColor: "#ff3d00", fillOpacity: 1, weight: 1 }).addTo(layers.burning));
  $("age").textContent = fmtAge(p.data_age_min);
  $("stale").classList.toggle("hidden", !p.data_stale);
  $("model").textContent = `model ${p.model}${p.fallback_reason ? " (fallback)" : ""}${p.embers_applied ? " · embers rule" : ""} · wind ${p.wind_source}`;
}

async function refresh() {
  if (!state.fireId) return;
  const v = await api(`/villages/at-risk?fire_id=${encodeURIComponent(state.fireId)}`);
  const ol = $("villages"); ol.innerHTML = ""; layers.villages.clearLayers();
  v.villages.forEach((x) => {
    const li = document.createElement("li");
    const mins = x.minutes_left == null ? "> 2 h" : `${x.minutes_left} min`;
    li.innerHTML = `<span class="badge ${x.status}">${x.status.replace("_", " ")}</span>
      <span class="name">${x.name}</span><span>${mins}</span><span class="small">→ ${x.leave_toward}</span>`;
    const send = document.createElement("button"); send.textContent = "Send";
    send.onclick = () => api("/alerts", { method: "POST", body: JSON.stringify({ village_id: x.id, fire_id: state.fireId, level: "leave_now" }) }).then(refresh);
    li.appendChild(send);
    if (x.last_alert_id) {
      const cancel = document.createElement("button"); cancel.textContent = "Cancel";
      cancel.onclick = () => api(`/alerts/${x.last_alert_id}/cancel`, { method: "POST" }).then(refresh);
      li.appendChild(cancel);
    }
    ol.appendChild(li);
    if (x.status !== "safe") {
      L.circleMarker([x.lat, x.lon], { radius: 6, color: "#fff", weight: 2, fillColor: x.status === "leave_now" ? "#b00020" : "#e07000", fillOpacity: 1 })
        .bindTooltip(`${x.name}: ${mins}`).addTo(layers.villages);
    }
  });
  const alerts = await api(`/alerts?fire_id=${encodeURIComponent(state.fireId)}`);
  const al = $("alerts"); al.innerHTML = "";
  alerts.slice().reverse().forEach((a) => {
    const li = document.createElement("li");
    if (a.status === "cancelled") li.classList.add("cancelled");
    li.innerHTML = `<span class="badge ${a.level}">${a.level.replace("_", " ")}</span>
      <span class="name">${a.village_name}</span><span class="small">${a.source} · ${new Date(a.created_at).toLocaleTimeString()}</span>`;
    al.appendChild(li);
  });
}

// ---------------------------------------------------------------- replay
async function loadFires() {
  const fires = await api("/replay");
  $("fire").innerHTML = fires.map((f) => `<option value="${f.fire_id}">${f.name}</option>`).join("");
  await loadReplay(fires[0].fire_id);
}

async function loadReplay(id) {
  state.replay = await api(`/replay/${encodeURIComponent(id)}`);
  state.pass = 0;
  await api("/reset", { method: "POST" });
  await showPass();
  const b = state.replay.passes[0].burning[0];
  map.setView([b.lat, b.lon], 11);
}

async function showPass() {
  const r = state.replay, i = state.pass, p = r.passes[i];
  await predict(p.burning, p.t, p.t, r.fire_id);
  layers.truth.clearLayers();
  const nxt = r.passes[i + 1];
  if (nxt && $("showTruth").checked) {
    nxt.burning.forEach((b) => L.circleMarker([b.lat, b.lon], { radius: 2, color: "#000", fillOpacity: 0.8, weight: 0 }).addTo(layers.truth));
  }
  const gap = nxt ? Math.round((new Date(nxt.t) - new Date(p.t)) / 60000) : null;
  $("passInfo").textContent = `pass ${i + 1}/${r.passes.length} · ${new Date(p.t).toUTCString()} · ${p.satellite || ""}` +
    (gap != null ? ` · next pass in ${gap} min (black dots)` : " · last pass") + (r.stub ? " · STUB DATA" : "");
}

$("fire").onchange = (e) => loadReplay(e.target.value);
$("prev").onclick = () => { if (state.pass > 0) { state.pass--; showPass(); } };
$("next").onclick = () => { if (state.pass < state.replay.passes.length - 1) { state.pass++; showPass(); } };
$("play").onclick = () => {
  if (state.timer) { clearInterval(state.timer); state.timer = null; $("play").textContent = "Play"; return; }
  $("play").textContent = "Pause";
  state.timer = setInterval(() => {
    if (state.pass >= state.replay.passes.length - 1) { $("play").click(); return; }
    state.pass++; showPass();
  }, 2500);
};
$("showTruth").onchange = showPass;

// ---------------------------------------------------------------- start a fire here
$("startMode").onclick = () => {
  state.startMode = !state.startMode;
  $("startMode").classList.toggle("active", state.startMode);
  map.getContainer().style.cursor = state.startMode ? "crosshair" : "";
};
map.on("click", async (e) => {
  if (!state.startMode) return;
  state.startMode = false; $("startMode").classList.remove("active"); map.getContainer().style.cursor = "";
  layers.truth.clearLayers();
  const t = new Date().toISOString();
  try { await predict([{ lat: e.latlng.lat, lon: e.latlng.lng }], t, t, null); }
  catch (err) { $("passInfo").textContent = err.message; }
});
$("reset").onclick = async () => { await api("/reset", { method: "POST" }); state.fireId = null; Object.values(layers).forEach((l) => l.clearLayers()); $("villages").innerHTML = ""; $("alerts").innerHTML = ""; };

setInterval(() => refresh().catch(console.error), POLL_MS);
loadFires().catch((e) => { $("passInfo").textContent = e.message; });
