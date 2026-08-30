/**
 * Provas locais da superfície L6. Não são fotografia de backend e não alimentam
 * o pipeline Python. Cada envelope declara o modo e a marca.
 */
import type {
  CenarioDoLab,
  RespostaDoDecisionLab,
  ResultadoDecisionLab,
} from '@/types/inteligenciaDecisao';

import { MARCA_SHADOW_FUTURO, type ModoDaBancada } from './projection';

const LEITURA = { lido_em: '2026-08-28T11:00:00Z', idade_s: 3600 };
const EIXOS = ['conta', 'campanha', 'orcamento', 'grupo', 'anuncio', 'keyword', 'segmentacao', 'conversao', 'leilao'] as const;

const ISOLAMENTO = {
  somente_sintetico: true as const,
  entra_em_contagens_reais: false as const,
  aceita_volc_campaign_id: false as const,
  oferece_aplicar: false as const,
  chamadas_externas: 0 as const,
  escopo_chamadas_externas: 'nenhuma',
  mutacoes_executadas: 0 as const,
};

const REPLAY = {
  dataset_version: 1,
  as_of: '2026-08-28T12:00:00Z',
  total: 8,
  passaram: 8,
  falharam: 0,
};

export interface EnvelopeDaProvaL6 {
  prova_id: string;
  rotulo: string;
  grupo: 'prova-l6';
  modo: ModoDaBancada;
  marca: string;
  nota: string;
  resposta: RespostaDoDecisionLab;
}

function degrausBase(overrides?: Partial<Record<(typeof EIXOS)[number], Partial<ResultadoDecisionLab['diagnostico']['degraus'][number]>>>): ResultadoDecisionLab['diagnostico']['degraus'] {
  return EIXOS.map((eixo) => ({
    eixo,
    estado: eixo === 'orcamento' ? 'limita' : 'ok',
    palavra: eixo === 'orcamento' ? 'perda por verba' : 'apurado',
    frase: eixo === 'orcamento' ? 'A conta mediu perda por orçamento.' : 'Este degrau foi observado.',
    motivo_da_conta: [],
    evidencias: eixo === 'orcamento'
      ? [{
        rotulo: 'perda por orçamento',
        valor: '0.22',
        campo: 'search_budget_lost_impression_share',
        janela: '2026-08-25 a 2026-08-27',
        leitura: LEITURA,
        origem: 'conta' as const,
      }]
      : [],
    impedimento: null,
    propostas: [],
    ...overrides?.[eixo],
  }));
}

function fotografia(parcial: Partial<ResultadoDecisionLab> & Pick<ResultadoDecisionLab, 'scenario_id' | 'rotulo'>): ResultadoDecisionLab {
  const base: ResultadoDecisionLab = {
    versao_contrato: 1,
    scenario_id: parcial.scenario_id,
    rotulo: parcial.rotulo,
    estado_da_superficie: 'atual',
    estado_da_leitura: 'atual',
    health_gate: { estado: 'liberado', rotulo: 'evidência utilizável', motivo: 'A fotografia está atual e inteira.' },
    veredito: { tipo: 'limitado', titulo: 'Demanda limitada por orçamento', resumo: 'Qualidade saudável favorece revisar verba.' },
    fatores: {
      favorece: [{ chave: 'qualidade', frase: 'Quality Score e componentes estão saudáveis nesta fotografia.', evidencia: 'quality' }],
      limita: [{ chave: 'rank', frase: 'Há impression share perdido por rank.', evidencia: 'daily_metrics.search_rank_lost_impression_share' }],
      desconhecido: [{ chave: 'receita', frase: 'Uma fonte permanece desconhecida.', evidencia: 'external_revenue' }],
    },
    politicas: [{
      regra_id: 'orakul_escala_com_guardas', versao: 1, titulo: 'ORAKUL, escala governada',
      owner: 'VOLC Decision Intelligence Lab', fonte: 'decision-lab:calibracao-sintetica-v1',
      nivel_autonomia: 'T1', publicavel: false, aplicavel: true, suficiencia: 'suficiente',
      motivo_suficiencia: null, faltantes: [], disparou: true, resultado: 'evento tipado emitido',
    }],
    conflitos: [{ codigo: 'quality_first', efeito: 'ordena_revisao', motivo: 'Qualidade vem antes do lance.' }],
    eventos: [{
      evento_id: 'evt-1', tipo: 'budget_limited_with_healthy_quality', entidade: 'synthetic:1:2',
      observado_em: LEITURA.lido_em, janela_inicio: '2026-08-25', janela_fim: '2026-08-27',
      evidencia_refs: ['quality'], severidade: 'atencao', dedup_key: 'abc', resolucao: 'aberta',
    }],
    diagnostico: {
      versao: 1,
      volc_campaign_id: `lab::${parcial.scenario_id}`,
      customer_id: 'synthetic',
      nome_campanha: 'LAB orçamento',
      moeda: 'BRL',
      estado_coleta: 'com_dados',
      frescor: 'recente',
      janela: '2026-08-25 a 2026-08-27',
      leitura: LEITURA,
      parcial: false,
      degraus: degrausBase(),
    },
    caixa_de_propostas: {
      versao: 1,
      volc_campaign_id: `lab::${parcial.scenario_id}`,
      propostas: [{
        id: 'prop-1',
        alvo: 'orcamento',
        titulo: 'Revisar aumento de orçamento',
        frase: 'Há demanda perdida por verba e qualidade saudável; o tamanho do passo continua humano.',
        eixo: 'orcamento',
        evidencias: [{
          rotulo: 'perda por orçamento',
          valor: '0.22',
          campo: 'search_budget_lost_impression_share',
          janela: '2026-08-25 a 2026-08-27',
          leitura: LEITURA,
          origem: 'conta',
        }],
        confianca: 'alta',
        amostra: { n: 132, unidade: 'cliques observados', janela: '2026-08-25 a 2026-08-27', insuficiente: false },
        diff: {
          linhas: [{ rotulo: 'orçamento', antes: '20000000', depois: null, delta: null }],
          inalterado: ['estado da campanha'],
          gasto_diario: null,
        },
        aprovacao: { estado: 'nao_submetida', por: null, em: null, impressao: null, motivo: null, vale_ate: null },
        bloqueio: {
          dependencia: 'Laboratório sintético sem executor, aprovação ou trava de escrita aberta.',
          destrava: 'endpoint',
        },
      }],
      leitura: LEITURA,
    },
    propostas_tipadas: [{
      proposta_id: 'prop-1', idempotency_key: 'a'.repeat(64), evento_id: 'evt-1',
      regra_chave: 'orakul_escala_com_guardas', regra_versao: 1, operacao: 'orcamento',
      alvo: 'synthetic:1:2', antes: '20000000', depois: null, confianca: 'alta',
      bloqueios: ['laboratório sem executor'], aprovacao: 'nao_submetida', aplicacao: 'nao_executada', recibo: null,
    }],
    execucao: { estado: 'bloqueada', autorizacao: null, aplicacao: null, recibo: null, mutacoes_executadas: 0 },
    evidencias: [
      { ref: 'source', fonte: { nome: 'decision_lab_fixture', tipo: 'sintetica_hermetica' }, janela: { inicio: '2026-08-25', fim: '2026-08-27' }, lido_em: LEITURA.lido_em },
      { ref: 'campaign', customer_id: 'synthetic', campaign_id: '2', status: 'ENABLED', channel: 'SEARCH', bidding: 'MANUAL_CPC' },
    ],
    features: {},
    timeline: [
      { ordem: 1, tipo: 'observacao', estado: 'recebida', texto: 'Fotografia recebida.', observado_em: LEITURA.lido_em, janela: { inicio: '2026-08-25', fim: '2026-08-27' } },
      { ordem: 2, tipo: 'validacao_frescor', estado: 'atual', texto: 'Contrato, janela e anulabilidade foram conferidos.' },
      { ordem: 3, tipo: 'features', estado: 'calculadas', texto: 'Features foram calculadas em Python, sem zero-fill.' },
      { ordem: 4, tipo: 'politicas', estado: 'avaliadas', texto: 'Políticas versionadas foram avaliadas.' },
      { ordem: 5, tipo: 'conflitos', estado: 'arbitrados', texto: 'Conflitos antes da decisão.' },
      { ordem: 6, tipo: 'diagnostico', estado: 'limitado', texto: 'Diagnóstico fechado.' },
      { ordem: 7, tipo: 'proposta', estado: 'bloqueada', texto: 'Proposta sem executor.' },
      { ordem: 8, tipo: 'replay_eval', estado: 'pronto_para_comparacao', texto: 'Saída pronta para comparação.' },
    ],
    critica: {
      estado: 'explicada', autoridade: 'explicador_sem_poder_decisorio',
      resposta: { resumo: 'A decisão respeita os conflitos.', questoes: [], campos_considerados: ['veredito'] },
    },
    autoridade: { calculadora: 'python_puro', llm: 'critico_explicador', decisao: 'politicas_versionadas', mutacao: 'inexistente' },
    api_google_ads: { namespace: 'v25', minor_documentada_localmente: 'v25.1', v25_2: 'nao_afirmada' },
    marcas: ['PROTÓTIPO', 'DADOS SINTÉTICOS'],
  };
  return { ...base, ...parcial, diagnostico: parcial.diagnostico ?? base.diagnostico };
}

function comEnvelope(foto: ResultadoDecisionLab, extras?: { catalogo?: CenarioDoLab[] }): RespostaDoDecisionLab {
  return Object.assign(foto, {
    catalogo: extras?.catalogo ?? CATALOGO_SERVIDOR,
    replay: REPLAY,
    isolamento: ISOLAMENTO,
  });
}

export const CATALOGO_SERVIDOR: CenarioDoLab[] = [
  { scenario_id: 'budget-limited-healthy', rotulo: 'Budget limited com qualidade saudável', grupo: 'dourado' },
  { scenario_id: 'partial-read', rotulo: 'Leitura parcial', grupo: 'dourado' },
];

export function fotografiaDouradaBudgetLimited(): RespostaDoDecisionLab {
  return comEnvelope(fotografia({
    scenario_id: 'budget-limited-healthy',
    rotulo: 'Budget limited com qualidade saudável',
    caixa_de_propostas: {
      versao: 1,
      volc_campaign_id: 'lab::budget-limited-healthy',
      propostas: [],
      leitura: LEITURA,
    },
  }));
}

function estadoTerminal(
  superficie: ResultadoDecisionLab extends never ? never : string,
  campos: Record<string, unknown>,
): RespostaDoDecisionLab {
  return {
    versao_contrato: 1,
    scenario_id: String(campos.scenario_id),
    rotulo: String(campos.rotulo),
    estado_da_superficie: superficie,
    marcas: ['PROTÓTIPO', 'DADOS SINTÉTICOS'],
    catalogo: CATALOGO_SERVIDOR,
    replay: REPLAY,
    isolamento: ISOLAMENTO,
    ...campos,
  } as unknown as RespostaDoDecisionLab;
}

const sinteticoCompleto = comEnvelope(fotografia({
  scenario_id: 'prova-l6-sintetico-completo',
  rotulo: 'Sintético completo',
}));

const propostaBloqueada = comEnvelope(fotografia({
  scenario_id: 'prova-l6-proposta-bloqueada',
  rotulo: 'Sintético com proposta bloqueada',
  conflitos: [
    { codigo: 'margin_gate', efeito: 'veta_escala', motivo: 'Demanda existe, mas a margem não sustenta aumento de gasto.' },
  ],
  veredito: { tipo: 'bloqueado', titulo: 'Escala bloqueada por guardas', resumo: 'Há uma proposta formulada, e ela permanece sem executor.' },
}));

const evidenciaParcial = comEnvelope(fotografia({
  scenario_id: 'prova-l6-evidencia-parcial',
  rotulo: 'Evidência parcial',
  estado_da_superficie: 'parcial',
  estado_da_leitura: 'parcial',
  health_gate: { estado: 'parcial', rotulo: 'leitura parcial', motivo: 'Campos ausentes permanecem ausentes e bloqueiam proposta.' },
  veredito: { tipo: 'nao_apurado', titulo: 'Leitura parcial não autoriza decisão', resumo: 'Ainda falta evidência suficiente para qualquer hipótese de causa.' },
  diagnostico: {
    versao: 1,
    volc_campaign_id: 'lab::prova-l6-evidencia-parcial',
    customer_id: 'synthetic',
    nome_campanha: 'LAB parcial',
    moeda: 'BRL',
    estado_coleta: 'parcial',
    frescor: 'recente',
    janela: '2026-08-25 a 2026-08-27',
    leitura: LEITURA,
    parcial: true,
    degraus: degrausBase({
      orcamento: {
        estado: 'nao_apurado',
        palavra: 'não apurado',
        frase: 'A perda por orçamento não foi medida para a janela.',
        evidencias: [],
        impedimento: 'campo ausente',
      },
    }),
  },
  propostas_tipadas: [],
  caixa_de_propostas: {
    versao: 1,
    volc_campaign_id: 'lab::prova-l6-evidencia-parcial',
    propostas: [],
    leitura: null,
  },
}));

const leituraAntiga = comEnvelope(fotografia({
  scenario_id: 'prova-l6-leitura-antiga',
  rotulo: 'Leitura antiga',
  estado_da_superficie: 'stale',
  estado_da_leitura: 'stale',
  health_gate: { estado: 'stale', rotulo: 'leitura antiga', motivo: 'A fotografia ultrapassou o frescor aceito pelo perfil sintético.' },
  veredito: { tipo: 'nao_apurado', titulo: 'Leitura antiga não autoriza decisão', resumo: 'Os dados existem, e já não bastam para concluir.' },
  propostas_tipadas: [],
}));

const listaVazia = comEnvelope(fotografia({
  scenario_id: 'prova-l6-lista-vazia',
  rotulo: 'Lista observada e vazia',
  evidencias: [
    { ref: 'source', fonte: { nome: 'decision_lab_fixture', tipo: 'sintetica_hermetica' }, janela: { inicio: '2026-08-25', fim: '2026-08-27' }, lido_em: LEITURA.lido_em },
    { ref: 'search_terms', rotulo: 'termos de busca', itens: [], fonte: 'conta', interpretacao: 'A lista de termos foi lida e veio vazia.' },
  ],
}));

const campoAusente = comEnvelope(fotografia({
  scenario_id: 'prova-l6-campo-ausente',
  rotulo: 'Campo ausente',
  evidencias: [
    { ref: 'source', fonte: { nome: 'decision_lab_fixture', tipo: 'sintetica_hermetica' }, janela: { inicio: '2026-08-25', fim: '2026-08-27' }, lido_em: LEITURA.lido_em },
    { ref: 'landing_page_experience', rotulo: 'experiência da página', estado_da_medida: 'campo_ausente', ausente: true, fonte: 'conta', interpretacao: 'Este campo não veio na fotografia.' },
  ],
}));

const zeroMedido = comEnvelope(fotografia({
  scenario_id: 'prova-l6-zero-medido',
  rotulo: 'Zero realmente medido',
  veredito: { tipo: 'indeterminado', titulo: 'Sem entrega, causa indeterminada', resumo: 'A campanha mediu zero impressões. Zero medido não autoriza inventar a causa.' },
  diagnostico: {
    versao: 1,
    volc_campaign_id: 'lab::prova-l6-zero-medido',
    customer_id: 'synthetic',
    nome_campanha: 'LAB zero',
    moeda: 'BRL',
    estado_coleta: 'parcial',
    frescor: 'recente',
    janela: '2026-08-27 a 2026-08-27',
    leitura: LEITURA,
    parcial: true,
    degraus: degrausBase({
      leilao: {
        estado: 'nao_apurado',
        palavra: 'sem leilão observado',
        frase: 'Nenhuma impressão confirma entrada em leilão.',
        evidencias: [{
          rotulo: 'impressões',
          valor: '0',
          campo: 'metrics.impressions',
          janela: '2026-08-27 a 2026-08-27',
          leitura: LEITURA,
          origem: 'conta',
        }],
        impedimento: 'sem entrega observada',
      },
    }),
  },
}));

const conflito = comEnvelope(fotografia({
  scenario_id: 'prova-l6-conflito',
  rotulo: 'Conflito entre evidências',
  fatores: {
    favorece: [{ chave: 'demanda', frase: 'Há impression share perdido por orçamento.', evidencia: 'window_metrics.search_budget_lost_impression_share' }],
    limita: [{ chave: 'margem', frase: 'A margem externa desta janela não sustenta escala.', evidencia: 'external_revenue' }],
    desconhecido: [],
  },
  conflitos: [
    { codigo: 'margin_gate', efeito: 'veta_escala', motivo: 'Demanda aponta para verba; margem aponta contra. O contrato registrou o conflito antes da proposta.', evidencia_refs: ['window_metrics.search_budget_lost_impression_share', 'external_revenue'] },
  ],
}));

const naoAplicavel = comEnvelope(fotografia({
  scenario_id: 'prova-l6-nao-aplicavel',
  rotulo: 'Não aplicável',
  evidencias: [
    { ref: 'source', fonte: { nome: 'decision_lab_fixture', tipo: 'sintetica_hermetica' }, janela: { inicio: '2026-08-25', fim: '2026-08-27' }, lido_em: LEITURA.lido_em },
    { ref: 'target_roas', rotulo: 'lance alvo', estado_da_medida: 'nao_aplicavel', fonte: 'conta', interpretacao: 'O contrato marcou lance alvo como não aplicável a esta estratégia.' },
  ],
}));

const shadow = comEnvelope(fotografia({
  scenario_id: 'prova-l6-shadow-futuro',
  rotulo: 'Shadow futuro (fixture)',
  veredito: {
    tipo: 'nao_apurado',
    titulo: 'Ainda não há leitura shadow neste laboratório',
    resumo: 'Esta superfície antecipa o modo shadow. A fixture não substitui uma fotografia do backend.',
  },
  health_gate: { estado: 'parcial', rotulo: 'shadow não ligado', motivo: 'O contrato operacional ainda não envia fotografia shadow.' },
  estado_da_superficie: 'parcial',
  estado_da_leitura: 'parcial',
  diagnostico: {
    versao: 1,
    volc_campaign_id: 'lab::prova-l6-shadow-futuro',
    customer_id: 'fixture-nao-lida',
    nome_campanha: 'Marcador de layout, não é fotografia',
    moeda: null,
    estado_coleta: null,
    frescor: 'nao_apurado',
    janela: 'janela não lida',
    leitura: null,
    parcial: true,
    degraus: EIXOS.map((eixo) => ({
      eixo,
      estado: 'nao_apurado',
      palavra: 'não lido',
      frase: 'Fixture de superfície futura: este degrau não veio do backend.',
      motivo_da_conta: [],
      evidencias: [],
      impedimento: 'shadow futuro ainda não tem fotografia',
      propostas: [],
    })),
  },
  evidencias: [
    { ref: 'source', fonte: { nome: 'fixture-local-l6', tipo: 'shadow_futuro_nao_lido' }, janela: null, lido_em: null },
  ],
  propostas_tipadas: [],
  caixa_de_propostas: {
    versao: 1,
    volc_campaign_id: 'lab::prova-l6-shadow-futuro',
    propostas: [],
    leitura: null,
  },
  fatores: { favorece: [], limita: [], desconhecido: [{ chave: 'shadow', frase: 'Nenhuma evidência de backend foi anexada a esta fixture.', evidencia: 'fixture-local' }] },
  conflitos: [],
  eventos: [],
}));

export const PROVAS_L6: EnvelopeDaProvaL6[] = [
  {
    prova_id: 'prova-l6-sintetico-completo',
    rotulo: 'Sintético completo',
    grupo: 'prova-l6',
    modo: 'sintetico',
    marca: 'LABORATÓRIO · DADOS SINTÉTICOS · SEM AÇÃO EXTERNA',
    nota: 'Fixture local. Completa o desenho da bancada com proposta bloqueada.',
    resposta: sinteticoCompleto,
  },
  {
    prova_id: 'prova-l6-proposta-bloqueada',
    rotulo: 'Sintético com proposta bloqueada',
    grupo: 'prova-l6',
    modo: 'sintetico',
    marca: 'LABORATÓRIO · DADOS SINTÉTICOS · SEM AÇÃO EXTERNA',
    nota: 'A proposta existe no contrato e permanece sem executor.',
    resposta: propostaBloqueada,
  },
  {
    prova_id: 'prova-l6-evidencia-parcial',
    rotulo: 'Evidência parcial',
    grupo: 'prova-l6',
    modo: 'sintetico',
    marca: 'LABORATÓRIO · DADOS SINTÉTICOS · SEM AÇÃO EXTERNA',
    nota: 'A insuficiência aparece antes de qualquer hipótese.',
    resposta: evidenciaParcial,
  },
  {
    prova_id: 'prova-l6-leitura-antiga',
    rotulo: 'Leitura antiga',
    grupo: 'prova-l6',
    modo: 'sintetico',
    marca: 'LABORATÓRIO · DADOS SINTÉTICOS · SEM AÇÃO EXTERNA',
    nota: 'A fotografia permanece visível e não autoriza decisão.',
    resposta: leituraAntiga,
  },
  {
    prova_id: 'prova-l6-indisponivel-sem-ultimo-bom',
    rotulo: 'Indisponível sem último bom',
    grupo: 'prova-l6',
    modo: 'sintetico',
    marca: 'LABORATÓRIO · DADOS SINTÉTICOS · SEM AÇÃO EXTERNA',
    nota: 'Falha sem fotografia anterior.',
    resposta: estadoTerminal('falha_sem_fotografia', {
      scenario_id: 'prova-l6-indisponivel-sem-ultimo-bom',
      rotulo: 'Indisponível sem último bom',
      ultima_fotografia: null,
      falha: { codigo: 'LAB-SEM-FOTO-SINTETICA', mensagem: 'A primeira leitura não terminou.' },
    }),
  },
  {
    prova_id: 'prova-l6-indisponivel-com-ultimo-bom',
    rotulo: 'Indisponível com último bom',
    grupo: 'prova-l6',
    modo: 'sintetico',
    marca: 'LABORATÓRIO · DADOS SINTÉTICOS · SEM AÇÃO EXTERNA',
    nota: 'A tentativa falhou; a última fotografia boa permanece.',
    resposta: estadoTerminal('falha_ultimo_bom', {
      scenario_id: 'prova-l6-indisponivel-com-ultimo-bom',
      rotulo: 'Indisponível com último bom',
      ultima_fotografia: fotografiaDouradaBudgetLimited(),
      falha: { codigo: 'LAB-FALHA-SINTETICA', mensagem: 'A tentativa falhou.' },
    }),
  },
  {
    prova_id: 'prova-l6-lista-vazia',
    rotulo: 'Lista observada e vazia',
    grupo: 'prova-l6',
    modo: 'sintetico',
    marca: 'LABORATÓRIO · DADOS SINTÉTICOS · SEM AÇÃO EXTERNA',
    nota: 'Vazio observado não é ausência de leitura.',
    resposta: listaVazia,
  },
  {
    prova_id: 'prova-l6-campo-ausente',
    rotulo: 'Campo ausente',
    grupo: 'prova-l6',
    modo: 'sintetico',
    marca: 'LABORATÓRIO · DADOS SINTÉTICOS · SEM AÇÃO EXTERNA',
    nota: 'Ausência de campo, distinta de zero.',
    resposta: campoAusente,
  },
  {
    prova_id: 'prova-l6-zero-medido',
    rotulo: 'Zero realmente medido',
    grupo: 'prova-l6',
    modo: 'sintetico',
    marca: 'LABORATÓRIO · DADOS SINTÉTICOS · SEM AÇÃO EXTERNA',
    nota: 'Zero medido permanece zero, nunca vira ausência.',
    resposta: zeroMedido,
  },
  {
    prova_id: 'prova-l6-nao-aplicavel',
    rotulo: 'Não aplicável',
    grupo: 'prova-l6',
    modo: 'sintetico',
    marca: 'LABORATÓRIO · DADOS SINTÉTICOS · SEM AÇÃO EXTERNA',
    nota: 'Estado de medida que o contrato vivo ainda não envia; só esta fixture o marca.',
    resposta: naoAplicavel,
  },
  {
    prova_id: 'prova-l6-conflito',
    rotulo: 'Conflito entre evidências',
    grupo: 'prova-l6',
    modo: 'sintetico',
    marca: 'LABORATÓRIO · DADOS SINTÉTICOS · SEM AÇÃO EXTERNA',
    nota: 'O contrato registrou o conflito antes da proposta.',
    resposta: conflito,
  },
  {
    prova_id: 'prova-l6-shadow-futuro',
    rotulo: 'Shadow futuro (fixture)',
    grupo: 'prova-l6',
    modo: 'shadow_futuro',
    marca: MARCA_SHADOW_FUTURO,
    nota: 'Fixture sintética de superfície futura. Sem ação externa.',
    resposta: shadow,
  },
];

export function provaPorId(id: string): EnvelopeDaProvaL6 | undefined {
  return PROVAS_L6.find((prova) => prova.prova_id === id);
}

export function catalogoDasProvas(): CenarioDoLab[] {
  return PROVAS_L6.map((prova) => ({
    scenario_id: prova.prova_id,
    rotulo: prova.rotulo,
    grupo: prova.grupo,
  }));
}
