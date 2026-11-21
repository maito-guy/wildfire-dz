// Civil Protection dashboard (docs/DESIGN.md). Talks only to the API contract (docs/contracts.md)
// through src/api/client.ts.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { lazy, Suspense, useEffect, useEffectEvent, useRef, useState } from "react";
import { toast } from "sonner";
import type { LatLon, PredictResponse, Replay, Village } from "./api/client";
import { api, ApiError } from "./api/client";
import { useFireData } from "./api/fireMap";
import { fetchRisk, RISK_KEY } from "./api/risk";
import { ApprovalQueue } from "./components/ApprovalQueue";
import type { WindInput } from "./components/Controls";
import { Controls } from "./components/Controls";
import type { HealthState, Mode } from "./components/Header";
import { Banners, ModeBar, StatusPill } from "./components/Header";
import type { Basemap, LayerKey, LayerVisibility, MapView } from "./components/map/FireMap";
import { MapControls } from "./components/map/MapOverlays";
import { RiskPanel } from "./components/RiskPanel";
import { Scoreboard } from "./components/Scoreboard";
import { Settings } from "./components/Settings";
import type { SendLevel } from "./components/VillageList";
import { VillageList } from "./components/VillageList";
import { fmtClock, sortByUrgency, statusWord, windSourceWord } from "./format";
import { useLiveEvents } from "./hooks/useEventSource";
import { useTheme } from "./lib/theme";
import { CaretDown } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { Toaster } from "@/components/ui/sonner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn, floating } from "@/lib/utils";

// MapLibre is most of the JS: load it after the lists, so the operator sees villages first on slow links.
const FireMap = lazy(() => import("./components/map/FireMap").then((m) => ({ default: m.FireMap })));

const POLL_MS = 3000; // refresh villages/alerts while a fire is active
const HEALTH_MS = 5000; // phones/dashboards connected, pending alerts
const PLAY_MS = 2500; // one replay pass every 2.5 s
const RISK_MS = 60_000; // today's risk; reading it also (re)creates the day's preventive flags

const DEFAULT_LAYERS: LayerVisibility = {
  burning: true,
  zone1h: true,
  zone2h: true,
  ai: true, // drawn only when /predict has an `ai` block (replays with model C's answers)
  villages: true,
  alertAreas: true,
  nextPass: true,
  detections: true,
  history: false,
  risk: false,
};

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
    `pass ${i + 1}/${r.passes.length} · ${new Date(p.t).toUTCString().slice(5, 22)} UTC · ${p.satellite ?? ""}` +
    (gap != null ? ` · next pass in ${gap} min` : " · last pass")
  );
}

export default function App() {
  const queryClient = useQueryClient();
  const live = useLiveEvents(); // GET /events: refreshes alerts and villages on every flag/alert event

  const [wind, setWind] = useState<WindInput>({ speedKmh: 30, fromDeg: 270 });
  const [appMode, setAppMode] = useState<Mode>("replay");
  const [layers, setLayers] = useState<LayerVisibility>(DEFAULT_LAYERS);
  const [tab, setTab] = useState("villages");
  const [panelOpen, setPanelOpen] = useState(true);
  const [basemap, setBasemap] = useState<Basemap>("normal");
  const [theme, toggleTheme] = useTheme();
  const [scoreOpen, setScoreOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [demoStartedAt, setDemoStartedAt] = useState<string | null>(null);
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

  // Ignore late /predict answers when a newer one was asked for (play, fast clicks).
  const predictSeq = useRef(0);
  const cShownRef = useRef(false); // model C shown on the last answer (D-18)

  const healthQ = useQuery({
    queryKey: ["health"],
    queryFn: ({ signal }) => api.health(signal),
    refetchInterval: HEALTH_MS,
  });

  const fires = useQuery({ queryKey: ["replays"], queryFn: api.replays });
  const riskQ = useQuery({ queryKey: RISK_KEY, queryFn: fetchRisk, refetchInterval: RISK_MS });
  const fireData = useFireData(); // satellite detections and fire history (#29)
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
    // D-18: when model C answers (replays), its "likely" zones replace B's on the map; B returns as the fallback.
    const c = p.model === "C";
    if (c !== cShownRef.current) {
      cShownRef.current = c;
      setLayers((l) =>
        c ? { ...l, zone1h: false, zone2h: false, nextPass: false, detections: false } : { ...l, zone1h: true, zone2h: true },
      );
    }
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
    if (appMode !== "demo") return;
    setPlaying(false);
    setMode("start");
    const t = new Date().toISOString();
    try {
      await predict([p], t, null);
      setDemoStartedAt(t);
    } catch (e) {
      setInfo(errorText(e));
    }
  }

  // Clears the fire on screen (not on the server: alerts already sent stay sent).
  function clearFire() {
    predictSeq.current++;
    setFireId(null);
    setPrediction(null);
    setBurning([]);
    setDemoStartedAt(null);
  }

  function changeMode(m: Mode) {
    if (m === appMode) return;
    setPlaying(false);
    setInfo("");
    setAppMode(m);
    if (m === "replay") {
      if (replay) void showPass(replay, pass);
      else if (fires.data?.[0]) void loadReplay(fires.data[0].fire_id);
    } else {
      setMode("start");
      clearFire();
      if (m === "live") setLayers((l) => ({ ...l, detections: true, history: true, risk: true }));
    }
  }

  async function onSend(vs: Village[], level: SendLevel): Promise<boolean> {
    setBusy(true);
    try {
      for (const v of vs) await api.sendAlert({ village_id: v.id, fire_id: fireId, level });
      const phones = healthQ.data?.phones_connected;
      toast.success(
        `${statusWord(level).toUpperCase()} sent to ${vs.map((v) => v.name).join(", ")}` +
          (phones != null ? ` · ${phones} ${phones === 1 ? "phone" : "phones"} connected` : ""),
      );
      setInfo("");
      return true;
    } catch (e) {
      setInfo(errorText(e));
      return false;
    } finally {
      setBusy(false);
      await refresh();
    }
  }

  async function onCancel(ids: string[]): Promise<boolean> {
    setBusy(true);
    try {
      for (const id of ids) await api.cancelAlert(id);
      toast.success(`${ids.length} ${ids.length === 1 ? "alert" : "alerts"} cancelled · phones show CANCELLED`);
      setInfo("");
      return true;
    } catch (e) {
      setInfo(errorText(e));
      return false;
    } finally {
      setBusy(false);
      await refresh();
    }
  }

  async function onReset() {
    setPlaying(false);
    try {
      await api.reset();
    } catch (e) {
      setInfo(errorText(e));
      return;
    }
    void queryClient.invalidateQueries({ queryKey: RISK_KEY }); // brings today's preventive flags back
    clearFire();
    setMode("start"); // hides the "really burned" layer until a pass is shown again
    setInfo("");
    queryClient.removeQueries({ queryKey: ["villages"] });
    queryClient.removeQueries({ queryKey: ["alerts"] });
    toast.success("Demo reset · every alert cleared");
  }

  const truth = mode === "replay" && replay ? (replay.passes[pass + 1]?.burning ?? []) : [];
  const passInfo = replay && mode === "replay" && prediction ? passInfoText(replay, pass) : "";
  const demoInfo =
    appMode === "demo" && prediction && demoStartedAt
      ? `Started ${fmtClock(demoStartedAt)} by map click · weather: ${windSourceWord(prediction.wind_source)} · ` +
        `model ${prediction.model}${prediction.embers_applied ? " · embers rule on" : ""} · click again to move it`
      : "";
  const setLayer = (k: LayerKey, v: boolean) => setLayers((l) => ({ ...l, [k]: v }));
  const cShown = prediction?.model === "C";
  const pending = healthQ.data?.pending_alerts ?? 0;
  const health: HealthState = { data: healthQ.data, unreachable: healthQ.isError, updatedAt: healthQ.dataUpdatedAt };
  // A tab click on a hidden panel opens it again.
  const openTab = (t: string) => {
    setTab(t);
    setPanelOpen(true);
  };
  const reopen = (t: string) => t === tab && setPanelOpen(true);
  const focus = (lat: number, lon: number, zoom: number) =>
    setView((v) => ({ center: [lat, lon], zoom, seq: (v?.seq ?? 0) + 1 }));

  return (
    <div className="relative h-dvh overflow-hidden bg-map-land">
      {/* Map first (DESIGN2 §1): full-bleed, everything else floats above it. */}
      <Suspense
        fallback={
          <div className="absolute inset-0 grid place-items-center font-mono text-xs text-muted-foreground">Loading map…</div>
        }
      >
        <FireMap
          prediction={prediction}
          burning={burning}
          truth={truth}
          villages={villages}
          alerts={alerts}
          detections={fireData.detections.data}
          history={fireData.history.data}
          risk={riskQ.data}
          layers={layers}
          view={view}
          basemap={basemap}
          demo={appMode === "demo"}
          onMapClick={onMapClick}
        />
      </Suspense>

      {/* Phone: one column (bar, status, panel at the bottom). Desktop: work column left, map tools right. */}
      <div className="pointer-events-none absolute inset-3 z-20 flex flex-col gap-2 pb-[env(safe-area-inset-bottom)] lg:inset-3 lg:flex-row lg:items-start lg:justify-between lg:gap-3">
        <div className="contents lg:flex lg:h-full lg:w-[360px] lg:shrink-0 lg:flex-col lg:gap-2">
          <div className="order-1 lg:order-none">
            <ModeBar mode={appMode} onMode={changeMode} theme={theme}>
              <Controls
                mode={appMode}
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
                stub={!!replay?.stub}
                demoInfo={demoInfo}
                info={info || (fires.error ? errorText(fires.error) : "")}
                wind={wind}
                onWind={setWind}
                onReset={onReset}
              />
            </ModeBar>
          </div>

          <aside
            className={floating(
              "glass-strong order-4 mt-auto flex min-h-0 flex-col overflow-hidden lg:order-none lg:mt-0",
              panelOpen ? "max-h-[64vh] lg:max-h-none lg:flex-1" : "",
            )}
          >
            <Tabs value={tab} onValueChange={openTab} className="flex min-h-0 flex-1 flex-col gap-0">
              <div className="flex items-center gap-1 p-2">
                <TabsList className="grid h-8 flex-1 grid-cols-3 rounded-[10px] bg-secondary p-[3px]">
                  <TabsTrigger value="villages" onClick={() => reopen("villages")}>
                    Villages
                  </TabsTrigger>
                  <TabsTrigger value="approval" onClick={() => reopen("approval")}>
                    Approval
                    {pending > 0 && (
                      <span className="rounded-full bg-fire px-1.5 font-mono text-[11px] text-fire-foreground tabular-nums">{pending}</span>
                    )}
                  </TabsTrigger>
                  <TabsTrigger value="risk" onClick={() => reopen("risk")}>
                    Risk today
                  </TabsTrigger>
                </TabsList>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={() => setPanelOpen((o) => !o)}
                  aria-expanded={panelOpen}
                  aria-label={panelOpen ? "Hide panel" : "Show panel"}
                  title={panelOpen ? "Hide panel" : "Show panel"}
                >
                  <CaretDown weight="bold" className={cn("transition-transform duration-200", !panelOpen && "rotate-180")} />
                </Button>
              </div>
              {panelOpen && (
                <>
                  <TabsContent value="villages" className="flex min-h-0 flex-1 flex-col">
                    <VillageList
                      villages={villages}
                      alerts={alerts}
                      busy={busy}
                      onSend={onSend}
                      onCancel={onCancel}
                      onFocus={(v) => focus(v.lat, v.lon, 13)}
                    />
                  </TabsContent>
                  <TabsContent value="approval" className="flex min-h-0 flex-1 flex-col">
                    <ApprovalQueue live={live.state} onSelect={(a) => focus(a.area.lat, a.area.lon, 13)} />
                  </TabsContent>
                  <TabsContent value="risk" className="flex min-h-0 flex-1 flex-col">
                    <RiskPanel
                      risk={riskQ.data}
                      error={riskQ.error ? errorText(riskQ.error) : ""}
                      onSelect={(p) => {
                        setLayer("risk", true);
                        focus(p.lat, p.lon, 11);
                      }}
                    />
                  </TabsContent>
                </>
              )}
            </Tabs>
          </aside>
        </div>

        <div className="order-2 flex flex-col items-end gap-2 lg:order-none">
          <StatusPill
            prediction={prediction}
            health={health}
            theme={theme}
            onTheme={toggleTheme}
            onScoreboard={() => setScoreOpen(true)}
            onSettings={() => setSettingsOpen(true)}
          />
          <MapControls basemap={basemap} onBasemap={setBasemap} layers={layers} onLayer={setLayer} aiAvailable={!!prediction?.ai} cShown={cShown} risk={riskQ.data} />
        </div>

        <div className="order-3 lg:absolute lg:left-1/2 lg:top-0 lg:w-max lg:max-w-md lg:-translate-x-1/2">
          <Banners health={health} live={live.state} prediction={prediction} />
        </div>
      </div>

      <Scoreboard open={scoreOpen} onOpenChange={setScoreOpen} />
      <Settings open={settingsOpen} onOpenChange={setSettingsOpen} />
      <Toaster theme={theme} />
    </div>
  );
}
