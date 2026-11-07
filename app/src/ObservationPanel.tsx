import { useEffect, useRef, useState } from "react";
import type { BenchmarkScore, CaptureFrame, CompanionBridge, LiveState, ObservationOptions, ObservationSample, Rect } from "./lib/types";

type Props = {
  bridge: CompanionBridge;
  observation: LiveState["observation"];
  disabled: boolean;
  startDisabled?: boolean;
  startHint?: string;
  calibrationState?: "needed" | "running";
  calibrationLabel: string;
  onCalibrate: () => void;
  modeLabel: string;
  trackerLabel: string;
  headStatus?: string;
  headAngles?: string;
  regionScope: "screen" | "window";
  regionScopeDisabled: boolean;
  onRegionScopeChange: (scope: "screen" | "window") => void;
  shortcutAvailable: boolean;
  onStart: (options: ObservationOptions) => void;
  onSelect: (frame: CaptureFrame) => void;
  onClear: () => void;
};
const errorText = (error: unknown) => error instanceof Error ? error.message : String(error);
const signalLabels = { gaze: "Regard", head: "Tête", hybrid: "Regard + tête", cursor: "Curseur", full: "Écran complet" };
const fraction = (hits: number, count: number) => `${hits} / ${count}${count ? ` (${Math.round(100 * hits / count)} %)` : ""}`;
const benchmarkReasons: Record<string, string> = { unpresented: "Affichage de la cible non confirmé.", transition: "Délai de stabilisation après le changement de cible.", unstable: "La cible a changé pendant la capture.", "invalid-timing": "Horodatage de capture non exploitable." };

/** Local review annotation only: never changes the PNG or the payload sent to Holo. */
function TargetMarker({ score, viewport }: { score: BenchmarkScore; viewport: Rect }) {
  const point = score.targetPixels;
  if (!point || ![point.x, point.y, point.radiusX, point.radiusY].every(Number.isFinite)) return null;
  return <span className="review-target-marker" role="img" aria-label="Position connue de la cible rouge — annotation locale"
    style={{ left: `${100 * (point.x - viewport.x) / viewport.width}%`, top: `${100 * (point.y - viewport.y) / viewport.height}%`, width: `${200 * point.radiusX / viewport.width}%`, height: `${200 * point.radiusY / viewport.height}%` }} />;
}

export default function ObservationPanel({ bridge, observation, disabled, startDisabled, startHint, calibrationState, calibrationLabel, onCalibrate, modeLabel, trackerLabel, headStatus, headAngles, regionScope, regionScopeDisabled, onRegionScopeChange, shortcutAvailable, onStart, onSelect, onClear }: Props) {
  const [durationSeconds, setDurationSeconds] = useState<15 | 30 | 60>(30);
  const [showOverlay, setShowOverlay] = useState(false);
  const [benchmark, setBenchmark] = useState(false);
  const [seedDraft, setSeedDraft] = useState("42");
  const [samples, setSamples] = useState<ObservationSample[]>([]);
  const [selected, setSelected] = useState<CaptureFrame | null>(null);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const generation = useRef(0);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;
  const active = observation?.status === "running" || observation?.status === "stopping";
  const settledCount = active ? 0 : observation?.sampleCount ?? 0;
  const autoSummary = observation?.benchmarkSummary;
  const retentionLabel = observation?.benchmark
    ? `${observation.capturedCount ?? autoSummary?.total ?? observation.sampleCount} captures analysées / ${observation.sampleCount} images conservées`
    : `${observation?.sampleCount ?? 0} captures conservées`;
  const start = () => {
    setError(null);
    if (!benchmark) { onStart({ durationSeconds, showOverlay }); return; }
    const seed = Number(seedDraft);
    if (!seedDraft.trim() || !Number.isInteger(seed) || seed < 0 || seed > 0xffff_ffff) {
      setError("Choisissez un numéro de parcours entier entre 0 et 4 294 967 295.");
      return;
    }
    onStart({ durationSeconds, showOverlay: false, benchmark: true, seed });
  };

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
    <p className="field-note" aria-label="Mode et suivi de l’essai">Mode : <strong>{modeLabel}</strong> · {trackerLabel}</p>
    {headStatus && <p className="field-note head-status" aria-label="Suivi de la tête">{headStatus}{headAngles ? ` · ${headAngles}` : ""}</p>}
    <p className="continuous-intro">Le panneau se masque pendant l’essai. Environ une capture par seconde, puis retour pour vérifier la zone retenue.</p>
    <div className="benchmark-controls">
      <label className="continuous-overlay"><input type="checkbox" checked={benchmark} disabled={disabled || active} onChange={event => { setBenchmark(event.target.checked); if (event.target.checked) setShowOverlay(false); }} /> Cible rouge — score automatique</label>
      {benchmark && <label className="benchmark-seed">Numéro du parcours
        <input aria-label="Numéro du parcours" type="number" min="0" max="4294967295" step="1" value={seedDraft} disabled={disabled || active} onChange={event => setSeedDraft(event.target.value)} />
      </label>}
    </div>
    {benchmark && <p className="field-note">Suivez la cible rouge : elle change de position environ toutes les 3 secondes. Les 800 premières millisecondes de chaque position sont exclues du score. Le contour reste masqué et ces mesures ne réentraînent pas la calibration.</p>}
    <div className="continuous-controls">
      <label className="continuous-duration">Durée de l’essai
        <select aria-label="Durée de l’essai" value={durationSeconds} disabled={disabled || active} onChange={event => setDurationSeconds(Number(event.target.value) as 15 | 30 | 60)}>
          <option value={15}>15 secondes</option><option value={30}>30 secondes</option><option value={60}>60 secondes</option>
        </select>
      </label>
      <label className="continuous-duration">Cadre de la région
        <select aria-label="Cadre de l’essai" value={regionScope} disabled={regionScopeDisabled || active} onChange={event => onRegionScopeChange(event.target.value as "screen" | "window")}>
          <option value="screen">Écran</option><option value="window">Fenêtre regardée</option>
        </select>
      </label>
      <label className="continuous-overlay"><input type="checkbox" checked={showOverlay} disabled={disabled || active || benchmark} onChange={event => setShowOverlay(event.target.checked)} /> Montrer le contour pendant l’essai</label>
      {active ? <button className="button secondary" disabled={observation?.status === "stopping"} onClick={() => void bridge.stopObservation().catch(cause => setError(errorText(cause)))}>{observation?.status === "stopping" ? "Arrêt en cours…" : "Arrêter l’observation"}</button>
        : calibrationState ? <button className="button primary" disabled={disabled || calibrationState === "running" || reviewBusy} onClick={onCalibrate}>{calibrationState === "running" ? "Calibration en cours…" : calibrationLabel}</button>
          : <button className="button primary" disabled={disabled || startDisabled || reviewBusy || !shortcutAvailable} onMouseDown={event => event.preventDefault()} onClick={start}>Observer et masquer le panneau</button>}
    </div>
    {startHint && !active && <p className="field-note">{startHint}</p>}
    <p className="continuous-shortcut">Retour anticipé : <kbd>⌘ / Ctrl</kbd> + <kbd>Maj</kbd> + <kbd>Espace</kbd>. Le panneau revient aussi à la fin de la durée choisie.</p>
    <p className="field-note">Un nouvel essai remplace les captures du précédent en mémoire. Le contour est désactivé par défaut pour ne pas attirer le regard.</p>
    {!shortcutAvailable && <p className="warning-text">Le raccourci de retour est indisponible. Libérez-le puis relancez l’app pour démarrer un essai masqué.</p>}
    {active && <p role="status">Observation en cours · {retentionLabel}. Aucun appel Holo.</p>}
    {!active && observation?.status === "stopped" && <p className="field-note" role="status">{stopReason || "Essai terminé"} · {retentionLabel}.</p>}
    {observation?.benchmark && (observation.discardedImageCount ?? 0) > 0 && <p className="field-note" aria-label="Rétention des images">{observation.discardedImageCount} image(s) retirée(s) de la revue pour respecter la limite mémoire de 64 Mio. Les mesures de toutes les captures restent dans le score, y compris celles sans image conservée.</p>}
    {(error || observation?.error) && <p className="warning-text" role="alert">{error || observation?.error}</p>}
    {!active && observation?.benchmark && autoSummary && <section className="benchmark-results" aria-label="Score automatique de la cible">
      <h3>Score automatique · parcours {observation.benchmark.seed}</h3>
      <div className="benchmark-metrics">
        <div><span>Cible entière · toutes captures évaluables</span><strong>{fraction(autoSummary.fullHits, autoSummary.scored)}</strong></div>
        <div><span>Cible entière · captures recadrées seules</span><strong>{fraction(autoSummary.croppedFullHits, autoSummary.croppedScored)}</strong></div>
        <div><span>Captures plein écran</span><strong>{autoSummary.fullFrames}<small>dont {autoSummary.fullFallbacks} repli(s)</small></strong></div>
        <div><span>Surface détaillée / écran · moyenne</span><strong>{autoSummary.meanAreaFraction == null ? "—" : `${Math.round(100 * autoSummary.meanAreaFraction)} %`}</strong></div>
      </div>
      <p className="field-note" aria-label="Taux de repli plein écran">Repli plein écran : {fraction(autoSummary.fullFallbacks, autoSummary.total)} de toutes les captures analysées.</p>
      {autoSummary.fallbackReasons && Object.keys(autoSummary.fallbackReasons).length > 0 && <ul className="field-note" aria-label="Causes des replis plein écran">
        {Object.entries(autoSummary.fallbackReasons).map(([reason, count]) => <li key={reason}>{count} capture(s) : {reason}</li>)}
      </ul>}
      <p className="field-note">Score calculé sur les {autoSummary.total} captures du parcours, indépendamment des images encore disponibles pour la revue.</p>
      <p className="field-note">Centre de la cible inclus : {fraction(autoSummary.centerHits, autoSummary.scored)} · {autoSummary.unscored} capture(s) exclue(s), notamment pendant la stabilisation.</p>
      <p className="field-note">Cible entière aux bords : {fraction(autoSummary.edge.fullHits, autoSummary.edge.scored)} · à l’intérieur : {fraction(autoSummary.interior.fullHits, autoSummary.interior.scored)}.</p>
      {autoSummary.scored === 0 && <p className="warning-text">Aucune capture évaluable : aucun taux de couverture ne peut être conclu pour cet essai.</p>}
      {samples[0]?.headRegionPolicy && <p className="field-note">Politique tête de cet essai : {samples[0].headRegionPolicy === "zones" ? "5 zones stables · expérimental" : "Point continu · référence"}.</p>}
      {samples[0]?.calibrationProfile && <p className="field-note">Profil de calibration de cet essai : {samples[0].calibrationProfile === "wide" ? "Bords étendus" : "Standard"}.</p>}
      <p className="field-note">Comparez le même numéro de parcours, la même durée, les mêmes dimensions et le même cadre de région. Notez le profil de calibration. Un plein écran peut contenir la cible sans produire de recadrage utile. La surface conservée ne mesure pas les tokens économisés.</p>
      <p className="field-note">Ce score mesure la couverture géométrique d’une cible demandée, pas le regard réel ni la réussite d’une tâche dans le logiciel.</p>
    </section>}
    {!active && observation?.benchmark && observation.status === "stopped" && samples.length === 0 && (observation.capturedCount ?? 0) > 0 && <button className="text-button" disabled={locked} onClick={() => void clear()}>Effacer cet essai local</button>}
    {!active && samples.length > 0 && <div className="observation-review">
      <div className="review-toolbar">
        <h3>{observation?.benchmark ? "Revoir les images conservées" : "Revoir les captures"}</h3>
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
              {selected.benchmark && <TargetMarker score={selected.benchmark} viewport={{ x: 0, y: 0, width: selected.sourceWidth, height: selected.sourceHeight }} />}
            </div> : <p>Référence indisponible pour cette capture.</p>}
          </figure>
          <figure><figcaption>Région retenue · {selected.detail.width} × {selected.detail.height}</figcaption><div className="review-detail"><img src={selected.detail.dataUrl} alt="Région retenue pendant l’essai" />{selected.benchmark && <TargetMarker score={selected.benchmark} viewport={selected.cropRect} />}</div></figure>
        </div>
        {selected.benchmark && <div className="benchmark-frame-result" aria-label="Résultat automatique de cette capture">
          <strong>{selected.benchmark.scorable ? (selected.benchmark.fullContained ? "Cible entière dans la région" : selected.benchmark.centerContained ? "Centre inclus · cible partiellement coupée" : "Cible hors de la région") : "Capture exclue du score"}</strong>
          {selected.benchmark.reason && <span>{benchmarkReasons[selected.benchmark.reason] || selected.benchmark.reason}</span>}
          <span>Cible {selected.benchmark.target.index + 1} · {selected.benchmark.target.zone === "edge" ? "bord de l’écran" : "intérieur"}{selected.calibrationProfile ? ` · calibration ${selected.calibrationProfile === "wide" ? "bords étendus" : "standard"}` : ""}</span>
          <p>La cible est réaffichée ici comme annotation locale. Les PNG préparés pour Holo restent inchangés et ne contiennent pas notre overlay.</p>
        </div>}
        <p className="review-context">{selected.selectedWindow ? `Fenêtre : ${selected.selectedWindow.appName}` : "Région de l’écran"} · {new Date(selected.capturedAt).toLocaleTimeString("fr-FR")}{selected.fallbackReason ? ` · Repli : ${selected.fallbackReason}` : ""}</p>
        {selected.signalUsed && <p className="review-context signal-used">Signal utilisé : <strong>{signalLabels[selected.signalUsed]}</strong>{selected.signalReason ? ` · ${selected.signalReason}` : ""}</p>}
        {selected.headDiagnostic && (selected.selection === "head" || selected.selection === "hybrid") && <p className="review-context" aria-label="Diagnostic tête de l’image revue">
          Diagnostic tête : {selected.headDiagnostic.message}
          {selected.headDiagnostic.rawPoint ? ` · projection avant bornage : (${Math.round(selected.headDiagnostic.rawPoint.x)}, ${Math.round(selected.headDiagnostic.rawPoint.y)}) px logiques` : ""}
        </p>}
        {selected.windowFallbackReason && <p className="warning-text">{selected.windowFallbackReason}</p>}
        {!selected.benchmark && <div className="review-annotation" aria-label="Présence de la cible dans cette capture">
          <span>La cible regardée est-elle dans la région ?</span>
          {([['present', 'Cible présente'], ['absent', 'Cible absente'], ['uncertain', 'Impossible à juger']] as const).map(([label, title]) => <button key={label} className={`button ${current?.annotation === label ? 'primary' : 'secondary'}`} aria-pressed={current?.annotation === label} disabled={locked} onClick={() => void annotate(label)}>{title}</button>)}
        </div>}
      </>}
      {!observation?.benchmark && <p className="review-summary" aria-live="polite">Cible présente : {present} / {labelled} captures jugées{labelled ? ` (${Math.round(100 * present / labelled)} %)` : ""} · {uncertain} incertaine(s) · {unlabelled} non annotée(s).</p>}
      <p className="field-note">La capture sélectionnée apparaît également ci-dessous ; son envoi à Holo reste une action séparée.</p>
    </div>}
  </section>;
}
