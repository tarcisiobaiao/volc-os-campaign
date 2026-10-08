/**
 * Formulário → pedido, nos quatro canais, contra o contrato GADS-CRIACAO-CANAIS-v1.
 *
 * ## O que este arquivo prova
 *
 * 1. **O fim do bug CPA → `cpc_inicial`.** Sob Maximizar conversões o número
 *    digitado no campo "CPA alvo" ia para `cpc_inicial`. Agora vai para
 *    `configuracao_search.lance.target_cpa`, e `cpc_inicial` só existe em CPC
 *    manual.
 * 2. **`match_por_keyword` chega ao pedido**, com a chave normalizada, só para
 *    keyword aprovada e só quando a escolha difere da aprovada.
 * 3. **Cada canal monta a forma dos payloads de exemplo do contrato (§8)** — a
 *    mesma que a prova viva aceitou em validate_only em 08/10/2026.
 * 4. **A forma passa no esquema que o servidor publica.** O fixture
 *    `esquema-canais.fixture.json` é a saída LITERAL de
 *    `backend/app/trafego/configuracao_canais.esquemas()` (o que
 *    `GET /api/trafego/canais/esquema` devolve, sem o envelope de asset).
 *    Regerar: `PYTHONPATH=.:backend backend/.venv/bin/python -c "import json;
 *    from app.trafego import configuracao_canais as c;
 *    print(json.dumps(c.esquemas(), ensure_ascii=False, indent=1))" >
 *    src/lib/trafego/configuracao/__tests__/esquema-canais.fixture.json`.
 */
import { describe, expect, it } from 'vitest';

import esquemaFixture from './esquema-canais.fixture.json';
import {
  FORM_DEMAND_GEN_VAZIO, FORM_DISPLAY_VAZIO, FORM_PMAX_VAZIO, FORM_SEARCH_VAZIO, novoGrupoPMax,
  mesclarFormulario,
} from '../formularios';
import type { FormDemandGen, FormDisplay, FormPMax, FormSearch } from '../formularios';
import {
  configuracaoDemandGen, configuracaoDisplay, configuracaoPMax, configuracaoSearch,
  faltasDeDemandGen, faltasDeSearch, matchPorKeywordDoPedido, montarPedidoDemandGen,
  montarPedidoDisplay, montarPedidoPMax, montarPedidoSearch, type BaseDoPedido,
} from '../montagem';
import { conferirForma, esquemaDoCanal, motivoIndisponivelPorHttp, opcoesDoEsquema, defaultDoEsquema } from '../esquema';
import {
  avisosPrevistosDeDisplay, avisosPrevistosDePMax, avisosPrevistosDeSearch,
} from '../revisao';
import type { AssetDemandGen, RevisaoDoConjuntoPago } from '@/types/trafego';
import type { EsquemaDosCanais } from '@/types/trafegoCanais';

const ESQUEMAS = esquemaFixture as unknown as EsquemaDosCanais;

const BASE: BaseDoPedido = {
  opportunity_id: 990001,
  run_id: null,
  customer_id: '5478096539',
  login_customer_id: '6016739364',
  budget_diario: 20,
  vertical: 'informativo',
  certificacoes: [],
  url_final: 'https://creditoup.com.br/r/guia-cursos-senac/',
};

const CONJUNTO = {
  selecionadas: [
    { termo: 'cursos senac 2026', match_type: 'PHRASE' },
    { termo: 'Cursos   Gratuitos Senac', match_type: 'PHRASE' },
    { termo: 'senac inscrição', match_type: 'EXACT' },
  ],
} as unknown as RevisaoDoConjuntoPago;

const asset = (tipo: AssetDemandGen['tipo'], nome: string): AssetDemandGen => ({
  tipo, nome, dados_base64: 'aW1n', conteudo_hash: `sha256:${'a'.repeat(64)}`, origem: 'humano',
  procedencia: { motor: 'humano', versao_do_motor: '1', insumo: nome, quando: '2026-10-08T00:00:00Z', pedido: '', custo_usd: null },
});

const semErrosDeForma = (valor: unknown, canal: keyof EsquemaDosCanais['canais'], campo: string) =>
  conferirForma(valor, esquemaDoCanal(ESQUEMAS, canal), campo)
    // Envelopes de asset: julgados pela ponte criativa no servidor (ver a página).
    .filter((e) => !/\.imagens(\[|$)/.test(e.caminho));

// ═══════════════════════════════════════════════════════════════════════════
// Search
// ═══════════════════════════════════════════════════════════════════════════

/** O formulário que reproduz `configuracao_search` do §8.1 do contrato. */
const FORM_SEARCH_8_1: FormSearch = {
  ...FORM_SEARCH_VAZIO,
  lance: { ...FORM_SEARCH_VAZIO.lance, tcpa: '4,5' },
  parceiros: false,
  expansaoDisplay: false,
  aiMax: true,
  aiCorrespondencia: true,
  aiPersonalizacao: true,
  aiExpansaoUrl: true,
  aiExclusoesDeUrl: '/blog/\n/contato',
  aiTermosExcluidos: 'gratis garantido',
  aiRestricoes: 'Não prometer vaga ou aprovação.',
  path1: 'cursos',
  path2: 'senac',
  fixacoes: [{ texto: 'Cursos Gratuitos do Senac', posicao: 'HEADLINE_1' }],
  programacao: ['MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY'].map((dia) => ({
    dia: dia as 'MONDAY', inicio: '07:00', fim: '23:00', ajuste: '',
  })),
  dispositivos: [{ dispositivo: 'TABLET', fator: '0' }],
  geo: true,
  geoPositivo: 'PRESENCE',
  geoNegativo: 'PRESENCE',
  geoIdiomas: 'pt\nen',
  inicio: '2026-10-20',
  fim: '2026-12-31',
  metaModo: 'acoes',
  metaAcoes: 'customers/5478096539/conversionActions/7467141090',
  metaCategorias: [{ categoria: 'PURCHASE', origem: 'WEBSITE', lance: false }],
};

/** `configuracao_search` literal do §8.1. */
const CONFIGURACAO_SEARCH_8_1 = {
  lance: { estrategia: 'MAXIMIZE_CONVERSIONS', target_cpa: 4.5 },
  rede: { google_search: true, parceiros: false, display_expansion: false },
  ai_max: {
    correspondencia_de_termos: true, personalizacao_de_texto: true, expansao_de_url_final: true,
    exclusoes_de_url: ['/blog/', '/contato'], termos_excluidos: ['gratis garantido'],
    restricoes_de_mensagem: ['Não prometer vaga ou aprovação.'],
  },
  anuncio: { path1: 'cursos', path2: 'senac', fixacoes: [{ texto: 'Cursos Gratuitos do Senac', posicao: 'HEADLINE_1' }] },
  programacao: ['MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY'].map((dia) => ({ dia, inicio: '07:00', fim: '23:00' })),
  dispositivos: [{ dispositivo: 'TABLET', fator: 0 }],
  geo: { tipo_positivo: 'PRESENCE', tipo_negativo: 'PRESENCE', idiomas: ['pt', 'en'] },
  inicio: '2026-10-20',
  fim: '2026-12-31',
  meta_de_conversao: {
    acoes_de_conversao: ['customers/5478096539/conversionActions/7467141090'],
    categorias: [{ categoria: 'PURCHASE', origem: 'WEBSITE', lance: false }],
  },
};

const pedidoSearch = (over: Partial<Parameters<typeof montarPedidoSearch>[0]> = {}) => montarPedidoSearch({
  base: BASE, copy: null, negativas: [], keywordsFora: [], estrategia: 'MAXIMIZE_CONVERSIONS',
  cpcManual: 0.2, graduacao: 30, metaConversaoId: null, form: FORM_SEARCH_8_1,
  matchEscolhido: {}, conjunto: CONJUNTO, ...over,
});

describe('Search — o fim do bug "CPA alvo" mandado como cpc_inicial', () => {
  it('sob Maximizar conversões, o CPA alvo vai para lance.target_cpa e cpc_inicial NÃO viaja', () => {
    const p = pedidoSearch({ cpcManual: 4.5 });
    expect(p.configuracao_search?.lance).toEqual({ estrategia: 'MAXIMIZE_CONVERSIONS', target_cpa: 4.5 });
    expect('cpc_inicial' in p).toBe(false);
    // As duas estratégias IGUAIS: com configuração, o motor recusa divergência.
    expect(p.estrategia_lance).toBe('MAXIMIZE_CONVERSIONS');
    expect(p.graduacao_em_conversoes).toBe(0);
  });

  it('em CPC manual o lance digitado É o cpc_inicial, e o lance da configuração não tem meta', () => {
    const p = pedidoSearch({ estrategia: 'MANUAL_CPC', cpcManual: 0.38 });
    expect(p.cpc_inicial).toBe(0.38);
    expect(p.configuracao_search?.lance).toEqual({ estrategia: 'MANUAL_CPC' });
    expect(p.graduacao_em_conversoes).toBe(30);
  });

  it('cada uma das cinco estratégias leva só os campos dela', () => {
    const lance = { tcpa: '9', troasPct: '400', tetoCpc: '0,35', local: 'TOP_OF_PAGE' as const, fracaoPct: '60' };
    const form = { ...FORM_SEARCH_8_1, lance };
    const de = (e: Parameters<typeof configuracaoSearch>[1]) => configuracaoSearch(form, e).lance;
    expect(de('MANUAL_CPC')).toEqual({ estrategia: 'MANUAL_CPC' });
    expect(de('TARGET_SPEND')).toEqual({ estrategia: 'TARGET_SPEND', teto_cpc: 0.35 });
    expect(de('MAXIMIZE_CONVERSIONS')).toEqual({ estrategia: 'MAXIMIZE_CONVERSIONS', target_cpa: 9 });
    expect(de('MAXIMIZE_CONVERSION_VALUE')).toEqual({ estrategia: 'MAXIMIZE_CONVERSION_VALUE', target_roas: 4 });
    expect(de('TARGET_IMPRESSION_SHARE')).toEqual({
      estrategia: 'TARGET_IMPRESSION_SHARE', local_impressao: 'TOP_OF_PAGE', fracao_impressao: 0.6, teto_cpc: 0.35,
    });
  });

  it('parcela de impressões sem local, fração e teto é falta — não um zero inventado', () => {
    const f = faltasDeSearch(FORM_SEARCH_VAZIO, 'TARGET_IMPRESSION_SHARE', {}, CONJUNTO);
    expect(f.economia).toEqual([
      'escolher onde a impressão deve aparecer',
      'declarar a parcela de impressões',
      'declarar o teto de CPC',
    ]);
    expect(configuracaoSearch(FORM_SEARCH_VAZIO, 'TARGET_IMPRESSION_SHARE').lance)
      .toEqual({ estrategia: 'TARGET_IMPRESSION_SHARE' });
  });
});

describe('Search — a configuração do contrato §8.1', () => {
  it('monta exatamente o `configuracao_search` do exemplo da prova viva', () => {
    expect(pedidoSearch().configuracao_search).toEqual(CONFIGURACAO_SEARCH_8_1);
  });

  it('a forma montada passa no esquema que o servidor publica', () => {
    expect(semErrosDeForma(pedidoSearch().configuracao_search, 'SEARCH', 'configuracao_search')).toEqual([]);
  });

  it('a rede vai nos dois lugares, iguais; sem decisão, não vai e vira falta', () => {
    const p = pedidoSearch();
    expect(p.rede).toEqual({ google_search: true, search_partners: false, display_expansion: false });
    const sem = pedidoSearch({ form: { ...FORM_SEARCH_8_1, parceiros: null } });
    expect(sem.rede).toBeUndefined();
    expect(sem.configuracao_search?.rede).toBeUndefined();
    expect(faltasDeSearch({ ...FORM_SEARCH_8_1, parceiros: null }, 'MANUAL_CPC', {}, CONJUNTO).alcance)
      .toContain('decidir sobre os parceiros de pesquisa');
  });

  it('expansão para Display ligada gera o aviso previsto pelo contrato', () => {
    const c = configuracaoSearch({ ...FORM_SEARCH_8_1, expansaoDisplay: true }, 'MANUAL_CPC');
    expect(avisosPrevistosDeSearch(c, {}).map((a) => a.codigo)).toContain('display_expansion');
  });

  it('AI Max ligado sem as três decisões não as inventa como false', () => {
    const c = configuracaoSearch({ ...FORM_SEARCH_VAZIO, aiMax: true, aiCorrespondencia: true }, 'MANUAL_CPC');
    expect(c.ai_max).toEqual({ correspondencia_de_termos: true });
    const erros = conferirForma(c, esquemaDoCanal(ESQUEMAS, 'SEARCH'), 'configuracao_search');
    expect(erros.map((e) => e.caminho)).toEqual([
      'configuracao_search.ai_max.personalizacao_de_texto',
      'configuracao_search.ai_max.expansao_de_url_final',
    ]);
  });

  it('o esquema acusa o caminho exato de um campo fora do limite', () => {
    const c = configuracaoSearch({ ...FORM_SEARCH_VAZIO, path1: 'caminho-longo-demais' }, 'MANUAL_CPC');
    const erros = conferirForma(c, esquemaDoCanal(ESQUEMAS, 'SEARCH'), 'configuracao_search');
    expect(erros).toEqual([{ caminho: 'configuracao_search.anuncio.path1', mensagem: 'máximo de 15 caracteres', codigo: 'ESQUEMA' }]);
  });
});

describe('Search — match_por_keyword chega ao pedido', () => {
  it('leva a escolha do operador, chaveada pelo texto normalizado', () => {
    const p = pedidoSearch({
      matchEscolhido: { 'cursos senac 2026': 'EXACT', 'cursos gratuitos senac': 'BROAD' },
    });
    expect(p.match_por_keyword).toEqual({ 'cursos senac 2026': 'EXACT', 'cursos gratuitos senac': 'BROAD' });
    expect(avisosPrevistosDeSearch(p.configuracao_search!, p.match_por_keyword!).map((a) => a.codigo))
      .toContain('MATCH_TYPE_ESCOLHIDO_NA_TELA');
  });

  it('escolha igual à aprovada não é troca; keyword fora do conjunto não viaja', () => {
    expect(matchPorKeywordDoPedido({ 'senac inscrição': 'EXACT', 'curso fantasma': 'BROAD' }, CONJUNTO)).toEqual({});
    expect('match_por_keyword' in pedidoSearch({ matchEscolhido: { 'senac inscrição': 'EXACT' } })).toBe(false);
  });

  it('ampla sob lance que não é por conversão vira falta na parada Termos', () => {
    const f = faltasDeSearch(FORM_SEARCH_8_1, 'MANUAL_CPC', { 'cursos senac 2026': 'BROAD' }, CONJUNTO);
    expect(f.termos?.[0]).toMatch(/ampla só com lance por conversão/);
    expect(faltasDeSearch(FORM_SEARCH_8_1, 'MAXIMIZE_CONVERSIONS', { 'cursos senac 2026': 'BROAD' }, CONJUNTO).termos)
      .toBeUndefined();
  });
});

// ═══════════════════════════════════════════════════════════════════════════
// Display
// ═══════════════════════════════════════════════════════════════════════════

const FORM_DISPLAY_8_2: FormDisplay = {
  ...FORM_DISPLAY_VAZIO,
  estrategia: 'TARGET_SPEND',
  tetoCpc: '0,35',
  segListasDeUsuarios: '9304580046',
  segInteresses: '92000\n80226',
  segTopicos: '369',
  segPlacements: 'g1.globo.com/educacao',
  segPalavrasChave: 'cursos senac\ncurso tecnico',
  segObservacao: true,
  excPlacements: 'site-ruim.com',
  excApps: '2-com.exemplo.jogo',
  excTopicos: '1493',
  listaNovaNome: 'Exclusoes Display prova',
  listaNovaPlacements: 'outro-ruim.com',
  listaNovaApps: '1-123456789',
  frequencia: [
    { impressoes: '3', unidade: 'DAY', nivel: 'AD_GROUP_AD' },
    { impressoes: '10', unidade: 'WEEK', nivel: 'CAMPAIGN' },
  ],
  agenda: [
    { dia: 'MONDAY', inicio: '06:00', fim: '24:00', ajuste: '' },
    { dia: 'TUESDAY', inicio: '06:15', fim: '12:30', ajuste: '' },
  ],
  dispositivosExcluidos: ['TABLET'],
  rdaCta: 'Saiba mais',
  rdaCorPrincipal: '#0A3D91',
  rdaCorDestaque: '#F2A900',
  rdaCoresFlexiveis: false,
};

const pedidoDisplay = (form: FormDisplay = FORM_DISPLAY_8_2) => montarPedidoDisplay({
  base: BASE,
  copy: { headlines: ['Cursos do Senac'], descriptions: ['Veja áreas.'], long_headlines: ['Guia'], business_name: 'Credito Up', sitelinks: [], callouts: [] },
  assets: [asset('imagem_marketing', 'disp_paisagem')],
  form,
  videosYoutube: 'jNQXAC9IVRw',
});

describe('Display — a configuração do contrato §8.2', () => {
  it('monta lance, segmentação, exclusões, frequência, agenda e RDA do exemplo', () => {
    const p = pedidoDisplay();
    expect(p.estrategia_lance).toBe('TARGET_SPEND');
    expect(p.configuracao_display).toMatchObject({
      lance: { estrategia: 'TARGET_SPEND', teto_cpc: 0.35 },
      segmentacao: {
        listas_de_usuarios: ['9304580046'], interesses: ['92000', '80226'], topicos: ['369'],
        placements: ['g1.globo.com/educacao'], palavras_chave: ['cursos senac', 'curso tecnico'],
        publicos_em_observacao: true, segmentacao_otimizada: false,
      },
      exclusoes: {
        placements: ['site-ruim.com'], apps: ['2-com.exemplo.jogo'], topicos: ['1493'],
        lista_nova: { nome: 'Exclusoes Display prova', placements: ['outro-ruim.com'], apps: ['1-123456789'] },
      },
      frequencia: [
        { impressoes: 3, unidade: 'DAY', nivel: 'AD_GROUP_AD' },
        { impressoes: 10, unidade: 'WEEK', nivel: 'CAMPAIGN' },
      ],
      agenda: [
        { dia: 'MONDAY', inicio_hora: 6, fim_hora: 24 },
        { dia: 'TUESDAY', inicio_hora: 6, fim_hora: 12, inicio_minuto: 15, fim_minuto: 30 },
      ],
      dispositivos_excluidos: ['TABLET'],
      presenca_geo: 'PRESENCE',
      anuncio: {
        chamada_para_acao: 'Saiba mais', cor_principal: '#0A3D91', cor_destaque: '#F2A900',
        cores_flexiveis: false, videos_youtube: ['jNQXAC9IVRw'],
      },
    });
    expect(semErrosDeForma(p.configuracao_display, 'DISPLAY', 'configuracao_display')).toEqual([]);
  });

  it('as exclusões de nascimento vão marcadas — e são as que o esquema declara como default', () => {
    const p = pedidoDisplay(FORM_DISPLAY_VAZIO);
    const padrao = defaultDoEsquema(esquemaDoCanal(ESQUEMAS, 'DISPLAY'), 'exclusoes.rotulos_de_conteudo');
    expect(p.configuracao_display?.exclusoes?.excluir_todos_os_apps).toBe(true);
    expect(p.configuracao_display?.exclusoes?.rotulos_de_conteudo).toEqual(padrao);
  });

  it('cpc_inicial só viaja em CPC manual; CPM manual leva o vCPM na configuração', () => {
    expect('cpc_inicial' in pedidoDisplay()).toBe(false);
    const manual = pedidoDisplay({ ...FORM_DISPLAY_8_2, estrategia: 'MANUAL_CPC', cpcManual: '0,25' });
    expect(manual.cpc_inicial).toBe(0.25);
    expect(manual.estrategia_lance).toBe('MANUAL_CPC');
    const cpm = pedidoDisplay({ ...FORM_DISPLAY_8_2, estrategia: 'MANUAL_CPM', cpm: '2' });
    expect(cpm.configuracao_display?.lance).toEqual({ estrategia: 'MANUAL_CPM', cpm_visivel: 2 });
    expect('cpc_inicial' in cpm).toBe(false);
  });

  it('tCPA e tROAS vão no envelope, só na estratégia deles', () => {
    const tcpa = pedidoDisplay({ ...FORM_DISPLAY_8_2, estrategia: 'MAXIMIZE_CONVERSIONS', tcpa: '3', troasPct: '400' });
    expect(tcpa.tcpa).toBe(3);
    expect('target_roas' in tcpa).toBe(false);
    const roas = pedidoDisplay({ ...FORM_DISPLAY_8_2, estrategia: 'MAXIMIZE_CONVERSION_VALUE', tcpa: '3', troasPct: '400' });
    expect(roas.target_roas).toBe(4);
    expect('tcpa' in roas).toBe(false);
  });

  it('vídeo por id gera o aviso VIDEO_SEM_PORTAO_DE_POLITICA antes da prova', () => {
    const avisos = avisosPrevistosDeDisplay(pedidoDisplay().configuracao_display!);
    expect(avisos.map((a) => a.codigo)).toContain('VIDEO_SEM_PORTAO_DE_POLITICA');
  });
});

// ═══════════════════════════════════════════════════════════════════════════
// Demand Gen
// ═══════════════════════════════════════════════════════════════════════════

const FORM_DG_8_3: FormDemandGen = {
  ...FORM_DEMAND_GEN_VAZIO,
  formato: 'VIDEO_RESPONSIVO',
  estrategia: 'TARGET_CPC',
  tcpc: '0,6',
  videoIds: 'M7lc1UVf-VE\njNQXAC9IVRw',
  videoCta: 'LEARN_MORE',
  breadcrumb1: 'cursos',
  breadcrumb2: 'senac',
  titulosLongos: 'Guia completo de cursos Senac: modalidades e inscrições',
  publico: true,
  publicoNome: 'Publico Cursos Senac (prova integracao)',
  userLists: 'customers/5478096539/userLists/9305091609',
  lookalikes: [{ nome: 'LAL visitantes (prova integracao)', sementes: '9304580046', expansao: 'BALANCED', paises: 'BR' }],
  exclusoesUserList: 'customers/5478096539/userLists/9302797284',
  idades: ['18-24', '25-34', '35-44'],
  generos: ['FEMALE', 'MALE'],
  rendas: ['INCOME_RANGE_0_50', 'INCOME_RANGE_50_60'],
  parentais: ['NOT_A_PARENT', 'PARENT'],
  segOtimizada: true,
  automacoes: { GENERATE_SHORTER_YOUTUBE_VIDEOS: true },
  agenda: ['MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY'].map((dia) => ({
    dia: dia as 'MONDAY', inicio: '08:00', fim: '22:30', ajuste: '',
  })),
};

describe('Demand Gen — vídeo responsivo do contrato §8.3', () => {
  const pedido = montarPedidoDemandGen({
    base: BASE,
    copy: { headlines: ['Guia de cursos Senac'], descriptions: ['Veja cursos.'], business_name: 'Credito Up', sitelinks: [], callouts: [], long_headlines: [] },
    demandGen: {
      upgraded_targeting: false,
      controles_de_canal: { estrategia: 'ALL_CHANNELS', selected_channels: null },
      audiencias: [], intencoes: [], exclusoes_de_audiencia: [],
    },
    assets: [asset('logo_quadrado', 'dg_logo'), asset('imagem_marketing', 'nao_vai')],
    form: FORM_DG_8_3,
  });

  it('o envelope diz a MESMA estratégia do lance (o servidor recusa divergência)', () => {
    expect(pedido.estrategia_lance).toBe('TARGET_CPC');
    expect(pedido.configuracao_demand_gen?.lance).toEqual({ estrategia: 'TARGET_CPC', target_cpc: 0.6 });
  });

  it('monta vídeo, público, automações e agenda do exemplo', () => {
    expect(pedido.configuracao_demand_gen).toMatchObject({
      formato: 'VIDEO_RESPONSIVO',
      video: { youtube_ids: ['M7lc1UVf-VE', 'jNQXAC9IVRw'], call_to_action: 'LEARN_MORE', breadcrumb1: 'cursos', breadcrumb2: 'senac' },
      publico: {
        nome: 'Publico Cursos Senac (prova integracao)',
        user_lists: ['customers/5478096539/userLists/9305091609'],
        lookalikes: [{ nome: 'LAL visitantes (prova integracao)', sementes: [9304580046], expansao: 'BALANCED', paises: ['BR'] }],
        exclusoes_user_list: ['customers/5478096539/userLists/9302797284'],
        idades: ['18-24', '25-34', '35-44'],
      },
      segmentacao_otimizada: true,
      agenda: expect.arrayContaining([{ dia: 'MONDAY', inicio: '08:00', fim: '22:30' }]),
    });
    // Só as automações DO FORMATO viajam, e as não marcadas vão OPTED_OUT, explícitas.
    expect(pedido.configuracao_demand_gen?.automacoes).toEqual({
      GENERATE_LANDING_PAGE_PREVIEW: 'OPTED_OUT',
      GENERATE_LANDING_PAGE_TEXT: 'OPTED_OUT',
      GENERATE_SHORTER_YOUTUBE_VIDEOS: 'OPTED_IN',
      GENERATE_VERTICAL_YOUTUBE_VIDEOS: 'OPTED_OUT',
    });
    expect(semErrosDeForma(pedido.configuracao_demand_gen, 'DEMAND_GEN', 'configuracao_demand_gen')).toEqual([]);
  });

  it('no vídeo, o kit é exatamente o logo quadrado e os títulos longos viajam na copy', () => {
    expect(pedido.assets_demand_gen.map((a) => a.tipo)).toEqual(['logo_quadrado']);
    expect(pedido.copy?.long_headlines).toEqual(['Guia completo de cursos Senac: modalidades e inscrições']);
  });

  it('carrossel aparece indisponível com o motivo do próprio esquema, e é falta', () => {
    const motivo = motivoIndisponivelPorHttp(esquemaDoCanal(ESQUEMAS, 'DEMAND_GEN'), 'carrossel');
    expect(motivo).toMatch(/fronteira HTTP ainda não transporta asset remoto aprovado/);
    expect(faltasDeDemandGen({ ...FORM_DG_8_3, formato: 'CARROSSEL' }, []).demand_kit?.[0])
      .toMatch(/carrossel não atravessa a fronteira HTTP/);
    expect(configuracaoDemandGen({ ...FORM_DG_8_3, formato: 'CARROSSEL' }).carrossel).toBeUndefined();
  });

  it('as opções de enum vêm do esquema vivo', () => {
    expect(opcoesDoEsquema(esquemaDoCanal(ESQUEMAS, 'DEMAND_GEN'), 'lance.estrategia', []))
      .toEqual(['MAXIMIZE_CONVERSIONS', 'MAXIMIZE_CONVERSION_VALUE', 'TARGET_SPEND', 'TARGET_CPC']);
  });
});

// ═══════════════════════════════════════════════════════════════════════════
// Performance Max
// ═══════════════════════════════════════════════════════════════════════════

describe('Performance Max — dois asset groups, como no §8.4', () => {
  const grupo = {
    ...novoGrupoPMax(),
    nome: 'Senac — Cursos livres',
    url: 'https://creditoup.com.br/r/guia-cursos-senac/?secao=livres',
    titulos: 'Cursos Livres do Senac\nÁreas e Modalidades\nComo se Inscrever',
    titulosLongos: 'Guia dos cursos livres do Senac com áreas, carga horária e inscrição',
    descricoes: 'Veja as áreas de cursos livres.\nEntenda modalidades, carga horária e o passo a passo para se inscrever.',
    sinaisConfirmados: true,
    temas: 'cursos livres senac',
    videos: 'jNQXAC9IVRw',
    path1: 'cursos',
    path2: 'livres',
    url_opcoes: { sufixo: 'vc_ag=livres\nvc_tema={_tema}', tracking: '{lpurl}?vc_tpl={_tema}', parametros: 'tema=livres' },
  };
  const form: FormPMax = {
    ...FORM_PMAX_VAZIO,
    path1: 'cursos',
    path2: 'senac',
    url_opcoes: { sufixo: 'vc_ag=geral', tracking: '', parametros: '' },
    videos: 'M7lc1UVf-VE',
    grupos: [grupo],
    automacoes: ['FINAL_URL_EXPANSION_TEXT_ASSET_AUTOMATION', 'TEXT_ASSET_AUTOMATION', 'AUTOMATED_VIDEO_CRAWL'],
    videoCrawl: [
      { url: 'https://creditoup.com.br/r/guia-cursos-senac/', plataforma: 'LANDING_PAGE', habilitada: true },
      { url: 'https://www.youtube.com/@senacbrasil', plataforma: 'YOUTUBE', habilitada: true },
    ],
    direitosDeclarados: true,
    exclusoesDeUrl: [{ nome: 'sem blog', argumento: '/blog/', operando: 'URL', operador: 'CONTAINS' }],
    termosExcluidos: 'gratis\ngarantido',
    restricoes: 'Não prometer vaga, bolsa ou aprovação.',
    corPrincipal: '#0B3D91',
    corDestaque: '#F2A900',
    fonte: 'Roboto',
    negativasTipadas: [{ texto: 'senac vagas emprego', match: 'PHRASE' }, { texto: 'senac login', match: 'EXACT' }],
    marcasExcluidas: [{ entity_id: '/g/11trqcwsy6', nome: 'Coursera' }],
    metas: [{ categoria: 'PURCHASE', origem: 'WEBSITE', lance: false }],
  };
  const imagem = asset('imagem_marketing', 'pm_paisagem_g2');
  const pedido = montarPedidoPMax({
    base: BASE,
    copy: { headlines: ['Cursos Senac 2026'], long_headlines: ['Guia'], descriptions: ['Conheça.'], business_name: 'Credito Up', sitelinks: [], callouts: [] },
    estrategia: 'MAXIMIZE_CONVERSIONS',
    meta: '3,5',
    brandGuidelines: true,
    audiencias: [],
    temas: ['cursos senac', 'senac cursos 2026'],
    negativas: ['download pirata'],
    nomeDoAssetGroup: 'Senac — Guia geral',
    assets: [],
    form,
    imagensDosGrupos: { [grupo.id]: [imagem] },
  });

  it('o envelope não carrega nenhum campo Search que o servidor proíbe em PMax', () => {
    for (const proibido of ['cpc_inicial', 'match_type', 'rede', 'keywords_fora']) {
      expect(proibido in pedido).toBe(false);
    }
    expect(pedido.tcpa).toBe(3.5);
    expect('videos_youtube' in pedido.pmax).toBe(false);
  });

  it('monta a configuração v25 do exemplo, com o grupo adicional completo', () => {
    expect(pedido.configuracao_pmax).toMatchObject({
      path1: 'cursos', path2: 'senac',
      opcoes_de_url: { sufixo_extra: [['vc_ag', 'geral']] },
      videos: [{ video_id: 'M7lc1UVf-VE' }],
      automacoes_optadas: ['FINAL_URL_EXPANSION_TEXT_ASSET_AUTOMATION', 'TEXT_ASSET_AUTOMATION', 'AUTOMATED_VIDEO_CRAWL'],
      video_crawl_direitos_declarados: true,
      exclusoes_de_url: [{ nome: 'sem blog', argumento: '/blog/' }],
      termos_excluidos: ['gratis', 'garantido'],
      diretrizes_de_marca: { cor_principal: '#0B3D91', cor_destaque: '#F2A900', fonte: 'Roboto' },
      negativas_tipadas: [{ texto: 'senac vagas emprego', match_type: 'PHRASE' }, { texto: 'senac login', match_type: 'EXACT' }],
      marcas_excluidas: [{ entity_id: '/g/11trqcwsy6', nome: 'Coursera' }],
      metas_de_conversao: [{ categoria: 'PURCHASE', origem: 'WEBSITE', biddable: false }],
    });
    expect(pedido.configuracao_pmax?.grupos_adicionais?.[0]).toEqual({
      nome: 'Senac — Cursos livres',
      url_final: 'https://creditoup.com.br/r/guia-cursos-senac/?secao=livres',
      textos: {
        headlines: ['Cursos Livres do Senac', 'Áreas e Modalidades', 'Como se Inscrever'],
        long_headlines: ['Guia dos cursos livres do Senac com áreas, carga horária e inscrição'],
        descriptions: ['Veja as áreas de cursos livres.', 'Entenda modalidades, carga horária e o passo a passo para se inscrever.'],
      },
      imagens: [imagem],
      sinais: [{ tipo: 'search_theme', valor: 'cursos livres senac' }],
      videos: [{ video_id: 'jNQXAC9IVRw' }],
      path1: 'cursos', path2: 'livres',
      opcoes_de_url: {
        sufixo_extra: [['vc_ag', 'livres'], ['vc_tema', '{_tema}']],
        tracking_url_template: '{lpurl}?vc_tpl={_tema}',
        parametros_personalizados: [['tema', 'livres']],
      },
    });
    expect(semErrosDeForma(pedido.configuracao_pmax, 'PERFORMANCE_MAX', 'configuracao_pmax')).toEqual([]);
  });

  it('sinais não confirmados viajam como null — "ninguém escolheu", que o servidor recusa', () => {
    const c = configuracaoPMax({ ...form, grupos: [{ ...grupo, sinaisConfirmados: false }] }, {}, true);
    expect(c.grupos_adicionais?.[0].sinais).toBeNull();
  });

  it('vídeo e meta de cliente novo geram os avisos previstos', () => {
    const c = configuracaoPMax({ ...form, clienteNovo: true, cnGoal: 'customers/1/goals/2' }, {}, true);
    expect(avisosPrevistosDePMax(c).map((a) => a.codigo))
      .toEqual(['VIDEO_SEM_PORTAO_DE_POLITICA', 'META_CLIENTE_NOVO_POS_CRIACAO']);
  });

  it('ROAS digitado em % vira razão no envelope', () => {
    const roas = montarPedidoPMax({
      base: BASE, copy: pedido.copy, estrategia: 'MAXIMIZE_CONVERSION_VALUE', meta: '400',
      brandGuidelines: false, audiencias: [], temas: [], negativas: [], nomeDoAssetGroup: '', assets: [],
      form: FORM_PMAX_VAZIO, imagensDosGrupos: {},
    });
    expect(roas.target_roas).toBe(4);
    expect('tcpa' in roas).toBe(false);
  });
});

describe('o rascunho gravado por versão anterior não derruba o formulário', () => {
  it('mescla campos novos sobre o vazio, inclusive mapas abertos', () => {
    const f = mesclarFormulario(FORM_DEMAND_GEN_VAZIO, { formato: 'VIDEO_RESPONSIVO', automacoes: { X: true }, campoMorto: 1 });
    expect(f.formato).toBe('VIDEO_RESPONSIVO');
    expect(f.automacoes).toEqual({ X: true });
    expect('campoMorto' in f).toBe(false);
    expect(f.inclIdade).toBe(true);
  });
});
