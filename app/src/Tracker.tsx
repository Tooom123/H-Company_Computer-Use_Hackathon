import { useEffect, useRef, useState } from 'react';
import type { GazeSample } from './lib/types';
import { cameraErrorMessage, WebGazerTracker } from './lib/webgazer';
import { HeadScreenMapper, type HeadPose } from './lib/head-pose';
import { calibrationTargets, type CalibrationProfile } from './lib/calibration-targets';
import './tracker.css';

type CollectionPhase = 'calibration' | 'validation' | 'head-calibration' | 'head-validation';
type Phase = 'intro' | 'starting' | CollectionPhase | 'head-intro' | 'summary' | 'tracking' | 'error';
type Target = { x: number; y: number };
type Sampling = {
  phase: CollectionPhase; target: Target; index: number;
  startedAt: number; lastAt: number; accepted: number; errors: number[];
};
const isCollectionPhase = (phase: Phase): phase is CollectionPhase => ['calibration', 'validation', 'head-calibration', 'head-validation'].includes(phase);
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
  const [headError, setHeadError] = useState<number | null>(null);
  const [mode, setMode] = useState<'gaze' | 'head' | 'hybrid'>('gaze');
  const [profile, setProfile] = useState<CalibrationProfile>('wide');
  const [viewport, setViewport] = useState({ width: window.innerWidth, height: window.innerHeight });
  const [error, setError] = useState('');
  const phaseRef = useRef<Phase>('intro');
  const tracker = useRef<WebGazerTracker | null>(null);
  const collection = useRef<Sampling | null>(null);
  const validationErrors = useRef<number[]>([]);
  const calibrationErrorRef = useRef<number | undefined>(undefined);
  const headErrorRef = useRef<number | undefined>(undefined);
  const modeRef = useRef<'gaze' | 'head' | 'hybrid'>('gaze');
  const profileRef = useRef<CalibrationProfile>('wide');
  const viewportRef = useRef(viewport);
  const headMapper = useRef(new HeadScreenMapper());
  const gazeCalibrated = useRef(false);
  const headCalibrated = useRef(false);
  const lastReportedTracking = useRef<'tracking' | 'lost' | null>(null);

  function changePhase(next: Phase) {
    phaseRef.current = next;
    setPhase(next);
  }

  function targetsFor(current: Phase) {
    return calibrationTargets(isCollectionPhase(current) ? current : 'validation', profileRef.current, viewportRef.current);
  }

  function calibrationStatus() {
    return { calibrationProfile: profileRef.current, calibrationErrorPx: calibrationErrorRef.current, headCalibrationErrorPx: headErrorRef.current,
      gazeCalibrated: gazeCalibrated.current, headCalibrated: headCalibrated.current,
      headMessage: headCalibrated.current ? 'Orientation FaceMesh calibrée · estimation approximative' : 'Tête non calibrée' };
  }

  useEffect(() => {
    let mounted = true;
    void window.companion.getState().then(state => {
      if (!mounted) return;
      const selected = state.settings.selection;
      modeRef.current = selected === 'head' || selected === 'hybrid' ? selected : 'gaze';
      setMode(modeRef.current);
    });
    const instance = new WebGazerTracker((sample: GazeSample | null, pose: HeadPose | null) => {
      if (phaseRef.current === 'tracking') {
        const gazePoint = gazeCalibrated.current ? sample : null;
        const headPrediction = pose && headCalibrated.current ? headMapper.current.predictWithDiagnostics(pose)
          : { point: null, reason: 'uncalibrated' as const };
        const headPoint = headPrediction.point;
        window.companion.reportGaze(gazePoint);
        window.companion.reportHead(pose ? { ...headPrediction, pose, emittedAt: Date.now() } : null);
        const state = gazePoint || headPoint ? 'tracking' : 'lost';
        if (state !== lastReportedTracking.current) {
          lastReportedTracking.current = state;
          window.companion.reportTracker({ state, ...calibrationStatus(),
            message: state === 'tracking' ? 'Suivi actif · traitement local' : 'Signaux indisponibles · repli plein écran' });
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
      } else if (current.phase === 'head-calibration') {
        if (!pose || !headMapper.current.addSample(pose, current.target)) return;
        current.accepted += 1;
      } else {
        const prediction = current.phase === 'head-validation' ? (pose && headMapper.current.predict(pose)) : sample;
        if (!prediction) return;
        current.errors.push(Math.hypot(prediction.x - current.target.x, prediction.y - current.target.y));
        current.accepted += 1;
      }
      const training = current.phase === 'calibration' || current.phase === 'head-calibration';
      const count = training ? CALIBRATION_SAMPLES : VALIDATION_SAMPLES;
      setProgress(current.accepted / count);
      if (current.accepted < count) return;
      collection.current = null;
      setSampling(false);
      setProgress(0);
      if (training) {
        if (current.index < targetsFor(current.phase).length - 1) setPoint(current.index + 1);
        else {
          setPoint(0);
          validationErrors.current = [];
          if (current.phase === 'head-calibration') {
            const fitted = headMapper.current.fit({ width: window.innerWidth, height: window.innerHeight });
            if (!fitted.ready) {
              setNotice(fitted.reason || 'Les mouvements sont insuffisants. Réessayez en orientant la tête vers chaque cible.');
              changePhase('head-intro');
            } else changePhase('head-validation');
          } else changePhase('validation');
        }
      } else {
        validationErrors.current.push(median(current.errors));
        if (current.index < targetsFor(current.phase).length - 1) setPoint(current.index + 1);
        else {
          const measured = median(validationErrors.current);
          if (current.phase === 'head-validation') {
            headErrorRef.current = measured;
            setHeadError(measured);
            headCalibrated.current = true;
          } else {
            calibrationErrorRef.current = measured;
            setCalibrationError(measured);
            gazeCalibrated.current = true;
          }
          window.companion.reportTracker({ state: 'calibrating', ...calibrationStatus(),
            message: 'Validation terminée · en attente de démarrage' });
          changePhase(current.phase === 'validation' && modeRef.current === 'hybrid' ? 'head-intro' : 'summary');
        }
      }
    });
    tracker.current = instance;
    const watchdog = window.setInterval(() => {
      if (collection.current && performance.now() - collection.current.startedAt > 7_000) {
        collection.current = null;
        setSampling(false);
        setProgress(0);
        setNotice('Pas assez de mesures. Gardez le visage visible et réessayez la cible. Pour la tête, reproduisez les mouvements de calibration.');
      }
    }, 200);
    const onResize = () => {
      if (phaseRef.current === 'intro') {
        viewportRef.current = { width: window.innerWidth, height: window.innerHeight };
        setViewport(viewportRef.current);
        return;
      }
      instance.dispose();
      collection.current = null;
      window.companion.reportGaze(null);
      window.companion.reportHead(null);
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
      mounted = false;
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
    viewportRef.current = { width: window.innerWidth, height: window.innerHeight };
    setViewport(viewportRef.current);
    changePhase('starting');
    window.companion.reportTracker({ state: 'calibrating', message: 'Initialisation de la webcam et du modèle local' });
    try {
      await window.companion.requestCamera();
      if (!tracker.current || phaseRef.current !== 'starting') return;
      await tracker.current?.start();
      if (!tracker.current || phaseRef.current !== 'starting') return;
      setPoint(0);
      changePhase(modeRef.current === 'head' ? 'head-intro' : 'calibration');
      window.companion.reportTracker({ state: 'calibrating', ...calibrationStatus(), message: 'Calibration humaine en cours' });
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
    if (collection.current || !isCollectionPhase(phase)) return;
    const target = targetsFor(phase)[point];
    collection.current = { phase, index: point,
      target: { ...target },
      startedAt: performance.now(), lastAt: 0, accepted: 0, errors: [] };
    setNotice('');
    setSampling(true);
    setProgress(0);
  }

  function startHeadCalibration() {
    headMapper.current.reset(); headCalibrated.current = false;
    headErrorRef.current = undefined; setHeadError(null);
    validationErrors.current = []; collection.current = null;
    setPoint(0); setProgress(0); setSampling(false); setNotice('');
    changePhase('head-calibration');
  }

  async function finish() {
    changePhase('tracking');
    window.companion.reportTracker({ state: 'tracking', ...calibrationStatus(), message: 'Suivi actif · traitement local' });
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
  const activeTarget = targetsFor(phase)[point];
  const isCollecting = isCollectionPhase(phase);
  const headPhase = phase === 'head-calibration' || phase === 'head-validation';
  const validating = phase === 'validation' || phase === 'head-validation';

  return <main className={`tracker-screen ${isCollecting ? 'tracker-collecting' : ''}`}>
    <header className="tracker-header">
      <div className="tracker-wordmark"><span className="tracker-logo">H</span> COMPANION <span className="tracker-tag">{mode === 'head' ? 'TÊTE' : mode === 'hybrid' ? 'REGARD + TÊTE' : 'REGARD'}</span></div>
      <button className="tracker-close" onClick={stopTracker}>Fermer la calibration · Échap</button>
    </header>

    {phase === 'intro' && <section className="tracker-card">
      <span className="tracker-eyebrow">VOTRE REGARD, UNE ZONE UTILE</span>
      <h1>{mode === 'head' ? 'Calibrons la tête.' : 'Calibrons le regard.'}</h1>
      <p>{mode === 'head' ? 'Cinq cibles pour relier vos mouvements de tête à l’écran, puis quatre cibles pour mesurer l’erreur.' : 'Neuf cibles pour apprendre, quatre autres pour mesurer. Pour cette étape, gardez la tête dans une position confortable et stable.'}</p>
      {mode === 'hybrid' && <p>Une seconde étape calibrera ensuite la tête, avec des mouvements légers vers cinq cibles. Les yeux et la tête seront évalués séparément.</p>}
      <label className="tracker-profile">Répartition des cibles
        <select aria-label="Profil de calibration" value={profile} onChange={event => {
          const next = event.target.value as CalibrationProfile;
          profileRef.current = next;
          setProfile(next);
        }}>
          <option value="wide">Bords étendus</option>
          <option value="standard">Standard</option>
        </select>
      </label>
      <p className="tracker-profile-note">{profile === 'wide'
        ? 'Les cibles approchent les quatre coins, à 48 px du bord pour rester entièrement visibles. Les points de validation sont distincts et proches des bords.'
        : 'Répartition initiale, plus centrale. Gardez ce profil pour comparer au premier essai.'}</p>
      <div className="tracker-privacy"><strong>La webcam reste sur ce Mac.</strong><span>Les images de votre visage ne sont pas envoyées à Holo. Vous pourrez arrêter le suivi depuis le panneau H-Companion.</span></div>
      <button className="tracker-primary" onClick={() => void startCamera()}>Activer la caméra et calibrer <span>↗</span></button>
      <small>La fenêtre s’efface pendant l’autorisation macOS, puis revient. Échap permet de quitter.</small>
    </section>}

    {phase === 'starting' && <section className="tracker-card" role="status">
      <span className="tracker-loader" />
      <h1>Préparation de la webcam</h1>
      <p>Autorisez l’accès à la caméra si macOS vous le demande. Le modèle de suivi est chargé localement.</p>
    </section>}

    {phase === 'head-intro' && <section className="tracker-card">
      <span className="tracker-eyebrow">ORIENTATION DE LA TÊTE · EXPÉRIMENTAL</span>
      <h1>Orientez la tête vers la cible.</h1>
      <p>Tournez légèrement le visage à gauche ou à droite, et inclinez-le vers le haut ou le bas, comme si votre nez désignait la cible. Gardez le buste et la distance à l’écran stables.</p>
      {profile === 'wide' && <p>Les cibles sont proches des coins. Gardez des mouvements confortables ; ne forcez pas la rotation du cou. Une position non détectée ne sera pas comptée.</p>}
      <p>Cliquez quand vous êtes en position et maintenez-la pendant la collecte. Cinq cibles servent à apprendre ; quatre autres mesurent l’erreur sans modifier le modèle. L’orientation de la tête n’est pas une mesure de l’endroit regardé.</p>
      {notice && <p role="alert">{notice}</p>}
      <button className="tracker-primary" onClick={startHeadCalibration}>Calibrer la tête · 5 cibles <span>↗</span></button>
    </section>}

    {isCollecting && <>
      <div className="tracker-instruction" aria-live="polite">
        <span className="tracker-eyebrow">{headPhase ? 'TÊTE · ' : 'YEUX · '}{validating ? 'VALIDATION INDÉPENDANTE' : 'APPRENTISSAGE'}</span>
        <h1>{headPhase ? (sampling ? 'Gardez la tête orientée vers la cible.' : 'Orientez la tête vers la cible, puis cliquez.') : (sampling ? 'Gardez les yeux sur la cible.' : 'Fixez la cible, puis cliquez dessus.')}</h1>
      </div>
      <button className={`tracker-target ${sampling ? 'is-sampling' : ''}`}
        style={{ left: `${activeTarget.x}px`, top: `${activeTarget.y}px` }}
        onClick={collectTarget} disabled={sampling} aria-label={`Cible ${point + 1}`}>
        <span className="tracker-target-ring" />
        <span className="tracker-target-number">{point + 1}</span>
      </button>
      <footer className="tracker-footer">
        <div className="tracker-progress-track"><span style={{ width: `${progress * 100}%` }} /></div>
        <strong>{point + 1} / {targetsFor(phase).length} cibles</strong>
        <p>{notice || (validating ? 'Ces mesures ne modifient pas la calibration.' : 'Seules ces cibles entraînent le modèle. Aucun apprentissage sur les clics de l’agent.')}</p>
      </footer>
    </>}

    {phase === 'summary' && <section className="tracker-card">
      <span className="tracker-eyebrow">VALIDATION TERMINÉE</span>
      <p className="tracker-profile-summary">Profil : {profile === 'wide' ? 'Bords étendus' : 'Standard'} · {viewport.width} × {viewport.height} px logiques</p>
      <h1>Votre zone est prête.</h1>
      {calibrationError !== null && <div className="tracker-result"><strong>{Math.round(calibrationError)}</strong><span>Yeux · px logiques<br />d’erreur médiane</span></div>}
      {headError !== null && <div className="tracker-result"><strong>{Math.round(headError)}</strong><span>Tête · px logiques<br />d’erreur médiane</span></div>}
      <p>Mesure sur quatre cibles distinctes : écart entre la prédiction et la fixation demandée. Ce n’est pas une mesure du regard réel par un appareil de référence.</p>
      <p>Après « Commencer le suivi », cette fenêtre devient invisible. L’erreur de validation reste visible dans le panneau, à côté du statut du regard.</p>
      <button className="tracker-primary" onClick={() => void finish()}>Commencer le suivi <span>↗</span></button>
      {!headCalibrated.current && gazeCalibrated.current && <button className="tracker-secondary" onClick={() => { setNotice(''); changePhase('head-intro'); }}>Ajouter la calibration de la tête</button>}
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
