import { useEffect, useRef, useState } from 'react';
import { agentVerdictLabel, archiveLabel, elapsedSeconds, isTerminal, monoWav, scopeVerdictLabel, spokenPrompt, stateLabel } from './lib/voice-pilot';
import type { AudioTranscript, PilotSnapshot, PilotStatus, Scenario, TaskFeedback, UsefulFeedback, VoicePurpose } from './lib/voice-pilot';
import './voice-pilot.css';

const storageKey = 'hcompanion.voice-pilot.v1';
const draftKey = (session: string) => `hcompanion.voice-pilot.feedback-draft.v1:${session}`;
type FeedbackDraft = { comment: string; outcome: TaskFeedback; useful: UsefulFeedback; allowTraining: boolean; feedbackAudio: AudioTranscript | null };
function stored(): { workflow?: string; reference?: string; session?: string; scenario?: string } {
  try { return JSON.parse(localStorage.getItem(storageKey) || '{}'); } catch { return {}; }
}
function storedDraft(session?: string): Partial<FeedbackDraft> {
  try {
    const value = session ? JSON.parse(localStorage.getItem(draftKey(session)) || '{}') : {};
    return value && typeof value === 'object' ? value : {};
  } catch { return {}; }
}
function errorText(error: unknown): string { return error instanceof Error ? error.message : String(error); }

export default function VoicePilot() {
  const initial = useRef(stored());
  const initialDraft = useRef(storedDraft(initial.current.session));
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [status, setStatus] = useState<PilotStatus | null>(null);
  const [scenarioId, setScenarioId] = useState(initial.current.scenario || '');
  const [reference, setReference] = useState(initial.current.reference || '');
  const [workflow] = useState(initial.current.workflow || crypto.randomUUID());
  const [sessionId, setSessionId] = useState<string | null>(initial.current.session || null);
  const [snapshot, setSnapshot] = useState<PilotSnapshot | null>(null);
  const [goal, setGoal] = useState('');
  const [requestAudio, setRequestAudio] = useState<AudioTranscript | null>(null);
  const [feedbackAudio, setFeedbackAudio] = useState<AudioTranscript | null>(initialDraft.current.feedbackAudio || null);
  const [comment, setComment] = useState(typeof initialDraft.current.comment === 'string' ? initialDraft.current.comment : '');
  const [outcome, setOutcome] = useState<TaskFeedback>(initialDraft.current.outcome || 'unknown');
  const [useful, setUseful] = useState<UsefulFeedback>(initialDraft.current.useful || 'unknown');
  const [allowTraining, setAllowTraining] = useState(initialDraft.current.allowTraining === true);
  const [feedbackSaved, setFeedbackSaved] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [recording, setRecording] = useState<VoicePurpose | null>(null);
  const [recordSeconds, setRecordSeconds] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [questionViewRequest, setQuestionViewRequest] = useState(0);
  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const recordTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const mounted = useRef(true);
  const polling = useRef(false);
  const questionSection = useRef<HTMLElement | null>(null);
  const responseSection = useRef<HTMLElement | null>(null);
  const feedbackSection = useRef<HTMLElement | null>(null);
  const displayedReports = useRef(new Set<string>());
  const scenario = scenarios.find(item => item.id === scenarioId);
  const terminal = isTerminal(snapshot?.state);
  const restoredTerminal = Boolean(snapshot?.restored_read_only && terminal);
  const active = Boolean(sessionId && snapshot && !terminal);
  const blockedSelection = Boolean(sessionId && !feedbackSaved);
  const speaking = Boolean(recording || busy?.startsWith('audio'));
  const canRetryWithoutFeedback = Boolean(sessionId && snapshot && (restoredTerminal || ['stopped', 'failed', 'preflight_failed'].includes(snapshot.state)) && !feedbackSaved && !snapshot.pilot?.feedback);
  const api = window.voicePilot;

  useEffect(() => {
    mounted.current = true;
    if (!api) { setError('Ouvrez cet écran depuis l’application H-Companion.'); return; }
    void Promise.all([api.request<PilotStatus>('GET', '/pilot/status'), api.request<Scenario[]>('GET', '/pilot/scenarios')])
      .then(([info, list]) => {
        if (!mounted.current) return;
        setStatus(info); setScenarios(list);
        // A restored episode owns its selection. For a fresh profile (or an old
        // saved selection outside this catalog), use the first available card.
        if (!initial.current.session) setScenarioId(current => list.some(item => item.id === current) ? current : list[0]?.id || '');
      })
      .catch(cause => { if (mounted.current) setError(`Le moteur n’est pas joignable. ${errorText(cause)}`); });
    return () => {
      mounted.current = false;
      if (recordTimer.current) clearInterval(recordTimer.current);
      if (recorder.current?.state === 'recording') recorder.current.stop();
      stream.current?.getTracks().forEach(track => track.stop());
    };
  }, [api]);

  useEffect(() => {
    try { localStorage.setItem(storageKey, JSON.stringify({ workflow, reference, session: sessionId, scenario: scenarioId })); } catch { /* Storage is optional. */ }
  }, [workflow, reference, sessionId, scenarioId]);

  useEffect(() => {
    if (!sessionId || !api) return;
    let cancelled = false;
    const update = async () => {
      if (polling.current) return;
      polling.current = true;
      try {
        const next = await api.request<PilotSnapshot>('GET', `/pilot/episodes/${encodeURIComponent(sessionId)}`);
        if (cancelled) return;
        setSnapshot(next);
        if (next.pilot?.scenario_id) setScenarioId(next.pilot.scenario_id);
        if (next.request?.goal) setGoal(next.request.goal);
        if (next.pilot?.feedback) setFeedbackSaved(true);
      } catch (cause) { if (!cancelled) setError(`Actualisation interrompue. ${errorText(cause)}`); }
      finally { polling.current = false; }
    };
    void update();
    const timer = setInterval(() => void update(), 1200);
    return () => { cancelled = true; clearInterval(timer); };
  }, [sessionId, api]);

  useEffect(() => {
    if (!sessionId || !terminal || !snapshot?.report_ready || displayedReports.current.has(sessionId)) return;
    // Treat the ready report as one event, not every polling snapshot. Never
    // pull someone away from a feedback field or an in-progress recording.
    displayedReports.current.add(sessionId);
    if (speaking || feedbackSection.current?.contains(document.activeElement)) return;
    responseSection.current?.scrollIntoView({ block: 'start', behavior: 'instant' });
  }, [sessionId, terminal, snapshot?.report_ready, speaking]);

  useEffect(() => {
    if (questionViewRequest) questionSection.current?.scrollIntoView({ block: 'start', behavior: 'instant' });
  }, [questionViewRequest]);

  async function run(label: string, action: () => Promise<void>) {
    if (busy) return;
    setBusy(label); setError(null); setNotice(null);
    try { await action(); } catch (cause) { setError(errorText(cause)); }
    finally { setBusy(null); }
  }
  function stopRecording() { if (recorder.current?.state === 'recording') recorder.current.stop(); }
  async function startRecording(purpose: VoicePurpose) {
    if (!api || recording || busy) return;
    setBusy('audio-permission'); setError(null); setNotice(null);
    try {
      const permission = await api.requestMicrophone();
      if (!permission.granted) throw new Error('Le microphone n’est pas autorisé. Vous pouvez saisir le texte ci-dessous.');
      const mic = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true }, video: false });
      if (!mounted.current) { mic.getTracks().forEach(track => track.stop()); return; }
      stream.current = mic;
      const preferred = ['audio/webm;codecs=opus', 'audio/webm'].find(type => MediaRecorder.isTypeSupported(type));
      const media = new MediaRecorder(mic, preferred ? { mimeType: preferred } : undefined);
      recorder.current = media;
      const chunks: BlobPart[] = [];
      let seconds = 0;
      media.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
      media.onerror = () => { setError('L’enregistrement a échoué. Recommencez ou saisissez le texte.'); stopRecording(); };
      media.onstop = () => {
        if (recordTimer.current) clearInterval(recordTimer.current);
        recordTimer.current = null;
        mic.getTracks().forEach(track => track.stop()); stream.current = null; recorder.current = null;
        if (!mounted.current) return;
        setRecording(null); setBusy('audio-transcription');
        const blob = new Blob(chunks, { type: media.mimeType || 'audio/webm' });
        void (async () => {
          try {
            if (blob.size < 100) throw new Error('L’enregistrement est vide. Recommencez en parlant après l’activation du micro.');
            if (blob.size > 12 * 1024 * 1024) throw new Error('Enregistrement trop volumineux. Faites un retour plus court.');
            const decoded = await new OfflineAudioContext(1, 1, 16000).decodeAudioData(await blob.arrayBuffer());
            const wav = monoWav(Array.from({ length: decoded.numberOfChannels }, (_, index) => decoded.getChannelData(index)), decoded.sampleRate);
            const result = await api.uploadAudio({ purpose, mimeType: 'audio/wav', data: wav });
            if (!mounted.current) return;
            if (!result.transcript.trim()) throw new Error('Aucune parole reconnue. Recommencez ou saisissez votre texte.');
            if (purpose === 'request') { setRequestAudio(result); setGoal(result.transcript); }
            else { setFeedbackAudio(result); setComment(result.transcript); }
            setNotice('Transcription prête. Relisez-la et corrigez les références si nécessaire.');
          } catch (cause) { if (mounted.current) setError(errorText(cause)); }
          finally { if (mounted.current) setBusy(null); }
        })();
      };
      media.start(300); setRecording(purpose); setRecordSeconds(0); setBusy(null);
      recordTimer.current = setInterval(() => { seconds += 1; setRecordSeconds(seconds); if (seconds >= 60) stopRecording(); }, 1000);
    } catch (cause) {
      stream.current?.getTracks().forEach(track => track.stop()); stream.current = null;
      setError(errorText(cause)); setBusy(null);
    }
  }
  function chooseScenario(id: string, retryWithoutFeedback = false) {
    const retryCurrent = retryWithoutFeedback && id === scenarioId && canRetryWithoutFeedback;
    if (busy || speaking || (retryWithoutFeedback ? !retryCurrent : blockedSelection)) return;
    const hasDraft = Boolean(comment.trim() || feedbackAudio || outcome !== 'unknown' || useful !== 'unknown' || allowTraining);
    if (retryWithoutFeedback && hasDraft && !saveLocalDraft()) return;
    setScenarioId(id); setSessionId(null); setSnapshot(null); setGoal(''); setComment('');
    setRequestAudio(null); setFeedbackAudio(null); setFeedbackSaved(false);
    setOutcome('unknown'); setUseful('unknown'); setAllowTraining(false); setError(null); setNotice(null);
    if (retryWithoutFeedback && hasDraft) setNotice('Le brouillon de retour reste conservé localement avec l’ancien essai. Aucun feedback ni consentement n’a été envoyé.');
    setQuestionViewRequest(value => value + 1);
  }
  function saveLocalDraft(): boolean {
    if (!sessionId) return false;
    try {
      localStorage.setItem(draftKey(sessionId), JSON.stringify({ comment, outcome, useful, allowTraining, feedbackAudio }));
      setNotice('Brouillon conservé sur ce poste uniquement. Il ne constitue pas un feedback enregistré ni un consentement transmis.');
      return true;
    } catch {
      setError('Impossible de conserver le brouillon local. Copiez votre texte avant de quitter cet essai.');
      return false;
    }
  }
  async function prepare() {
    if (!api || !scenario) return;
    await run('prepare', async () => {
      const next = await api.request<PilotSnapshot>('POST', '/pilot/episodes', {
        scenario_id: scenario.id, goal: goal.trim(), request_audio_id: requestAudio?.audio_id,
        run_reference: scenario.requires_reference ? reference.trim() : undefined, workflow_id: workflow,
      });
      setSnapshot(next); setSessionId(next.session_id); setFeedbackSaved(false);
    });
  }
  async function saveFeedback() {
    if (!api || !sessionId || snapshot?.restored_read_only) return;
    await run('feedback', async () => {
      await api.request('POST', `/pilot/episodes/${encodeURIComponent(sessionId)}/feedback`, {
        task_success_user: outcome, useful, comment, audio_id: feedbackAudio?.audio_id, allow_training: allowTraining,
      });
      setFeedbackSaved(true); setNotice('Votre retour et vos choix sont enregistrés avec cet essai.');
    });
  }
  const nextScenario = scenarios.findIndex(item => item.id === scenarioId) + 1;
  const duration = snapshot ? elapsedSeconds(snapshot) : null;
  const recordButton = (purpose: VoicePurpose, text: string) => (
    <button className={`vp-button vp-mic ${recording === purpose ? 'vp-recording' : ''}`}
      disabled={Boolean(busy) || Boolean(recording && recording !== purpose) || !status?.transcription.ready}
      onClick={() => recording === purpose ? stopRecording() : void startRecording(purpose)}>
      <span aria-hidden="true">{recording === purpose ? '■' : '●'}</span>
      {recording === purpose ? `Terminer · ${recordSeconds} s` : text}
    </button>
  );
  const audioNotice = () => <p className="vp-small">
    {status && <>Transcription : <strong>{status.transcription.provider}</strong>. {status.transcription.message || (status.transcription.ready ? 'Prête.' : 'La transcription n’est pas prête. La saisie reste disponible.')} </>}
    Le micro ne s’active qu’après votre clic. Arrêt automatique à 60 secondes. Une copie de votre audio et sa transcription sont conservées dans le dossier privé de l’essai.
  </p>;

  return <main className="vp-shell">
    <header className="vp-header">
      <div><span className="vp-brand">H-Companion</span><span className="vp-subtitle">Recette vocale · Odoo</span>
        {(status?.environment || status?.engine_revision) && <p className="vp-small" aria-label="Environnement du test">
          {status.environment && <strong>{status.environment.label}</strong>}
          {status.environment && status.engine_revision && ' · '}
          {status.engine_revision && <>Moteur <code>{status.engine_revision}</code></>}
        </p>}
        {status?.environment?.entry_url && <p className="vp-small">Odoo : <code>{status.environment.entry_url}</code></p>}
      </div>
      <div className="vp-header-tags"><span className={`vp-tag ${status?.simulated ? 'vp-tag-warning' : ''}`}>{status ? status.simulated ? 'SIMULATION' : status.model : 'Connexion au moteur…'}</span><span className="vp-tag">Écran complet</span></div>
    </header>
    <div className="vp-layout">
      <aside className="vp-sidebar" aria-label="Les dix scénarios">
        <p className="vp-eyebrow">VOTRE PARCOURS</p><h2>Dix demandes,<br />un retour à chaque fois.</h2>
        <nav>{scenarios.map(item => <button key={item.id} className={`vp-scenario ${item.id === scenarioId ? 'vp-selected' : ''}`}
          disabled={blockedSelection || Boolean(busy) || Boolean(recording)} aria-current={item.id === scenarioId ? 'step' : undefined}
          onClick={() => chooseScenario(item.id)}><span>{item.id}</span><span>{item.title}</span></button>)}</nav>
        <p className="vp-small">{scenarios.some(item => item.depends_on)
          ? 'Certains scénarios suivent le même parcours. Passez au suivant après avoir contrôlé l’étape précédente.'
          : 'Vérifiez la situation de départ de chaque scénario, puis donnez votre retour avant de passer au suivant.'}</p>
      </aside>
      <section className="vp-main" aria-label="Scénario et demande">
        <div className="vp-intro"><p className="vp-eyebrow">SCÉNARIO {scenario?.id || '—'} / 10</p><h1>{scenario?.title || 'Votre assistant se prépare.'}</h1><p>Parlez, relisez, puis observez H-Companion dans Odoo.</p>
          {status?.environment?.id === 'odoo-rich-v2.1' && <p className="vp-small">Lecture seule · CRM, achats, stock, projets et activités métier.</p>}
          <p className="vp-small">Ces essais servent de référence avec l’écran complet. Le recadrage du Vision Lab n’est pas activé pour ces essais.</p></div>
        {error && <div className="vp-alert vp-error" role="alert">{error}</div>}
        {notice && <div className="vp-alert" role="status">{notice}</div>}
        {busy === 'audio-transcription' && <div className="vp-alert" role="status">Transcription en cours… Le microphone est arrêté.</div>}

        {!sessionId && <section className="vp-card vp-scroll-target" ref={questionSection}>
          <div className="vp-card-heading"><span className="vp-number">1</span><h2>Posez votre question</h2></div>
          {scenario?.requires_reference && <div className="vp-reference"><label htmlFor="vp-reference">Référence commune aux scénarios 05 à 10</label><input id="vp-reference" value={reference} onChange={event => setReference(event.target.value)} placeholder="Référence libre réservée pour ce passage" disabled={speaking || Boolean(busy)} /><p>Utilisez la même référence pour toute la commande. Vérifiez qu’aucun autre passage ne l’utilise.</p></div>}
          {scenario && <blockquote className="vp-prompt">{spokenPrompt(scenario.prompt, reference)}</blockquote>}
          <div className="vp-actions">{recordButton('request', 'Dicter ma demande')}<button className="vp-link" disabled={speaking || Boolean(busy) || !scenario} onClick={() => { if (scenario) { setGoal(spokenPrompt(scenario.prompt, reference)); setRequestAudio(null); } }}>Utiliser cette consigne</button></div>
          {audioNotice()}
          <label htmlFor="vp-goal">Votre demande · transcription à relire</label><textarea id="vp-goal" value={goal} onChange={event => setGoal(event.target.value)} disabled={speaking || Boolean(busy)} rows={4} placeholder="Votre question apparaîtra ici. Vous pouvez aussi la saisir." />
          <div className="vp-actions vp-end"><button className="vp-button vp-primary" disabled={!api || !status || !goal.trim() || speaking || Boolean(busy) || Boolean(scenario?.requires_reference && !reference.trim())} onClick={() => void prepare()}>{busy === 'prepare' ? 'Préparation…' : 'Préparer le plan'}</button></div>
          <p className="vp-small">Cette étape prépare la demande. H-Companion attendra votre approbation avant d’agir.</p>
        </section>}

        {snapshot && <section className="vp-card">
          <div className="vp-card-heading"><span className="vp-number">2</span><h2>{stateLabel(snapshot.state)}</h2>{snapshot.simulated && <span className="vp-tag vp-tag-warning">SIMULÉ</span>}</div>
          <p className="vp-goal-summary">{snapshot.request?.goal || goal}</p>
          {snapshot.pilot?.quarantine && <div className="vp-alert vp-error" role="alert" aria-label="Trace en quarantaine">
            <strong>Trace en quarantaine — exclue de l’entraînement ; capture hors périmètre à revoir.</strong>
          </div>}
          {snapshot.state === 'awaiting_approval' && <>
            <h3>{snapshot.plan?.objective || 'Plan proposé'}</h3>
            <div className="vp-scope"><div><h4>Actions prévues</h4><ul>{snapshot.plan?.allowed_actions?.map(action => <li key={action}>{action}</li>)}</ul></div><div><h4>Actions interdites</h4><ul>{snapshot.plan?.forbidden_actions?.map(action => <li key={action}>{action}</li>)}</ul></div></div>
            <div className="vp-alert">Placez Odoo derrière ce panneau. Après approbation, il se masque et vous avez 3 secondes pour mettre Odoo au premier plan. Les captures sont envoyées à H pendant l’intervention.</div>
            <div className="vp-actions"><button className="vp-button vp-primary" disabled={Boolean(busy)} onClick={() => void run('approve', async () => { if (api && sessionId) setSnapshot(await api.approve(sessionId)); })}>Approuver et observer Odoo</button><button className="vp-button" disabled={Boolean(busy)} onClick={() => void run('stop', async () => { if (api && sessionId) setSnapshot(await api.stop(sessionId)); })}>Annuler cet essai</button></div>
          </>}
          {active && snapshot.state !== 'awaiting_approval' && <div className="vp-running"><p>Observez Odoo sans changer de fenêtre. Le panneau revient à la fin.</p><button className="vp-button vp-danger" onClick={() => void run('stop', async () => { if (api && sessionId) setSnapshot(await api.stop(sessionId)); })} disabled={Boolean(busy) || snapshot.state === 'stopping'}>Arrêter l’intervention</button></div>}
          {active && <p className="vp-small vp-stop-hint">Arrêt depuis Odoo : <kbd>⌘ / Ctrl</kbd> + <kbd>Maj</kbd> + <kbd>.</kbd> · Un arrêt n’annule pas les actions déjà effectuées.</p>}
          {snapshot.error && <p className="vp-error-text">{snapshot.error}</p>}
          {terminal && !snapshot.report_ready && <p className="vp-small" role="status">Préparation du compte rendu… La réponse apparaîtra ici.</p>}
          {terminal && snapshot.report_ready && <>
            <section className="vp-response vp-scroll-target" ref={responseSection} aria-labelledby="vp-response-title">
              <p className="vp-eyebrow">VOTRE RÉSULTAT</p>
              <h2 id="vp-response-title">Réponse de H-Companion</h2>
              <p className="vp-small">Vous dictez votre demande ; la réponse s’affiche par écrit, sans lecture audio.</p>
              <p className="vp-answer">{snapshot.declared?.summary || snapshot.declared?.blocker || 'Aucun résultat annoncé.'}</p>
            </section>
            <div className="vp-verification"><p className="vp-eyebrow">VÉRIFICATION SÉPARÉE</p><p>{snapshot.verification?.observed || 'Aucune vérification disponible.'}</p></div>
            {snapshot.pilot?.agent_review?.reviewer_type === 'ai' && <section className="vp-verification" aria-label="Revue IA">
              <p className="vp-eyebrow">REVUE IA DE LA RÉPONSE</p>
              <p><strong>Verdict IA : {agentVerdictLabel(snapshot.pilot.agent_review.task_success_agent)}</strong></p>
              {snapshot.pilot.agent_review.scope_compliance_agent !== undefined && <p><strong>Périmètre du parcours : {scopeVerdictLabel(snapshot.pilot.agent_review.scope_compliance_agent)}</strong></p>}
              <p className="vp-small">Cette revue est distincte du vérificateur du moteur et de votre retour. Elle ne détermine ni votre satisfaction, ni l’utilité de l’aide, ni votre accord d’entraînement.</p>
            </section>}
            <div className="vp-metrics"><span>{duration === null ? 'Durée non disponible' : `${duration.toLocaleString('fr-FR', { maximumFractionDigits: 1 })} s · action et vérification`}</span><span>{archiveLabel(snapshot.pilot?.export_status)}</span></div>
          </>}
          {canRetryWithoutFeedback && <div className="vp-alert">
            <p>Cet essai reste conservé sans feedback ni nouveau consentement d’entraînement. Un éventuel brouillon de retour sera conservé localement avec cet essai, sans être envoyé. Pour réessayer, posez une nouvelle question puis approuvez son plan.</p>
            <div className="vp-actions"><button className="vp-button" disabled={Boolean(busy) || speaking} onClick={() => chooseScenario(scenarioId, true)}>{restoredTerminal ? 'Conserver cet essai et retenter' : 'Retenter sans ajouter de feedback'}</button></div>
          </div>}
        </section>}

        {terminal && snapshot?.report_ready && <section className="vp-card" ref={feedbackSection} aria-label="Retour utilisateur">
          <div className="vp-card-heading"><span className="vp-number">3</span><h2>Votre retour sur l’aide reçue</h2></div>
          <p>« La tâche est-elle réussie ? Cette aide était-elle utile ? Ai-je dû corriger quelque chose ? » Vous pouvez aussi dire que vous n’avez pas pu observer le passage.</p>
          {!feedbackSaved ? <>
            {restoredTerminal && <p className="vp-alert">Cet ancien essai est restauré en lecture seule. Vous pouvez conserver un brouillon sur ce poste ou retenter ; le serveur n’accepte plus de feedback pour cet épisode.</p>}
            <div className="vp-actions">{recordButton('feedback', 'Dicter mon retour')}</div>
            {audioNotice()}
            <label htmlFor="vp-comment">Votre retour · transcription à relire</label><textarea id="vp-comment" rows={4} value={comment} onChange={event => setComment(event.target.value)} disabled={speaking || Boolean(busy)} placeholder="Décrivez ce qui vous a aidé, ce qui manque ou la correction nécessaire." />
            <div className="vp-feedback-fields"><div><label htmlFor="vp-outcome">Selon vous, la tâche est…</label><select id="vp-outcome" value={outcome} onChange={event => setOutcome(event.target.value as TaskFeedback)} disabled={speaking || Boolean(busy)}><option value="unknown">Non évaluée / je n’ai pas pu voir</option><option value="success">Réussie</option><option value="partial">Partiellement réussie</option><option value="failed">Échouée</option></select></div><div><label htmlFor="vp-useful">L’aide était-elle utile ?</label><select id="vp-useful" value={useful} onChange={event => setUseful(event.target.value as UsefulFeedback)} disabled={speaking || Boolean(busy)}><option value="unknown">Je ne sais pas encore</option><option value="yes">Oui</option><option value="no">Non</option></select></div></div>
            <label className="vp-consent"><input type="checkbox" checked={allowTraining} onChange={event => setAllowTraining(event.target.checked)} disabled={speaking || Boolean(busy)} /><span>J’autorise la réutilisation de cet essai, de ses captures et de mon retour pour préparer des données d’entraînement.</span></label>
            <p className="vp-small">Vos choix restent distincts de la vérification automatique. L’autorisation ne rend pas automatiquement la trace utilisable pour un entraînement.</p>
            <div className="vp-actions vp-end">{restoredTerminal
              ? <button className="vp-button" disabled={speaking || Boolean(busy)} onClick={() => saveLocalDraft()}>Conserver mon brouillon local</button>
              : <button className="vp-button vp-primary" disabled={speaking || Boolean(busy)} onClick={() => void saveFeedback()}>{busy === 'feedback' ? 'Enregistrement…' : 'Enregistrer mon retour'}</button>}</div>
          </> : <div className="vp-saved" role="status"><strong>Retour enregistré avec cet essai.</strong><p>Les scénarios de la liste sont à nouveau disponibles.</p><div className="vp-actions"><button className="vp-button" onClick={() => chooseScenario(scenarioId)}>Refaire ce scénario</button>{nextScenario > 0 && nextScenario < scenarios.length && <button className="vp-button vp-primary" onClick={() => chooseScenario(scenarios[nextScenario].id)}>Préparer le scénario {scenarios[nextScenario].id}</button>}</div></div>}
        </section>}
        <footer className="vp-footer">Cette recette constitue un premier lot de tests utilisateurs.{scenarios.some(item => item.depends_on) && ' Les étapes liées d’un même parcours ne sont pas des tâches indépendantes.'}</footer>
      </section>
    </div>
  </main>;
}
