import { useEffect, useRef, useState } from 'react';
import type { GazeSample } from './lib/types';
import { cameraErrorMessage, WebGazerTracker } from './lib/webgazer';
import './tracker.css';

type Phase = 'intro' | 'starting' | 'calibration' | 'validation' | 'summary' | 'tracking' | 'error';
type Target = { x: number; y: number };
type Sampling = {
  phase: 'calibration' | 'validation'; target: Target; index: number;
  startedAt: number; lastAt: number; accepted: number; errors: number[];
};
const CALIBRATION = [0.18, 0.5, 0.82].flatMap(y => [0.12, 0.5, 0.88].map(x => ({ x, y })));
const VALIDATION = [{ x: 0.3, y: 0.32 }, { x: 0.7, y: 0.68 }, { x: 0.7, y: 0.32 }, { x: 0.3, y: 0.68 }];
const CALIBRATION_SAMPLES = 5;
const VALIDATION_SAMPLES = 10;
const median = (values: number[]) => {
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
};

export default function Tracker() {
  const [phase, setPhase] = useState<Phase>('intro');
  const [point, setPoint] = useState(0);
  const [progress, setProgress] = useState(0);
  const [sampling, setSampling] = useState(false);
  const [notice, setNotice] = useState('');
  const [calibrationError, setCalibrationError] = useState<number | null>(null);
  const [error, setError] = useState('');
  const phaseRef = useRef<Phase>('intro');
  const tracker = useRef<WebGazerTracker | null>(null);
  const collection = useRef<Sampling | null>(null);
  const validationErrors = useRef<number[]>([]);
  const calibrationErrorRef = useRef<number | undefined>(undefined);
  const lastReportedTracking = useRef<'tracking' | 'lost' | null>(null);

  function changePhase(next: Phase) {
    phaseRef.current = next;
    setPhase(next);
  }

  useEffect(() => {
    const instance = new WebGazerTracker((sample: GazeSample | null) => {
      if (phaseRef.current === 'tracking') {
        window.companion.reportGaze(sample);
        const state = sample ? 'tracking' : 'lost';
        if (state !== lastReportedTracking.current) {
          lastReportedTracking.current = state;
          window.companion.reportTracker({ state, calibrationErrorPx: calibrationErrorRef.current,
            message: sample ? 'Regard actif · traitement local' : 'Regard indisponible · repli plein écran' });
        }
        return;
      }
      const current = collection.current;
      if (!current) return;
      const now = performance.now();
      if (now - current.startedAt < 650 || now - current.lastAt < 100) return;
      current.lastAt = now;
      if (current.phase === 'calibration') {
        if (!instance.recordCalibrationPoint(current.target.x, current.target.y)) return;
        current.accepted += 1;
      } else {
        if (!sample) return;
        current.errors.push(Math.hypot(sample.x - current.target.x, sample.y - current.target.y));
        current.accepted += 1;
      }
      const count = current.phase === 'calibration' ? CALIBRATION_SAMPLES : VALIDATION_SAMPLES;
      setProgress(current.accepted / count);
      if (current.accepted < count) return;
      collection.current = null;
      setSampling(false);
      setProgress(0);
      if (current.phase === 'calibration') {
        if (current.index < CALIBRATION.length - 1) setPoint(current.index + 1);
        else {
          setPoint(0);
          changePhase('validation');
        }
      } else {
        validationErrors.current.push(median(current.errors));
        if (current.index < VALIDATION.length - 1) setPoint(current.index + 1);
        else {
          const measured = median(validationErrors.current);
          calibrationErrorRef.current = measured;
          setCalibrationError(measured);
          window.companion.reportTracker({ state: 'calibrating', calibrationErrorPx: measured,
            message: 'Validation terminée · en attente de démarrage' });
          changePhase('summary');
        }
      }
    });
    tracker.current = instance;
    const watchdog = window.setInterval(() => {
      if (collection.current && performance.now() - collection.current.startedAt > 7_000) {
        collection.current = null;
        setSampling(false);
        setProgress(0);
        setNotice('Pas assez de mesures. Regardez la cible, gardez votre visage visible et réessayez.');
      }
    }, 200);
    const onResize = () => {
      if (phaseRef.current === 'intro') return;
      instance.dispose();
      collection.current = null;
      window.companion.reportGaze(null);
      const message = 'La taille de l’écran a changé. Relancez la calibration.';
      window.companion.reportTracker({ state: 'error', message });
      if (phaseRef.current === 'tracking') void window.companion.stopTracker();
      else { setError(message); changePhase('error'); }
    };
    const onUnload = () => instance.dispose();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        instance.dispose(); collection.current = null;
        void window.companion.stopTracker();
      }
    };
    window.addEventListener('resize', onResize);
    window.addEventListener('beforeunload', onUnload);
    window.addEventListener('keydown', onKeyDown);
    return () => {
      window.clearInterval(watchdog);
      window.removeEventListener('resize', onResize);
      window.removeEventListener('beforeunload', onUnload);
      window.removeEventListener('keydown', onKeyDown);
      collection.current = null;
      instance.dispose();
      if (tracker.current === instance) tracker.current = null;
    };
  }, []);

  async function startCamera() {
    changePhase('starting');
    window.companion.reportTracker({ state: 'calibrating', message: 'Initialisation de la webcam et du modèle local' });
    try {
      await window.companion.requestCamera();
      if (!tracker.current || phaseRef.current !== 'starting') return;
      await tracker.current?.start();
      if (!tracker.current || phaseRef.current !== 'starting') return;
      setPoint(0);
      changePhase('calibration');
      window.companion.reportTracker({ state: 'calibrating', message: 'Calibration humaine · 9 cibles' });
    } catch (cause) {
      const message = cameraErrorMessage(cause);
      setError(message);
      changePhase('error');
      window.companion.reportTracker({ state: 'error', message });
    }
  }

  function stopTracker() {
    collection.current = null;
    tracker.current?.dispose();
    void window.companion.stopTracker();
  }

  function collectTarget() {
    if (collection.current || (phase !== 'calibration' && phase !== 'validation')) return;
    const relative = (phase === 'calibration' ? CALIBRATION : VALIDATION)[point];
    collection.current = { phase, index: point,
      target: { x: relative.x * window.innerWidth, y: relative.y * window.innerHeight },
      startedAt: performance.now(), lastAt: 0, accepted: 0, errors: [] };
    setNotice('');
    setSampling(true);
    setProgress(0);
  }

  async function finish() {
    changePhase('tracking');
    window.companion.reportTracker({ state: 'tracking', calibrationErrorPx: calibrationErrorRef.current,
      message: 'Regard actif · traitement local' });
    try { await window.companion.finishCalibration(); }
    catch (cause) {
      tracker.current?.dispose();
      const message = cameraErrorMessage(cause);
      window.companion.reportTracker({ state: 'error', message });
      setError(message);
      changePhase('error');
    }
  }

  // The renderer stays alive for WebGazer; only its visuals disappear. Main makes it click-through.
  if (phase === 'tracking') return null;
  const activeTarget = (phase === 'calibration' ? CALIBRATION : VALIDATION)[point];
  const isCollecting = phase === 'calibration' || phase === 'validation';

  return <main className="tracker-screen">
    <header className="tracker-header">
      <div className="tracker-wordmark"><span className="tracker-logo">H</span> COMPANION <span className="tracker-tag">REGARD</span></div>
      <button className="tracker-close" onClick={stopTracker}>Fermer la calibration · Échap</button>
    </header>

    {phase === 'intro' && <section className="tracker-card">
      <span className="tracker-eyebrow">VOTRE REGARD, UNE ZONE UTILE</span>
      <h1>Calibrons le regard.</h1>
      <p>Neuf cibles pour apprendre, quatre autres pour mesurer. Gardez la tête dans une position confortable, face à l’écran.</p>
      <div className="tracker-privacy"><strong>La webcam reste sur ce Mac.</strong><span>Les images de votre visage ne sont pas envoyées à Holo. Vous pourrez arrêter le suivi depuis le panneau H-Companion.</span></div>
      <button className="tracker-primary" onClick={() => void startCamera()}>Activer la caméra et calibrer <span>↗</span></button>
      <small>La fenêtre s’efface pendant l’autorisation macOS, puis revient. Échap permet de quitter.</small>
    </section>}

    {phase === 'starting' && <section className="tracker-card" role="status">
      <span className="tracker-loader" />
      <h1>Préparation de la webcam</h1>
      <p>Autorisez l’accès à la caméra si macOS vous le demande. Le modèle de suivi est chargé localement.</p>
    </section>}

    {isCollecting && <>
      <div className="tracker-instruction" aria-live="polite">
        <span className="tracker-eyebrow">{phase === 'calibration' ? '01 / APPRENTISSAGE' : '02 / VALIDATION INDÉPENDANTE'}</span>
        <h1>{sampling ? 'Gardez les yeux sur la cible.' : 'Fixez la cible, puis cliquez dessus.'}</h1>
      </div>
      <button className={`tracker-target ${sampling ? 'is-sampling' : ''}`}
        style={{ left: `${activeTarget.x * 100}%`, top: `${activeTarget.y * 100}%` }}
        onClick={collectTarget} disabled={sampling} aria-label={`Cible ${point + 1}`}>
        <span className="tracker-target-ring" />
        <span className="tracker-target-number">{point + 1}</span>
      </button>
      <footer className="tracker-footer">
        <div className="tracker-progress-track"><span style={{ width: `${progress * 100}%` }} /></div>
        <strong>{point + 1} / {phase === 'calibration' ? CALIBRATION.length : VALIDATION.length} cibles</strong>
        <p>{notice || (phase === 'validation' ? 'Ces mesures ne modifient pas la calibration.' : 'Seules ces cibles entraînent le modèle. Aucun apprentissage sur les clics de l’agent.')}</p>
      </footer>
    </>}

    {phase === 'summary' && <section className="tracker-card">
      <span className="tracker-eyebrow">VALIDATION TERMINÉE</span>
      <h1>Votre zone est prête.</h1>
      <div className="tracker-result"><strong>{Math.round(calibrationError ?? 0)}</strong><span>px logiques<br />d’erreur médiane</span></div>
      <p>Mesure sur quatre cibles distinctes : écart entre la prédiction et la fixation demandée. Ce n’est pas une mesure du regard réel par un appareil de référence.</p>
      <p>Après « Commencer le suivi », cette fenêtre devient invisible. L’erreur de validation reste visible dans le panneau, à côté du statut du regard.</p>
      <button className="tracker-primary" onClick={() => void finish()}>Commencer le suivi <span>↗</span></button>
      <button className="tracker-secondary" onClick={() => window.location.reload()}>Refaire la calibration</button>
    </section>}

    {phase === 'error' && <section className="tracker-card" role="alert">
      <span className="tracker-eyebrow">SUIVI INDISPONIBLE</span>
      <h1>La caméra a besoin d’attention.</h1>
      <p>{error}</p>
      <button className="tracker-primary" onClick={() => window.location.reload()}>Réessayer</button>
      <button className="tracker-secondary" onClick={stopTracker}>Continuer sans regard</button>
    </section>}
  </main>;
}
