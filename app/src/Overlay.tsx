import { useEffect, useRef, useState } from "react";
import { GazeHeatmap } from "./lib/gaze-heatmap.js";
import type { LiveState, Rect } from "./lib/types";

/**
 * Gaze halo (Tom): a honeycomb of very transparent red cells around the estimated gaze, sized by the
 * tracker's uncertainty. Desktop targets are not known here yet, so the cloud is gaze-only; pass them
 * with heat.setTargets() once they come from accessibility / Holo element localization.
 */
function GazeHalo({ uncertaintyPx }: { uncertaintyPx?: number }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const heat = useRef<GazeHeatmap | null>(null);
  useEffect(() => {
    if (!canvas.current || !window.companion?.onGaze) return;
    const h = new GazeHeatmap({ canvas: canvas.current });
    h.setTargets([]);
    h.start();
    heat.current = h;
    const off = window.companion.onGaze((sample) => h.push(sample));
    return () => { off(); h.stop(); heat.current = null; };
  }, []);
  useEffect(() => { heat.current?.setUncertainty(uncertaintyPx); }, [uncertaintyPx]);
  return <canvas ref={canvas} data-testid="gaze-halo"
    style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }} />;
}

function Zone({
  rect,
  label,
  sent,
}: {
  rect: Rect;
  label: string;
  sent: boolean;
}) {
  return (
    <div
      className={`screen-zone ${sent ? "screen-zone-sent" : "screen-zone-candidate"}`}
      style={{
        left: rect.x,
        top: rect.y,
        width: rect.width,
        height: rect.height,
      }}
    >
      <span>{label}</span>
    </div>
  );
}

export default function Overlay() {
  const [state, setState] = useState<LiveState | null>(null);
  useEffect(() => {
    document.documentElement.classList.add("overlay-document");
    let active = true;
    const bridge = window.companion;
    if (!bridge)
      return () => {
        document.documentElement.classList.remove("overlay-document");
      };
    const unsubscribe = bridge.onState((value) => {
      if (active) setState(value);
    });
    void bridge
      .getState()
      .then((value) => {
        if (active) setState(value);
      })
      .catch(() => undefined);
    return () => {
      active = false;
      unsubscribe();
      document.documentElement.classList.remove("overlay-document");
    };
  }, []);
  const target = state?.benchmarkTarget;
  useEffect(() => {
    if (!target) return;
    let second = 0;
    // Acknowledge after two animation frames, not merely when React receives
    // the coordinates. Main records receipt on its own monotonic clock.
    const first = requestAnimationFrame(() => {
      second = requestAnimationFrame(() => window.companion.reportTargetPresented({ runId: target.runId, index: target.index }));
    });
    return () => { cancelAnimationFrame(first); cancelAnimationFrame(second); };
  }, [target?.runId, target?.index]);
  if (!state) return null;
  if (target) return <div className="screen-overlay" aria-hidden="true">
    <div data-testid="benchmark-target" style={{
      position: 'absolute', left: target.x - target.radius, top: target.y - target.radius,
      width: 2 * target.radius, height: 2 * target.radius, borderRadius: '50%',
      boxSizing: 'border-box', background: '#ef233c', border: '2px solid white',
    }} />
  </div>;
  const showCaptured = state.observation?.status === 'running' || state.settings.regionScope === 'window';
  return (
    <div className="screen-overlay" aria-hidden="true">
      {state.tracker.state === "tracking" && <GazeHalo uncertaintyPx={state.tracker.calibrationErrorPx} />}
      {showCaptured && state.observed && (
        <Zone rect={state.observed.rect} label="DERNIÈRE CAPTURE LOCALE" sent={false} />
      )}
      {!showCaptured && state.candidate && (
        <Zone rect={state.candidate} label="ZONE CANDIDATE" sent={false} />
      )}
      {state.sent && (
        <Zone
          rect={state.sent.rect}
          label={`ENVOYÉE À HOLO · ${state.sent.frameId}`}
          sent
        />
      )}
    </div>
  );
}
