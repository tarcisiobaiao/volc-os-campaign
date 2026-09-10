import { useEffect, useMemo, useRef, useState } from 'react';
import { Download, ImageIcon, Loader2, Package, RefreshCw, Trash2, ZoomIn } from 'lucide-react';
import { assistenteIntegrado } from '@/components/trafego/meta/ponteAssistente';
import { Button, buttonVariants } from '@/components/ui/button';
import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { criativosApi } from '@/lib/criativosApi';
import { jobTerminou, type CreativeJob, type Rendition } from '@/types/criativos';
import type { BriefingResumido, GeracaoRegistrada } from '../tipos';
import { zipDeImagens } from '../zip';
import { PacksDeCriativos } from './PacksDeCriativos';

function salvar(blob: Blob, nome: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a'); a.href = url; a.download = nome;
  document.body.appendChild(a); a.click(); a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export interface PedidoNaGaleria {
  runRef: string;
  geracaoRef: string | null;
  briefings: BriefingResumido[];
  modelo?: string | null;
  qualidade?: string | null;
}
type ItemDaGaleria = { chave: string; slot: string; rotulo: string; peca?: Rendition };

/** Placeholders are presentation, never fabricated assets, master IDs or receipts. */
function MiniaturaEmPreparo({ rotulo, ativo = false }: { rotulo: string; ativo?: boolean }) {
  return <div className="studio-generation-placeholder flex h-full min-h-44 flex-col items-center justify-center gap-4 px-5 text-center">
    <span className="relative flex h-14 w-14 items-center justify-center rounded-2xl border border-primary/20 bg-background/80 text-primary">
      {ativo ? <Loader2 className="h-6 w-6 motion-safe:animate-spin" aria-hidden /> : <ImageIcon className="h-6 w-6" aria-hidden />}
    </span>
    <div className="relative"><p className="text-sm font-medium text-foreground">{ativo ? 'Gerando imagem' : 'Preparando imagem'}</p><p className="mt-1 text-xs text-muted-foreground">{rotulo}</p></div>
  </div>;
}

/** Read canonical jobs independently of the long-running generation request. */
export function GaleriaDeGeracoes({ geracoes, onComecar, pedido, consultando = false, onConcluida }: {
  geracoes: GeracaoRegistrada[]; onComecar: () => void; pedido?: PedidoNaGaleria | null;
  consultando?: boolean; onConcluida?: () => void;
}) {
  const [jobs, setJobs] = useState<CreativeJob[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [lendo, setLendo] = useState(false);
  const [revisao, setRevisao] = useState(0);
  const concluidas = useRef(new Set<string>());
  const painel = useRef<HTMLElement>(null);
  const aoConcluir = useRef(onConcluida);
  aoConcluir.current = onConcluida;
  const pedidoId = pedido ? `${pedido.runRef}:${pedido.geracaoRef}` : null;
  useEffect(() => { if (pedidoId) painel.current?.focus(); }, [pedidoId]);
  const ids = useMemo(() => [...new Set(geracoes.map(g => g.job_id))].sort().join(','), [geracoes]);
  useEffect(() => {
    let encerrado = false; let timer: ReturnType<typeof setTimeout> | undefined;
    // A newly registered concept must not erase completed thumbnails or selections.
    setJobs(atuais => atuais.filter(j => ids.split(',').includes(j.id)));
    setErro(null); setLendo(false);
    if (!ids) return;
    async function ler() {
      setLendo(true);
      try {
        // `allSettled`, e não `all`: com `all`, UM id que falha rejeita tudo e
        // descarta as leituras que deram certo — a galeria apagava os formatos
        // já prontos por causa de um 404 transitório em outro job. Falha em um
        // formato não pode apagar os formatos concluídos.
        const respostas = await Promise.allSettled(
          ids.split(',').map(id => criativosApi.job(id)),
        );
        if (encerrado) return;
        const lidos = respostas
          .filter((r): r is PromiseFulfilledResult<CreativeJob> => r.status === 'fulfilled')
          .map(r => r.value);
        const falharam = respostas.length - lidos.length;

        setJobs(atuais => ids.split(',').flatMap(id => {
          const job = lidos.find(j => j.id === id) ?? atuais.find(j => j.id === id);
          return job ? [job] : [];
        }));
        // Leitura parcial é um estado próprio: mostra o que chegou E diz o que
        // faltou. Antes isso virava "acervo vazio", que é a leitura errada mais
        // cara desta tela.
        setErro(
          falharam === 0
            ? null
            : lidos.length === 0
              ? 'Não foi possível atualizar os criativos. Tente novamente; nenhum trabalho será reenviado.'
              : `${falharam} de ${respostas.length} trabalho(s) não puderam ser lidos agora. O que já ficou pronto continua abaixo.`,
        );

        // Continuar tentando enquanto houver trabalho não terminal OU leitura
        // falha. Antes o `catch` matava o timer e a galeria parava para sempre
        // no primeiro erro — o operador via "não foi possível" e nada mais
        // acontecia, mesmo com o motor concluindo do outro lado.
        if (falharam > 0 || lidos.some(j => !jobTerminou(j.estado))) {
          timer = setTimeout(ler, 2000);
        }
      } catch {
        if (!encerrado) {
          setErro('Não foi possível atualizar os criativos. Tente novamente; nenhum trabalho será reenviado.');
          timer = setTimeout(ler, 8000);
        }
      } finally { if (!encerrado) setLendo(false); }
    }
    void ler();
    return () => { encerrado = true; clearTimeout(timer); };
  }, [ids, revisao]);

  const pecas = jobs.flatMap(j => j.renditions);
  const itensDoPedido: ItemDaGaleria[] = pedido?.briefings.map((b, indice) => {
    const ponte = geracoes.find(g => g.run_ref === pedido.runRef &&
      (g.geracao_ref === 'original' ? null : g.geracao_ref ?? null) === pedido.geracaoRef && g.creative_ref === b.creative_ref);
    const peca = jobs.find(j => j.id === ponte?.job_id)?.renditions.find(p => p.slot === b.formato_slot);
    return { chave: `${pedido.runRef}:${pedido.geracaoRef}:${b.creative_ref}:${b.formato_slot}`, slot: b.formato_slot, rotulo: `Peça ${indice + 1} · ${b.formato_slot}`, peca };
  }) ?? [];
  const reservas = itensDoPedido.filter(i => !i.peca);
  const itens: ItemDaGaleria[] = [...itensDoPedido, ...pecas.filter(p => !itensDoPedido.some(i => i.peca?.id === p.id)).map(p => ({ chave: p.id, slot: p.slot, rotulo: p.rotulo, peca: p }))];
  const prontas = pecas.filter(p => p.estado === 'pronta').length;
  const falhas = pecas.filter(p => p.estado === 'falhou').length;
  const canceladas = pecas.filter(p => p.estado === 'cancelada').length;
  const ativas = pecas.filter(p => p.estado === 'gerando').length;
  const pendentes = pecas.filter(p => p.estado === 'pendente').length + reservas.length;
  const terminou = Boolean(ids) && !erro && jobs.length === ids.split(',').length && jobs.every(j => jobTerminou(j.estado)) && !reservas.length;
  useEffect(() => {
    if (!terminou || concluidas.current.has(ids)) return;
    concluidas.current.add(ids);
    aoConcluir.current?.();
  }, [terminou, ids]);

  return <div className="space-y-4">
    {(pedido || pecas.length > 0) && <section ref={painel} tabIndex={-1} aria-label="Progresso da geração" className="studio-surface border-primary/20 bg-card focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary">
      <div className="flex items-start gap-3"><span className="mt-1 text-primary">{!terminou ? <Loader2 className="h-5 w-5 motion-safe:animate-spin" aria-hidden /> : <ImageIcon className="h-5 w-5" aria-hidden />}</span><div>
        <h2 className="font-display text-lg font-semibold">{terminou ? (falhas || canceladas ? 'Geração encerrada com pendências' : 'Suas imagens estão prontas') : 'Suas ideias estão ganhando forma'}</h2>
        <p role="status" aria-live="polite" aria-atomic="true" className="mt-1 text-sm text-muted-foreground">{prontas} de {pecas.length + reservas.length} prontas{ativas > 0 ? ` · ${ativas} em produção` : ''}{pendentes > 0 ? ` · ${pendentes} aguardando` : ''}{falhas > 0 ? ` · ${falhas} com falha` : ''}{canceladas > 0 ? ` · ${canceladas} canceladas` : ''}</p>
        <p className="mt-2 text-xs text-muted-foreground">{terminou ? 'Galeria atualizada automaticamente. Confira cada peça antes de usar.' : 'Cada miniatura aparece assim que o arquivo fica pronto. Você pode acompanhar sem atualizar a página.'}</p>
        {pedido?.modelo && <p className="mt-2 text-xs text-muted-foreground">{pedido.modelo} · {pedido.qualidade}</p>}
      </div></div>
    </section>}
    {erro && <div role="alert" className="studio-surface text-sm"><p className="text-destructive">{erro}</p><Button className="mt-3" variant="outline" onClick={() => setRevisao(r => r + 1)}><RefreshCw className="h-4 w-4" aria-hidden />Atualizar criativos</Button></div>}
    {lendo && jobs.length === 0 && <p role="status" className="flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" aria-hidden />Buscando seus criativos…</p>}
    {(!erro || jobs.length > 0 || reservas.length > 0) && <GaleriaDeAssets pecas={pecas} itens={itens} onComecar={onComecar} carregando={consultando || Boolean(pedido) || lendo || Boolean(ids && !jobs.length && !erro)} onArquivada={() => setRevisao(r => r + 1)} />}
  </div>;
}

export function GaleriaDeAssets({ pecas, itens, onComecar, carregando = false, onArquivada }: { pecas: Rendition[]; itens?: ItemDaGaleria[]; onComecar: () => void; carregando?: boolean; onArquivada?: () => void }) {
  const [ampliada, setAmpliada] = useState<Rendition | null>(null);
  const [selecionadas, setSelecionadas] = useState<string[]>([]);
  const [baixando, setBaixando] = useState(false);
  const [confirmandoExclusao, setConfirmandoExclusao] = useState(false);
  const [excluindo, setExcluindo] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const prontas = pecas.filter(p => p.previewUrl && p.estado === 'pronta');
  const selecionadasProntas = prontas.filter(p => selecionadas.includes(p.id));
  // Um master pode possuir mais de uma rendition. Arquivar duas proporções do
  // mesmo master em paralelo faria a primeira vencer e a segunda responder
  // 404, produzindo um falso "parcial" na tela. A unidade destrutiva é o
  // master, então ela precisa ser deduplicada antes de qualquer request.
  const mastersExcluiveis = [...new Set(
    selecionadasProntas.flatMap(p => p.masterId ? [p.masterId] : []),
  )];
  useEffect(() => {
    const idsVisiveis = new Set(pecas.map(p => p.id));
    setSelecionadas(atuais => atuais.filter(id => idsVisiveis.has(id)));
  }, [pecas]);
  async function bytes(p: Rendition) {
    if (!p.previewUrl) throw Error('Prévia indisponível.');
    // Signed URL from the authenticated backend. Never attach session credentials to storage.
    const r = await fetch(p.previewUrl, { credentials: 'omit', redirect: 'error' });
    if (!r.ok) throw Error('O link expirou ou o arquivo não está disponível. Atualize a página.');
    const blob = await r.blob();
    // O tipo REAL dos bytes ainda é conferido contra a lista fechada. O que
    // deixou de ser exigido é a igualdade com `p.mime` quando `p.mime` é null:
    // o contrato documenta null como "ninguém mediu", e `blob.type !== null`
    // é sempre verdadeiro — o guard travava o download de toda rendition cujo
    // MIME não tinha sido registrado, que é justamente o caso de um acervo
    // recém-gerado. Quando o MIME FOI medido, divergir continua sendo recusa.
    const tipoAceito = ['image/png', 'image/jpeg', 'image/webp'].includes(blob.type);
    const bateComOMedido = p.mime == null || blob.type === p.mime;
    if (!tipoAceito || !bateComOMedido || blob.size > 25 * 1024 * 1024) {
      throw Error('O arquivo não pôde ser baixado como imagem.');
    }
    return blob;
  }
  const nome = (p: Rendition) => `criativo-${p.id.replace(/[^a-zA-Z0-9_-]/g, '')}-${p.slot.replace(/[^a-zA-Z0-9_-]/g, '')}.${p.mime === 'image/jpeg' ? 'jpg' : p.mime === 'image/webp' ? 'webp' : 'png'}`;
  async function baixar(uma?: Rendition) {
    setBaixando(true); setErro(null);
    try {
      if (uma) salvar(await bytes(uma), nome(uma));
      else {
        const arquivos: { name: string; data: Uint8Array }[] = []; let total = 0;
        for (const p of prontas.filter(p => selecionadas.includes(p.id))) {
          const blob = await bytes(p); total += blob.size;
          if (total > 100 * 1024 * 1024) throw Error('Selecione menos imagens para um ZIP de até 100 MB.');
          arquivos.push({ name: nome(p), data: new Uint8Array(await blob.arrayBuffer()) });
        }
        salvar(zipDeImagens(arquivos), 'criativos-meta.zip');
      }
    } catch (e) { setErro(e instanceof Error ? e.message : 'Não foi possível baixar os arquivos.'); }
    finally { setBaixando(false); }
  }

  async function excluirSelecionadas() {
    setExcluindo(true); setErro(null);
    const resultados = await Promise.allSettled(
      mastersExcluiveis.map(masterId => criativosApi.arquivarAsset(masterId)),
    );
    const mastersRemovidos = new Set(
      mastersExcluiveis.filter((_, indice) => resultados[indice].status === 'fulfilled'),
    );
    const falhas = resultados.filter(resultado => resultado.status === 'rejected');
    setSelecionadas(atuais => atuais.filter(id => {
      const peca = pecas.find(item => item.id === id);
      return !peca?.masterId || !mastersRemovidos.has(peca.masterId);
    }));
    setConfirmandoExclusao(false); setExcluindo(false);
    if (falhas.length) {
      const primeira = (falhas[0] as PromiseRejectedResult).reason;
      setErro(
        mastersRemovidos.size
          ? `${mastersRemovidos.size} peça(s) saíram da biblioteca; ${falhas.length} não puderam ser excluídas. ${primeira instanceof Error ? primeira.message : ''}`.trim()
          : primeira instanceof Error ? primeira.message : 'Não foi possível excluir as peças. Elas continuam na biblioteca.',
      );
    }
    if (mastersRemovidos.size) onArquivada?.();
  }

  if (!pecas.length && !carregando) return <section className="studio-surface py-12 text-center">
    <span className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/5 text-primary"><ImageIcon className="h-6 w-6" aria-hidden /></span>
    <h2 className="mt-5 font-display text-xl font-semibold">Seu próximo criativo começa aqui</h2>
    <p className="mx-auto mt-2 max-w-sm text-sm leading-relaxed text-muted-foreground">As imagens geradas aparecem nesta galeria. Você poderá ampliar, selecionar e baixar as peças individualmente ou em ZIP.</p>
    <Button className="mt-6" variant="outline" onClick={onComecar}>Preparar um briefing</Button>
  </section>;

  return <section aria-label="Galeria de criativos" className="space-y-5">
    <div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="font-display text-xl font-semibold">Seus criativos</h2><p className="mt-1 text-xs text-muted-foreground">{prontas.length} de {itens?.length ?? pecas.length} arquivos disponíveis · revisão de uso separada</p></div><div className="flex flex-wrap gap-2"><Button variant="outline" disabled={baixando || !selecionadasProntas.length} onClick={() => void baixar()}><Package className="h-4 w-4" aria-hidden />{baixando ? 'Preparando…' : 'Baixar selecionados (.zip)'}</Button><Button variant="destructive" disabled={excluindo || !mastersExcluiveis.length} onClick={() => setConfirmandoExclusao(true)}><Trash2 className="h-4 w-4" aria-hidden />Excluir selecionados</Button></div></div>
    {erro && <p role="alert" className="text-sm text-destructive">{erro}</p>}
    <div className="grid grid-cols-1 gap-4 min-[440px]:grid-cols-2 sm:grid-cols-3">{(itens ?? pecas.map(p => ({ chave: p.id, slot: p.slot, rotulo: p.rotulo, peca: p }))).map(item => { const p = item.peca; return p ? <article key={item.chave} className="overflow-hidden rounded-xl border border-border bg-card">
      <div className="flex min-h-44 items-center justify-center bg-muted/30 p-3" style={{ aspectRatio: `${p.largura ?? p.larguraPedida} / ${p.altura ?? p.alturaPedida}` }}>
        {p.previewUrl ? <img src={p.previewUrl} alt={p.rotulo} className="studio-generation-reveal max-h-full w-full object-contain" loading="lazy" /> : p.estado === 'gerando' || p.estado === 'pendente' ? <MiniaturaEmPreparo rotulo={p.rotulo} ativo={p.estado === 'gerando'} /> : <div className="text-center text-xs text-muted-foreground"><ImageIcon className="mx-auto mb-2 h-6 w-6" aria-hidden />{p.estado === 'cancelada' ? 'Geração cancelada' : 'Falha nesta peça'}{p.erro && <p className="mt-2 max-w-56">{p.erro.mensagem}</p>}</div>}
      </div>
      <div className="space-y-3 p-3"><label className="flex items-center gap-2 text-xs font-medium"><input type="checkbox" aria-label={`Selecionar ${p.rotulo}`} disabled={!p.previewUrl || p.estado !== 'pronta'} checked={selecionadas.includes(p.id)} onChange={() => setSelecionadas(a => a.includes(p.id) ? a.filter(id => id !== p.id) : [...a, p.id])} className="h-4 w-4 accent-primary" />{p.rotulo}</label><p className="text-[11px] tabular-nums text-muted-foreground">{p.largura ?? '—'} × {p.altura ?? '—'} px</p><div className="flex gap-2"><Button variant="outline" size="sm" disabled={!p.previewUrl} onClick={() => setAmpliada(p)} aria-label={`Ampliar ${p.rotulo}`}><ZoomIn className="h-4 w-4" aria-hidden /><span className="sr-only">Ampliar</span></Button><Button variant="outline" size="sm" disabled={!p.previewUrl || baixando} onClick={() => void baixar(p)} aria-label={`Baixar ${p.rotulo}`}><Download className="h-4 w-4" aria-hidden /><span>Baixar</span></Button></div></div>
    </article> : <article key={item.chave} className="overflow-hidden rounded-xl border border-border bg-card"><div style={{ aspectRatio: item.slot.replace('x', ' / ') }} className="min-h-44"><MiniaturaEmPreparo rotulo={item.rotulo} /></div><div className="min-h-[118px] space-y-3 p-3"><p className="text-xs font-medium">{item.rotulo}</p><p className="text-xs text-muted-foreground">Aguardando registro do arquivo</p></div></article>; })}</div>
    <PacksDeCriativos masterRefs={[...new Set(prontas.filter(p => selecionadas.includes(p.id) && p.masterId).map(p => p.masterId!))]} />
    {assistenteIntegrado() && <div className="mt-4 border-t border-border pt-4">
      <Button disabled={!selecionadas.length || selecionadas.length > 10 || prontas.filter(p => selecionadas.includes(p.id)).some(p => !p.masterId)}
        onClick={() => window.parent.postMessage({ type: 'volc:creative-selection',
          masterRefs: prontas.filter(p => selecionadas.includes(p.id)).map(p => p.masterId),
        }, window.location.origin)}>Selecionar para esta campanha</Button>
      <p className="mt-2 text-xs text-muted-foreground">Seleciona as peças prontas. Enviar à conta e publicar são ações separadas.</p>
    </div>}
    <Dialog open={Boolean(ampliada)} onOpenChange={open => { if (!open) setAmpliada(null); }}><DialogContent className="max-w-3xl"><DialogTitle>{ampliada?.rotulo ?? 'Prévia do criativo'}</DialogTitle><DialogDescription>Confira a composição na proporção original.</DialogDescription>{ampliada?.previewUrl && <img src={ampliada.previewUrl} alt={ampliada.rotulo} className="max-h-[70vh] w-full object-contain" />}</DialogContent></Dialog>
    <AlertDialog open={confirmandoExclusao} onOpenChange={setConfirmandoExclusao}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Excluir {mastersExcluiveis.length} peça(s) da biblioteca?</AlertDialogTitle>
          <AlertDialogDescription>
            Elas deixam de aparecer na galeria e não poderão entrar em novos packs. O arquivo, a geração e o recibo são preservados para auditoria. Uma peça já aprovada precisa ter a aprovação revogada antes.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={excluindo}>Manter peças</AlertDialogCancel>
          <AlertDialogAction className={buttonVariants({ variant: 'destructive' })} disabled={excluindo} onClick={(evento) => { evento.preventDefault(); void excluirSelecionadas(); }}>
            {excluindo ? 'Excluindo…' : 'Excluir da biblioteca'}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </section>;
}
