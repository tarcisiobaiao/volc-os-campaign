import React, { useEffect, useMemo, useState } from 'react';
import {
  ArrowLeft, ArrowRight, Check, CheckCircle2, CircleDollarSign, Crosshair,
  FileCheck2, Image, Info, Layers3, Loader2, LockKeyhole, Megaphone,
  Settings2, ShieldCheck, Users,
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
type Draft = {
  accountRef: string; pageRef: string; assetRef: string;
  campaignName: string; adsetName: string; creativeName: string; adName: string;
  destinationUrl: string; message: string; headline: string; description: string;
  budgetBrl: string; startTime: string;
  categoryConfirmed: boolean; cta: string;
};

const inicioPadrao = () => {
  const data = new Date(Date.now() + 30 * 60 * 1000);
  data.setSeconds(0, 0);
  const local = new Date(data.getTime() - data.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
};

const DRAFT_INICIAL: Draft = {
  accountRef: '', pageRef: '', assetRef: '',
  campaignName: 'VOLC · Meta · Tráfego · LPV',
  adsetName: 'Brasil · Amplo · LPV · Automático',
  creativeName: 'Criativo estático · v1', adName: 'Anúncio estático · v1',
  destinationUrl: 'https://focogenial.com/',
  message: 'Descubra as informações importantes antes de decidir.',
  headline: 'Entenda como funciona', description: 'Conteúdo informativo e independente.',
  budgetBrl: '10,00', startTime: inicioPadrao(),
  categoryConfirmed: false, cta: 'LEARN_MORE',
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
  return {
    account_ref: draft.accountRef, page_ref: draft.pageRef, asset_ref: draft.assetRef,
    campaign_name: draft.campaignName, adset_name: draft.adsetName,
    creative_name: draft.creativeName, ad_name: draft.adName,
    destination_url: draft.destinationUrl, message: draft.message,
    headline: draft.headline, description: draft.description,
    daily_budget_minor: reaisParaMinor(draft.budgetBrl),
    start_time: new Date(draft.startTime).toISOString(),
    special_ad_categories: [],
    special_categories_confirmed: draft.categoryConfirmed,
    call_to_action_type: draft.cta,
  };
}

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
          assetRef: resultado.imagens.some((item) => item.referencia_opaca === atual.assetRef) ? atual.assetRef : (resultado.imagens[0]?.referencia_opaca || ''),
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
  const navegar = (proxima: Etapa) => {
    const novos = new URLSearchParams(params);
    novos.set('etapa', proxima); novos.delete('modo'); setParams(novos);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const conta = contas.find((item) => item.referencia_opaca === draft.accountRef);
  const pagina = paginas.find((item) => item.referencia_opaca === draft.pageRef);
  const imagem = imagens.find((item) => item.referencia_opaca === draft.assetRef);
  const prontoLocal = useMemo(() => Boolean(
    draft.accountRef && draft.pageRef && draft.assetRef && draft.campaignName.trim()
    && draft.adsetName.trim() && draft.adName.trim() && draft.destinationUrl.startsWith('https://')
    && draft.message.trim() && draft.headline.trim() && reaisParaMinor(draft.budgetBrl) > 0
    && draft.startTime && draft.categoryConfirmed
  ), [draft]);

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
      case 'criativo': return <Grupo titulo="Monte o anúncio estático" ajuda="A imagem precisa existir na conta; o hash real permanece no backend.">
        <Campo id="meta-ad-name" rotulo="Nome do anúncio"><Input id="meta-ad-name" value={draft.adName} onChange={(e) => mudar('adName', e.target.value)} /></Campo>
        <Campo id="meta-creative-name" rotulo="Nome do criativo"><Input id="meta-creative-name" value={draft.creativeName} onChange={(e) => mudar('creativeName', e.target.value)} /></Campo>
        <Campo id="meta-primary" rotulo="Texto principal" largo><Textarea id="meta-primary" rows={4} value={draft.message} onChange={(e) => mudar('message', e.target.value)} /></Campo>
        <Campo id="meta-headline" rotulo="Título"><Input id="meta-headline" value={draft.headline} onChange={(e) => mudar('headline', e.target.value)} /></Campo>
        <Campo id="meta-description" rotulo="Descrição"><Input id="meta-description" value={draft.description} onChange={(e) => mudar('description', e.target.value)} /></Campo>
        <Campo id="meta-cta" rotulo="Chamada para ação"><select id="meta-cta" className={campo} value={draft.cta} onChange={(e) => mudar('cta', e.target.value)}><option value="LEARN_MORE">Saiba mais</option><option value="APPLY_NOW">Inscreva-se</option><option value="SIGN_UP">Cadastre-se</option><option value="GET_QUOTE">Solicitar cotação</option><option value="CONTACT_US">Fale conosco</option></select></Campo>
        <Campo id="meta-media" rotulo="Imagem da conta"><select id="meta-media" className={campo} value={draft.assetRef} onChange={(e) => mudar('assetRef', e.target.value)} disabled={!draft.accountRef || ocupado === 'assets'}><option value="">Selecione uma imagem existente</option>{imagens.map((item) => <option key={item.referencia_opaca} value={item.referencia_opaca}>{item.nome}{item.largura && item.altura ? ` · ${item.largura}×${item.altura}` : ''}</option>)}</select></Campo>
        <Fixo rotulo="Peça escolhida" valor={imagem?.nome || 'Ainda não escolhida'} detalhe="O hash real permanece somente no backend." />
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
            <Resumo rotulo="Receita" valor="Tráfego · Website · LPV · imagem estática" /><Resumo rotulo="Orçamento" valor={`R$ ${draft.budgetBrl}/dia · conjunto`} />
            <Resumo rotulo="Estrutura" valor="1 campanha · 1 conjunto · 1 criativo · 1 anúncio" /><Resumo rotulo="Estado ao nascer" valor="PAUSADA em todos os níveis veiculáveis" />
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
    <div className="grid gap-5 lg:grid-cols-[260px_minmax(0,1fr)]"><nav aria-label="Etapas da criação Meta" className="h-fit rounded-xl border border-border bg-card p-2 shadow-card lg:sticky lg:top-4">{ETAPAS.map((item, posicao) => { const Icone = item.icone; const atual = item.id === etapa; const passou = posicao < indice; return <button key={item.id} type="button" onClick={() => navegar(item.id)} aria-current={atual ? 'step' : undefined} className={cn('flex min-h-13 w-full items-center gap-3 rounded-lg px-3 text-left transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring', atual ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:bg-muted hover:text-foreground')}><span className={cn('flex h-8 w-8 shrink-0 items-center justify-center rounded-full border text-xs', atual ? 'border-primary-foreground/35' : passou ? 'border-success/30 bg-success/10 text-success' : 'border-border')}>{passou ? <Check className="h-4 w-4" /> : <Icone className="h-4 w-4" />}</span><span className="min-w-0"><strong className="block truncate text-sm font-semibold">{item.nome}</strong><span className={cn('block truncate text-[11px]', atual ? 'text-primary-foreground/70' : 'text-muted-foreground')}>{item.resumo}</span></span></button>; })}</nav>
      <form className="rounded-xl border border-border bg-card p-5 shadow-card md:p-7" onSubmit={(evento) => evento.preventDefault()}>{conteudo}<div className="mt-7 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-5"><Button type="button" variant="outline" disabled={indice === 0} onClick={() => navegar(ETAPAS[indice - 1].id)}><ArrowLeft className="mr-2 h-4 w-4" /> Voltar</Button>{indice < ETAPAS.length - 1 && <Button type="button" onClick={() => navegar(ETAPAS[indice + 1].id)}>Continuar <ArrowRight className="ml-2 h-4 w-4" /></Button>}</div></form></div>
  </main></Layout>;
};

export default MetaCriacaoPage;
