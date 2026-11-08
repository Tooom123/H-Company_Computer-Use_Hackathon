export type VoicePurpose = 'request' | 'feedback';
export type TaskFeedback = 'success' | 'partial' | 'failed' | 'unknown';
export type UsefulFeedback = 'yes' | 'no' | 'unknown';
export type Scenario = {
  id: string; title: string; prompt: string; procedure_id: string;
  requires_reference: boolean; depends_on?: string;
};
export type AudioTranscript = { audio_id: string; transcript: string; provider: string };
export type PilotStatus = {
  model: string; simulated: boolean; busy: boolean;
  environment?: { id: string; label: string; entry_url: string; company: string; fixture_version: string };
  engine_revision?: string; support_revision?: string;
  transcription: { provider: string; ready: boolean; message?: string };
};
export type PilotPlan = { objective?: string; explanation?: string; allowed_actions?: string[]; forbidden_actions?: string[]; planned_changes?: string[] };
export type AgentReview = {
  reviewer_type: 'ai'; task_success_agent: 'success' | 'partial' | 'failure' | 'unknown';
  scope_compliance_agent?: 'success' | 'partial' | 'failure' | 'unknown';
};
export type TraceQuarantine = { status: string; reason: string };
export type PilotSnapshot = {
  session_id: string; state: string; simulated: boolean; plan?: PilotPlan;
  restored_read_only?: boolean;
  request?: { goal?: string; procedure_id?: string };
  declared?: { outcome?: string; summary?: string; blocker?: string | null };
  verification?: { performed?: boolean; satisfied?: boolean | null; observed?: string; checks?: Record<string, boolean> };
  steps?: { kind?: string; message?: string; description?: string }[];
  error?: string | null; report_ready?: boolean; report?: { timings?: { approved_at?: string; finished_at?: string }; feedback?: unknown };
  pilot?: { scenario_id?: string; workflow_id?: string; run_reference?: string; feedback?: unknown; export_status?: unknown; agent_review?: AgentReview; quarantine?: TraceQuarantine };
};
export interface VoicePilotAPI {
  request<T = unknown>(method: 'GET' | 'POST', path: string, body?: unknown): Promise<T>;
  uploadAudio(input: { purpose: VoicePurpose; mimeType: string; data: ArrayBuffer }): Promise<AudioTranscript>;
  approve(sessionId: string): Promise<PilotSnapshot>;
  stop(sessionId: string): Promise<PilotSnapshot>;
  requestMicrophone(): Promise<{ granted: boolean }>;
}
declare global { interface Window { voicePilot?: VoicePilotAPI } }

const terminalStates = new Set(['resolved', 'escalated', 'stopped', 'preflight_failed', 'failed', 'abandoned', 'workaround']);
export function isTerminal(state?: string): boolean { return Boolean(state && terminalStates.has(state)); }
export function stateLabel(state: string): string {
  return ({ created: 'Préparation', awaiting_approval: 'Votre accord est attendu', running: 'H-Companion agit',
    verifying: 'Vérification du résultat', awaiting_user: 'À vous de jouer', stopping: 'Arrêt demandé',
    resolved: 'Résultat vérifié', escalated: 'Un contrôle reste à résoudre', stopped: 'Essai interrompu',
    preflight_failed: 'Préparation bloquée', failed: 'Essai en échec', abandoned: 'Essai arrêté', workaround: 'Solution de contournement' } as Record<string, string>)[state] || state;
}
export function spokenPrompt(prompt: string, reference: string): string {
  return prompt.replaceAll('REFERENCE_DU_PASSAGE', reference.trim() || 'la référence de notre passage');
}
export function agentVerdictLabel(verdict?: string): string {
  return ({ success: 'Réussite', partial: 'Réussite partielle', failure: 'Échec', unknown: 'Non évaluée' } as Record<string, string>)[verdict || ''] || 'Non évaluée';
}
export function scopeVerdictLabel(verdict: string): string {
  return ({ success: 'Respecté', partial: 'Partiellement respecté', failure: 'Non respecté', unknown: 'Non évalué' } as Record<string, string>)[verdict] || 'Non évalué';
}
export function elapsedSeconds(snapshot: PilotSnapshot): number | null {
  const timings = snapshot.report?.timings;
  if (!timings?.approved_at || !timings.finished_at) return null;
  const value = (Date.parse(timings.finished_at) - Date.parse(timings.approved_at)) / 1000;
  return Number.isFinite(value) && value >= 0 ? value : null;
}
export function archiveLabel(status: unknown): string {
  const raw = typeof status === 'string' ? status : status && typeof status === 'object'
    ? String((status as Record<string, unknown>).status || (status as Record<string, unknown>).state || '') : '';
  return ({ complete: 'Archive des traces enregistrée', completed: 'Archive des traces enregistrée',
    exported: 'Archive des traces enregistrée', ready: 'Archive des traces enregistrée',
    pending: 'Archivage en attente', running: 'Archivage en cours', exporting: 'Archivage en cours',
    partial: 'Archive partielle — à examiner', failed: 'Archivage à reprendre', error: 'Archivage à reprendre',
    simulated: 'Essai simulé — aucune trace H réelle', skipped_simulated: 'Essai simulé — aucune trace H réelle',
    skipped: 'Pas de session H à archiver', skipped_no_h_session: 'Pas de session H à archiver',
    not_configured: 'Archivage non configuré' } as Record<string, string>)[raw]
    || 'État de l’archive en attente';
}

/** PCM16 WAV carries a duration even when Chromium's WebM recording has no duration header. */
export function monoWav(channels: readonly Float32Array[], sampleRate: number): ArrayBuffer {
  if (!channels.length || !Number.isInteger(sampleRate) || sampleRate < 8000 || sampleRate > 96000) throw new Error('Format audio invalide.');
  const frames = channels[0].length;
  if (!frames || channels.some(channel => channel.length !== frames)) throw new Error('Enregistrement audio vide ou incomplet.');
  const buffer = new ArrayBuffer(44 + frames * 2);
  const data = new DataView(buffer);
  const text = (offset: number, value: string) => { for (let i = 0; i < value.length; i += 1) data.setUint8(offset + i, value.charCodeAt(i)); };
  text(0, 'RIFF'); data.setUint32(4, 36 + frames * 2, true); text(8, 'WAVE'); text(12, 'fmt ');
  data.setUint32(16, 16, true); data.setUint16(20, 1, true); data.setUint16(22, 1, true);
  data.setUint32(24, sampleRate, true); data.setUint32(28, sampleRate * 2, true);
  data.setUint16(32, 2, true); data.setUint16(34, 16, true); text(36, 'data'); data.setUint32(40, frames * 2, true);
  for (let i = 0; i < frames; i += 1) {
    const mixed = channels.reduce((sum, channel) => sum + (Number.isFinite(channel[i]) ? channel[i] : 0), 0) / channels.length;
    const value = Math.max(-1, Math.min(1, mixed));
    data.setInt16(44 + i * 2, Math.round(value * (value < 0 ? 32768 : 32767)), true);
  }
  return buffer;
}
