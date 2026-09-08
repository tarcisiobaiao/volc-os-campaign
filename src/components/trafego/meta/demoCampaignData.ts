/** Pure, scoped demo adapter. No transport, credentials, storage or production fallback. */
import type { ConjuntoFinanceiroMeta, ItemMetaReadModel, RazaoDaSomaMeta } from '@/lib/pautadorApi';
import type { MetaCampaignDataApi } from './MetaCampaignData';
import { META_DEMO, META_INSIGHTS_DEMO } from './modelo';

export const CONTA_DEMO_META = 'metaacct_demo_campaign';
const CARIMBO = '2026-09-04T18:00:00Z';
const FUSO = 'America/Sao_Paulo';
const status = (s: string) => s === 'ATIVO' ? 'ACTIVE' : s === 'PAUSADO' ? 'PAUSED' : 'DRAFT';
const razao = (n: number, dias: number): RazaoDaSomaMeta => ({
  conjuntos: n, dias, conjuntos_atribuidos: dias ? n : 0, linhas: n * dias,
  linhas_atribuidas: n * dias, linhas_sem_utm: 0, linhas_sem_leitura_gam: 0,
  linhas_sem_entrega: 0, spend_completo: dias > 0, revenue_completo: dias > 0,
});

export function criarDadosDemoCampanha(id: string): MetaCampaignDataApi | null {
  const origem = META_DEMO.campanhas.find(c => c.id === id);
  const leitura = META_INSIGHTS_DEMO[id];
  if (!origem || !leitura) return null;
  let propostaNumero = 0;
  const campanha: ItemMetaReadModel = {
    entity_ref: id, meta_campaign_id: id, nome: origem.nome,
    status: status(origem.status), effective_status: status(origem.status),
    id_mascarado: 'DEMO · campanha', objetivo: 'OUTCOME_TRAFFIC',
    daily_budget: 12000, lifetime_budget: null, bid_strategy: 'LOWEST_COST_WITHOUT_CAP',
    bid_amount: null, observado_em: CARIMBO,
  };
  const conjuntos: ItemMetaReadModel[] = META_DEMO.conjuntos.filter(c => c.paiId === id).map(c => ({
    entity_ref: c.id, meta_adset_id: c.id, meta_campaign_id: id,
    nome: c.nome, status: status(c.status), effective_status: status(c.status),
    id_mascarado: `DEMO · ${c.nome}`, optimization_goal: 'LANDING_PAGE_VIEWS',
    // This example is CBO: no fictitious simultaneous adset budget.
    daily_budget: null, lifetime_budget: null, bid_strategy: 'LOWEST_COST_WITHOUT_CAP',
    bid_amount: null, observado_em: CARIMBO,
  }));
  const anuncios: ItemMetaReadModel[] = conjuntos.flatMap(c => {
    const conhecidos = META_DEMO.anuncios.filter(a => a.paiId === c.entity_ref);
    const exemplos = conhecidos.length ? conhecidos : [
      { id: `${c.entity_ref}-ad-a`, nome: 'Certificação · passo a passo', status: 'ATIVO' },
      { id: `${c.entity_ref}-ad-b`, nome: 'Voltar a estudar · imagem B', status: 'PAUSADO' },
    ];
    return exemplos.map(a => ({ entity_ref: a.id, meta_ad_id: a.id, meta_adset_id: c.meta_adset_id,
      nome: a.nome, status: status(a.status), effective_status: status(a.status),
      id_mascarado: 'DEMO · anúncio', observado_em: CARIMBO }));
  });
  const criativos: ItemMetaReadModel[] = anuncios.map(a => ({
    meta_creative_id: `demo-creative-${a.entity_ref}`, entity_ref: `demo-creative-${a.entity_ref}`,
    nome: `Peça demonstrativa · ${a.nome}`, object_story_id: null, observado_em: CARIMBO,
  }));
  const vinculos = anuncios.map((a, i) => ({ meta_ad_id: a.meta_ad_id, meta_creative_id: criativos[i].meta_creative_id }));
  const linhas = leitura.serie.map(d => {
    const [dia, mes] = d.data.split('/');
    return { ...d, iso: `2026-${mes}-${dia}` };
  });
  function conferir(ref: string, conta?: string | null) {
    if (ref !== id || conta !== CONTA_DEMO_META) throw new Error('Escopo fora deste exemplo. Nenhuma API real foi consultada.');
  }
  const inventario: Record<string, ItemMetaReadModel[]> = {
    campanhas: [campanha], conjuntos, anuncios, criativos, vinculos,
    insights: linhas.map(d => ({ nivel: 'campaign', periodo_inicio: d.iso, periodo_fim: d.iso,
      currency: 'BRL', spend: d.gasto, impressions: d.impressoes, reach: d.alcance,
      inline_link_clicks: d.cliquesNoLink, landing_page_views: d.visualizacoesDaPagina,
      ctr: d.cliquesNoLink / d.impressoes * 100 })),
  };
  return {
    async contasMetaReadModel() { return { ok: true, has_snapshot: true, estado: 'COM_SNAPSHOT', contas: [{
      conta_ref: CONTA_DEMO_META, cofre_ativo_id: CONTA_DEMO_META,
      nome_observado: 'Conta demonstrativa · não conectada', id_mascarado: 'DEMO',
      moeda: 'BRL', timezone_name: FUSO, account_status: '1',
      observado_em: CARIMBO, ultima_leitura_ok_em: CARIMBO,
    }] }; },
    async inventarioMetaReadModel(entidade, opcoes) {
      conferir(id, typeof opcoes === 'string' ? opcoes : opcoes?.contaRef);
      const items = inventario[entidade] ?? [];
      return { ok: true, estado: 'COM_SNAPSHOT', has_snapshot: true, entidade,
        conta_ref: CONTA_DEMO_META, moeda: 'BRL', fuso: FUSO, frescor: CARIMBO,
        items, completo: true, has_more: false, proximo_cursor: null, motivo: null };
    },
    async detalheMetaReadModel(entidade, ref, conta) {
      conferir(id, conta);
      const item = (inventario[entidade] ?? []).find(x => x.entity_ref === ref) ?? null;
      return { ok: true, has_snapshot: !!item, estado: item ? 'COM_SNAPSHOT' : 'SEM_SNAPSHOT', entidade, item, conta_ref: CONTA_DEMO_META };
    },
    async financeiroMeta(ref, conta, inicio, fim) {
      conferir(ref, conta);
      const de = inicio || '2026-08-29', ate = fim || '2026-09-04';
      const dias = linhas.filter(d => d.iso >= de && d.iso <= ate);
      // Partition INTEGER cents per day: children add back to the same total exactly.
      const parcela = (total: number, i: number) => {
        const primeiros = Math.floor(total / conjuntos.length);
        return i === conjuntos.length - 1 ? total - primeiros * i : primeiros;
      };
      const filhos: ConjuntoFinanceiroMeta[] = conjuntos.map((c, i) => {
        const spend = dias.length ? dias.reduce((s,d) => s + parcela(Math.round(d.gasto*100),i),0)/100 : null;
        const revenue = dias.length ? dias.reduce((s,d) => s + parcela(Math.round(d.receitaGam*100),i),0)/100 : null;
        const impressions = dias.length ? dias.reduce((s,d) => s + parcela(d.impressoes,i),0) : null;
        const clicks = dias.length ? dias.reduce((s,d) => s + parcela(d.cliquesNoLink,i),0) : null;
        const profit = spend !== null && revenue !== null ? Math.round((revenue-spend)*100)/100 : null;
        return { adset_ref: String(c.entity_ref), id_mascarado: String(c.nome), spend,
          revenue_brl: revenue, revenue_original: revenue, impressions, clicks,
          gam_impressions: null, gam_clicks: null, reach: null,
          ctr: impressions && clicks !== null ? clicks/impressions*100 : null,
          cpc: clicks && spend !== null ? spend/clicks : null,
          roas_ratio: spend && revenue !== null ? revenue/spend : null,
          profit_gross: profit, retorno_excedente_pct: spend && profit !== null ? profit/spend*100 : null,
          currency: 'BRL', timezone: FUSO, source: 'DEMO', source_freshness: CARIMBO,
          revenue_freshness: CARIMBO, razao: razao(1,dias.length) };
      });
      const total = (campo: 'spend'|'revenue_brl'|'impressions'|'clicks') =>
        dias.length && filhos.length ? filhos.reduce((s,c) => s + Number(c[campo]),0) : null;
      const spend = total('spend'), revenue = total('revenue_brl'), impressions = total('impressions'), clicks = total('clicks');
      const profit = spend !== null && revenue !== null ? Math.round((revenue-spend)*100)/100 : null;
      return { ok: true, estado: dias.length ? 'COM_SNAPSHOT' : 'SEM_SNAPSHOT', grao: 'adset',
        currency: 'BRL', timezone: FUSO, periodo_inicio: de, periodo_fim: ate,
        provisorio: false, frescor: CARIMBO, receita_frescor: CARIMBO,
        spend, revenue, profit_gross: profit, roas_ratio: spend && revenue !== null ? revenue/spend : null,
        retorno_excedente_pct: spend && profit !== null ? profit/spend*100 : null, impressions, clicks,
        ctr: impressions && clicks !== null ? clicks/impressions*100 : null,
        cpc: clicks && spend !== null ? spend/clicks : null,
        spend_completo: dias.length > 0, revenue_completo: dias.length > 0, conjuntos: filhos,
        razao: razao(filhos.length,dias.length), impedimentos: dias.length ? [] : ['DEMO_PERIODO_SEM_DADOS'],
      };
    },
    async planejarGestaoMeta(pedido) {
      conferir(pedido.campanha_ref, pedido.conta_ref);
      const alvo = pedido.entidade === 'campanha' ? campanha : (pedido.entidade === 'anuncio' ? anuncios : conjuntos).find(c => c.entity_ref === pedido.referencia);
      if (!alvo || alvo.entity_ref !== pedido.referencia) throw new Error('Objeto fora do exemplo.');
      if (pedido.acao === 'DUPLICAR_CONJUNTO' && (pedido.entidade !== 'conjunto' || !pedido.nome?.trim())) throw new Error('Escolha um conjunto e o nome da cópia.');
      if (pedido.valor_minor !== undefined && (!Number.isSafeInteger(pedido.valor_minor) || pedido.valor_minor <= 0)) throw new Error('Valor inválido.');
      const antes = Object.fromEntries(['status','daily_budget','lifetime_budget','bid_strategy','bid_amount'].map(k=>[k,alvo[k] ?? null]));
      const depois = pedido.acao === 'PAUSAR' ? { status: 'PAUSED' }
        : pedido.acao === 'ORCAMENTO_DIARIO' ? { daily_budget_minor: pedido.valor_minor, moeda_proposta: 'BRL' }
        : pedido.acao === 'LANCE' ? { bid_strategy: pedido.estrategia, bid_amount_minor: pedido.valor_minor ?? null, ...(pedido.valor_minor ? {moeda_proposta:'BRL'} : {}) }
        : { nome: pedido.nome, status: 'PAUSED', incluir_anuncios: true };
      return { estado: 'PROPOSTA_LOCAL_NAO_EXECUTAVEL', demonstracao: true, efeito_externo: 'NENHUM', executavel: false, persistida: false,
        plano_sha256: `DEMO-NAO-EXECUTAVEL-${++propostaNumero}`, nome: String(alvo.nome), observado_em: CARIMBO,
        antes, depois, efeito_proposto: 'Simulação da alteração escolhida. Nenhum objeto foi alterado ou criado.',
        requisitos_para_executar: ['Estes dados são fictícios e não autorizam execução.', 'Na operação real: confirmar ABO/CBO, moeda, elegibilidade, aprovação e recibo antes do despacho.'],
        receita: 'A receita permanece no conjunto original. Uma cópia teria novo ID, tracking próprio e nenhum histórico transferido.' };
    },
  };
}
