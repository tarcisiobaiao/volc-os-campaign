import React, { useEffect, useMemo, useState } from 'react';
import {
  ArrowLeft, ArrowRight, Check, CheckCircle2, CircleDollarSign, Crosshair,
  Copy, FileCheck2, Image, Info, Layers3, Loader2, LockKeyhole, Megaphone,
  Plus, Settings2, ShieldCheck, Trash2, Users,
} from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';

import { Layout } from '@/components/layout/Layout';
import { MetaConfiguracaoLocal } from '@/components/trafego/meta/MetaConfiguracaoLocal';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  AtivoCriacaoMeta, ContaMetaLocal, pautadorApi, PlanoMetaPausadoInput,
  ResultadoCompilacaoMeta, ResultadoValidacaoPlanoMeta,
} from '@/lib/pautadorApi';
import { cn } from '@/lib/utils';

const ETAPAS = [
  { id: 'base', nome: 'Base', resumo: 'conta e página', icone: Layers3 },
  { id: 'campanha', nome: 'Campanha', resumo: 'objetivo e política', icone: Megaphone },
  { id: 'orcamento', nome: 'Orçamento', resumo: 'verba e agenda', icone: CircleDollarSign },
  { id: 'conjunto', nome: 'Conjunto', resumo: 'otimização e entrega', icone: Crosshair },
  { id: 'publico', nome: 'Público', resumo: 'alcance permitido', icone: Users },
  { id: 'criativo', nome: 'Anúncio', resumo: 'peça e mensagem', icone: Image },
  { id: 'mensuracao', nome: 'Mensuração', resumo: 'LPV e destino', icone: Settings2 },
  { id: 'revisao', nome: 'Revisão', resumo: 'plano verificável', icone: FileCheck2 },
] as const;

type Etapa = typeof ETAPAS[number]['id'];
type ModoCriativo = 'single' | 'batch' | 'flexible';
type VariacaoDraft = {
  key: string;
  assetRef: string;
  creativeName: string;
  adName: string;
  message: string;
  headline: string;
  description: string;
  cta: string;
};
type Draft = {
  accountRef: string; pageRef: string;
  campaignName: string; adsetName: string;
  destinationUrl: string;
  budgetBrl: string; startTime: string;
  categoryConfirmed: boolean; budgetSharing: boolean;
  creativeMode: ModoCriativo;
  variations: VariacaoDraft[];
};

const inicioPadrao = () => {
  const data = new Date(Date.now() + 30 * 60 * 1000);
  data.setSeconds(0, 0);
  const local = new Date(data.getTime() - data.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
};

const DRAFT_INICIAL: Draft = {
  accountRef: '', pageRef: '',
  campaignName: 'VOLC · Meta · Tráfego · LPV',
  adsetName: 'Brasil · Amplo · LPV · Automático',
  destinationUrl: 'https://focogenial.com/',
  budgetBrl: '10,00', startTime: inicioPadrao(),
  categoryConfirmed: false, budgetSharing: false, creativeMode: 'single',
  variations: [{
    key: 'variation-001', assetRef: '',
    creativeName: 'Criativo estático · v1', adName: 'Anúncio estático · v1',
    message: 'Descubra as informações importantes antes de decidir.',
    headline: 'Entenda como funciona', description: 'Conteúdo informativo e independente.',
    cta: 'LEARN_MORE',
  }],
};

const campo = 'h-11 w-full rounded-lg border border-input bg-card px-3 text-sm text-foreground transition-[border-color,box-shadow] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/35';

const Grupo: React.FC<{ titulo: string; ajuda?: string; children: React.ReactNode }> = ({ titulo, ajuda, children }) => (
  <section className="border-b border-border/70 py-6 first:pt-0 last:border-0 last:pb-0">
    <h2 className="font-display text-xl font-semibold tracking-tight text-foreground">{titulo}</h2>
    {ajuda && <p className="mt-1.5 max-w-[72ch] text-sm leading-relaxed text-muted-foreground">{ajuda}</p>}
    <div className="mt-5 grid gap-4 md:grid-cols-2">{children}</div>
  </section>
);

const Campo: React.FC<{ id: string; rotulo: string; ajuda?: string; children: React.ReactNode; largo?: boolean }> = ({ id, rotulo, ajuda, children, largo }) => (
  <div className={cn('space-y-2', largo && 'md:col-span-2')}>
    <Label htmlFor={id}>{rotulo}</Label>{children}
    {ajuda && <p className="text-xs leading-relaxed text-muted-foreground">{ajuda}</p>}
  </div>
);

const Fixo: React.FC<{ rotulo: string; valor: string; detalhe: string }> = ({ rotulo, valor, detalhe }) => (
  <div className="rounded-xl border border-primary/15 bg-primary/[0.035] p-4">
    <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-muted-foreground">{rotulo}</p>
    <p className="mt-2 font-semibold text-foreground">{valor}</p>
    <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{detalhe}</p>
  </div>
);

const Resumo: React.FC<{ rotulo: string; valor: string; pendente?: boolean }> = ({ rotulo, valor, pendente }) => (
  <div className="flex items-start justify-between gap-5 border-b border-border/70 py-3.5 last:border-0">
    <dt className="text-sm text-muted-foreground">{rotulo}</dt>
    <dd className={cn('max-w-[68%] break-words text-right text-sm font-semibold', pendente ? 'text-warning' : 'text-foreground')}>{valor}</dd>
  </div>
);

function reaisParaMinor(valor: string): number {
  const numero = Number(valor.trim().replace(/\./g, '').replace(',', '.'));
  return Number.isFinite(numero) ? Math.round(numero * 100) : 0;
}

function paraPlano(draft: Draft): PlanoMetaPausadoInput {
  const primeira = draft.variations[0];
  return {
    account_ref: draft.accountRef, page_ref: draft.pageRef, asset_ref: primeira.assetRef,
    campaign_name: draft.campaignName, adset_name: draft.adsetName,
    creative_name: primeira.creativeName, ad_name: primeira.adName,
    destination_url: draft.destinationUrl, message: primeira.message,
    headline: primeira.headline, description: primeira.description,
    daily_budget_minor: reaisParaMinor(draft.budgetBrl),
    start_time: new Date(draft.startTime).toISOString(),
    special_ad_categories: [],
    special_categories_confirmed: draft.categoryConfirmed,
    is_adset_budget_sharing_enabled: draft.budgetSharing,
    call_to_action_type: primeira.cta,
    variations: draft.variations.map((item) => ({
      variation_key: item.key,
      asset_ref: item.assetRef,
      creative_name: item.creativeName,
      ad_name: item.adName,
      message: item.message,
      headline: item.headline,
      description: item.description,
      call_to_action_type: item.cta,
    })),
  };
}

const PreviewDaPeca: React.FC<{
  accountRef: string;
  ativo?: AtivoCriacaoMeta;
}> = ({ accountRef, ativo }) => {
  const [url, setUrl] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  useEffect(() => {
    setErro(null);
    setUrl((anterior) => {
      if (anterior) URL.revokeObjectURL(anterior);
      return null;
    });
    if (!accountRef || !ativo?.referencia_opaca || !ativo.preview_disponivel) return;
    let vivo = true;
    let criada: string | null = null;
    pautadorApi.previewAtivoMeta(accountRef, ativo.referencia_opaca)
      .then((proxima) => {
        criada = proxima;
        if (vivo) setUrl(proxima);
        else URL.revokeObjectURL(proxima);
      })
      .catch((exc) => vivo && setErro(
        exc instanceof Error ? exc.message : 'Não foi possível carregar a prévia.'));
    return () => {
      vivo = false;
      if (criada) URL.revokeObjectURL(criada);
    };
  }, [accountRef, ativo?.referencia_opaca, ativo?.preview_disponivel]);
  return <div className="flex min-h-40 items-center justify-center overflow-hidden rounded-lg bg-muted/35">
    {url ? <img src={url} alt={`Prévia de ${ativo?.nome || 'imagem selecionada'}`} className="h-full max-h-64 w-full object-contain" /> : <div className="flex flex-col items-center gap-2 px-5 text-center text-xs text-muted-foreground"><Image className="h-7 w-7 opacity-50" /><span>{erro || (ativo?.preview_disponivel ? 'Carregando prévia…' : 'Prévia indisponível')}</span></div>}
  </div>;
};

const MetaCriacaoPage: React.FC = () => {
  const [params, setParams] = useSearchParams();
  const pedida = params.get('etapa') as Etapa | null;
  const etapa = ETAPAS.some((item) => item.id === pedida) ? pedida! : 'base';
  const indice = ETAPAS.findIndex((item) => item.id === etapa);
  const [draft, setDraft] = useState<Draft>(DRAFT_INICIAL);
  const [contas, setContas] = useState<ContaMetaLocal[]>([]);
  const [paginas, setPaginas] = useState<AtivoCriacaoMeta[]>([]);
  const [imagens, setImagens] = useState<AtivoCriacaoMeta[]>([]);
  const [validateEnabled, setValidateEnabled] = useState(false);
  const [carregando, setCarregando] = useState(true);
  const [ocupado, setOcupado] = useState<'assets' | 'compile' | 'validate' | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [compilacao, setCompilacao] = useState<ResultadoCompilacaoMeta | null>(null);
  const [validacao, setValidacao] = useState<ResultadoValidacaoPlanoMeta | null>(null);

  useEffect(() => {
    let vivo = true;
    Promise.all([pautadorApi.contasMetaLocal(), pautadorApi.capacidadesCriacaoMeta()])
      .then(([inventario, capacidades]) => {
        if (!vivo) return;
        setContas(inventario.contas);
        setValidateEnabled(capacidades.validate_only === 'ENABLED');
        if (inventario.contas.length === 1) {
          setDraft((atual) => ({ ...atual, accountRef: inventario.contas[0].referencia_opaca }));
        }
      })
      .catch((exc) => vivo && setErro(exc instanceof Error ? exc.message : 'Não foi possível ler as contas Meta.'))
      .finally(() => vivo && setCarregando(false));
    return () => { vivo = false; };
  }, []);

  useEffect(() => {
    if (!draft.accountRef) { setPaginas([]); setImagens([]); return; }
    let vivo = true;
    setOcupado('assets');
    pautadorApi.ativosCriacaoMeta(draft.accountRef)
      .then((resultado) => {
        if (!vivo) return;
        setPaginas(resultado.paginas); setImagens(resultado.imagens);
        setDraft((atual) => ({
          ...atual,
          pageRef: resultado.paginas.some((item) => item.referencia_opaca === atual.pageRef) ? atual.pageRef : (resultado.paginas[0]?.referencia_opaca || ''),
          variations: atual.variations.map((variacao) => ({
            ...variacao,
            assetRef: resultado.imagens.some((item) => item.referencia_opaca === variacao.assetRef)
              ? variacao.assetRef : (resultado.imagens[0]?.referencia_opaca || ''),
          })),
        }));
      })
      .catch((exc) => vivo && setErro(exc instanceof Error ? exc.message : 'Não foi possível ler páginas e imagens.'))
      .finally(() => vivo && setOcupado(null));
    return () => { vivo = false; };
  }, [draft.accountRef]);

  const mudar = <K extends keyof Draft>(chave: K, valor: Draft[K]) => {
    setDraft((atual) => ({ ...atual, [chave]: valor }));
    setCompilacao(null); setValidacao(null); setErro(null);
  };
  const mudarVariacao = <K extends keyof VariacaoDraft>(indiceVariacao: number, chave: K, valor: VariacaoDraft[K]) => {
    setDraft((atual) => ({
      ...atual,
      variations: atual.variations.map((item, posicao) => (
        posicao === indiceVariacao ? { ...item, [chave]: valor } : item
      )),
    }));
    setCompilacao(null); setValidacao(null); setErro(null);
  };
  const adicionarVariacao = () => {
    setDraft((atual) => {
      if (atual.variations.length >= 10) return atual;
      const numero = atual.variations.length + 1;
      const base = atual.variations.at(-1) || DRAFT_INICIAL.variations[0];
      return {
        ...atual,
        creativeMode: 'batch',
        variations: [...atual.variations, {
          ...base,
          key: `variation-${String(numero).padStart(3, '0')}`,
          creativeName: `Criativo estático · v${numero}`,
          adName: `Anúncio estático · v${numero}`,
        }],
      };
    });
    setCompilacao(null); setValidacao(null);
  };
  const duplicarVariacao = (indiceVariacao: number) => {
    setDraft((atual) => {
      if (atual.variations.length >= 10) return atual;
      const numero = atual.variations.length + 1;
      const base = atual.variations[indiceVariacao];
      return {
        ...atual,
        creativeMode: 'batch',
        variations: [...atual.variations, {
          ...base,
          key: `variation-${String(numero).padStart(3, '0')}`,
          creativeName: `${base.creativeName} · cópia ${numero}`,
          adName: `${base.adName} · cópia ${numero}`,
        }],
      };
    });
    setCompilacao(null); setValidacao(null);
  };
  const removerVariacao = (indiceVariacao: number) => {
    setDraft((atual) => ({
      ...atual,
      creativeMode: atual.variations.length === 2 ? 'single' : atual.creativeMode,
      variations: atual.variations.filter((_, posicao) => posicao !== indiceVariacao),
    }));
    setCompilacao(null); setValidacao(null);
  };
  const navegar = (proxima: Etapa) => {
    const novos = new URLSearchParams(params);
    novos.set('etapa', proxima); novos.delete('modo'); setParams(novos);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const conta = contas.find((item) => item.referencia_opaca === draft.accountRef);
  const pagina = paginas.find((item) => item.referencia_opaca === draft.pageRef);
  const variacoesValidas = draft.variations.length > 0 && draft.variations.length <= 10
    && draft.variations.every((item) => Boolean(
      item.assetRef && item.creativeName.trim() && item.adName.trim()
      && item.message.trim() && item.headline.trim() && item.description.trim() && item.cta
    ));
  const prontoLocal = useMemo(() => Boolean(
    draft.accountRef && draft.pageRef && draft.campaignName.trim()
    && draft.adsetName.trim() && draft.destinationUrl.startsWith('https://')
    && variacoesValidas && reaisParaMinor(draft.budgetBrl) > 0
    && draft.startTime && draft.categoryConfirmed && draft.creativeMode !== 'flexible'
  ), [draft, variacoesValidas]);

  const compilar = async () => {
    setOcupado('compile'); setErro(null);
    try { setCompilacao(await pautadorApi.compilarPlanoMeta(paraPlano(draft))); setValidacao(null); }
    catch (exc) { setErro(exc instanceof Error ? exc.message : 'O plano não pôde ser compilado.'); }
    finally { setOcupado(null); }
  };
  const validar = async () => {
    setOcupado('validate'); setErro(null);
    try { setValidacao(await pautadorApi.validarPlanoMeta(paraPlano(draft))); }
    catch (exc) { setErro(exc instanceof Error ? exc.message : 'A Meta recusou a validação remota.'); }
    finally { setOcupado(null); }
  };

  const conteudo = (() => {
    switch (etapa) {
      case 'base': return <Grupo titulo="Escolha a autoridade desta campanha" ajuda="Conta, Página e imagem são relidas da Meta. O navegador recebe apenas referências opacas.">
        <Campo id="meta-conta" rotulo="Conta de anúncios"><select id="meta-conta" className={campo} value={draft.accountRef} onChange={(e) => mudar('accountRef', e.target.value)} disabled={carregando}><option value="">Selecione uma conta real</option>{contas.map((item) => <option key={item.referencia_opaca} value={item.referencia_opaca}>{item.nome} · {item.id_mascarado || 'ID protegido'} · {item.moeda || 'moeda não lida'}</option>)}</select></Campo>
        <Campo id="meta-pagina" rotulo="Página do Facebook"><select id="meta-pagina" className={campo} value={draft.pageRef} onChange={(e) => mudar('pageRef', e.target.value)} disabled={!draft.accountRef || ocupado === 'assets'}><option value="">Selecione uma Página desta conta</option>{paginas.map((item) => <option key={item.referencia_opaca} value={item.referencia_opaca}>{item.nome} · {item.id_mascarado}</option>)}</select></Campo>
        <Fixo rotulo="Conta efetiva" valor={conta?.nome || 'Ainda não escolhida'} detalhe="BRL é obrigatório no primeiro canário. A conta é resolvida novamente em cada ato." />
        <Fixo rotulo="Página efetiva" valor={pagina?.nome || 'Ainda não escolhida'} detalhe="A Página precisa estar disponível para promoção na conta selecionada." />
      </Grupo>;
      case 'campanha': return <Grupo titulo="Defina identidade e enquadramento" ajuda="O primeiro contrato é estreito: tráfego para site, em leilão e sempre pausado.">
        <Campo id="meta-nome" rotulo="Nome da campanha" largo><Input id="meta-nome" value={draft.campaignName} onChange={(e) => mudar('campaignName', e.target.value)} /></Campo>
        <Fixo rotulo="Objetivo" valor="Tráfego" detalhe="OUTCOME_TRAFFIC · fixado pelo servidor" />
        <Fixo rotulo="Compra e estado" valor="Leilão · PAUSADA" detalhe="Nenhum caminho de ativação existe nesta bancada." />
        <Fixo rotulo="Categoria especial" valor="Nenhuma" detalhe="A receita P0 não aceita crédito, emprego, moradia ou política até seus contratos próprios serem provados." />
        <label className="flex min-h-11 cursor-pointer items-start gap-3 rounded-lg border border-border bg-muted/20 p-3 text-sm"><input type="checkbox" checked={draft.categoryConfirmed} onChange={(e) => mudar('categoryConfirmed', e.target.checked)} className="mt-0.5 h-4 w-4" /><span><strong className="block">Confirmo o enquadramento acima</strong><span className="text-xs text-muted-foreground">A ausência de categoria também é uma declaração explícita.</span></span></label>
      </Grupo>;
      case 'orcamento': return <Grupo titulo="Defina o limite do canário" ajuda="A verba fica no conjunto e usa menor custo sem limite de lance.">
        <Campo id="meta-budget" rotulo="Orçamento diário · BRL"><Input id="meta-budget" inputMode="decimal" value={draft.budgetBrl} onChange={(e) => mudar('budgetBrl', e.target.value)} /></Campo>
        <Campo id="meta-start" rotulo="Início"><Input id="meta-start" type="datetime-local" value={draft.startTime} onChange={(e) => mudar('startTime', e.target.value)} /></Campo>
        <Fixo rotulo="Escopo" valor="Conjunto de anúncios" detalhe="daily_budget no AdSet · sem Advantage campaign budget" />
        <Fixo rotulo="Lance" valor="Maior volume · menor custo" detalhe="LOWEST_COST_WITHOUT_CAP · sem bid_amount" />
        <label className="flex min-h-11 cursor-pointer items-start gap-3 rounded-xl border border-primary/15 bg-primary/[0.035] p-4 md:col-span-2"><input type="checkbox" checked={draft.budgetSharing} onChange={(e) => mudar('budgetSharing', e.target.checked)} className="mt-0.5 h-4 w-4" /><span><strong className="block text-sm text-foreground">Permitir compartilhamento de orçamento entre conjuntos</strong><span className="mt-1 block text-xs leading-relaxed text-muted-foreground">Campo Meta obrigatório: <code>is_adset_budget_sharing_enabled</code>. Desativado, cada conjunto preserva integralmente sua verba; ativado, a Meta pode compartilhar até 20% entre conjuntos elegíveis.</span></span></label>
      </Grupo>;
      case 'conjunto': return <Grupo titulo="Configure a unidade de entrega" ajuda="A meta e o evento de cobrança formam uma única receita validada pelo engine.">
        <Campo id="meta-adset-name" rotulo="Nome do conjunto" largo><Input id="meta-adset-name" value={draft.adsetName} onChange={(e) => mudar('adsetName', e.target.value)} /></Campo>
        <Fixo rotulo="Meta de desempenho" valor="Visualizações da página de destino" detalhe="LANDING_PAGE_VIEWS" />
        <Fixo rotulo="Cobrança" valor="Impressões" detalhe="IMPRESSIONS · sujeito ao validate_only da conta" />
        <Fixo rotulo="Destino" valor="Site" detalhe="WEBSITE · não cria experiência instantânea" />
        <Fixo rotulo="Mensuração promovida" valor="Nenhuma nesta receita" detalhe="Pixel e conversão personalizada pertencem à futura receita Sales/Leads." />
      </Grupo>;
      case 'publico': return <Grupo titulo="Público e inventário do primeiro canário" ajuda="Automático por omissão não significa Advantage+ inferido.">
        <Fixo rotulo="País" valor="Brasil" detalhe="geo_locations.countries = BR" /><Fixo rotulo="Idade" valor="18 a 65+" detalhe="Faixa ampla e explícita" />
        <Fixo rotulo="Posicionamentos" valor="Automáticos" detalhe="Nenhuma lista manual é enviada" /><Fixo rotulo="Advantage Audience" valor="Não declarado" detalhe="Não afirmamos ligado nem desligado sem read-back próprio." />
      </Grupo>;
      case 'criativo': return <Grupo titulo="Monte os anúncios" ajuda="Cada linha é um anúncio explícito: uma peça, uma mensagem e um estado PAUSADO. Não há produto cartesiano escondido.">
        <div className="md:col-span-2">
          <div className="grid gap-2 rounded-lg border border-border bg-muted p-1 sm:grid-cols-3" role="radiogroup" aria-label="Modo de criativo">
            {([
              ['single', 'Individual', 'uma peça'],
              ['batch', 'Lote controlado', 'até 10 anúncios'],
              ['flexible', 'Flexível', 'inspeção do contrato'],
            ] as const).map(([id, nome, detalhe]) => {
              return <button key={id} type="button" role="radio" aria-checked={draft.creativeMode === id} onClick={() => mudar('creativeMode', id)} className={cn('min-h-14 rounded-md px-3 py-2 text-left transition-[background-color,color,box-shadow] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring', draft.creativeMode === id ? 'bg-card text-foreground shadow-card' : 'text-muted-foreground hover:bg-card/45 hover:text-foreground')}><strong className="block text-sm">{nome}</strong><span className="block text-xs">{detalhe}{id === 'flexible' ? ' · emissão bloqueada' : ''}</span></button>;
            })}
          </div>
          <p className="mt-2 text-xs text-muted-foreground"><strong>{draft.variations.length} de 10</strong> anúncios no lote. O limite 10 é uma contenção operacional VOLC, não um limite declarado pela Meta.</p>
        </div>
        {draft.creativeMode === 'flexible' ? <div className="md:col-span-2 rounded-lg border border-warning/25 bg-warning/5 p-5" role="status">
          <div className="flex items-start gap-3"><LockKeyhole className="mt-0.5 h-5 w-5 shrink-0 text-warning" /><div><h3 className="font-display text-lg font-semibold text-foreground">Criativo flexível está modelado, mas não será fingido</h3><p className="mt-1 max-w-[70ch] text-sm leading-relaxed text-muted-foreground">O inventário v26 confirma até 10 imagens, 10 vídeos, 5 textos, 5 títulos, 5 CTAs e 30 assets totais. Ainda faltam provar a forma exata de <code>asset_feed_spec</code>, <code>is_dynamic_creative</code>, labels, regras por posicionamento e read-back. Até isso passar no validate_only, este modo não emite payload.</p></div></div>
        </div> : <div className="space-y-5 md:col-span-2">
          {draft.variations.map((variacao, posicao) => {
            const ativo = imagens.find((item) => item.referencia_opaca === variacao.assetRef);
            return <section key={variacao.key} className="overflow-hidden rounded-lg border border-border bg-card">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border bg-muted/30 px-4 py-3"><div><p className="text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">Anúncio {posicao + 1}</p><p className="mt-0.5 text-sm font-semibold text-foreground">{variacao.headline || 'Sem título'}</p></div><div className="flex items-center gap-1"><Button type="button" variant="ghost" size="sm" disabled={draft.variations.length >= 10} onClick={() => duplicarVariacao(posicao)}><Copy className="mr-1.5 h-4 w-4" />Duplicar</Button><Button type="button" variant="ghost" size="sm" disabled={draft.variations.length === 1} onClick={() => removerVariacao(posicao)}><Trash2 className="mr-1.5 h-4 w-4" />Remover</Button></div></div>
              <div className="grid gap-5 p-4 lg:grid-cols-[minmax(190px,30%)_1fr]">
                <div><PreviewDaPeca accountRef={draft.accountRef} ativo={ativo} /><p className="mt-2 break-words text-xs font-medium text-foreground">{ativo?.nome || 'Escolha uma imagem'}</p>{ativo?.largura && ativo?.altura && <p className="text-xs text-muted-foreground">{ativo.largura} × {ativo.altura}px</p>}</div>
                <div className="grid gap-4 md:grid-cols-2">
                  <Campo id={`meta-media-${posicao}`} rotulo="Imagem da conta" largo><select id={`meta-media-${posicao}`} className={campo} value={variacao.assetRef} onChange={(e) => mudarVariacao(posicao, 'assetRef', e.target.value)} disabled={!draft.accountRef || ocupado === 'assets'}><option value="">Selecione uma imagem existente</option>{imagens.map((item) => <option key={item.referencia_opaca} value={item.referencia_opaca}>{item.nome}{item.largura && item.altura ? ` · ${item.largura}×${item.altura}` : ''}</option>)}</select></Campo>
                  <Campo id={`meta-ad-name-${posicao}`} rotulo="Nome do anúncio"><Input id={`meta-ad-name-${posicao}`} value={variacao.adName} onChange={(e) => mudarVariacao(posicao, 'adName', e.target.value)} /></Campo>
                  <Campo id={`meta-creative-name-${posicao}`} rotulo="Nome do criativo"><Input id={`meta-creative-name-${posicao}`} value={variacao.creativeName} onChange={(e) => mudarVariacao(posicao, 'creativeName', e.target.value)} /></Campo>
                  <Campo id={`meta-primary-${posicao}`} rotulo="Texto principal" largo><Textarea id={`meta-primary-${posicao}`} rows={3} value={variacao.message} onChange={(e) => mudarVariacao(posicao, 'message', e.target.value)} /></Campo>
                  <Campo id={`meta-headline-${posicao}`} rotulo="Título"><Input id={`meta-headline-${posicao}`} value={variacao.headline} onChange={(e) => mudarVariacao(posicao, 'headline', e.target.value)} /></Campo>
                  <Campo id={`meta-description-${posicao}`} rotulo="Descrição"><Input id={`meta-description-${posicao}`} value={variacao.description} onChange={(e) => mudarVariacao(posicao, 'description', e.target.value)} /></Campo>
                  <Campo id={`meta-cta-${posicao}`} rotulo="Chamada para ação" largo><select id={`meta-cta-${posicao}`} className={campo} value={variacao.cta} onChange={(e) => mudarVariacao(posicao, 'cta', e.target.value)}><option value="LEARN_MORE">Saiba mais</option><option value="APPLY_NOW">Inscreva-se</option><option value="SIGN_UP">Cadastre-se</option><option value="GET_QUOTE">Solicitar cotação</option><option value="CONTACT_US">Fale conosco</option></select></Campo>
                </div>
              </div>
            </section>;
          })}
          <Button type="button" variant="outline" className="w-full border-dashed" disabled={draft.variations.length >= 10} onClick={adicionarVariacao}><Plus className="mr-2 h-4 w-4" />Adicionar outro anúncio ao lote</Button>
        </div>}
      </Grupo>;
      case 'mensuracao': return <Grupo titulo="Feche destino e mensuração" ajuda="Traffic/LPV não exige promoted_object; conversões não entram escondidas neste canário.">
        <Campo id="meta-url" rotulo="URL final HTTPS" largo><Input id="meta-url" type="url" value={draft.destinationUrl} onChange={(e) => mudar('destinationUrl', e.target.value)} /></Campo>
        <Fixo rotulo="Otimização" valor="Landing Page Views" detalhe="A Meta valida a compatibilidade; o VOLC não presume aprovação." />
        <Fixo rotulo="Objeto promovido" valor="Omitido" detalhe="Nenhum pixel, dataset ou custom conversion é criado ou selecionado." />
        <Fixo rotulo="Atribuição" valor="Padrão efetivo da conta" detalhe="Nenhuma janela é forçada sem contrato específico." />
        <Fixo rotulo="URL final" valor={draft.destinationUrl || 'Pendente'} detalhe="Inclua UTMs diretamente nesta URL quando necessárias." />
      </Grupo>;
      case 'revisao': return <>
        <Grupo titulo="Pedido verificável para nascimento pausado" ajuda="Primeiro compile; depois valide as raízes sem criar nenhum objeto.">
          <dl className="md:col-span-2">
            <Resumo rotulo="Conta" valor={conta ? `${conta.nome} · ${conta.id_mascarado || 'ID protegido'}` : 'não selecionada'} pendente={!conta} />
            <Resumo rotulo="Página" valor={pagina?.nome || 'não selecionada'} pendente={!pagina} />
            <Resumo rotulo="Campanha" valor={draft.campaignName || 'não informada'} pendente={!draft.campaignName} />
            <Resumo rotulo="Receita" valor={`Tráfego · Website · LPV · ${draft.variations.length > 1 ? 'lote estático' : 'imagem estática'}`} /><Resumo rotulo="Orçamento" valor={`R$ ${draft.budgetBrl}/dia · conjunto`} />
            <Resumo rotulo="Compartilhamento entre conjuntos" valor={draft.budgetSharing ? 'Ativado · até 20%' : 'Desativado'} />
            <Resumo rotulo="Estrutura" valor={`1 campanha · 1 conjunto · ${draft.variations.length} criativo${draft.variations.length === 1 ? '' : 's'} · ${draft.variations.length} anúncio${draft.variations.length === 1 ? '' : 's'}`} /><Resumo rotulo="Estado ao nascer" valor="PAUSADA em todos os níveis veiculáveis" />
            <Resumo rotulo="Plano" valor={compilacao ? `${compilacao.plano.plano_sha256.slice(0, 16)}…` : 'ainda não compilado'} pendente={!compilacao} />
            <Resumo rotulo="Validação externa" valor={validacao?.ok ? `aceita · ${validacao.operacoes_validadas.join(', ')}` : 'não executada'} pendente={!validacao?.ok} />
          </dl>
        </Grupo>
        <div className="mt-5 grid gap-3 md:grid-cols-2">
          <Button type="button" variant="outline" className="min-h-12" disabled={!prontoLocal || ocupado !== null} onClick={compilar}>{ocupado === 'compile' ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <ShieldCheck className="mr-2 h-4 w-4" />}Conferir plano</Button>
          <Button type="button" className="min-h-12" disabled={!compilacao || !validateEnabled || ocupado !== null} onClick={validar} title={validateEnabled ? 'Executa somente execution_options=validate_only' : 'Flag META_VALIDATE_ONLY_ENABLED fechada'}>{ocupado === 'validate' ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <CheckCircle2 className="mr-2 h-4 w-4" />}Validar na Meta · zero criação</Button>
        </div>
        <div className="mt-4 flex items-start gap-2 rounded-xl border border-warning/25 bg-warning/5 p-4 text-sm"><LockKeyhole className="mt-0.5 h-4 w-4 shrink-0 text-warning" /><p><strong>Criação real não está montada nesta rota.</strong> O compilador e o executor pausado existem, mas o transporte final aguarda autorização separada para Supabase write e Meta mutate.</p></div>
        <Button type="button" className="mt-3 w-full" disabled>Criar campanha pausada</Button>
      </>;
    }
  })();

  return <Layout><main className="p-4 md:p-8">
    <header className="relative mb-6 overflow-hidden rounded-2xl border border-white/10 bg-[#101524] p-6 text-white shadow-xl md:p-8"><div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-cyan-400 via-violet-500 to-red-500" /><div className="relative flex flex-wrap items-start justify-between gap-5"><div><Link to="/trafego?rede=meta&aba=preparar" className="inline-flex min-h-9 items-center gap-2 text-sm text-white/60 hover:text-white"><ArrowLeft className="h-4 w-4" /> Tráfego · Meta Ads</Link><div className="mt-3 flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.18em] text-cyan-300"><Megaphone className="h-3.5 w-3.5" /> nascimento controlado · v26</div><h1 className="mt-2 font-display text-[2rem] font-bold leading-tight tracking-tight md:text-[2.65rem]">Nova campanha Meta</h1><p className="mt-3 max-w-[68ch] text-sm leading-relaxed text-white/60">Traffic → Website → LPV, peça existente e tudo veiculável nascendo pausado.</p></div><MetaConfiguracaoLocal /></div></header>
    {erro && <div role="alert" className="mb-5 rounded-xl border border-destructive/25 bg-destructive/5 px-4 py-3 text-sm text-destructive">{erro}</div>}
    <div className="mb-5 flex items-start gap-2 rounded-xl border border-verified/25 bg-verified/5 px-4 py-3 text-xs"><Info className="mt-0.5 h-4 w-4 shrink-0 text-verified" /><p><strong>Contrato ligado.</strong> Contas, Páginas e imagens vêm da Meta; o plano é compilado pelo Python. Apenas validate_only pode sair daqui, após clique explícito e flag do servidor.</p></div>
    <div className="grid gap-5 lg:grid-cols-[260px_minmax(0,1fr)]"><nav aria-label="Etapas da criação Meta" className="h-fit rounded-xl border border-border bg-card p-2 shadow-card lg:sticky lg:top-4">{ETAPAS.map((item, posicao) => { const Icone = item.icone; const atual = item.id === etapa; const passou = posicao < indice; return <button key={item.id} type="button" onClick={() => navegar(item.id)} aria-current={atual ? 'step' : undefined} className={cn('flex min-h-13 w-full items-center gap-3 rounded-lg px-3 text-left transition-[background-color,color,box-shadow] duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring', atual ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:bg-muted hover:text-foreground')}><span className={cn('flex h-8 w-8 shrink-0 items-center justify-center rounded-full border text-xs', atual ? 'border-primary-foreground/35' : passou ? 'border-success/30 bg-success/10 text-success' : 'border-border')}>{passou ? <Check className="h-4 w-4" /> : <Icone className="h-4 w-4" />}</span><span className="min-w-0"><strong className="block truncate text-sm font-semibold">{item.nome}</strong><span className={cn('block truncate text-[11px]', atual ? 'text-primary-foreground/70' : 'text-muted-foreground')}>{item.resumo}</span></span></button>; })}</nav>
      <form className="rounded-xl border border-border bg-card p-5 shadow-card md:p-7" onSubmit={(evento) => evento.preventDefault()}>{conteudo}<div className="mt-7 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-5"><Button type="button" variant="outline" disabled={indice === 0} onClick={() => navegar(ETAPAS[indice - 1].id)}><ArrowLeft className="mr-2 h-4 w-4" /> Voltar</Button>{indice < ETAPAS.length - 1 && <Button type="button" onClick={() => navegar(ETAPAS[indice + 1].id)}>Continuar <ArrowRight className="ml-2 h-4 w-4" /></Button>}</div></form></div>
  </main></Layout>;
};

export default MetaCriacaoPage;
