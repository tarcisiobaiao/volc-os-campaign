import { useEffect, useRef, useState } from 'react';
import { CircleCheck, Hash, Loader2, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { analisarPaginaCriativa } from '@/features/creative-studio/api';
import { readMetaCampaignDraft, reserveMetaNaming } from '@/lib/metaCampaignDraftApi';
import type { Draft } from './rascunho';
import { aplicarNomenclatura, gerarNomenclatura, novaNomenclatura, siteDoDestino, tipoDoDestino } from './nomenclatura';

export function NomenclaturaAutomatica({ draft, draftRef, save, onChange, sizes, demo, conversionNames = {} }: {
  draft: Draft; draftRef: string; save: () => Promise<boolean>; onChange: (draft: Draft) => void;
  sizes: Record<string, string>; demo: boolean;
  conversionNames?: Record<string, string>;
}) {
  const [busy, setBusy] = useState(false), [analyzing, setAnalyzing] = useState(false), [error, setError] = useState('');
  const [analysisRetry, setAnalysisRetry] = useState(0);
  const latest = useRef({ draft, draftRef }); latest.current = { draft, draftRef };
  const flight = useRef(false);
  const analysisSequence = useRef(0);
  const automaticReservation = useRef('');
  const naming = draft.naming ?? novaNomenclatura(draft);
  const reserved = naming.campaignNumber && naming.accountRef === draft.accountRef;
  const preview = gerarNomenclatura(draft, naming, sizes, conversionNames).names;
  function edit(patch: Partial<typeof naming>) { onChange({ ...draft, naming: { ...naming, ...patch } }); }
  async function activate() {
    if (flight.current || demo) return;
    flight.current = true; setBusy(true); setError('');
    const account = draft.accountRef, ref = draftRef;
    try {
      if (!await save()) throw new Error('Salve o rascunho para reservar sua sequência.');
      const saved = await readMetaCampaignDraft(ref);
      if (saved.draft.accountRef !== account) throw new Error('A conta mudou. Confira a seleção antes de continuar.');
      const reservation = await reserveMetaNaming(ref, saved.version);
      if (latest.current.draftRef !== ref || latest.current.draft.accountRef !== account || reservation.account_ref !== account) {
        throw new Error('A conta mudou durante a consulta. A reserva foi preservada na conta de origem.');
      }
      const current = latest.current.draft;
      onChange(aplicarNomenclatura(current, { ...(current.naming ?? naming), enabled: true,
        campaignNumber: reservation.campaign_number, accountRef: account }, sizes, false, conversionNames));
    } catch (e) { setError(e instanceof Error ? e.message : 'Não foi possível reservar a numeração.'); }
    finally { flight.current = false; setBusy(false); }
  }

  /** A conta já foi escolhida nas primeiras etapas. Quando o destino fica
   * válido, lemos seu contexto uma vez e guardamos a URL de origem no próprio
   * rascunho. Assim reload, voltar/avançar e autosave não repetem análise paga. */
  useEffect(() => {
    if (demo || !draft.accountRef || !/^https:\/\/[^\s]+$/i.test(draft.destinationUrl)
        || naming.topicSourceUrl === draft.destinationUrl) return;
    const ticket = ++analysisSequence.current;
    const account = draft.accountRef;
    const destination = draft.destinationUrl;
    const timer = window.setTimeout(() => {
      setAnalyzing(true); setError('');
      void analisarPaginaCriativa(destination).then(context => {
        if (ticket !== analysisSequence.current || latest.current.draft.accountRef !== account
            || latest.current.draft.destinationUrl !== destination) return;
        const current = latest.current.draft;
        const currentNaming = current.naming ?? novaNomenclatura(current);
        const topic = (context.assunto_principal || context.titulo || context.assunto)
          .replace(/\s+/g, ' ').trim().slice(0, 200);
        if (!topic) throw new Error('A página não informou um assunto principal reconhecível.');
        const siteAnteriorAutomatico = currentNaming.topicSourceUrl
          ? siteDoDestino(currentNaming.topicSourceUrl) : '';
        const tipoAnteriorAutomatico = currentNaming.topicSourceUrl
          ? tipoDoDestino(currentNaming.topicSourceUrl) : '';
        onChange({ ...current, naming: { ...currentNaming, enabled: true, topic,
          topicSourceUrl: destination,
          site: !currentNaming.site || currentNaming.site === siteAnteriorAutomatico
            ? siteDoDestino(destination) : currentNaming.site,
          landingType: !currentNaming.landingType || currentNaming.landingType === tipoAnteriorAutomatico
            ? tipoDoDestino(destination) : currentNaming.landingType,
        } });
      }).catch(exc => {
        if (ticket === analysisSequence.current) setError(
          exc instanceof Error ? exc.message : 'Não foi possível identificar o assunto da página.');
      }).finally(() => { if (ticket === analysisSequence.current) setAnalyzing(false); });
    }, 700);
    return () => { window.clearTimeout(timer); analysisSequence.current += 1; };
  }, [demo, draft.accountRef, draft.destinationUrl, naming.topicSourceUrl, analysisRetry]);

  /** Depois que o assunto foi persistido no estado, reserva a sequência da
   * conta automaticamente. `activate` salva primeiro e o RPC é idempotente por
   * rascunho; o marcador evita uma segunda tentativa causada por rerenders. */
  useEffect(() => {
    if (demo || reserved || analyzing || !draft.accountRef || !naming.topic.trim()
        || !naming.site.trim() || naming.topicSourceUrl !== draft.destinationUrl) return;
    const key = `${draftRef}:${draft.accountRef}:${draft.destinationUrl}`;
    if (automaticReservation.current === key) return;
    automaticReservation.current = key;
    const timer = window.setTimeout(() => { void activate(); }, 150);
    return () => window.clearTimeout(timer);
  }, [demo, reserved, analyzing, draftRef, draft.accountRef, draft.destinationUrl,
    naming.topic, naming.site, naming.topicSourceUrl]);

  /** Uma reserva existente não precisa (nem deve) consultar a Meta novamente.
   * Ainda assim, URL, assunto, formato, conjunto e conversão podem mudar. A
   * nomenclatura acompanha essas alterações usando as chaves estáveis já
   * reservadas; valores editados manualmente continuam protegidos por
   * `generated`. */
  useEffect(() => {
    if (demo || !reserved || !naming.enabled) return;
    const next = aplicarNomenclatura(draft, naming, sizes, false, conversionNames);
    const before = JSON.stringify({ campaignName: draft.campaignName,
      sets: draft.conjuntos.map(item => [item.key, item.nome]),
      ads: draft.variations.map(item => [item.key, item.adName, item.creativeName]),
      naming: draft.naming });
    const after = JSON.stringify({ campaignName: next.campaignName,
      sets: next.conjuntos.map(item => [item.key, item.nome]),
      ads: next.variations.map(item => [item.key, item.adName, item.creativeName]),
      naming: next.naming });
    if (before !== after) onChange(next);
  }, [demo, reserved, draft, naming, sizes, conversionNames]);

  return <details open={Boolean(analyzing || busy || error || !reserved)} className="my-5 rounded-xl border border-border bg-card p-4 sm:p-5">
    <summary className="min-h-11 cursor-pointer font-semibold marker:text-primary"><Hash className="mr-2 inline h-4 w-4 text-primary" aria-hidden />Nomes organizados automaticamente
      {reserved ? <span className="ml-2 inline-flex items-center gap-1 text-sm font-normal text-success"><CircleCheck className="h-4 w-4" aria-hidden />CP{String(naming.campaignNumber).padStart(4, '0')} · ativo</span>
        : <span className="ml-2 text-sm font-normal text-muted-foreground">{analyzing ? 'identificando assunto…' : busy ? 'conferindo histórico…' : 'automático'}</span>}
    </summary>
    <div className="mt-3 space-y-4">
      <p className="max-w-prose text-sm text-muted-foreground">Identificamos o assunto da página e reservamos o próximo número no histórico desta conta. A reserva é do rascunho e não renomeia campanhas existentes.</p>
      <fieldset disabled={busy} className="grid gap-4 border-0 p-0 sm:grid-cols-2">
        <label className="space-y-1 text-sm font-medium">Assunto principal<Input value={naming.topic} maxLength={200} onChange={e => edit({ topic: e.target.value })} placeholder="CNH do Brasil - Renovação" /></label>
        <label className="space-y-1 text-sm font-medium">Identificação do site<Input value={naming.site} maxLength={80} onChange={e => edit({ site: e.target.value })} placeholder="TECHNEWS_BR" /></label>
        <label className="space-y-1 text-sm font-medium">Tipo da página<Input value={naming.landingType} maxLength={40} onChange={e => edit({ landingType: e.target.value })} placeholder={tipoDoDestino(draft.destinationUrl) || 'Sem tag adicional'} /><span className="block text-xs font-normal text-muted-foreground">LP_R identifica a rota /r/ do WordPress, não a conversão.</span></label>
        <label className="space-y-1 text-sm font-medium">Rótulo da conversão (opcional)<Input value={naming.conversionLabel} maxLength={80} onChange={e => edit({ conversionLabel: e.target.value })} placeholder="Ex.: REWARDED, se for o evento escolhido" /><span className="block text-xs font-normal text-muted-foreground">Só nomeia. Não altera o evento de otimização.</span></label>
        <label className="flex min-h-11 items-center gap-2 text-sm"><input type="checkbox" checked={naming.quiz} onChange={e => edit({ quiz: e.target.checked })} />A página possui quiz</label>
      </fieldset>
      <div className="flex flex-wrap items-center gap-3">
        {error && <Button type="button" variant="secondary" disabled={busy || analyzing || demo || !draft.accountRef
          || (naming.topicSourceUrl === draft.destinationUrl && (!naming.topic.trim() || !naming.site.trim()))} onClick={() => {
          if (naming.topicSourceUrl !== draft.destinationUrl) {
            setAnalysisRetry(value => value + 1);
          } else void activate();
        }}><RefreshCw className="h-4 w-4" aria-hidden />Tentar novamente</Button>}
        {(busy || analyzing) && <span role="status" aria-live="polite" className="inline-flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden />{analyzing ? 'Lendo o contexto da página…' : 'Conferindo a próxima sequência da conta…'}</span>}
        {reserved && <label className="flex min-h-11 items-center gap-2 text-sm"><input type="checkbox" checked={naming.enabled} onChange={e => edit({ enabled: e.target.checked })} />Acompanhar alterações da campanha</label>}
      </div>
      {demo && <p className="text-sm text-muted-foreground">Demonstração: a numeração real da conta não é reservada.</p>}
      {!draft.accountRef && <p className="text-sm text-muted-foreground">Selecione a conta para reservar sua numeração.</p>}
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      {reserved && <div className="space-y-2 border-t border-border pt-4"><p className="text-sm font-semibold">Padrão proposto</p><ul className="space-y-2 text-xs">{Object.entries(preview).slice(0, 10).map(([key, value]) => <li key={key} className="break-words font-mono">{value}</li>)}</ul>
        <p className="text-xs text-muted-foreground">Nomes editados manualmente são preservados. Os números dos conjuntos e anúncios não mudam ao reordenar. No flexível, as imagens são agrupadas e o primeiro nome do grupo identifica o anúncio final.</p>
      </div>}
    </div>
  </details>;
}
