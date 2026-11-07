import { useEffect, useRef, useState } from "react";
import ObservationPanel from "./ObservationPanel";
import type {
  CaptureFrame,
  EncodedImage,
  InferenceResult,
  LiveState,
  RuntimeStatus,
  Settings,
} from "./lib/types";

const defaults: Settings = {
  selection: "gaze",
  roiWidth: 800,
  roiHeight: 600,
  includeGlobal: true,
  overlay: true,
  regionScope: "screen",
};
const selectionLabels = {
  gaze: "Regard",
  head: "Tête",
  hybrid: "Regard + tête",
  cursor: "Curseur",
  full: "Écran complet",
} as const;
const trackerLabels = {
  off: "Caméra arrêtée",
  calibrating: "Calibration",
  tracking: "Suivi actif",
  lost: "Signal indisponible",
  error: "Suivi interrompu",
} as const;
const number = (value: number | null | undefined) =>
  value == null ? "—" : new Intl.NumberFormat("fr-FR").format(value);
const milliseconds = (value: number | null | undefined) =>
  value == null ? "—" : `${number(Math.round(value))} ms`;
const degrees = (value: number | null | undefined) =>
  value == null ? "—" : `${number(Math.round(value))}°`;
const errorText = (error: unknown) =>
  error instanceof Error ? error.message : String(error);

function Brand() {
  return (
    <div className="brand">
      <span className="brand-symbol" aria-hidden="true">
        h<span>·</span>
      </span>
      <div>
        <strong>H-Companion</strong>
        <span>Visual context lab</span>
      </div>
    </div>
  );
}

function ImageCard({
  image,
  title,
  subtitle,
  kind,
}: {
  image: EncodedImage | null;
  title: string;
  subtitle: string;
  kind: "detail" | "global";
}) {
  return (
    <section className={`image-card image-card-${kind}`} aria-label={title}>
      <div className="image-card-heading">
        <div>
          <h3>{title}</h3>
          <p>{subtitle}</p>
        </div>
        {image && (
          <span className="dimension-chip">
            {image.width} × {image.height}
          </span>
        )}
      </div>
      <div className={`image-stage ${image ? "has-image" : ""}`}>
        {image ? (
          <img src={image.dataUrl} alt={title} draggable={false} />
        ) : (
          <div className="empty-image">
            <span className="empty-frame" aria-hidden="true" />
            <p>
              {kind === "detail"
                ? "Votre prochaine observation apparaîtra ici."
                : "Aucun aperçu global dans cette observation."}
            </p>
          </div>
        )}
      </div>
      {image && (
        <details className="image-hash">
          <summary>Empreinte du buffer image</summary>
          <code>SHA-256 {image.sha256}</code>
        </details>
      )}
    </section>
  );
}

export default function App() {
  const bridge = window.companion;
  const [runtime, setRuntime] = useState<RuntimeStatus | null>(null);
  const [selectedModel, setSelectedModel] = useState("");
  const [live, setLive] = useState<LiveState | null>(null);
  const [settings, setSettings] = useState<Settings>(defaults);
  const [widthDraft, setWidthDraft] = useState(String(defaults.roiWidth));
  const [heightDraft, setHeightDraft] = useState(String(defaults.roiHeight));
  const [frame, setFrame] = useState<CaptureFrame | null>(null);
  const [result, setResult] = useState<InferenceResult | null>(null);
  const [prompt, setPrompt] = useState(
    "Décris cette interface et indique comment réaliser la prochaine étape.",
  );
  const [error, setError] = useState<string | null>(null);
  const [operation, setOperation] = useState<string | null>(null);
  const [configurationPending, setConfigurationPending] = useState(0);
  const operationRef = useRef(false);
  const settingsRef = useRef<Settings>(defaults);
  const settingsInitialized = useRef(false);
  const configurationQueue = useRef<Promise<void>>(Promise.resolve());
  const widthInput = useRef<HTMLInputElement>(null);
  const heightInput = useRef<HTMLInputElement>(null);
  const mounted = useRef(true);
  const frameRef = useRef<string | null>(null);

  useEffect(() => {
    mounted.current = true;
    if (!bridge)
      return () => {
        mounted.current = false;
      };
    const acceptState = (state: LiveState) => {
      if (!mounted.current) return;
      setLive(state);
      // Main broadcasts every 100 ms. Older applied settings must not overwrite
      // edits that are still waiting in the configuration queue.
      if (!settingsInitialized.current) {
        settingsInitialized.current = true;
        settingsRef.current = state.settings;
        setSettings(state.settings);
      }
    };
    const unsubscribe = bridge.onState(acceptState);
    void Promise.all([bridge.getStatus(), bridge.getState()])
      .then(([status, state]) => {
        if (mounted.current) {
          setRuntime(status);
          setSelectedModel(status.model);
          acceptState(state);
        }
      })
      .catch((reason) => {
        if (mounted.current) setError(errorText(reason));
      });
    return () => {
      mounted.current = false;
      unsubscribe();
    };
  }, [bridge]);

  useEffect(() => {
    setWidthDraft(String(settings.roiWidth));
  }, [settings.roiWidth]);
  useEffect(() => {
    setHeightDraft(String(settings.roiHeight));
  }, [settings.roiHeight]);

  const run = async (label: string, action: () => Promise<void>) => {
    if (operationRef.current) return;
    operationRef.current = true;
    setOperation(label);
    setError(null);
    try {
      await action();
    } catch (reason) {
      if (mounted.current) setError(errorText(reason));
    } finally {
      operationRef.current = false;
      if (mounted.current) setOperation(null);
    }
  };
  const persistSettings = (next: Settings) => {
    settingsRef.current = next;
    setSettings(next);
    setConfigurationPending((count) => count + 1);
    const request = configurationQueue.current
      .catch(() => {})
      .then(() => bridge.configure(next));
    configurationQueue.current = request;
    const finished = () => {
      if (mounted.current) setConfigurationPending((count) => count - 1);
    };
    void request.then(finished, finished);
    return request;
  };
  const changeSettings = (patch: Partial<Settings>) => {
    void persistSettings({ ...settingsRef.current, ...patch }).catch((reason) => {
      if (mounted.current) setError(errorText(reason));
    });
  };
  const parseDimension = (draft: string) => {
    const value = Number(draft);
    if (!Number.isInteger(value) || value < 64 || value > 8192) {
      throw new Error("La dimension doit être un nombre entier compris entre 64 et 8 192 pixels.");
    }
    return value;
  };
  const commitDimension = (
    dimension: "roiWidth" | "roiHeight",
    draft: string,
  ) => {
    try {
      const value = parseDimension(draft);
      if (value !== settingsRef.current[dimension]) changeSettings({ [dimension]: value });
    } catch (reason) {
      setError(errorText(reason));
    }
  };
  const applyVisibleSettings = () => persistSettings({
    ...settingsRef.current,
    roiWidth: settingsRef.current.selection === "full" ? settingsRef.current.roiWidth : parseDimension(widthInput.current?.value ?? widthDraft),
    roiHeight: settingsRef.current.selection === "full" ? settingsRef.current.roiHeight : parseDimension(heightInput.current?.value ?? heightDraft),
  });
  const clearPreparedFrame = () => {
    frameRef.current = null;
    setFrame(null);
    setResult(null);
  };
  const selectPreparedFrame = (next: CaptureFrame) => {
    frameRef.current = next.frameId;
    setFrame(next);
    setResult(null);
  };
  const startObservation = (options: { durationSeconds: 15 | 30 | 60; showOverlay: boolean }) =>
    void run("observation-start", async () => {
      clearPreparedFrame();
      await applyVisibleSettings();
      await bridge.startObservation(options);
    });
  const calibrate = () => void run("tracker-start", async () => {
    // Calibration follows the selected mode, including a mode write still queued in IPC.
    await configurationQueue.current;
    await bridge.startTracker();
  });
  const capture = () =>
    void run("capture", async () => {
      clearPreparedFrame();
      // A click on Capture also blurs the last edited input. Wait for every
      // queued write and explicitly apply both visible values before capture.
      // Reading the elements also handles native accessibility value edits.
      await applyVisibleSettings();
      const next = await bridge.capture();
      if (!mounted.current) return;
      selectPreparedFrame(next);
    });
  const analyze = () => {
    if (!frame || !prompt.trim()) return;
    const frameId = frame.frameId;
    void run("inference", async () => {
      setResult(null);
      const next = await bridge.analyze({
        frameId,
        prompt: prompt.trim(),
        model: selectedModel,
      });
      if (!mounted.current || frameRef.current !== next.frameId) return;
      setResult(next);
    });
  };
  const cancel = async () => {
    try {
      await bridge.cancel();
    } catch (reason) {
      setError(errorText(reason));
    }
  };

  if (!bridge)
    return (
      <main className="app-shell unavailable">
        <Brand />
        <div className="unavailable-card">
          <span className="eyebrow">Application desktop</span>
          <h1>Ouvrez H-Companion dans Electron.</h1>
          <p>
            La capture d’écran, le suivi du regard et les appels Holo utilisent
            le bridge local de l’application.
          </p>
          <code>cd app &amp;&amp; npm run dev</code>
          <p className="muted">
            Ce navigateur n’est connecté à aucune caméra ni à Holo.
          </p>
        </div>
      </main>
    );

  const observationActive = live?.observation?.status === "running" || live?.observation?.status === "stopping";
  const busy = Boolean(operation || live?.busy || observationActive);
  const inferencePending =
    operation === "inference" || live?.busy === "inference";
  const capturePending = operation === "capture" || live?.busy === "capture";
  const tracker = live?.tracker ?? { state: "off" as const };
  const cameraOn = tracker.state !== "off" && tracker.state !== "error";
  const requiresGaze = settings.selection === "gaze" || settings.selection === "hybrid";
  const requiresHead = settings.selection === "head" || settings.selection === "hybrid";
  const trackingStarted = tracker.state === "tracking" || tracker.state === "lost";
  const needsCalibration = (requiresGaze && (!trackingStarted || tracker.gazeCalibrated === false))
    || (requiresHead && (!trackingStarted || tracker.headCalibrated !== true));
  const calibrationLabel = settings.selection === "head" ? "Calibrer la tête"
    : settings.selection === "hybrid" ? "Calibrer les yeux et la tête" : "Activer le regard et calibrer";
  const headStatus = requiresHead || tracker.headCalibrated
    ? tracker.headMessage || (tracker.headCalibrated ? "Tête calibrée" : "Tête non calibrée")
    : undefined;
  const headAngles = live?.head?.available
    ? `Orientation approximative : rotation ${degrees(live.head.yaw)} · haut/bas ${degrees(live.head.pitch)} · inclinaison ${degrees(live.head.roll)}`
    : undefined;
  const sent = Boolean(frame && live?.sent?.frameId === frame.frameId);
  const shownResult = result?.frameId === frame?.frameId ? result : null;
  const isSimulated = Boolean(frame?.simulated || shownResult?.simulated);
  const canCapture = Boolean(
    runtime?.captureAvailable && !busy && tracker.state !== "calibrating",
  );
  const canAnalyze = Boolean(
    frame && runtime?.apiKeyConfigured && !busy && prompt.trim() && selectedModel,
  );
  const availableModels = runtime
    ? [...new Set([runtime.model, ...(runtime.models ?? [])])]
    : [];
  const requestState = inferencePending
    ? "En cours"
    : shownResult?.status === "completed"
      ? "Réponse reçue"
      : shownResult?.status === "cancelled"
        ? "Annulée"
        : shownResult?.status === "failed"
          ? "Échec"
          : "Non envoyée";

  return (
    <main className="app-shell">
      <header className="topbar">
        <Brand />
        <div className="topbar-status">
          <span className="badge neutral">Prototype de recherche</span>
          {isSimulated && <span className="badge warning">SIMULÉ</span>}
          <span
            className={`connection ${runtime?.apiKeyConfigured ? "connected" : ""}`}
          >
            <i aria-hidden="true" />
            {runtime?.apiKeyConfigured
              ? "Holo configuré"
              : "Holo non configuré"}
          </span>
        </div>
      </header>
      <section className="page-heading">
        <div>
          <span className="eyebrow">Le regard comme contexte</span>
          <h1>Voir ce que voit Holo.</h1>
          <p>Une zone utile, une image précise, des mesures observées.</p>
        </div>
        <div className="model-tag">
          <label htmlFor="holo-model">MODÈLE POUR LE PROCHAIN ENVOI</label>
          <select
            id="holo-model"
            aria-label="Modèle Holo"
            value={selectedModel}
            disabled={busy || !runtime}
            onChange={(event) => setSelectedModel(event.target.value)}
          >
            {!runtime && <option value="">Chargement…</option>}
            {availableModels.map((model) => (
              <option key={model} value={model}>{model}</option>
            ))}
          </select>
          <small>Analyse visuelle · aucune action exécutée</small>
        </div>
      </section>
      {error && (
        <div className="notice error" role="alert">
          <strong>L’opération n’a pas abouti.</strong>
          <span>{error}</span>
          <button
            className="text-button"
            onClick={() => setError(null)}
            aria-label="Fermer le message d’erreur"
          >
            Fermer
          </button>
        </div>
      )}
      <ObservationPanel
        bridge={bridge}
        observation={live?.observation}
        disabled={!canCapture}
        startDisabled={needsCalibration}
        calibrationState={needsCalibration ? (tracker.state === "calibrating" ? "running" : "needed") : undefined}
        calibrationLabel={calibrationLabel}
        onCalibrate={calibrate}
        modeLabel={selectionLabels[settings.selection]}
        trackerLabel={trackerLabels[tracker.state]}
        headStatus={headStatus}
        headAngles={headAngles}
        regionScope={settings.regionScope ?? "screen"}
        regionScopeDisabled={busy || !live || settings.selection === "full"}
        onRegionScopeChange={regionScope => changeSettings({ regionScope })}
        startHint={needsCalibration ? "La calibration est nécessaire après chaque lancement. Calibrez aussi chaque signal ajouté : yeux, tête, ou les deux. Terminez les cibles, cliquez sur « Commencer le suivi », puis revenez lancer l’essai. Curseur et Écran complet fonctionnent sans webcam." : undefined}
        shortcutAvailable={runtime?.observationShortcutAvailable === true}
        onStart={startObservation}
        onSelect={selectPreparedFrame}
        onClear={clearPreparedFrame}
      />
      <div className="workspace-grid">
        <aside
          className="controls-column"
          aria-label="Configuration de l’observation"
        >
          <section className="panel control-panel">
            <div className="section-heading">
              <span className="step-number">01</span>
              <h2>Choisir le contexte</h2>
            </div>
            <fieldset className="mode-select" disabled={busy || !live || tracker.state === "calibrating"}>
              <legend>Méthode de sélection</legend>
              {(["gaze", "head", "hybrid", "cursor", "full"] as const).map((mode) => (
                <label
                  key={mode}
                  className={settings.selection === mode ? "selected" : ""}
                >
                  <input
                    type="radio"
                    name="selection"
                    value={mode}
                    checked={settings.selection === mode}
                    onChange={() => changeSettings({ selection: mode })}
                  />
                  <span>{selectionLabels[mode]}</span>
                </label>
              ))}
            </fieldset>
            {settings.selection === "head" && <p className="field-note">Orientez doucement le visage vers la zone voulue. La tête indique une direction approximative, pas le point exact regardé.</p>}
            {settings.selection === "hybrid" && <p className="field-note">Essai combiné : 70 % regard, 30 % tête. Si un signal manque, la capture indique celui réellement utilisé.</p>}
            <label className="region-scope-label">Cadre de la région
              <select
                aria-label="Cadre de la région"
                value={settings.regionScope ?? "screen"}
                disabled={busy || !live || settings.selection === "full"}
                onChange={event => changeSettings({ regionScope: event.target.value as "screen" | "window" })}
              >
                <option value="screen">Écran</option>
                <option value="window">Fenêtre regardée</option>
              </select>
            </label>
            <div className="tracker-status">
              <span
                className={`status-light ${tracker.state}`}
                aria-hidden="true"
              />
              <div>
                <strong>{trackerLabels[tracker.state]}</strong>
                <span>
                  {tracker.message ||
                    (tracker.state === "off"
                      ? "Activation volontaire · traitement local"
                      : "WebGazer · aucune image du visage envoyée")}
                </span>
              </div>
            </div>
            <div className="camera-buttons">
              {cameraOn ? (
                <>
                  <button
                    className="button secondary"
                    onClick={() =>
                      void bridge
                        .stopTracker()
                        .catch((reason) => setError(errorText(reason)))
                    }
                  >
                    Arrêter la caméra
                  </button>
                  <button
                    className="text-button"
                    disabled={busy || tracker.state === "calibrating"}
                    onClick={calibrate}
                  >
                    Recalibrer
                  </button>
                </>
              ) : (
                <button
                  className="button secondary"
                  disabled={busy || !runtime}
                  onClick={calibrate}
                >
                  Activer la caméra et calibrer
                </button>
              )}
            </div>
            {tracker.calibrationErrorPx != null && (
              <p className="field-note">
                Erreur de validation du regard :{" "}
                {number(Math.round(tracker.calibrationErrorPx))} px d’affichage.
              </p>
            )}
            {headStatus && <p className="field-note head-status">{headStatus}</p>}
            {tracker.headCalibrationErrorPx != null && <p className="field-note">Erreur de validation de la tête : {number(Math.round(tracker.headCalibrationErrorPx))} px d’affichage.</p>}
            <div className="control-divider" />
            <div className="field-label">
              Taille de la région <span>pixels source</span>
            </div>
            <div className="size-fields">
              <label>
                <span>Largeur</span>
                <input
                  ref={widthInput}
                  aria-label="Largeur de la région"
                  type="number"
                  min="64"
                  max="8192"
                  step="32"
                  value={widthDraft}
                  disabled={busy || settings.selection === "full" || !live}
                  onChange={(event) => setWidthDraft(event.target.value)}
                  onBlur={(event) => commitDimension("roiWidth", event.currentTarget.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") event.currentTarget.blur();
                  }}
                />
              </label>
              <span className="size-times" aria-hidden="true">
                ×
              </span>
              <label>
                <span>Hauteur</span>
                <input
                  ref={heightInput}
                  aria-label="Hauteur de la région"
                  type="number"
                  min="64"
                  max="8192"
                  step="32"
                  value={heightDraft}
                  disabled={busy || settings.selection === "full" || !live}
                  onChange={(event) => setHeightDraft(event.target.value)}
                  onBlur={(event) => commitDimension("roiHeight", event.currentTarget.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") event.currentTarget.blur();
                  }}
                />
              </label>
            </div>
            <p className="field-note applied-region" role="status">
              Réglage enregistré : {number(live?.settings.roiWidth)} × {number(live?.settings.roiHeight)} px
              {configurationPending > 0 ? " · enregistrement…" : ""}
            </p>
            <label className="toggle-row">
              <span>
                <strong>Ajouter un aperçu global</strong>
                <small>Le reste de l’écran en résolution réduite</small>
              </span>
              <input
                type="checkbox"
                checked={settings.includeGlobal}
                disabled={busy || settings.selection === "full" || !live}
                onChange={(event) =>
                  changeSettings({ includeGlobal: event.target.checked })
                }
              />
            </label>
            <label className="toggle-row">
              <span>
                <strong>Afficher la zone sur l’écran</strong>
                <small>Contour visible, clics traversants</small>
              </span>
              <input
                type="checkbox"
                checked={settings.overlay}
                disabled={busy || !live}
                onChange={(event) =>
                  changeSettings({ overlay: event.target.checked })
                }
              />
            </label>
            <div className="overlay-key">
              <span>
                <i className="candidate-key" />
                Candidate
              </span>
              <span>
                <i className="sent-key" />
                Envoyée, figée
              </span>
            </div>
          </section>
          <section className="panel capture-panel">
            <div className="section-heading">
              <span className="step-number">02</span>
              <h2>Préparer l’image</h2>
            </div>
            <p>La capture reste locale jusqu’à votre envoi à Holo.</p>
            <button
              className="button primary full-width"
              disabled={!canCapture}
              // Capture flushes both inputs itself. Keep mouse-down from first
              // triggering a blur write whose error could move this button.
              onMouseDown={(event) => event.preventDefault()}
              onClick={capture}
            >
              {capturePending ? "Regardez le logiciel…" : "Capturer dans 3 s"}
            </button>
            {runtime && !runtime.captureAvailable && (
              <p className="field-note warning-text">
                {runtime.captureError ||
                  "La capture native est indisponible sur cette configuration."}
              </p>
            )}
            <div className="capture-footnote">
              <span aria-hidden="true">◈</span>
              <span>
                Regardez la zone du logiciel pendant les 3 secondes. Les
                fenêtres H-Companion se masquent pendant la capture.
              </span>
            </div>
          </section>
          <section className="hardware-note">
            <span className="eyebrow">Session locale</span>
            <p>
              {runtime
                ? `${runtime.display.bounds.width} × ${runtime.display.bounds.height} points · échelle ${runtime.display.scaleFactor}×`
                : "Connexion à l’application…"}
            </p>
            <p>Écran principal · WebGazer</p>
          </section>
        </aside>
        <div className="observation-column">
          <section className="panel observation-panel">
            <div className="observation-title">
              <div>
                <span className="eyebrow">Observation immuable</span>
                <h2>
                  {frame
                    ? frame.global
                      ? "Zone détaillée + aperçu global"
                      : frame.selection === "full" || frame.fallbackReason || frame.regionDisposition === "full-size"
                        ? "Écran complet"
                        : "Zone détaillée"
                    : "Image préparée pour Holo"}
                </h2>
              </div>
              <span className={`badge ${sent ? "success" : "neutral"}`}>
                {sent
                  ? "Envoyée à Holo"
                  : frame
                    ? "Préparée · locale"
                    : "Aucune capture"}
              </span>
            </div>
            <div className="frame-meta">
              <span>
                Frame <code>{frame?.frameId ?? "—"}</code>
              </span>
              <span>
                {frame
                  ? selectionLabels[frame.selection]
                  : selectionLabels[settings.selection]}
              </span>
              {frame && (
                <span>
                  {new Date(frame.capturedAt).toLocaleTimeString("fr-FR")}
                </span>
              )}
            </div>
            {frame?.fallbackReason && (
              <div className="notice compact warning" role="status">
                <strong>Repli plein écran</strong>
                <span>{frame.fallbackReason}</span>
              </div>
            )}
            {frame?.regionDisposition === "full-size" && !frame.fallbackReason && (
              <div className="notice compact warning" role="status">
                <strong>La région demandée couvre tout l’écran</strong>
                <span>Réduisez les dimensions de la région pour préparer un recadrage.</span>
              </div>
            )}
            <div
              className={`images-layout ${frame?.global ? "with-global" : ""}`}
            >
              <ImageCard
                image={frame?.detail ?? null}
                title={
                  frame?.global ? "Région détaillée" : "Image de l’observation"
                }
                subtitle={
                  sent
                    ? "Buffer exact envoyé à Holo"
                    : "Buffer exact préparé pour l’envoi"
                }
                kind="detail"
              />
              {frame?.global && (
                <ImageCard
                  image={frame.global}
                  title="Aperçu global"
                  subtitle={
                    sent
                      ? "Également envoyé à Holo"
                      : "Également inclus à l’envoi"
                  }
                  kind="global"
                />
              )}
            </div>
            <div
              className="coordinates-bar"
              aria-label="Coordonnées de la capture"
            >
              <div>
                <span>X</span>
                <strong>{number(frame?.cropRect.x)}</strong>
              </div>
              <div>
                <span>Y</span>
                <strong>{number(frame?.cropRect.y)}</strong>
              </div>
              <div>
                <span>Largeur</span>
                <strong>{number(frame?.cropRect.width)}</strong>
              </div>
              <div>
                <span>Hauteur</span>
                <strong>{number(frame?.cropRect.height)}</strong>
              </div>
              <div className="source-size">
                <span>Capture source</span>
                <strong>
                  {frame
                    ? `${number(frame.sourceWidth)} × ${number(frame.sourceHeight)}`
                    : "—"}
                </strong>
              </div>
            </div>
            <p className="coordinates-note">
              Pixels de capture · origine en haut à gauche
              {frame?.gazeAgeMs != null
                ? ` · âge du regard au choix, avant capture : ${milliseconds(frame.gazeAgeMs)}`
                : ""}
              {frame?.headAgeMs != null ? ` · âge de la tête : ${milliseconds(frame.headAgeMs)}` : ""}
            </p>
            {frame?.signalUsed && <p className="coordinates-note signal-used">Signal utilisé : <strong>{selectionLabels[frame.signalUsed]}</strong>{frame.signalReason ? ` · ${frame.signalReason}` : ""}</p>}
            {frame?.requestedRegion && (
              <p className="coordinates-note requested-region">
                Région demandée pour cette capture : {number(frame.requestedRegion.width)} × {number(frame.requestedRegion.height)} px
                {` · surface conservée : ${Math.round(100 * frame.cropRect.width * frame.cropRect.height / (frame.sourceWidth * frame.sourceHeight))} %`}
              </p>
            )}
            {frame?.selectedWindow && <p className="coordinates-note">Fenêtre retenue : {frame.selectedWindow.appName}</p>}
            {frame?.windowFallbackReason && <p className="field-note warning-text">{frame.windowFallbackReason}</p>}
          </section>
          <section
            className="metrics-section"
            aria-label="Mesures de la requête"
          >
            <div className="metrics-heading">
              <h2>Mesures observées</h2>
              <span>
                {inferencePending
                  ? "En attente de la réponse API"
                  : shownResult
                    ? "Valeurs retournées par l’API"
                    : "Aucune requête mesurée"}
              </span>
            </div>
            {(shownResult || inferencePending) && (
              <p className="measured-model" aria-live="polite">
                {inferencePending ? "Modèle interrogé : " : "Modèle mesuré : "}
                <strong>{shownResult?.model ?? selectedModel}</strong>
                {shownResult && shownResult.model !== selectedModel && (
                  <span> · Ces mesures précèdent le changement de modèle.</span>
                )}
              </p>
            )}
            <div className="metrics-grid">
              <Metric
                label="Tokens d’entrée"
                value={number(shownResult?.usage.inputTokens)}
                note="Images + texte"
              />
              <Metric
                label="Tokens de sortie"
                value={number(shownResult?.usage.outputTokens)}
                note="Réponse du modèle"
              />
              <Metric
                label="Tokens totaux"
                value={number(shownResult?.usage.totalTokens)}
                note={
                  shownResult?.usage.cachedInputTokens != null
                    ? `${number(shownResult.usage.cachedInputTokens)} en cache (entrée)`
                    : "Cache non renseigné"
                }
                accent
              />
              <Metric
                label="Latence de requête"
                value={milliseconds(shownResult?.latencyMs)}
                note={
                  shownResult?.status === "cancelled"
                    ? "Durée avant annulation"
                    : shownResult?.status === "failed"
                      ? "Durée avant échec"
                      : "Envoi → réponse complète"
                }
              />
            </div>
            <div className="metrics-detail">
              <span>
                Préparation locale :{" "}
                <strong>{milliseconds(frame?.preparationMs)}</strong>
              </span>
              <span>
                Requête : <code>{shownResult?.requestId ?? "—"}</code>
              </span>
            </div>
          </section>
          <section className="panel inference-panel">
            <div className="section-heading">
              <span className="step-number">03</span>
              <h2>Interroger Holo</h2>
              <span className="request-state" role="status">
                {requestState}
              </span>
            </div>
            <label className="prompt-label" htmlFor="holo-prompt">
              Consigne pour cette observation
            </label>
            <textarea
              id="holo-prompt"
              rows={2}
              maxLength={8000}
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              disabled={inferencePending}
              placeholder="Que souhaitez-vous comprendre dans cette interface ?"
            />
            <div className="send-row">
              <p>
                {runtime?.apiKeyConfigured
                  ? "Les images affichées ci-dessus seront envoyées avec votre consigne."
                  : "Ajoutez HAI_API_KEY à app/.env puis relancez l’application."}
              </p>
              <div>
                {inferencePending && (
                  <button
                    className="button secondary cancel-button"
                    onClick={() => void cancel()}
                  >
                    Annuler
                  </button>
                )}
                <button
                  className="button primary"
                  disabled={!canAnalyze}
                  onClick={analyze}
                >
                  {inferencePending ? "Holo analyse…" : "Envoyer à Holo"}
                  <span aria-hidden="true">↗</span>
                </button>
              </div>
            </div>
          </section>
          {shownResult && (
            <section
              className={`panel result-panel ${shownResult.status !== "completed" ? "result-error" : ""}`}
              aria-label="Réponse de Holo"
            >
              <div className="section-heading">
                <h2>
                  {shownResult.status === "completed"
                    ? "Réponse de Holo"
                    : shownResult.status === "cancelled"
                      ? "Requête annulée"
                      : "Requête interrompue"}
                </h2>
                {shownResult.simulated && (
                  <span className="badge warning">SIMULÉ</span>
                )}
              </div>
              <p className="response-model">Réponse de <strong>{shownResult.model}</strong></p>
              {shownResult.error && (
                <p role="alert" className="warning-text">
                  {shownResult.error}
                </p>
              )}
              <p className="model-response">
                {shownResult.text ||
                  (shownResult.status === "completed"
                    ? "La réponse ne contient pas de texte."
                    : "Aucune réponse exploitable reçue.")}
              </p>
              <p className="field-note">
                Analyse visuelle uniquement. Aucune action ni réussite de tâche
                n’est déduite de cette réponse.
                {shownResult.usage.totalTokens == null
                  ? " Usage inconnu : cette requête n’est pas considérée comme gratuite."
                  : ""}
              </p>
            </section>
          )}
        </div>
      </div>
      <footer className="app-footer">
        <span>H-Companion · Vision pilot</span>
        <span>Les économies se mesurent face à une référence comparable.</span>
      </footer>
    </main>
  );
}

function Metric({
  label,
  value,
  note,
  accent = false,
}: {
  label: string;
  value: string;
  note: string;
  accent?: boolean;
}) {
  return (
    <div className={`metric-card ${accent ? "accent" : ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{note}</small>
    </div>
  );
}
