import { useEffect, useRef, useState } from 'react';
import { Loader2, WandSparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { readMetaCampaignDraft, suggestMetaCopy, type CopySuggestions } from '@/lib/metaCampaignDraftApi';
import { textosFlexiveisDoConjunto, type Draft, type TextosFlexiveisDraft } from './rascunho';

function copyContextFingerprint(draft: Draft, draftRef: string, adsetKey: string, count: number) {
  return JSON.stringify([draftRef, adsetKey, draft.accountRef, draft.pageRef, draft.recipeId, draft.destinationUrl, draft.naming?.topic,
    textosFlexiveisDoConjunto(draft, adsetKey), count,
    draft.variations.filter(v => v.adsetKey === adsetKey).map(v => [v.assetRef, v.cta, v.packOrigin])]);
}

function dedupeCanonicalTexts(texts: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const text of texts) {
    const trimmed = text.trim();
    if (!trimmed) continue;
    const key = trimmed.replace(/\s+/g, ' ').toLowerCase();
    if (!seen.has(key)) {
      seen.add(key);
      out.push(text);
    }
  }
  return out;
}

export function VarinhaDeCopy({ draft, draftRef, adsetKey, save, onApply, demo }: {
  draft: Draft; draftRef: string; adsetKey: string; save: () => Promise<boolean>;
  onApply: (value: TextosFlexiveisDraft) => void; demo: boolean;
}) {
  const [open, setOpen] = useState(false), [busy, setBusy] = useState(false);
  const [error, setError] = useState(''), [result, setResult] = useState<CopySuggestions | null>(null);
  const [count, setCount] = useState(3), [notice, setNotice] = useState('');
  const flight = useRef<AbortController | null>(null);
  const pool = textosFlexiveisDoConjunto(draft, adsetKey);
  // These identity guards stay in the browser; they are never LLM context.
  const context = copyContextFingerprint(draft, draftRef, adsetKey, count);
  const latest = useRef(context); latest.current = context;
  const generatedFor = useRef('');
  useEffect(() => () => flight.current?.abort(), []);
  const stale = result !== null && generatedFor.current !== context;
  const merge = (key: keyof TextosFlexiveisDraft) => dedupeCanonicalTexts([...pool[key], ...result![key]]);
  const combined: TextosFlexiveisDraft | null = result ? {
    primary_text: merge('primary_text'), headline: merge('headline'), description: merge('description'),
  } : null;
  const fits = combined && Object.values(combined).every(values => values.length <= 5);
  async function generate() {
    if (flight.current || demo) return;
    const controller = new AbortController(); flight.current = controller;
    const initial = latest.current;
    setBusy(true); setError(''); setResult(null); setNotice('');
    try {
      if (!await save()) throw new Error('Salve o rascunho antes de pedir sugestões.');
      const saved = await readMetaCampaignDraft(draftRef);
      if (saved.draft.accountRef !== draft.accountRef || saved.draft.pageRef !== draft.pageRef) throw new Error('A conta ou Página salva mudou. Recarregue o rascunho.');
      if (initial !== latest.current) throw new Error('O contexto mudou. Confira seus textos e peça novamente.');
      if (copyContextFingerprint(saved.draft, draftRef, adsetKey, count) !== initial) throw new Error('O contexto salvo mudou em outra sessão. Recarregue o rascunho antes de gerar sugestões.');
      const response = await suggestMetaCopy(draftRef, saved.version, adsetKey, count, '', controller.signal);
      if (controller.signal.aborted) return;
      if (initial !== latest.current) throw new Error('O contexto mudou durante a geração. Seus textos foram preservados.');
      generatedFor.current = initial; setResult(response);
    } catch (e) { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : 'Não foi possível gerar sugestões.'); }
    finally { flight.current = null; if (!controller.signal.aborted) setBusy(false); }
  }
  function apply(append: boolean) {
    if (!result || stale) return;
    onApply(append ? combined! : { primary_text: result.primary_text, headline: result.headline, description: result.description });
    setResult(null); setNotice('Sugestões aplicadas. Revise os textos antes da aprovação final.');
  }
  return <section className="space-y-3 border-b border-border pb-5">
    <div className="flex flex-wrap items-center gap-3">
      <Button type="button" variant="outline" disabled={busy || demo} aria-expanded={open} onClick={() => { setOpen(true); void generate(); }}>
        {busy ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : <WandSparkles className="h-4 w-4" aria-hidden />}
        {busy ? 'Criando com seu contexto…' : 'Sugerir copies com IA'}
      </Button>
      <details className="text-sm text-muted-foreground"><summary className="flex min-h-11 cursor-pointer items-center">{count} opções por tipo · ajustar</summary>
        <label>Quantidade de sugestões<select aria-label="Quantidade de sugestões" className="ml-2 min-h-11 rounded-md border border-input bg-card px-3 text-foreground" value={count} disabled={busy} onChange={e => setCount(Number(e.target.value))}>{[1,2,3,4,5].map(n => <option key={n} value={n}>{n}</option>)}</select></label>
      </details>
    </div>
    <p className="max-w-prose text-sm text-muted-foreground">Partimos dos textos e do assunto salvos, sem pedir outro briefing. LP e estratégia só entram quando vinculadas e autorizadas para o modelo. A geração usa a API de texto; você escolhe o que aplicar.</p>
    {demo && <p className="text-sm text-muted-foreground">Abra um rascunho real para usar o agente de copy.</p>}
    {open && <div className="space-y-3">
      {busy && <div role="status" className="space-y-3 rounded-lg bg-muted/40 p-4"><p className="text-sm">Criando ângulos de benefício, curiosidade e objeção com o contexto disponível.</p>
        <div aria-hidden className="space-y-2 motion-safe:animate-pulse"><div className="h-3 w-4/5 rounded bg-muted" /><div className="h-3 w-3/5 rounded bg-muted" /><div className="h-3 w-2/3 rounded bg-muted" /></div>
      </div>}
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      {result && <div className="space-y-4 rounded-xl border border-border bg-card p-4 text-card-foreground">
        <h4 className="font-semibold">Sugestões para revisar</h4>
        {result.context_summary && <details className="text-sm">
          <summary className="min-h-11 cursor-pointer text-primary">{result.context_summary.mode === 'CURRENT_TEXTS_ONLY' ? 'Contexto disponível: textos deste conjunto' : `Contexto conectado · ${result.context_summary.facts_count} fatos disponíveis`}</summary>
          <ul className="space-y-1 text-muted-foreground">{result.context_summary.sources.map((source, i) => <li key={`${source.kind}:${i}`}>{source.name} · {source.item_count} item(ns)</li>)}</ul>
          <p className="mt-2 text-muted-foreground">Fontes salvas, não uma nova leitura da página nem inspeção de imagem.</p>
        </details>}
        {result.context_summary?.warnings.map((warning, i) => <p key={i} className="text-sm text-muted-foreground">{warning}</p>)}
        {(['primary_text','headline','description'] as const).map(k => result[k].length > 0 && <div key={k}><p className="text-sm font-semibold">{k === 'primary_text' ? 'Textos principais' : k === 'headline' ? 'Títulos' : 'Descrições'}</p><ol className="mt-2 list-decimal space-y-2 pl-5 text-sm">{result[k].map((t,i) => <li key={i} className="break-words">{t}</li>)}</ol></div>)}
        {stale && <p role="alert" className="text-sm text-warning">O contexto mudou. Gere novas sugestões antes de aplicar.</p>}
        {!fits && <p className="text-sm text-muted-foreground">Acrescentar ultrapassaria cinco opções. Você pode substituir o banco atual.</p>}
        <div className="flex flex-wrap gap-2"><Button type="button" disabled={stale || !fits} onClick={() => apply(true)}>Acrescentar ao banco</Button><Button type="button" variant="outline" disabled={stale} onClick={() => apply(false)}>Substituir textos atuais</Button><Button type="button" variant="ghost" onClick={() => setResult(null)}>Descartar</Button></div>
      </div>}
    </div>}
    {notice && <p role="status" className="text-sm text-success">{notice}</p>}
  </section>;
}
