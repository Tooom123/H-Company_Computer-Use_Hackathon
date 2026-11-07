import { useEffect, useState } from "react";
import type { LiveState, Rect } from "./lib/types";

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
  if (!state) return null;
  const showCaptured = state.observation?.status === 'running' || state.settings.regionScope === 'window';
  return (
    <div className="screen-overlay" aria-hidden="true">
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
