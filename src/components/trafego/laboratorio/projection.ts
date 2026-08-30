/**
 * Projeção da bancada L6: o browser só nomeia, agrupa e exibe.
 *
 * Nada aqui escolhe limiar, fecha diagnóstico, classifica suficiência,
 * reordena prioridades do servidor ou transforma `null` em zero.
 * Se o contrato não trouxe o campo, a superfície declara a ausência.
 */
import { AUSENTE, horaExata, idade, lidoHa } from '@/components/trafego/inventario/formato';
import type { EvidenciaDeCampo, Proposta } from '@/types/diagnostico';
import type {
  CenarioDoLab,
  ConflitoDoLab,
  FatorDoLab,
  PoliticaDoLab,
  PropostaTipadaDoLab,
  RespostaDoDecisionLab,
  ResultadoDecisionLab,
} from '@/types/inteligenciaDecisao';
import { ehResultadoDecisionLab } from '@/types/inteligenciaDecisao';

export const MARCA_SINTETICA = 'LABORATÓRIO · DADOS SINTÉTICOS · SEM AÇÃO EXTERNA';
export const MARCA_SINTETICA_COM_PROTOTIPO =
  'LABORATÓRIO · PROTÓTIPO · DADOS SINTÉTICOS · SEM AÇÃO EXTERNA';
/** Fixture local. Nunca afirma leitura, conta ou dado real. */
export const MARCA_SHADOW_FUTURO = 'SHADOW FUTURO · FIXTURE SINTÉTICA · SEM AÇÃO EXTERNA';
/**
 * Reservado a um payload futuro do backend, com fonte, conta e carimbo.
 * `projetarBancada` não o aplica a `shadow_futuro`. Fixtures não o usam.
 */
export const MARCA_SHADOW_REAL = 'SHADOW READ · DADOS REAIS · CONTA TESTE · SEM AÇÃO';
export const SELO_SEM_ACAO = 'nenhuma ação será executada';

export type ModoDaBancada = 'sintetico' | 'shadow_futuro';
export type CoberturaVisivel = 'completa' | 'parcial' | 'antiga' | 'indisponivel';
export type EstadoDaMedida =
  | 'valor'
  | 'ausente'
  | 'zero_medido'
  | 'nao_aplicavel'
  | 'falha'
  | 'lista_vazia'
  | 'campo_ausente';

export type IdDaFamilia =
  | 'entrega_leilao'
  | 'orcamento_lance'
  | 'qualidade'
  | 'keywords'
  | 'conversao'
  | 'integridade';

export interface EvidenciaVisivel {
  chave: string;
  rotulo: string;
  valorExibido: string;
  estado: EstadoDaMedida;
  fonte: string;
  janela: string;
  carimbo: string;
  interpretacao: string;
  ressalva: string | null;
  campo: string | null;
}

export interface FamiliaVisivel {
  id: IdDaFamilia;
  titulo: string;
  itens: EvidenciaVisivel[];
}

export interface EstagioVisivel {
  id: 'observado' | 'qualificado' | 'diagnosticado' | 'proposto';
  titulo: string;
  entrou: string;
  saiu: string;
  bloqueou: string;
  evidencia: string;
  itensDoContrato: string[];
}

export interface PropostaVisivel {
  id: string;
  acao: string;
  frase: string;
  alvo: string;
  antes: string;
  depois: string;
  efeito: string;
  evidencias: EvidenciaVisivel[];
  amostra: string;
  confianca: string;
  bloqueios: string[];
  idempotencyKey: string;
  estado: 'proposta_nao_executada';
}

export interface BancadaVisivel {
  modo: ModoDaBancada;
  marca: string;
  notaDeModo: string;
  fonte: string;
  campanha: string | null;
  conta: string | null;
  janela: string;
  momentoDaLeitura: string;
  idadeDaLeitura: string;
  cobertura: CoberturaVisivel;
  coberturaRotulo: string;
  coberturaMotivo: string;
  seloSemAcao: string;
  tituloExecutivo: string;
  fraseExecutiva: string;
  insuficienciaAntesDaHipotese: boolean;
  familias: FamiliaVisivel[];
  estagios: EstagioVisivel[];
  diagnosticoPrincipal: string;
  diagnosticoResumo: string;
  hipotesesSecundarias: string[];
  confiancaDoDiagnostico: string;
  apoiam: FatorDoLab[];
  contradizem: FatorDoLab[];
  aindaNecessario: FatorDoLab[];
  conflitos: ConflitoDoLab[];
  politicas: PoliticaDoLab[];
  propostas: PropostaVisivel[];
  caixaVaziaConfirmada: boolean;
  caixaNaoApurada: boolean;
  mutacoesExecutadas: 0;
  recibo: string;
  replay: string | null;
  namespaceApi: string;
}

const FAMILIAS: Array<{ id: IdDaFamilia; titulo: string; eixos: string[] }> = [
  { id: 'entrega_leilao', titulo: 'Entrega e leilão', eixos: ['campanha', 'leilao', 'grupo', 'anuncio'] },
  { id: 'orcamento_lance', titulo: 'Orçamento e lance', eixos: ['orcamento'] },
  { id: 'qualidade', titulo: 'Qualidade e relevância', eixos: [] },
  { id: 'keywords', titulo: 'Palavras-chave e termos de busca', eixos: ['keyword', 'segmentacao'] },
  { id: 'conversao', titulo: 'Conversão e receita', eixos: ['conversao'] },
  { id: 'integridade', titulo: 'Integridade e frescor da leitura', eixos: ['conta'] },
];

const ZERO_MEDIDO = new Set(['0', '0.0', '0.00', '0,0']);

export function estadoDaMedida(valor: unknown, extra?: { estado?: unknown; impedimento?: string | null }): EstadoDaMedida {
  if (extra?.estado === 'nao_aplicavel') return 'nao_aplicavel';
  if (extra?.estado === 'falha' || (extra?.impedimento && valor == null)) return 'falha';
  if (extra?.estado === 'campo_ausente') return 'campo_ausente';
  if (valor === null || valor === undefined) return 'ausente';
  if (Array.isArray(valor) && valor.length === 0) return 'lista_vazia';
  if (typeof valor === 'number' && valor === 0) return 'zero_medido';
  if (typeof valor === 'string' && ZERO_MEDIDO.has(valor.trim())) return 'zero_medido';
  return 'valor';
}

export function valorExibido(valor: unknown, estado: EstadoDaMedida): string {
  if (estado === 'ausente' || estado === 'campo_ausente') return AUSENTE;
  if (estado === 'nao_aplicavel') return 'não aplicável';
  if (estado === 'falha') return AUSENTE;
  if (estado === 'lista_vazia') return 'lista observada e vazia';
  if (estado === 'zero_medido') return '0';
  if (valor == null) return AUSENTE;
  if (typeof valor === 'string') return valor;
  if (typeof valor === 'number' || typeof valor === 'boolean') return String(valor);
  try {
    return JSON.stringify(valor);
  } catch {
    return AUSENTE;
  }
}

export function coberturaDoContrato(entrada: {
  estado_da_superficie?: string;
  estado_da_leitura?: string;
}): CoberturaVisivel {
  const superficie = entrada.estado_da_superficie;
  const leitura = entrada.estado_da_leitura;
  if (
    superficie === 'falha_sem_fotografia' ||
    superficie === 'falha_ultimo_bom' ||
    superficie === 'versao_desconhecida' ||
    leitura === 'invalida'
  ) {
    return 'indisponivel';
  }
  if (superficie === 'stale' || leitura === 'stale') return 'antiga';
  if (superficie === 'parcial' || leitura === 'parcial') return 'parcial';
  if (superficie === 'vazio_confirmado') return 'completa';
  return 'completa';
}

export function palavraDaCobertura(cobertura: CoberturaVisivel): string {
  if (cobertura === 'completa') return 'completa';
  if (cobertura === 'parcial') return 'parcial';
  if (cobertura === 'antiga') return 'antiga';
  return 'indisponível';
}

function textoOuAusencia(valor: unknown, ausencia: string): string {
  if (valor == null) return ausencia;
  const texto = String(valor).trim();
  return texto.length > 0 ? texto : ausencia;
}

function evidenciaDeCampo(e: EvidenciaDeCampo, interpretacao: string, ressalva: string | null): EvidenciaVisivel {
  const extra = e as EvidenciaDeCampo & { estado_da_medida?: unknown };
  const estado = estadoDaMedida(e.valor, { estado: extra.estado_da_medida });
  return {
    chave: `${e.campo}:${e.rotulo}`,
    rotulo: e.rotulo,
    valorExibido: valorExibido(e.valor, estado),
    estado,
    fonte: e.origem,
    janela: e.janela ?? 'janela não declarada',
    carimbo: e.leitura ? `${lidoHa(e.leitura.idade_s)} · ${horaExata(e.leitura.lido_em) ?? e.leitura.lido_em}` : 'sem data de leitura',
    interpretacao,
    ressalva,
    campo: e.campo,
  };
}

function evidenciasPublicas(resultado: ResultadoDecisionLab): EvidenciaVisivel[] {
  const saida: EvidenciaVisivel[] = [];
  resultado.evidencias.forEach((bruta, indice) => {
    if (!bruta || typeof bruta !== 'object') return;
    const item = bruta;
    if (Array.isArray(item.itens) && item.itens.length === 0) {
      saida.push({
        chave: `pub-${indice}-lista`,
        rotulo: textoOuAusencia(item.rotulo ?? item.ref, 'lista observada'),
        valorExibido: 'lista observada e vazia',
        estado: 'lista_vazia',
        fonte: textoOuAusencia(item.fonte, 'fonte não declarada'),
        janela: janelaDeBruta(item),
        carimbo: textoOuAusencia(item.lido_em, 'sem data de leitura'),
        interpretacao: textoOuAusencia(item.interpretacao, 'O contrato enviou a lista, e ela veio vazia.'),
        ressalva: typeof item.ressalva === 'string' ? item.ressalva : null,
        campo: typeof item.ref === 'string' ? item.ref : null,
      });
      return;
    }
    if (item.estado_da_medida === 'nao_aplicavel') {
      saida.push({
        chave: `pub-${indice}-na`,
        rotulo: textoOuAusencia(item.rotulo ?? item.ref, 'campo'),
        valorExibido: 'não aplicável',
        estado: 'nao_aplicavel',
        fonte: textoOuAusencia(item.fonte, 'fonte não declarada'),
        janela: janelaDeBruta(item),
        carimbo: textoOuAusencia(item.lido_em, 'sem data de leitura'),
        interpretacao: textoOuAusencia(item.interpretacao, 'O contrato marcou este campo como não aplicável.'),
        ressalva: typeof item.ressalva === 'string' ? item.ressalva : null,
        campo: typeof item.ref === 'string' ? item.ref : null,
      });
      return;
    }
    if (item.estado_da_medida === 'campo_ausente' || item.ausente === true) {
      saida.push({
        chave: `pub-${indice}-ausente`,
        rotulo: textoOuAusencia(item.rotulo ?? item.ref, 'campo'),
        valorExibido: AUSENTE,
        estado: 'campo_ausente',
        fonte: textoOuAusencia(item.fonte, 'fonte não declarada'),
        janela: janelaDeBruta(item),
        carimbo: textoOuAusencia(item.lido_em, 'sem data de leitura'),
        interpretacao: textoOuAusencia(item.interpretacao, 'Este campo não veio na fotografia.'),
        ressalva: typeof item.ressalva === 'string' ? item.ressalva : null,
        campo: typeof item.ref === 'string' ? item.ref : null,
      });
    }
  });
  return saida;
}

function janelaDeBruta(item: Record<string, unknown>): string {
  const janela = item.janela;
  if (janela && typeof janela === 'object') {
    const recorte = janela as { inicio?: unknown; fim?: unknown };
    if (recorte.inicio || recorte.fim) {
      return `${recorte.inicio ?? 'início não declarado'} a ${recorte.fim ?? 'fim não declarado'}`;
    }
  }
  if (typeof janela === 'string' && janela.trim()) return janela;
  return 'janela não declarada';
}

function fonteDoResultado(resultado: ResultadoDecisionLab): string {
  const primeira = resultado.evidencias[0];
  if (primeira && typeof primeira === 'object' && primeira !== null && 'fonte' in primeira) {
    const fonte = (primeira as { fonte?: unknown }).fonte;
    if (fonte && typeof fonte === 'object') {
      const nome = (fonte as { nome?: unknown; tipo?: unknown });
      return [nome.nome, nome.tipo].filter(Boolean).map(String).join(' · ') || 'fonte não declarada';
    }
    if (typeof fonte === 'string' && fonte.trim()) return fonte;
  }
  return 'dataset sintético hermético';
}

function campanhaEConta(resultado: ResultadoDecisionLab): { campanha: string | null; conta: string | null } {
  const diagnostico = resultado.diagnostico;
  return {
    campanha: diagnostico.nome_campanha || null,
    conta: diagnostico.customer_id || null,
  };
}

function evidenciaInsuficiente(resultado: ResultadoDecisionLab): boolean {
  if (resultado.veredito.tipo === 'nao_apurado' || resultado.veredito.tipo === 'indeterminado') return true;
  if (resultado.health_gate.estado === 'parcial' || resultado.health_gate.estado === 'stale') return true;
  if (resultado.estado_da_leitura !== 'atual') return true;
  return resultado.politicas.some((politica) => politica.suficiencia !== 'suficiente' && politica.faltantes.length > 0);
}

function familiasDoResultado(resultado: ResultadoDecisionLab): FamiliaVisivel[] {
  const extras = evidenciasPublicas(resultado);
  const porEixo = new Map<string, EvidenciaVisivel[]>();
  for (const degrau of resultado.diagnostico.degraus) {
    const interpretacao = degrau.frase;
    const ressalva = degrau.impedimento;
    const itens = degrau.evidencias.map((e) => evidenciaDeCampo(e, interpretacao, ressalva));
    if (itens.length === 0) {
      if (!degrau.impedimento) {
        porEixo.set(degrau.eixo, []);
        continue;
      }
      const estado = estadoDaMedida(null, {
        impedimento: degrau.impedimento,
        estado: degrau.impedimento === 'campo ausente' ? 'campo_ausente' : 'falha',
      });
      itens.push({
        chave: `degrau-${degrau.eixo}`,
        rotulo: degrau.palavra,
        valorExibido: valorExibido(null, estado),
        estado,
        fonte: 'diagnóstico enviado pelo contrato',
        janela: resultado.diagnostico.janela,
        carimbo: resultado.diagnostico.leitura
          ? lidoHa(resultado.diagnostico.leitura.idade_s)
          : 'sem data de leitura',
        interpretacao,
        ressalva,
        campo: degrau.eixo,
      });
    }
    porEixo.set(degrau.eixo, itens);
  }

  return FAMILIAS.map((familia) => {
    const itens: EvidenciaVisivel[] = [];
    for (const eixo of familia.eixos) {
      itens.push(...(porEixo.get(eixo) ?? []));
    }
    if (familia.id === 'qualidade') {
      const qualidade = resultado.fatores.favorece.concat(resultado.fatores.limita, resultado.fatores.desconhecido)
        .filter((fator) => fator.chave === 'qualidade');
      for (const fator of qualidade) {
        itens.push({
          chave: `fator-${fator.chave}-${fator.evidencia}`,
          rotulo: 'qualidade',
          valorExibido: resultado.fatores.desconhecido.includes(fator) ? AUSENTE : 'declarado pelo contrato',
          estado: resultado.fatores.desconhecido.includes(fator) ? 'ausente' : 'valor',
          fonte: fator.evidencia,
          janela: resultado.diagnostico.janela,
          carimbo: resultado.diagnostico.leitura ? lidoHa(resultado.diagnostico.leitura.idade_s) : 'sem data de leitura',
          interpretacao: fator.frase,
          ressalva: resultado.fatores.desconhecido.includes(fator)
            ? 'O contrato declara esta qualidade como desconhecida, não como fato.'
            : 'Interpretação enviada pelo contrato; não é um recálculo desta tela.',
          campo: fator.evidencia,
        });
      }
    }
    if (familia.id === 'keywords') {
      itens.push(...extras.filter((e) => e.estado === 'lista_vazia' || e.campo?.includes('search') || e.campo?.includes('keyword')));
    }
    if (familia.id === 'orcamento_lance') {
      itens.push(...extras.filter((e) => e.estado === 'nao_aplicavel'));
    }
    if (familia.id === 'integridade') {
      itens.push({
        chave: 'integridade-gate',
        rotulo: 'cobertura da leitura',
        valorExibido: palavraDaCobertura(coberturaDoContrato(resultado)),
        estado: resultado.health_gate.estado === 'liberado'
          || resultado.health_gate.estado === 'stale'
          || resultado.health_gate.estado === 'parcial'
          ? 'valor'
          : 'falha',
        fonte: 'health_gate',
        janela: resultado.diagnostico.janela,
        carimbo: resultado.diagnostico.leitura ? lidoHa(resultado.diagnostico.leitura.idade_s) : 'sem data de leitura',
        interpretacao: resultado.health_gate.motivo,
        ressalva: resultado.diagnostico.parcial ? 'O diagnóstico veio marcado como leitura parcial.' : null,
        campo: 'health_gate.estado',
      });
      itens.push(...extras.filter((e) => e.estado === 'campo_ausente' || e.estado === 'falha'));
    }
    if (familia.id === 'conversao') {
      const receita = resultado.fatores.favorece.concat(resultado.fatores.limita, resultado.fatores.desconhecido)
        .filter((fator) => fator.chave === 'margem' || fator.chave === 'receita');
      for (const fator of receita) {
        itens.push({
          chave: `fator-${fator.chave}`,
          rotulo: fator.chave,
          valorExibido: resultado.fatores.desconhecido.includes(fator) ? AUSENTE : 'declarado pelo contrato',
          estado: resultado.fatores.desconhecido.includes(fator) ? 'ausente' : 'valor',
          fonte: fator.evidencia,
          janela: resultado.diagnostico.janela,
          carimbo: resultado.diagnostico.leitura ? lidoHa(resultado.diagnostico.leitura.idade_s) : 'sem data de leitura',
          interpretacao: fator.frase,
          ressalva: 'Só aparece quando o contrato enviou este fator. Esta tela não calcula margem.',
          campo: fator.evidencia,
        });
      }
    }
    return { id: familia.id, titulo: familia.titulo, itens };
  });
}

function estagiosDoResultado(resultado: ResultadoDecisionLab): EstagioVisivel[] {
  const porTipo = new Map<string, ResultadoDecisionLab['timeline'][number][]>();
  for (const item of resultado.timeline) {
    const lista = porTipo.get(item.tipo) ?? [];
    lista.push(item);
    porTipo.set(item.tipo, lista);
  }
  const textos = (tipos: string[]): string[] =>
    tipos.flatMap((tipo) => (porTipo.get(tipo) ?? []).map((item) => item.texto));

  const conflitos = resultado.conflitos.map((c) => c.motivo);
  const bloqueiosProposta = resultado.propostas_tipadas.flatMap((p) => p.bloqueios);
  const politicasInsuficientes = resultado.politicas
    .filter((p) => p.suficiencia !== 'suficiente')
    .map((p) => p.motivo_suficiencia ?? `faltam: ${p.faltantes.join(', ') || 'não declarado'}`);

  const agrupados: EstagioVisivel[] = [
    {
      id: 'observado',
      titulo: 'Observado',
      entrou: textos(['observacao']).join(' ') || 'O contrato não descreveu a entrada da observação.',
      saiu: textos(['validacao_frescor']).join(' ') || resultado.health_gate.motivo,
      bloqueou: resultado.estado_da_leitura === 'atual' ? 'Nenhum bloqueio de leitura neste estágio.' : resultado.health_gate.motivo,
      evidencia: resultado.timeline.find((i) => i.evidencia_ref)?.evidencia_ref ?? fonteDoResultado(resultado),
      itensDoContrato: textos(['observacao', 'validacao_frescor']),
    },
    {
      id: 'qualificado',
      titulo: 'Qualificado',
      entrou: textos(['features', 'politicas']).join(' ') || 'O contrato não descreveu a qualificação.',
      saiu: resultado.politicas.map((p) => `${p.titulo}: ${p.resultado}`).join(' · ') || 'Nenhuma política veio neste contrato.',
      bloqueou: [...conflitos, ...politicasInsuficientes].join(' ') || 'Nenhum veto declarado neste estágio.',
      evidencia: resultado.politicas[0]?.fonte ?? 'políticas versionadas do contrato',
      itensDoContrato: textos(['features', 'politicas', 'conflitos']),
    },
    {
      id: 'diagnosticado',
      titulo: 'Diagnosticado',
      entrou: textos(['diagnostico']).join(' ') || resultado.veredito.titulo,
      saiu: resultado.veredito.resumo,
      bloqueou: resultado.veredito.tipo === 'nao_apurado' || resultado.veredito.tipo === 'indeterminado'
        ? resultado.veredito.resumo
        : 'O contrato formulou um diagnóstico; ele permanece hipótese.',
      evidencia: resultado.fatores.favorece[0]?.evidencia ?? resultado.fatores.limita[0]?.evidencia ?? 'diagnóstico do contrato',
      itensDoContrato: textos(['diagnostico']),
    },
    {
      id: 'proposto',
      titulo: 'Proposto',
      entrou: textos(['proposta']).join(' ') || 'O contrato não descreveu a emissão da proposta.',
      saiu: resultado.propostas_tipadas.length === 0
        ? 'Nenhuma proposta tipada foi emitida.'
        : `${resultado.propostas_tipadas.length} proposta(s) tipada(s), não executada(s).`,
      bloqueou: bloqueiosProposta.length > 0
        ? bloqueiosProposta.join(' ')
        : resultado.execucao.estado === 'bloqueada'
          ? 'Execução bloqueada: sem autorização, aplicação ou recibo.'
          : 'Nenhum bloqueio declarado.',
      evidencia: resultado.propostas_tipadas[0]?.proposta_id ?? 'sem proposta',
      itensDoContrato: textos(['proposta', 'replay_eval']),
    },
  ];

  const tiposConhecidos = new Set([
    'observacao', 'validacao_frescor', 'features', 'politicas', 'conflitos',
    'diagnostico', 'proposta', 'replay_eval',
  ]);
  const restantes = resultado.timeline.filter((item) => !tiposConhecidos.has(item.tipo));
  if (restantes.length > 0) {
    agrupados[0] = {
      ...agrupados[0],
      itensDoContrato: [...agrupados[0].itensDoContrato, ...restantes.map((i) => i.texto)],
    };
  }
  return agrupados;
}

function evidenciasDeDesconhecida(valor: unknown, interpretacao: string): EvidenciaVisivel[] {
  if (!Array.isArray(valor)) return [];
  return valor.flatMap((item, indice) => {
    if (!item || typeof item !== 'object') return [];
    const e = item as Partial<EvidenciaDeCampo>;
    if (typeof e.rotulo !== 'string') return [];
    return [evidenciaDeCampo(e as EvidenciaDeCampo, interpretacao, null)];
  }).concat().filter(Boolean);
}

function propostasVisiveis(resultado: ResultadoDecisionLab): PropostaVisivel[] {
  const caixa = resultado.caixa_de_propostas.propostas;
  const porId = new Map(caixa.map((p) => [p.id, p]));
  const usadas = new Set<string>();

  const deTipada = (tipada: PropostaTipadaDoLab, caixaItem?: Proposta): PropostaVisivel => {
    const extras = tipada as PropostaTipadaDoLab & { evidencias?: unknown };
    const evidencias = caixaItem?.evidencias?.map((e) => evidenciaDeCampo(e, caixaItem.frase, caixaItem.bloqueio?.dependencia ?? null))
      ?? evidenciasDeDesconhecida(extras.evidencias, caixaItem?.frase ?? 'Evidência anexada à proposta tipada.');
    const efeito = caixaItem?.diff?.gasto_diario == null ? 'não estimado' : 'efeito de gasto declarado no contrato';
    return {
      id: tipada.proposta_id,
      acao: caixaItem?.titulo ?? tipada.operacao,
      frase: caixaItem?.frase ?? 'O contrato não enviou frase operacional para esta proposta tipada.',
      alvo: tipada.alvo,
      antes: tipada.antes ?? caixaItem?.diff?.linhas[0]?.antes ?? AUSENTE,
      depois: tipada.depois ?? caixaItem?.diff?.linhas[0]?.depois ?? AUSENTE,
      efeito,
      evidencias,
      amostra: caixaItem
        ? caixaItem.amostra.n == null
          ? `amostra não apurada · ${caixaItem.amostra.janela}`
          : `${caixaItem.amostra.n} ${caixaItem.amostra.unidade} · ${caixaItem.amostra.janela}`
        : 'amostra não declarada neste contrato',
      confianca: caixaItem?.confianca ?? tipada.confianca,
      bloqueios: tipada.bloqueios,
      idempotencyKey: tipada.idempotency_key,
      estado: 'proposta_nao_executada',
    };
  };

  const lista: PropostaVisivel[] = resultado.propostas_tipadas.map((tipada) => {
    const caixaItem = porId.get(tipada.proposta_id);
    if (caixaItem) usadas.add(caixaItem.id);
    return deTipada(tipada, caixaItem);
  });

  for (const item of caixa) {
    if (usadas.has(item.id)) continue;
    lista.push({
      id: item.id,
      acao: item.titulo,
      frase: item.frase,
      alvo: item.alvo,
      antes: item.diff.linhas[0]?.antes ?? AUSENTE,
      depois: item.diff.linhas[0]?.depois ?? AUSENTE,
      efeito: item.diff.gasto_diario == null ? 'não estimado' : 'efeito de gasto declarado no contrato',
      evidencias: item.evidencias.map((e) => evidenciaDeCampo(e, item.frase, item.bloqueio?.dependencia ?? null)),
      amostra: item.amostra.n == null
        ? `amostra não apurada · ${item.amostra.janela}`
        : `${item.amostra.n} ${item.amostra.unidade} · ${item.amostra.janela}`,
      confianca: item.confianca,
      bloqueios: item.bloqueio ? [item.bloqueio.dependencia] : [],
      idempotencyKey: 'não declarada neste contrato',
      estado: 'proposta_nao_executada',
    });
  }
  return lista;
}

function hipotesesSecundarias(resultado: ResultadoDecisionLab): string[] {
  const extra = (resultado.veredito as { hipoteses_secundarias?: unknown }).hipoteses_secundarias;
  if (!Array.isArray(extra)) return [];
  return extra.filter((item): item is string => typeof item === 'string' && item.trim().length > 0);
}

function confiancaDoDiagnostico(resultado: ResultadoDecisionLab): string {
  const declarada = (resultado.veredito as { confianca?: unknown }).confianca;
  if (typeof declarada === 'string' && declarada.trim()) return declarada;
  return 'confiança não declarada neste contrato';
}

export function projetarBancada(
  resultado: ResultadoDecisionLab,
  modo: ModoDaBancada = 'sintetico',
): BancadaVisivel {
  const { campanha, conta } = campanhaEConta(resultado);
  const cobertura = coberturaDoContrato(resultado);
  const insuficiente = evidenciaInsuficiente(resultado);
  const leitura = resultado.diagnostico.leitura;

  return {
    modo,
    marca: modo === 'shadow_futuro' ? MARCA_SHADOW_FUTURO : MARCA_SINTETICA,
    notaDeModo: modo === 'shadow_futuro'
      ? 'Fixture local de superfície futura. Sem fotografia de backend e sem ação externa.'
      : 'Fotografia sintética. Nenhuma ação externa sai desta bancada.',
    fonte: fonteDoResultado(resultado),
    campanha,
    conta,
    janela: resultado.diagnostico.janela,
    momentoDaLeitura: leitura ? (horaExata(leitura.lido_em) ?? leitura.lido_em) : 'sem data de leitura',
    idadeDaLeitura: leitura ? idade(leitura.idade_s) : 'sem data de leitura',
    cobertura,
    coberturaRotulo: resultado.health_gate.rotulo,
    coberturaMotivo: resultado.health_gate.motivo,
    seloSemAcao: SELO_SEM_ACAO,
    tituloExecutivo: resultado.veredito.titulo,
    fraseExecutiva: insuficiente
      ? resultado.veredito.resumo
      : resultado.veredito.resumo,
    insuficienciaAntesDaHipotese: insuficiente,
    familias: familiasDoResultado(resultado),
    estagios: estagiosDoResultado(resultado),
    diagnosticoPrincipal: resultado.veredito.titulo,
    diagnosticoResumo: resultado.veredito.resumo,
    hipotesesSecundarias: hipotesesSecundarias(resultado),
    confiancaDoDiagnostico: confiancaDoDiagnostico(resultado),
    apoiam: resultado.fatores.favorece,
    contradizem: resultado.fatores.limita,
    aindaNecessario: resultado.fatores.desconhecido,
    conflitos: resultado.conflitos,
    politicas: resultado.politicas,
    propostas: propostasVisiveis(resultado),
    caixaVaziaConfirmada: resultado.caixa_de_propostas.leitura != null && resultado.caixa_de_propostas.propostas.length === 0,
    caixaNaoApurada: resultado.caixa_de_propostas.leitura == null,
    mutacoesExecutadas: 0,
    recibo: 'não existe, nada foi executado',
    replay: resultado.replay
      ? `${resultado.replay.passaram}/${resultado.replay.total} cenários passaram`
      : null,
    namespaceApi: `${resultado.api_google_ads.namespace} / ${resultado.api_google_ads.minor_documentada_localmente}`,
  };
}

export function fotografiaDaResposta(resposta: RespostaDoDecisionLab | null): ResultadoDecisionLab | null {
  if (!resposta) return null;
  if (ehResultadoDecisionLab(resposta)) return resposta;
  return resposta.ultima_fotografia ?? null;
}

export function catalogoComProvas(catalogo: CenarioDoLab[], provas: CenarioDoLab[]): CenarioDoLab[] {
  return [...catalogo, ...provas];
}
