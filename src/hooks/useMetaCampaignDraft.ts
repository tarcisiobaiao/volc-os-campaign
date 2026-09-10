import { useCallback, useEffect, useRef, useState } from 'react';
import type { Draft } from '@/components/trafego/meta/rascunho';
import { draftWithoutAuthority, MetaDraftError, readMetaCampaignDraft, saveMetaCampaignDraft } from '@/lib/metaCampaignDraftApi';

interface Options { draftRef: string; draft: Draft; onRestore: (draft: Draft) => void; enabled?: boolean; requireExisting?: boolean }
type Status = 'loading' | 'idle' | 'saving' | 'error' | 'conflict' | 'local';
function canonical(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === 'object') return Object.fromEntries(
    Object.entries(value).filter(([, item]) => item !== undefined).sort(([a], [b]) => a.localeCompare(b))
      .map(([key, item]) => [key, canonical(item)]),
  );
  return value;
}
const fingerprint = (draft: Draft) => JSON.stringify(canonical(draftWithoutAuthority(draft)));

/** Serialized autosave with optimistic concurrency. Conflicts never overwrite. */
export function useMetaCampaignDraft({ draftRef, draft, onRestore, enabled = true, requireExisting = false }: Options) {
  const [status, setStatus] = useState<Status>(enabled ? 'loading' : 'local');
  const [version, setVersion] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [savedFingerprint, setSavedFingerprint] = useState('');
  const [hydrated, setHydrated] = useState(false);
  const latest = useRef(draft); latest.current = draft;
  const restore = useRef(onRestore); restore.current = onRestore;
  const active = useRef(0);
  const ready = useRef(false);
  const revision = useRef(0);
  const saved = useRef('');
  const failure = useRef<Status | null>(null);
  const failedContent = useRef('');
  const retryOnEdit = useRef(false);
  const flight = useRef<Promise<boolean> | null>(null);

  const reload = useCallback(async () => {
    const epoch = ++active.current;
    ready.current = false; revision.current = 0; saved.current = ''; failure.current = null;
    failedContent.current = ''; retryOnEdit.current = false;
    setVersion(0); setSavedFingerprint(''); setError(null); setHydrated(false);
    if (!enabled) { setStatus('local'); return; }
    setStatus('loading');
    // Invalidate responses immediately, before waiting for a prior write.
    // Otherwise that write can restart autosave while a recovery is pending.
    if (flight.current) await flight.current;
    if (epoch !== active.current) return;
    try {
      const response = await readMetaCampaignDraft(draftRef);
      if (epoch !== active.current) return;
      revision.current = response.version;
      saved.current = fingerprint(response.draft);
      latest.current = response.draft;
      restore.current(response.draft);
      setVersion(response.version); setSavedFingerprint(saved.current);
      ready.current = true; setHydrated(true); setStatus('idle');
    } catch (exc) {
      if (epoch !== active.current) return;
      if (!requireExisting && exc instanceof MetaDraftError && exc.status === 404 && exc.code === 'META_DRAFT_NOT_FOUND') {
        ready.current = true; setHydrated(true); setStatus('idle');
      } else {
        failure.current = 'error'; setStatus('error');
        setError(exc instanceof MetaDraftError && exc.status === 404
          ? 'Este rascunho não está disponível. Ele pode ter sido excluído ou pertencer a outra sessão. Escolha outro rascunho ou inicie uma nova campanha.'
          : exc instanceof Error ? exc.message : 'Não foi possível recuperar o rascunho.');
      }
    }
  }, [draftRef, enabled, requireExisting]);

  useEffect(() => { void reload(); return () => { active.current++; ready.current = false; }; }, [reload]);

  const saveNow = useCallback(async (): Promise<boolean> => {
    if (!enabled) return true;
    if (!ready.current || failure.current === 'conflict') return false;
    if (flight.current) return flight.current;
    // Do not install an already-resolved flight: its synchronous finally would
    // otherwise run before assignment and prevent every subsequent real save.
    if (fingerprint(latest.current) === saved.current) return true;
    const epoch = active.current;
    failure.current = null; setError(null);
    const run = async () => {
      let attempted = '';
      try {
        while (epoch === active.current && fingerprint(latest.current) !== saved.current) {
          const value = draftWithoutAuthority(latest.current);
          const sent = fingerprint(value);
          attempted = sent;
          setStatus('saving');
          const response = await saveMetaCampaignDraft(draftRef, revision.current, value);
          if (epoch !== active.current) return false;
          if (response.version !== revision.current + 1 || fingerprint(response.draft) !== sent) {
            throw new MetaDraftError('O servidor não confirmou o conteúdo salvo. Recarregue o rascunho.', 'META_DRAFT_VERSION_CONFLICT', 409);
          }
          revision.current = response.version; saved.current = sent;
          setVersion(response.version); setSavedFingerprint(sent);
        }
        if (epoch === active.current) setStatus('idle');
        return epoch === active.current;
      } catch (exc) {
        if (epoch !== active.current) return false;
        const next = exc instanceof MetaDraftError && exc.status === 409 ? 'conflict' : 'error';
        failure.current = next; setStatus(next);
        failedContent.current = attempted;
        retryOnEdit.current = !(exc instanceof MetaDraftError)
          || exc.status >= 500 || exc.status === 408 || exc.status === 429;
        setError(exc instanceof Error ? exc.message : 'Não foi possível salvar o rascunho.');
        return false;
      } finally { flight.current = null; }
    };
    flight.current = run();
    return flight.current;
  }, [draftRef, enabled]);

  const currentFingerprint = fingerprint(draft);
  useEffect(() => {
    if (!enabled || !ready.current || status === 'conflict' || status === 'loading'
        || currentFingerprint === saved.current) return;
    // A new edit may recover a transient failure. The same failed payload must
    // not generate an endless timer retry; auth/conflicts still need recovery.
    if (status === 'error' && (!retryOnEdit.current || currentFingerprint === failedContent.current)) return;
    const timer = window.setTimeout(() => { void saveNow(); }, 700);
    return () => window.clearTimeout(timer);
  }, [currentFingerprint, enabled, saveNow, status]);

  useEffect(() => {
    if (!enabled || currentFingerprint === savedFingerprint) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [enabled, currentFingerprint, savedFingerprint]);

  return { loading: status === 'loading', saving: status === 'saving',
    blocked: enabled && (!hydrated || status === 'conflict'),
    saved: enabled && ready.current && currentFingerprint === savedFingerprint,
    version, error, conflict: status === 'conflict', saveNow, reload };
}
