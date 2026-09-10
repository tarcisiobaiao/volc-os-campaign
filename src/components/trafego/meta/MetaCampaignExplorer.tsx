import { useMemo, useState, type ReactNode } from 'react';
import { ArrowLeft, ArrowRight, ImageIcon, Search, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import type { FinanceiroMeta, ItemMetaReadModel } from '@/lib/pautadorApi';
import { AcoesDaHierarquia, type EscopoDaHierarquia } from './AcoesDaHierarquia';

export interface MetaCampaignExplorerProps {
  arvore: Array<{ conjunto: ItemMetaReadModel; anuncios: Array<{ anuncio: ItemMetaReadModel; criativo: ItemMetaReadModel | null }> }>;
  financeiro: FinanceiroMeta | null;
  escopo: EscopoDaHierarquia;
  overview: ReactNode;
  loading?: boolean;
  partial?: boolean;
}

type MetricaAd = NonNullable<FinanceiroMeta['anuncios']>[number];
type Linha = { key: string; paiKey: string; pai: ItemMetaReadModel; anuncio: ItemMetaReadModel; criativo: ItemMetaReadModel | null; creativeKey: string; metrica: MetricaAd | null };
const texto = (item: ItemMetaReadModel | null, ...campos: string[]) => campos.map(c => item?.[c]).find((v): v is string => typeof v === 'string' && !!v.trim()) ?? '';
const identidade = (item: ItemMetaReadModel, campo: string, fallback: string) => texto(item, 'entity_ref', campo) || fallback;
const nome = (item: ItemMetaReadModel | null, fallback: string) => texto(item, 'nome', 'name') || fallback;
const numero = (valor: unknown): number | null => {
  if (valor === null || valor === undefined || typeof valor === 'boolean' || (typeof valor === 'string' && !valor.trim())) return null;
  if (typeof valor !== 'number' && typeof valor !== 'string') return null;
  const n = Number(valor); return Number.isFinite(n) ? n : null;
};
const medida = (valor: unknown, casas = 0) => { const n = numero(valor); return n === null ? '—' : n.toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas }); };
function moeda(valor: unknown, currency: string | null | undefined) {
  const n = numero(valor); if (n === null) return '—';
  if (!currency) return `${medida(n, 2)} (moeda não informada)`;
  try { return n.toLocaleString('pt-BR', { style: 'currency', currency }); } catch { return `${medida(n, 2)} (moeda não informada)`; }
}
const percentual = (valor: unknown) => numero(valor) === null ? '—' : `${medida(valor, 2)}%`;

/** Only URLs accepted by an image element; no data/blob/HTML payloads or protocol-relative paths. */
function urlDaImagem(item: ItemMetaReadModel | null): string | null {
  const raw = texto(item, 'thumbnail_url', 'image_url');
  if (!raw || /[\\\u0000-\u001f]/.test(raw)) return null;
  try {
    const local = raw.startsWith('/') && !raw.startsWith('//');
    if (!local && !/^https?:\/\//i.test(raw)) return null;
    const url = new URL(raw, 'https://local.invalid');
    if (url.username || url.password || !['https:', 'http:'].includes(url.protocol)) return null;
    if (local && /(?:^|\/)\.\.(?:\/|$)/.test(decodeURIComponent(raw.split(/[?#]/)[0]))) return null;
    return raw;
  } catch { return null; }
}

function Miniatura({ item, className = '' }: { item: ItemMetaReadModel | null; className?: string }) {
  const url = urlDaImagem(item);
  const [falha, setFalha] = useState<string | null>(null);
  return <div className={`flex items-center justify-center overflow-hidden rounded-lg bg-muted/40 ${className}`}>
    {url && falha !== url ? <img src={url} alt={nome(item, 'Criativo Meta')} loading="lazy" referrerPolicy="no-referrer" onError={() => setFalha(url)} className="h-full w-full object-contain" /> : <span className="flex flex-col items-center gap-1 p-2 text-center text-xs text-muted-foreground"><ImageIcon aria-hidden className="h-5 w-5" /><span>Prévia indisponível</span></span>}
  </div>;
}

function Status({ item }: { item: ItemMetaReadModel }) {
  const status = texto(item, 'effective_status', 'status');
  const rotulo: Record<string, string> = { ACTIVE: 'Ativo', PAUSED: 'Pausado', CAMPAIGN_PAUSED: 'Campanha pausada', ADSET_PAUSED: 'Conjunto pausado', ARCHIVED: 'Arquivado', DELETED: 'Excluído' };
  return <span className={`inline-flex rounded-md border px-2 py-1 text-xs ${status === 'ACTIVE' ? 'border-success/30 bg-success/5 text-success' : 'border-border text-muted-foreground'}`}>{rotulo[status] ?? (status || 'Não informado')}</span>;
}

function IdentidadeDaPeca({ item }: { item: ItemMetaReadModel | null }) {
  const post = texto(item, 'effective_object_story_id', 'object_story_id');
  const creative = texto(item, 'entity_ref', 'meta_creative_id');
  return <details className="min-w-0"><summary className="min-h-10 cursor-pointer py-2 text-sm font-medium">Identidade e publicação</summary><dl className="space-y-2 text-xs"><div><dt className="text-muted-foreground">Referência do criativo</dt><dd className="mt-1 break-all">{creative || 'Não disponível nesta leitura'}</dd></div><div><dt className="text-muted-foreground">ID da publicação</dt><dd className="mt-1 break-all">{post || 'Não disponível nesta leitura'}</dd></div></dl><p className="mt-2 text-xs text-muted-foreground">Reutilizar a mesma publicação pode preservar seu engajamento. A elegibilidade deve ser conferida ao preparar o novo anúncio.</p></details>;
}

/** Only matching ad-level facts may enter a creative subtotal. Never sum reach or parent revenue. */
function agregar(linhas: Linha[]) {
  const medidas = linhas.flatMap(l => l.metrica ? [l.metrica] : []);
  const soma = (campo: 'spend' | 'impressions' | 'clicks') => {
    const valores = medidas.map(m => numero(m[campo]));
    return !valores.length || valores.some(v => v === null) ? null : (valores as number[]).reduce((a, b) => a + b, 0);
  };
  const spend = soma('spend'), impressions = soma('impressions'), clicks = soma('clicks');
  return { spend, impressions, clicks, ctr: clicks !== null && impressions !== null && impressions > 0 ? clicks / impressions * 100 : null,
    quantidade: medidas.length, parcial: medidas.length !== linhas.length || medidas.some(m => !m.completo) };
}

/** Scope-keyed remount prevents stale filters/details/actions surviving an account, campaign or period switch. */
export function MetaCampaignExplorer(props: MetaCampaignExplorerProps) {
  const chave = JSON.stringify([props.escopo.contaRef, props.escopo.campanhaRef, props.financeiro?.periodo_inicio, props.financeiro?.periodo_fim]);
  return <Explorer key={chave} {...props} />;
}

function Explorer({ arvore, financeiro, escopo, overview, loading = false, partial = false }: MetaCampaignExplorerProps) {
  const [aba, setAba] = useState('campanha');
  const [busca, setBusca] = useState('');
  const [paiFiltro, setPaiFiltro] = useState('');
  const [pecaFiltro, setPecaFiltro] = useState('');
  const [detalhe, setDetalhe] = useState('');
  const conjuntos = arvore.map((a, i) => ({ ...a, key: identidade(a.conjunto, 'meta_adset_id', `pai-sem-id:${i}`) }));
  const linhas = useMemo(() => {
    const vistas = new Set<string>();
    return arvore.flatMap((a, i) => {
      const paiKey = identidade(a.conjunto, 'meta_adset_id', `pai-sem-id:${i}`);
      return a.anuncios.flatMap((r, j) => {
        const adKey = identidade(r.anuncio, 'meta_ad_id', `anuncio-sem-id:${i}:${j}`);
        const key = `${paiKey}:${adKey}`;
        if (vistas.has(key)) return [];
        vistas.add(key);
        const criativoId = texto(r.criativo, 'entity_ref', 'meta_creative_id') || texto(r.anuncio, 'meta_creative_id');
        const candidatos = financeiro?.anuncios?.filter(m => m.ad_ref === adKey && m.adset_ref === paiKey) ?? [];
        return [{ ...r, key, paiKey, pai: a.conjunto, creativeKey: criativoId || `criativo-sem-id:${key}`, metrica: candidatos.length === 1 ? candidatos[0] : null }];
      });
    });
  }, [arvore, financeiro]);
  const termo = busca.trim().toLocaleLowerCase('pt-BR');
  const visiveis = linhas.filter(l => (!paiFiltro || l.paiKey === paiFiltro) && (!pecaFiltro || l.creativeKey === pecaFiltro)
    && (!termo || [nome(l.anuncio, ''), nome(l.criativo, ''), nome(l.pai, '')].some(n => n.toLocaleLowerCase('pt-BR').includes(termo))));
  const grupos = [...visiveis.reduce((mapa, l) => { const grupo = mapa.get(l.creativeKey) ?? []; grupo.push(l); mapa.set(l.creativeKey, grupo); return mapa; }, new Map<string, Linha[]>())];
  const adAberto = visiveis.find(l => l.key === detalhe);
  const limpar = () => { setBusca(''); setPaiFiltro(''); setPecaFiltro(''); setDetalhe(''); };
  const abrirConjunto = (key: string) => { setPaiFiltro(key); setPecaFiltro(''); setBusca(''); setDetalhe(''); setAba('anuncios'); };
  const abrirPeca = (key: string, destino: 'anuncios' | 'criativos') => { setPecaFiltro(key); setBusca(''); setDetalhe(''); setAba(destino); };
  const acoes = (l: ItemMetaReadModel, entidade: 'conjunto' | 'anuncio') => l.entity_ref ? <AcoesDaHierarquia {...escopo} referencia={l.entity_ref} nome={nome(l, entidade === 'conjunto' ? 'Conjunto sem nome' : 'Anúncio sem nome')} entidade={entidade} compacto /> : <p className="text-xs text-muted-foreground">Identidade indisponível para ações.</p>;
  const dadosParciais = partial || financeiro?.anuncios_completo === false;
  const periodo = financeiro?.periodo_inicio ? `${financeiro.periodo_inicio} a ${financeiro.periodo_fim ?? 'data não informada'}` : 'Período não informado';

  function kpis(l: Linha) {
    const m = l.metrica;
    return <dl className="grid grid-cols-2 gap-x-6 gap-y-4 py-4 sm:grid-cols-3 lg:grid-cols-6">{[
      ['Gasto', moeda(m?.spend, financeiro?.currency)], ['Impressões', medida(m?.impressions)], ['Cliques', medida(m?.clicks)],
      ['CTR', percentual(m?.ctr)], ['CPC', moeda(m?.cpc, financeiro?.currency)], ['CPM', moeda(m?.cpm, financeiro?.currency)],
    ].map(([label, value]) => <div key={label}><dt className="text-xs text-muted-foreground">{label}</dt><dd className="mt-1 font-semibold tabular-nums">{value}</dd></div>)}</dl>;
  }

  return <Tabs value={aba} onValueChange={a => { setAba(a); setDetalhe(''); if (a === 'conjuntos') setPecaFiltro(''); }} className="min-w-0 space-y-5">
    <TabsList aria-label="Nível da campanha Meta" className="grid h-auto w-full grid-cols-2 gap-1 p-1 sm:grid-cols-4">
      <TabsTrigger value="campanha" className="min-h-11">Campanha</TabsTrigger>
      <TabsTrigger value="conjuntos" className="min-h-11">Conjuntos ({conjuntos.length})</TabsTrigger>
      <TabsTrigger value="anuncios" className="min-h-11">Anúncios ({linhas.length})</TabsTrigger>
      <TabsTrigger value="criativos" className="min-h-11">Criativos ({new Set(linhas.map(l => l.creativeKey)).size})</TabsTrigger>
    </TabsList>
    <TabsContent value="campanha">{overview}</TabsContent>
    {aba !== 'campanha' && <div className="space-y-3 rounded-xl border border-border bg-card p-4">
      <p className="text-xs text-muted-foreground">Nesta campanha · {periodo}. Valores do período selecionado.</p>
      <div className="flex flex-col gap-3 sm:flex-row"><label className="relative min-w-0 flex-1"><span className="sr-only">Buscar pelo nome</span><Search aria-hidden className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-muted-foreground" /><Input type="search" placeholder="Buscar pelo nome" value={busca} onChange={e => { setBusca(e.target.value); setDetalhe(''); }} className="min-h-11 pl-9" /></label>
        <label className="min-w-0 text-xs text-muted-foreground"><span className="sr-only">Filtrar conjunto</span><select aria-label="Filtrar conjunto" className="min-h-11 w-full max-w-full rounded-md border border-input bg-background px-3 text-sm text-foreground sm:max-w-72" value={paiFiltro} onChange={e => { setPaiFiltro(e.target.value); setDetalhe(''); }}><option value="">Todos os conjuntos</option>{conjuntos.map(c => <option key={c.key} value={c.key}>{nome(c.conjunto, 'Conjunto sem nome')}</option>)}</select></label>
      </div>
      {(paiFiltro || pecaFiltro || busca) && <nav aria-label="Filtros da hierarquia" className="flex flex-wrap items-center gap-2 text-sm"><span>{paiFiltro ? nome(conjuntos.find(c => c.key === paiFiltro)?.conjunto ?? null, 'Conjunto selecionado') : 'Todos os conjuntos'}</span>{pecaFiltro && <span> / Criativo selecionado</span>}<Button size="sm" variant="ghost" className="min-h-10" onClick={limpar}><X aria-hidden className="h-4 w-4" />Limpar filtros</Button></nav>}
      {dadosParciais && <p role="status" className="text-sm text-warning">Leitura parcial. Contagens e agrupamentos incluem somente os itens carregados nesta campanha.</p>}
      {loading && <div role="status" className="space-y-2"><p className="text-sm text-muted-foreground">Atualizando os dados deste período…</p><div className="h-3 w-2/3 rounded bg-muted motion-safe:animate-pulse" /></div>}
    </div>}

    <TabsContent value="conjuntos" className="min-w-0 space-y-3">
      <p className="text-sm text-muted-foreground">Receita GAM medida por conjunto. Clique no nome para explorar seus anúncios.</p>
      <div role="region" aria-label="Tabela de conjuntos" tabIndex={0} className="relative max-w-full overflow-x-auto rounded-xl border border-border bg-card">
        <table style={{ display: 'table' }} className="w-full text-left text-sm"><thead className="bg-muted/40 text-xs text-muted-foreground"><tr>{['Conjunto', 'Estado', 'Gasto', 'Receita GAM', 'ROAS', 'Lucro bruto', 'Impressões', 'Cliques', 'CTR', 'CPC', 'Anúncios carregados', 'Ações'].map(t => <th key={t} scope="col" className="whitespace-nowrap px-4 py-3">{t}</th>)}</tr></thead><tbody>
          {conjuntos.filter(c => (!paiFiltro || c.key === paiFiltro) && (!termo || nome(c.conjunto, '').toLocaleLowerCase('pt-BR').includes(termo))).map(c => {
            const candidatas = financeiro?.conjuntos?.filter(f => f.adset_ref === c.key) ?? [];
            const m = candidatas.length === 1 ? candidatas[0] : null;
            return <tr key={c.key} className="border-t border-border align-top"><th scope="row" className="min-w-48 px-4 py-4"><Button variant="link" className="h-auto whitespace-normal p-0 text-left" onClick={() => abrirConjunto(c.key)}>{nome(c.conjunto, 'Conjunto sem nome')}<ArrowRight aria-hidden className="h-4 w-4 shrink-0" /></Button></th><td className="px-4 py-4"><Status item={c.conjunto} /></td><td className="whitespace-nowrap px-4 py-4 tabular-nums">{moeda(m?.spend, financeiro?.currency)}</td><td className="whitespace-nowrap px-4 py-4 tabular-nums">{moeda(m?.revenue_brl, financeiro?.currency)}</td><td className="px-4 py-4 tabular-nums">{medida(m?.roas_ratio, 2)}</td><td className="whitespace-nowrap px-4 py-4 tabular-nums">{moeda(m?.profit_gross, financeiro?.currency)}</td><td className="px-4 py-4 tabular-nums">{medida(m?.impressions)}</td><td className="px-4 py-4 tabular-nums">{medida(m?.clicks)}</td><td className="px-4 py-4 tabular-nums">{percentual(m?.ctr)}</td><td className="whitespace-nowrap px-4 py-4 tabular-nums">{moeda(m?.cpc, financeiro?.currency)}</td><td className="px-4 py-4 tabular-nums">{linhas.filter(l => l.paiKey === c.key).length}</td><td className="px-4 py-4">{acoes(c.conjunto, 'conjunto')}</td></tr>;
          })}
        </tbody></table>
      </div>
      {!conjuntos.some(c => (!paiFiltro || c.key === paiFiltro) && (!termo || nome(c.conjunto, '').toLocaleLowerCase('pt-BR').includes(termo))) && <p role="status" className="py-6 text-sm text-muted-foreground">Nenhum conjunto encontrado com estes filtros.</p>}
    </TabsContent>

    <TabsContent value="anuncios" className="min-w-0 space-y-4">
      <p className="text-sm text-muted-foreground">Desempenho de cada anúncio. Receita, ROAS e lucro permanecem no conjunto, sem rateio artificial.</p>
      {!financeiro?.anuncios?.length && !loading && <p role="status" className="text-sm text-muted-foreground">Métricas de anúncio indisponíveis neste período. Os anúncios conhecidos continuam abaixo.</p>}
      {adAberto ? <section aria-label={`Detalhes de ${nome(adAberto.anuncio, 'Anúncio sem nome')}`} className="rounded-xl border border-border bg-card p-4 sm:p-6">
        <Button variant="ghost" className="mb-4" onClick={() => setDetalhe('')}><ArrowLeft aria-hidden className="h-4 w-4" />Voltar à lista</Button>
        <div className="flex flex-col gap-4 sm:flex-row"><Miniatura item={adAberto.criativo} className="h-48 w-full shrink-0 sm:w-40" /><div className="min-w-0"><p className="text-xs text-muted-foreground">{nome(adAberto.pai, 'Conjunto sem nome')} · {periodo}</p><h2 className="mt-1 break-words text-xl font-semibold">{nome(adAberto.anuncio, 'Anúncio sem nome')}</h2><div className="mt-2"><Status item={adAberto.anuncio} /></div><Button variant="link" className="mt-2 px-0" onClick={() => abrirPeca(adAberto.creativeKey, 'criativos')}>Ver criativo vinculado<ArrowRight aria-hidden className="h-4 w-4" /></Button></div></div>
        {kpis(adAberto)}<p className="text-xs text-muted-foreground">{adAberto.metrica ? `${adAberto.metrica.completo ? 'Leitura completa' : 'Leitura parcial'} · observada em ${adAberto.metrica.source_freshness ?? 'data não informada'}` : 'Não há leitura de métricas para este anúncio e conjunto no período.'}</p>{acoes(adAberto.anuncio, 'anuncio')}
      </section> : <div role="region" aria-label="Tabela de anúncios" tabIndex={0} className="relative max-w-full overflow-x-auto rounded-xl border border-border bg-card"><table style={{ display: 'table' }} className="w-full text-left text-sm"><thead className="bg-muted/40 text-xs text-muted-foreground"><tr>{['Anúncio', 'Conjunto', 'Estado', 'Gasto', 'Impressões', 'Cliques', 'CTR', 'CPC', 'CPM', 'Ações'].map(t => <th key={t} scope="col" className="whitespace-nowrap px-4 py-3">{t}</th>)}</tr></thead><tbody>{visiveis.map(l => <tr key={l.key} className="border-t border-border align-top"><th scope="row" className="min-w-64 px-4 py-4"><div className="flex items-center gap-3"><Miniatura item={l.criativo} className="h-20 w-20 shrink-0" /><Button variant="link" className="h-auto whitespace-normal p-0 text-left" onClick={() => setDetalhe(l.key)}>{nome(l.anuncio, 'Anúncio sem nome')}</Button></div>{l.metrica?.completo === false && <p className="mt-2 text-xs text-warning">Métricas parciais</p>}</th><td className="min-w-40 px-4 py-4">{nome(l.pai, 'Conjunto sem nome')}</td><td className="px-4 py-4"><Status item={l.anuncio} /></td><td className="whitespace-nowrap px-4 py-4 tabular-nums">{moeda(l.metrica?.spend, financeiro?.currency)}</td><td className="px-4 py-4 tabular-nums">{medida(l.metrica?.impressions)}</td><td className="px-4 py-4 tabular-nums">{medida(l.metrica?.clicks)}</td><td className="px-4 py-4 tabular-nums">{percentual(l.metrica?.ctr)}</td><td className="whitespace-nowrap px-4 py-4 tabular-nums">{moeda(l.metrica?.cpc, financeiro?.currency)}</td><td className="whitespace-nowrap px-4 py-4 tabular-nums">{moeda(l.metrica?.cpm, financeiro?.currency)}</td><td className="px-4 py-4">{acoes(l.anuncio, 'anuncio')}</td></tr>)}</tbody></table></div>}
      {!visiveis.length && <p role="status" className="py-6 text-sm text-muted-foreground">Nenhum anúncio encontrado com estes filtros.</p>}
    </TabsContent>

    <TabsContent value="criativos" className="min-w-0 space-y-4">
      <p className="text-sm text-muted-foreground">Agrupados pela identidade do criativo no snapshot atual. As métricas pertencem aos anúncios vinculados, não comprovam qual peça veiculou durante todo o período. Sem soma de receita ou alcance.</p>
      <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">{grupos.map(([key, ads]) => {
        const item = ads.find(l => l.criativo)?.criativo ?? null;
        const agregado = agregar(ads);
        const titulo = nome(item, 'Criativo sem nome');
        const body = texto(item, 'body', 'message', 'texto_principal');
        const headline = texto(item, 'title', 'headline', 'titulo');
        const description = texto(item, 'description', 'descricao');
        return <article key={key} className="min-w-0 overflow-hidden rounded-xl border border-border bg-card"><Miniatura item={item} className="h-60 rounded-none" /><div className="space-y-3 p-4"><div><h2 className="break-words text-base font-semibold">{titulo}</h2><p className="mt-1 text-xs text-muted-foreground">Usado em {ads.length} anúncio(s) carregado(s){key.startsWith('criativo-sem-id:') ? ' · identidade não disponível' : ''}</p></div>
          <p className="text-xs text-muted-foreground">{agregado.parcial ? `Subtotal disponível: ${agregado.quantidade} de ${ads.length} anúncios com leitura` : `Desempenho de ${agregado.quantidade} anúncio(s) neste período`}{partial ? ' · inventário parcial' : ''}</p>
          <dl className="grid grid-cols-3 gap-2 border-y border-border py-3 text-sm">{[['Gasto', moeda(agregado.spend, financeiro?.currency)], ['Impressões', medida(agregado.impressions)], ['CTR', percentual(agregado.ctr)]].map(([label,value]) => <div key={label} className="min-w-0"><dt className="text-xs text-muted-foreground">{label}</dt><dd className="mt-1 break-words font-semibold tabular-nums">{value}</dd></div>)}</dl>
          <details><summary className="min-h-10 cursor-pointer py-2 text-sm font-medium">Ver copy do criativo</summary>{headline || body || description ? <div className="space-y-2 whitespace-pre-wrap break-words text-sm"><p className="font-semibold">{headline}</p><p>{body}</p><p className="text-muted-foreground">{description}</p></div> : <p className="text-sm text-muted-foreground">Texto não disponível nesta leitura.</p>}</details>
          <IdentidadeDaPeca item={item} />
          <Button variant="outline" className="min-h-11 w-full" onClick={() => abrirPeca(key, 'anuncios')}>Ver {ads.length} anúncio(s)<ArrowRight aria-hidden className="h-4 w-4" /></Button>
        </div></article>;
      })}</div>
      {!grupos.length && <p role="status" className="py-6 text-sm text-muted-foreground">Nenhum criativo encontrado com estes filtros.</p>}
    </TabsContent>
  </Tabs>;
}
