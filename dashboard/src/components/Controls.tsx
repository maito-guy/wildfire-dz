import type { ReplayFire } from "../api/client";

export interface WindInput {
  speedKmh: number;
  fromDeg: number;
}

interface Props {
  fires: ReplayFire[];
  fireId: string;
  onSelectFire: (id: string) => void;
  canPrev: boolean;
  canNext: boolean;
  onPrev: () => void;
  onNext: () => void;
  playing: boolean;
  onTogglePlay: () => void;
  passInfo: string;
  info: string;
  startMode: boolean;
  onToggleStartMode: () => void;
  wind: WindInput;
  onWind: (w: WindInput) => void;
  showTruth: boolean;
  onShowTruth: (v: boolean) => void;
  onReset: () => void;
}

export function Controls(p: Props) {
  return (
    <section className="controls">
      <div className="row">
        <label>
          Replay{" "}
          <select value={p.fireId} onChange={(e) => p.onSelectFire(e.target.value)}>
            {p.fires.map((f) => (
              <option key={f.fire_id} value={f.fire_id}>
                {f.name}
              </option>
            ))}
          </select>
        </label>
        <button onClick={p.onPrev} disabled={!p.canPrev} aria-label="Previous pass">
          ◀
        </button>
        <button onClick={p.onNext} disabled={!p.canNext} aria-label="Next pass">
          ▶
        </button>
        <button onClick={p.onTogglePlay} disabled={!p.canNext && !p.playing}>
          {p.playing ? "Pause" : "Play"}
        </button>
      </div>
      <div className="row small">{p.passInfo || "—"}</div>
      {p.info && <div className="row small error">{p.info}</div>}
      <div className="row">
        <button className={p.startMode ? "active" : undefined} onClick={p.onToggleStartMode}>
          Start a fire here
        </button>
        <label>
          Wind{" "}
          <input
            type="number"
            min={0}
            max={150}
            value={p.wind.speedKmh}
            onChange={(e) => p.onWind({ ...p.wind, speedKmh: Number(e.target.value) })}
          />{" "}
          km/h
        </label>
        <label>
          from{" "}
          <input
            type="number"
            min={0}
            max={359}
            value={p.wind.fromDeg}
            onChange={(e) => p.onWind({ ...p.wind, fromDeg: Number(e.target.value) })}
          />
          °
        </label>
      </div>
      <div className="row small">
        <label>
          <input type="checkbox" checked={p.showTruth} onChange={(e) => p.onShowTruth(e.target.checked)} /> show
          what really burned next pass
        </label>
        <button className="ghost" onClick={p.onReset}>
          Reset demo
        </button>
      </div>
    </section>
  );
}
