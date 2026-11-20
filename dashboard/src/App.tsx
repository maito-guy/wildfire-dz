// Civil Protection dashboard. Talks only to the API contract (docs/contracts.md) through src/api/client.ts.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useEffectEvent, useRef, useState } from "react";
import type { LatLon, PredictResponse, Replay, Village } from "./api/client";
import { api, ApiError } from "./api/client";
import { fetchRisk, RISK_KEY } from "./api/risk";
import { AlertLog } from "./components/AlertLog";
import { ApprovalQueue } from "./components/ApprovalQueue";
import type { WindInput } from "./components/Controls";
import { Controls } from "./components/Controls";
import type { MapView } from "./components/FireMap";
import { FireMap } from "./components/FireMap";
import { Header } from "./components/Header";
import { RiskLayer } from "./components/RiskLayer";
import { RiskPanel } from "./components/RiskPanel";
import { Scoreboard } from "./components/Scoreboard";
import { Settings } from "./components/Settings";
import { VillageList } from "./components/VillageList";
import { sortByUrgency } from "./format";
import { useLiveEvents } from "./hooks/useEventSource";

const POLL_MS = 3000; // refresh villages/alerts while a fire is active
const HEALTH_MS = 5000; // phones/dashboards connected, pending alerts
const PLAY_MS = 2500; // one replay pass every 2.5 s
const RISK_MS = 60_000; // today's risk; reading it also (re)creates the day's preventive flags

function errorText(e: unknown): string {
  if (e instanceof ApiError && e.status === 401) {
    return `${e.message} — set the operator token in Settings.`;
  }
  return e instanceof Error ? e.message : String(e);
}

function passInfoText(r: Replay, i: number): string {
  const p = r.passes[i];
  const nxt = r.passes[i + 1];
  const gap = nxt ? Math.round((Date.parse(nxt.t) - Date.parse(p.t)) / 60000) : null;
  return (
    `pass ${i + 1}/${r.passes.length} · ${new Date(p.t).toUTCString()} · ${p.satellite ?? ""}` +
    (gap != null ? ` · next pass in ${gap} min (black dots)` : " · last pass") +
    (r.stub ? " · STUB DATA" : "")
  );
}

export default function App() {
  const queryClient = useQueryClient();
  const live = useLiveEvents(); // GET /events: refreshes alerts and villages on every flag/alert event

  const [wind, setWind] = useState<WindInput>({ speedKmh: 30, fromDeg: 270 });
  const [showTruth, setShowTruth] = useState(true);
  const [startMode, setStartMode] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [info, setInfo] = useState("");
  const [busy, setBusy] = useState(false);

  const [fireId, setFireId] = useState<string | null>(null); // fire on the map (from /predict)
  const [prediction, setPrediction] = useState<PredictResponse | null>(null);
  const [burning, setBurning] = useState<LatLon[]>([]);
  const [mode, setMode] = useState<"replay" | "start">("replay");

  const [selectedFire, setSelectedFire] = useState("");
  const [replay, setReplay] = useState<Replay | null>(null);
  const [pass, setPass] = useState(0);
  const [view, setView] = useState<MapView | null>(null);
  const [showRisk, setShowRisk] = useState(false);

  // Ignore late /predict answers when a newer one was asked for (play, fast clicks).
  const predictSeq = useRef(0);

  const healthQ = useQuery({
    queryKey: ["health"],
    queryFn: ({ signal }) => api.health(signal),
    refetchInterval: HEALTH_MS,
  });

  const fires = useQuery({ queryKey: ["replays"], queryFn: api.replays });
  const riskQ = useQuery({ queryKey: RISK_KEY, queryFn: fetchRisk, refetchInterval: RISK_MS });
  const villagesQ = useQuery({
    queryKey: ["villages", fireId],
    queryFn: () => api.villagesAtRisk(fireId!),
    enabled: fireId != null,
    refetchInterval: POLL_MS,
  });
  const alertsQ = useQuery({
    queryKey: ["alerts", fireId],
    queryFn: () => api.alerts(fireId!),
    enabled: fireId != null,
    refetchInterval: POLL_MS,
  });

  const villages = fireId ? sortByUrgency(villagesQ.data?.villages ?? []) : [];
  const alerts = fireId ? (alertsQ.data ?? []) : [];

  const refresh = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: ["villages"] }),
      queryClient.invalidateQueries({ queryKey: ["alerts"] }),
    ]);

  async function predict(points: LatLon[], time: string, id: string | null) {
    const seq = ++predictSeq.current;
    const p = await api.predict({
      burning: points,
      time,
      observed_at: time,
      model: "auto",
      wind: { speed_kmh: wind.speedKmh, from_deg: ((wind.fromDeg % 360) + 360) % 360 },
      ...(id ? { fire_id: id } : {}),
    });
    if (seq !== predictSeq.current) return;
    setPrediction(p);
    setBurning(points);
    setFireId(p.fire_id);
    setInfo("");
    await refresh();
  }

  async function showPass(r: Replay, i: number) {
    setPass(i);
    setMode("replay");
    try {
      await predict(r.passes[i].burning, r.passes[i].t, r.fire_id);
    } catch (e) {
      setInfo(errorText(e));
      setPlaying(false);
    }
  }

  async function loadReplay(id: string) {
    setSelectedFire(id);
    setPlaying(false);
    try {
      const r = await queryClient.fetchQuery({ queryKey: ["replay", id], queryFn: () => api.replay(id) });
      setReplay(r);
      let resetError = "";
      try {
        await api.reset();
        void queryClient.invalidateQueries({ queryKey: RISK_KEY }); // brings today's preventive flags back
      } catch (e) {
        resetError = `Reset before replay failed: ${errorText(e)}`;
      }
      const first = r.passes[0]?.burning[0];
      if (first) setView((v) => ({ center: [first.lat, first.lon], zoom: 11, seq: (v?.seq ?? 0) + 1 }));
      await showPass(r, 0);
      if (resetError) setInfo(resetError); // after showPass, which clears the message on success
    } catch (e) {
      setInfo(errorText(e));
    }
  }

  // First load: open the first replay fire, like the vanilla dashboard did.
  const loaded = useRef(false);
  const onFiresLoaded = useEffectEvent((id: string) => {
    void loadReplay(id);
  });
  useEffect(() => {
    const first = fires.data?.[0];
    if (first && !loaded.current) {
      loaded.current = true;
      onFiresLoaded(first.fire_id);
    }
  }, [fires.data]);

  const lastPass = replay ? replay.passes.length - 1 : 0;
  const canPrev = replay != null && pass > 0;
  const canNext = replay != null && pass < lastPass;

  const onTick = useEffectEvent(() => {
    if (replay && pass < lastPass) void showPass(replay, pass + 1);
    else setPlaying(false);
  });
  useEffect(() => {
    if (!playing) return;
    const t = window.setTimeout(onTick, PLAY_MS);
    return () => window.clearTimeout(t);
  }, [playing, pass]);

  async function onMapClick(p: LatLon) {
    if (!startMode) return;
    setStartMode(false);
    setPlaying(false);
    setMode("start");
    try {
      await predict([p], new Date().toISOString(), null);
    } catch (e) {
      setInfo(errorText(e));
    }
  }

  async function write(action: () => Promise<unknown>) {
    setBusy(true);
    try {
      await action();
      setInfo("");
    } catch (e) {
      setInfo(errorText(e));
    } finally {
      setBusy(false);
      await refresh();
    }
  }

  const onSend = (v: Village) =>
    write(() => api.sendAlert({ village_id: v.id, fire_id: fireId, level: "leave_now" }));
  const onCancel = (alertId: string) => write(() => api.cancelAlert(alertId));

  async function onReset() {
    setPlaying(false);
    try {
      await api.reset();
    } catch (e) {
      setInfo(errorText(e));
      return;
    }
    predictSeq.current++;
    void queryClient.invalidateQueries({ queryKey: RISK_KEY }); // brings today's preventive flags back
    setFireId(null);
    setPrediction(null);
    setBurning([]);
    setMode("start"); // hides the "really burned" layer until a pass is shown again
    setInfo("");
    queryClient.removeQueries({ queryKey: ["villages"] });
    queryClient.removeQueries({ queryKey: ["alerts"] });
  }

  const truth = mode === "replay" && showTruth && replay ? (replay.passes[pass + 1]?.burning ?? []) : [];
  const passInfo = replay && mode === "replay" && prediction ? passInfoText(replay, pass) : "";

  return (
    <div className="app">
      <Header
        prediction={prediction}
        health={{ data: healthQ.data, unreachable: healthQ.isError, updatedAt: healthQ.dataUpdatedAt }}
      />
      <main>
        <FireMap
          prediction={prediction}
          burning={burning}
          truth={truth}
          villages={villages}
          view={view}
          startMode={startMode}
          onMapClick={onMapClick}
        >
          {showRisk && riskQ.data && <RiskLayer risk={riskQ.data} />}
        </FireMap>
        <aside>
          <Controls
            fires={fires.data ?? []}
            fireId={selectedFire}
            onSelectFire={loadReplay}
            canPrev={canPrev}
            canNext={canNext}
            onPrev={() => replay && canPrev && showPass(replay, pass - 1)}
            onNext={() => replay && canNext && showPass(replay, pass + 1)}
            playing={playing}
            onTogglePlay={() => setPlaying((x) => !x)}
            passInfo={passInfo}
            info={info || (fires.error ? errorText(fires.error) : "")}
            startMode={startMode}
            onToggleStartMode={() => setStartMode((x) => !x)}
            wind={wind}
            onWind={setWind}
            showTruth={showTruth}
            onShowTruth={setShowTruth}
            onReset={onReset}
          />
          <RiskPanel
            risk={riskQ.data}
            error={riskQ.error ? errorText(riskQ.error) : ""}
            show={showRisk}
            onShow={setShowRisk}
            onSelect={(p) => {
              setShowRisk(true);
              setView((v) => ({ center: [p.lat, p.lon], zoom: 11, seq: (v?.seq ?? 0) + 1 }));
            }}
          />
          <ApprovalQueue
            live={live.state}
            fireId={fireId}
            villages={villages}
            onSelect={(a) => setView((v) => ({ center: [a.area.lat, a.area.lon], zoom: 13, seq: (v?.seq ?? 0) + 1 }))}
          />
          <VillageList villages={villages} busy={busy} onSend={onSend} onCancel={onCancel} />
          <AlertLog alerts={alerts} />
          <Scoreboard />
          <Settings />
        </aside>
      </main>
    </div>
  );
}
