import { useEffect, useRef, useState } from "react";
import type { CaptureFrame, CompanionBridge, LiveState, ObservationSample } from "./lib/types";

type Props = {
  bridge: CompanionBridge;
  observation: LiveState["observation"];
  disabled: boolean;
  startDisabled?: boolean;
  startHint?: string;
  shortcutAvailable: boolean;
  onStart: (options: { durationSeconds: 15 | 30 | 60; showOverlay: boolean }) => void;
  onSelect: (frame: CaptureFrame) => void;
  onClear: () => void;
};
const errorText = (error: unknown) => error instanceof Error ? error.message : String(error);

export default function ObservationPanel({ bridge, observation, disabled, startDisabled, startHint, shortcutAvailable, onStart, onSelect, onClear }: Props) {
  const [durationSeconds, setDurationSeconds] = useState<15 | 30 | 60>(30);
  const [showOverlay, setShowOverlay] = useState(false);
  const [samples, setSamples] = useState<ObservationSample[]>([]);
  const [selected, setSelected] = useState<CaptureFrame | null>(null);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const generation = useRef(0);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;
  const active = observation?.status === "running" || observation?.status === "stopping";
  const settledCount = active ? 0 : observation?.sampleCount ?? 0;

  useEffect(() => {
    const request = ++generation.current;
    setError(null);
    if (active) {
      setSamples([]);
      setSelected(null);
      setReviewBusy(false);
      return;
    }
    setReviewBusy(true);
    void bridge.listObservations().then(async next => {
      if (request !== generation.current) return;
      setSamples(next);
      if (!next.length) { setSelected(null); return; }
      const frame = await bridge.selectObservation(next[0].frameId);
      if (request !== generation.current) return;
      setSelected(frame);
      onSelectRef.current(frame);
    }).catch(cause => {
      if (request === generation.current) setError(errorText(cause));
    }).finally(() => {
      if (request === generation.current) setReviewBusy(false);
    });
    return () => { generation.current += 1; };
  }, [bridge, active, observation?.startedAt, settledCount]);

  const selectSample = async (sample: ObservationSample) => {
    const request = ++generation.current;
    setReviewBusy(true);
    setError(null);
    try {
      const frame = await bridge.selectObservation(sample.frameId);
      if (request !== generation.current) return;
      setSelected(frame);
      onSelectRef.current(frame);
    } catch (cause) {
      if (request === generation.current) setError(errorText(cause));
    } finally {
      if (request === generation.current) setReviewBusy(false);
    }
  };
  const annotate = async (label: "present" | "absent" | "uncertain") => {
    if (!selected) return;
    const frameId = selected.frameId;
    setReviewBusy(true);
    setError(null);
    try {
      await bridge.annotateObservation({ frameId, label });
      setSamples(current => current.map(sample => sample.frameId === frameId ? { ...sample, annotation: label } : sample));
    } catch (cause) { setError(errorText(cause)); }
    finally { setReviewBusy(false); }
  };
  const clear = async () => {
    generation.current += 1;
    setReviewBusy(true);
    setError(null);
    try {
      await bridge.clearObservations();
      setSamples([]);
      setSelected(null);
      onClear();
    } catch (cause) { setError(errorText(cause)); }
    finally { setReviewBusy(false); }
  };
  const index = samples.findIndex(sample => sample.frameId === selected?.frameId);
  const current = samples[index];
  const present = samples.filter(sample => sample.annotation === "present").length;
  const absent = samples.filter(sample => sample.annotation === "absent").length;
  const uncertain = samples.filter(sample => sample.annotation === "uncertain").length;
  const labelled = present + absent;
  const unlabelled = samples.length - labelled - uncertain;
  const locked = active || disabled || reviewBusy;
  const stopReason = {
    duration: "Durée écoulée", user: "Essai arrêté", "memory-limit": "Limite de mémoire atteinte",
    error: "Essai interrompu", "display-changed": "Géométrie écran modifiée", "panel-returned": "Panneau revenu au premier plan",
  }[observation?.stopReason ?? ""];

  return <section className="panel continuous-panel" aria-label="Essai continu local">
    <div className="observation-title">
      <div><span className="eyebrow">Essai en situation</span><h2>Observer sans le panneau</h2></div>
      <span className="badge neutral">Local · aucun envoi automatique</span>
    </div>
    <p className="continuous-intro">Le panneau se masque pendant l’essai. Environ une capture par seconde, puis retour pour vérifier la zone retenue.</p>
    <div className="continuous-controls">
      <label className="continuous-duration">Durée de l’essai
        <select aria-label="Durée de l’essai" value={durationSeconds} disabled={disabled || active} onChange={event => setDurationSeconds(Number(event.target.value) as 15 | 30 | 60)}>
          <option value={15}>15 secondes</option><option value={30}>30 secondes</option><option value={60}>60 secondes</option>
        </select>
      </label>
      <label className="continuous-overlay"><input type="checkbox" checked={showOverlay} disabled={disabled || active} onChange={event => setShowOverlay(event.target.checked)} /> Montrer le contour pendant l’essai</label>
      {active ? <button className="button secondary" disabled={observation?.status === "stopping"} onClick={() => void bridge.stopObservation().catch(cause => setError(errorText(cause)))}>{observation?.status === "stopping" ? "Arrêt en cours…" : "Arrêter l’observation"}</button>
        : <button className="button primary" disabled={disabled || startDisabled || reviewBusy || !shortcutAvailable} onMouseDown={event => event.preventDefault()} onClick={() => onStart({ durationSeconds, showOverlay })}>Observer et masquer le panneau</button>}
    </div>
    {startHint && !active && <p className="field-note">{startHint}</p>}
    <p className="continuous-shortcut">Retour anticipé : <kbd>⌘ / Ctrl</kbd> + <kbd>Maj</kbd> + <kbd>Espace</kbd>. Le panneau revient aussi à la fin de la durée choisie.</p>
    <p className="field-note">Un nouvel essai remplace les captures du précédent en mémoire. Le contour est désactivé par défaut pour ne pas attirer le regard.</p>
    {!shortcutAvailable && <p className="warning-text">Le raccourci de retour est indisponible. Libérez-le puis relancez l’app pour démarrer un essai masqué.</p>}
    {active && <p role="status">Observation en cours · {observation?.sampleCount ?? 0} captures conservées. Aucun appel Holo.</p>}
    {!active && observation?.status === "stopped" && <p className="field-note" role="status">{stopReason || "Essai terminé"} · {observation.sampleCount} captures conservées.</p>}
    {(error || observation?.error) && <p className="warning-text" role="alert">{error || observation?.error}</p>}
    {!active && samples.length > 0 && <div className="observation-review">
      <div className="review-toolbar">
        <h3>Revoir les captures</h3>
        <div className="review-navigation">
          <button className="button secondary" aria-label="Capture précédente" disabled={locked || index <= 0} onClick={() => void selectSample(samples[index - 1])}>←</button>
          <span className="review-count" aria-live="polite">Capture {Math.max(0, index + 1)} / {samples.length}</span>
          <button className="button secondary" aria-label="Capture suivante" disabled={locked || index < 0 || index >= samples.length - 1} onClick={() => void selectSample(samples[index + 1])}>→</button>
        </div>
        <button className="text-button" disabled={locked} onClick={() => void clear()}>Effacer cet essai local</button>
      </div>
      {selected && <>
        <div className="review-images">
          <figure><figcaption>Bureau de référence · reste local</figcaption>
            {selected.reference ? <div className="review-reference">
              <img src={selected.reference.dataUrl} alt="Bureau de référence de l’essai" />
              <div className="review-crop-outline" aria-label="Zone retenue dans le bureau" style={{left: `${100 * selected.cropRect.x / selected.sourceWidth}%`, top: `${100 * selected.cropRect.y / selected.sourceHeight}%`, width: `${100 * selected.cropRect.width / selected.sourceWidth}%`, height: `${100 * selected.cropRect.height / selected.sourceHeight}%`}} />
            </div> : <p>Référence indisponible pour cette capture.</p>}
          </figure>
          <figure><figcaption>Région retenue · {selected.detail.width} × {selected.detail.height}</figcaption><img src={selected.detail.dataUrl} alt="Région retenue pendant l’essai" /></figure>
        </div>
        <p className="review-context">{selected.selectedWindow ? `Fenêtre : ${selected.selectedWindow.appName}` : "Région de l’écran"} · {new Date(selected.capturedAt).toLocaleTimeString("fr-FR")}{selected.fallbackReason ? ` · Repli : ${selected.fallbackReason}` : ""}</p>
        {selected.windowFallbackReason && <p className="warning-text">{selected.windowFallbackReason}</p>}
        <div className="review-annotation" aria-label="Présence de la cible dans cette capture">
          <span>La cible regardée est-elle dans la région ?</span>
          {([['present', 'Cible présente'], ['absent', 'Cible absente'], ['uncertain', 'Impossible à juger']] as const).map(([label, title]) => <button key={label} className={`button ${current?.annotation === label ? 'primary' : 'secondary'}`} aria-pressed={current?.annotation === label} disabled={locked} onClick={() => void annotate(label)}>{title}</button>)}
        </div>
      </>}
      <p className="review-summary" aria-live="polite">Cible présente : {present} / {labelled} captures jugées{labelled ? ` (${Math.round(100 * present / labelled)} %)` : ""} · {uncertain} incertaine(s) · {unlabelled} non annotée(s).</p>
      <p className="field-note">Cette annotation mesure la couverture visuelle de la cible, pas la réussite d’une tâche. La capture sélectionnée apparaît également ci-dessous ; son envoi à Holo reste une action séparée.</p>
    </div>}
  </section>;
}
