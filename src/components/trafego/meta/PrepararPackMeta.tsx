import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Loader2, ShieldCheck, Upload } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { lerPack, type CreativePack, type DraftPackSelection } from '@/features/creative-studio/api';
import { CapaPack, caminhoPack } from '@/features/creative-studio/componentes/PackVisual';
import { criativosApi } from '@/lib/criativosApi';
import { pautadorApi, type RegistroMidiaMeta, type RevisaoMidiaMeta } from '@/lib/pautadorApi';

type Capabilities = Awaited<ReturnType<typeof pautadorApi.capacidadesMidiaMeta>>;
export function PrepararPackMeta({selection, accountRef, accountName, setName, demo, attached, onAttach, draftRef}: {
  draftRef?: string;
  selection: DraftPackSelection; accountRef: string; accountName: string; setName: string;
  demo: boolean; attached: boolean; onAttach: (pack: CreativePack, receipt: RegistroMidiaMeta) => void;
}) {
  const [pack, setPack] = useState<CreativePack>();
  const [cap, setCap] = useState<Capabilities>();
  const [review, setReview] = useState<RevisaoMidiaMeta>();
  const [checked, setChecked] = useState(false);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [receipt, setReceipt] = useState<RegistroMidiaMeta>();
  const [feedback, setFeedback] = useState('');
  const [loadedScope, setLoadedScope] = useState('');
  const scope = JSON.stringify([draftRef, accountRef, demo, selection.adset_key, selection.pack_id, selection.version, selection.manifest_sha256, selection.master_refs]);
  const readCapabilities = () => draftRef
    ? pautadorApi.capacidadesMidiaMeta(accountRef, draftRef, selection.master_refs)
    : pautadorApi.capacidadesMidiaMeta(accountRef);
  const scopeRef = useRef(scope); scopeRef.current = scope;
  const live = useRef(true);
  const lock = useRef<number | null>(null);
  const sequence = useRef(0);
  useEffect(() => {
    live.current = true;
    let cancelled = false;
    setPack(undefined); setCap(undefined); setReview(undefined); setReceipt(undefined);
    setChecked(false); setError(''); setFeedback(''); setBusy(''); lock.current = null;
    if (!accountRef || demo) return () => { cancelled = true; live.current = false; };
    void Promise.all([lerPack(selection.pack_id, selection.manifest_sha256), readCapabilities()])
      .then(([p, c]) => { if (!cancelled && scopeRef.current === scope) {setPack(p); setCap(c); setLoadedScope(scope);} })
      .catch(e => {if (!cancelled && scopeRef.current === scope) setError(e.message);});
    return () => { cancelled = true; live.current = false; };
  }, [scope]);

  async function run(label: string, action: (current: () => boolean) => Promise<void>) {
    if (lock.current !== null) return;
    const id = ++sequence.current; const startedScope = scope;
    const current = () => live.current && scopeRef.current === startedScope && lock.current === id;
    lock.current = id; setBusy(label); setError(''); setFeedback('');
    try { await action(current); } catch(e) {if (current()) setError(e instanceof Error ? e.message : 'Não foi possível concluir.');}
    finally {if (current()) {lock.current = null; setBusy('');}}
  }
  const valid = loadedScope === scope && Boolean(pack && selection.manifest_sha256
    && pack.manifest_sha256 === selection.manifest_sha256 && selection.master_refs.length
    && new Set(selection.master_refs).size === selection.master_refs.length
    && selection.master_refs.every(ref => pack.manifest.items.some(item => item.master_ref === ref)));
  const policyReady = cap?.inspecao_de_imagem?.disponivel;
  const reviewMatches = Boolean(review && review.resultados.length === selection.master_refs.length
    && new Set(review.resultados.map(r => r.master_ref)).size === selection.master_refs.length
    && selection.master_refs.every(ref => review.resultados.some(r => r.master_ref === ref)));
  return <section aria-label="Preparar imagens do pack" className="space-y-4 rounded-xl border border-border bg-card p-5">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><h3 className="text-lg font-semibold">Do pack para este conjunto</h3>
        <p className="mt-1 text-sm text-muted-foreground">{accountName || 'Escolha uma conta'} → <strong>{setName}</strong>. {selection.master_refs.length} imagem(ns), sem gerar novamente.</p></div>
      <Button variant="outline" asChild><Link to={caminhoPack(selection.pack_id)}>Abrir galeria e copy</Link></Button>
    </div>
    {demo ? <p role="status">Demonstração: não aprova imagens nem envia mídia à Meta.</p> : <>
      {pack && <div className="grid gap-3 sm:grid-cols-3">{selection.master_refs.map(ref => {
        const item = pack.manifest.items.find(i => i.master_ref === ref);
        const result = review?.resultados.find(r => r.master_ref === ref);
        return <div key={ref} className="overflow-hidden rounded-lg border border-border">
          <CapaPack item={item} nome={item?.nome || pack.nome} />
          <div className="space-y-1 p-3 text-sm"><p className="font-medium">{item?.nome || pack.nome}</p>
            <p className="text-muted-foreground">{result ? result.utilizavel ? 'Imagem revisada para envio' : result.codigo === 'META_ASSET_POLICY_UNAVAILABLE' ? 'Inspeção de imagem indisponível' : result.codigo === 'META_ASSET_POLICY_BLOCKED' ? 'Política exige revisão' : 'Aprovação final pendente' : 'Aguardando revisão final'}</p>
          </div></div>;
      })}</div>}
      {cap && !policyReady && <p role="status" className="rounded-lg border border-warning/40 bg-warning/10 p-3 text-sm">
        Falta configurar a conferência de {cap.inspecao_de_imagem.capacidades_ausentes.map(c => c === 'marca_visual' ? 'marcas e logotipos' : c === 'texto_na_imagem' ? 'texto na imagem' : c).join(' e ')}. Seu pack continua salvo. O envio à Meta fica disponível quando essa revisão estiver funcionando.
      </p>}
      {cap?.registro_de_imagem !== 'ENABLED' && cap && <p className="text-sm text-muted-foreground">{cap.motivo || 'Envio de imagens não habilitado para esta conta.'}</p>}
      {cap?.registro_de_imagem === 'ENABLED' && cap.escopo_do_envio === 'DRAFT_SELECTED_MEDIA_ONLY' && <p role="status" className="text-sm text-muted-foreground">Envio autorizado apenas para as imagens selecionadas deste rascunho. Isso não publica nem ativa anúncios.</p>}
      {attached ? <p role="status" className="flex items-center gap-2 text-sm"><ShieldCheck className="h-4 w-4" aria-hidden />Peças vinculadas a este conjunto. Revise a copy e as declarações de uso abaixo antes de conferir o plano.</p> : <>
        <label className="flex cursor-pointer items-start gap-3 text-sm"><input type="checkbox" checked={checked} disabled={!!busy || !valid}
          onChange={e => {setChecked(e.target.checked); setReview(undefined);}} className="mt-1 h-4 w-4 accent-primary" />
          <span>Revisei as imagens, marcas e direitos de uso e assumo a responsabilidade pelo envio à Meta. Esta aprovação é humana, sem análise por IA, e não publica anúncios.</span></label>
        <div className="flex flex-wrap gap-3">
          <Button variant="outline" disabled={!!busy || !checked || !valid} onClick={() => void run('Conferindo imagens e aprovações…', async current => {
            setReview(undefined);
            const existing = await pautadorApi.revisarMidiaMeta(accountRef, selection.master_refs);
            if (!current()) return;
            if (existing.resultados.length !== selection.master_refs.length || new Set(existing.resultados.map(r => r.master_ref)).size !== selection.master_refs.length
              || selection.master_refs.some(ref => !existing.resultados.some(r => r.master_ref === ref))) throw new Error('A revisão não devolveu exatamente as imagens selecionadas. Nenhuma aprovação foi registrada.');
            setReview(existing);
            const pending = existing.resultados.filter(r => !r.aprovacao_humana
              && r.codigo === 'META_ASSET_FINAL_APPROVAL_REQUIRED').map(r => r.master_ref);
            for (const [index, ref] of pending.entries()) {
              if (!current()) return;
              setBusy(`Registrando aprovação ${index + 1} de ${pending.length}…`);
              try {
                await criativosApi.decidir(ref, {decisao: 'aprovado', finalidade: 'meta_ads'});
              } catch (e) {
                if (!current()) return;
                setReview(undefined);
                throw new Error(`Não foi possível confirmar a aprovação da imagem ${selection.master_refs.indexOf(ref) + 1}. ${index} aprovação(ões) anterior(es) desta tentativa já foram registradas e continuam salvas. Confira novamente para retomar. ${e instanceof Error ? e.message : ''}`);
              }
            }
            if (!current()) return;
            setBusy('Concluindo a conferência…');
            const r = pending.length ? await pautadorApi.revisarMidiaMeta(accountRef, selection.master_refs) : existing;
            if (!current()) return;
            setReview(r);
            if (r.resultados.length !== selection.master_refs.length || new Set(r.resultados.map(row => row.master_ref)).size !== selection.master_refs.length
              || selection.master_refs.some(ref => !r.resultados.some(row => row.master_ref === ref))) throw new Error('A conferência final está incompleta. As aprovações registradas continuam salvas; confira novamente antes de enviar.');
            setFeedback(r.ok ? 'Conferência concluída. As imagens estão revisadas; confira abaixo a liberação de envio.' : 'Conferência concluída com pendências. Veja o motivo de cada imagem abaixo.');
            setCap(undefined);
            const updatedCap = await readCapabilities();
            if (!current()) return;
            setCap(updatedCap);
          })}>Registrar minha aprovação</Button>
          <Button disabled={!!busy || !reviewMatches || !review?.ok || !review.resultados.every(r => r.utilizavel) || !policyReady || cap?.registro_de_imagem !== 'ENABLED' || !valid}
            onClick={() => void run('Enviando imagens à conta…', async current => {
              setReceipt(undefined);
              const r = draftRef ? await pautadorApi.registrarMidiaMeta(accountRef, review!.resultados, draftRef)
                : await pautadorApi.registrarMidiaMeta(accountRef, review!.resultados);
              if (!current()) return;
              setReceipt(r);
              if (r.ok) onAttach(pack!, r);
              else setError('O registro não confirmou todas as imagens. Nenhum anúncio foi anexado. Confira os estados abaixo antes de qualquer nova tentativa.');
            })}><Upload className="h-4 w-4" aria-hidden />Enviar à conta e montar anúncios</Button>
        </div>
        <p className="text-xs text-muted-foreground">O segundo botão envia mídia à conta {accountName || 'selecionada'}. A criação da campanha exige outra confirmação, ao final. Aprovações registradas permanecem salvas ao trocar de conjunto. Fechar a tela não cancela um envio já iniciado.</p>
      </>}
      {review && <div className="space-y-3 border-t pt-4" aria-label="Resultado da conferência">
        <p role="status" className="font-medium">{feedback || 'Resultado da conferência das imagens'}</p>
        {!reviewMatches && <p role="alert" className="text-sm text-destructive">A revisão não corresponde à seleção atual. Confira novamente antes de enviar.</p>}
        <ul className="space-y-3 text-sm">{review.resultados.map((result, index) => <li key={result.master_ref}>
          <p className="font-medium">Imagem {index + 1}: {result.utilizavel ? 'aprovada e revisada' : 'envio pendente'}</p>
          <p>{result.aprovacao_humana ? 'Aprovação humana registrada.' : 'Aprovação humana ainda não registrada.'}</p>
          {!result.utilizavel && <p>{result.codigo === 'META_ASSET_POLICY_UNAVAILABLE' ? 'Um detector não concluiu a inspeção. Confira os detalhes e tente novamente quando o serviço estiver disponível.'
            : result.codigo === 'META_ASSET_POLICY_BLOCKED' ? 'A inspeção encontrou uma restrição. Ajuste a imagem ou comprove a autorização correspondente antes de enviar.' : 'Registre a aprovação final desta imagem para Meta Ads.'}</p>}
          {result.politica.achados?.length ? <p>Identidades encontradas: {result.politica.achados.map(a => a.termo).join(', ')}.</p> : null}
          {!result.utilizavel && <details className="mt-1"><summary className="cursor-pointer py-1 text-muted-foreground">Ver diagnóstico da imagem</summary>
            <p className="break-words font-mono text-xs">{result.codigo} · {result.politica.decisao}</p>
            <ul>{result.politica.motivos.filter(m => typeof m === 'string').map((m, i) => <li key={i} className="break-words text-xs">{String(m)}</li>)}</ul>
            {result.politica.detectores?.map(d => <p key={d.nome} className="text-xs">{d.nome}: {d.resultado}</p>)}
          </details>}
        </li>)}</ul>
        {cap && cap.registro_de_imagem !== 'ENABLED' && <p role="alert" className="rounded-lg border border-warning/40 bg-warning/10 p-3 text-sm"><strong>{draftRef ? 'Envio ainda não liberado para esta seleção do rascunho.' : 'Envio ainda não liberado neste servidor para esta conta.'}</strong> A conferência não abre essa autorização. Seu pack e suas aprovações continuam salvos; nenhuma imagem foi enviada à Meta.</p>}
      </div>}
      {receipt && !receipt.ok && <ul className="space-y-1 text-sm">{receipt.resultados.map(r => <li key={r.master_ref}>{r.estado} · {r.motivo || r.codigo}</li>)}</ul>}
    </>}
    {busy && <p role="status" className="flex items-center gap-2 text-sm"><Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden />{busy}</p>}
    {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
  </section>;
}
