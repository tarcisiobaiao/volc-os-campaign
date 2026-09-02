/**
 * Prontidão de operação — o contrato de leitura, e o guarda de forma.
 *
 * ## O que esta camada existe para impedir
 *
 * A regra de prontidão mora no backend (`app/asset_vault/prontidao.py`), e é lá
 * que ela deve morar: é regra de negócio, e componente React não é lugar de
 * regra. O que mora aqui é o **vocabulário** — os rótulos em português e o tom
 * de cada resposta — mais um guarda de forma.
 *
 * O guarda não é zelo: é a mesma disciplina de `cofreApi`. Se a API mudar de
 * forma, ou um proxy no meio devolver outra coisa, o painel precisa dizer que
 * não entendeu — e não desenhar uma prontidão vazia que parece um "nada
 * pendente". Um `pronto: false` com zero bloqueios seria a pior tela possível:
 * ela diz que algo impede sem dizer o quê.
 *
 * ## Por que três valores e não um booleano
 *
 * `desconhecido` NÃO é `não`. "Não há perfil de navegador relacionado" é um fato
 * do inventário; "não sei se o perfil está aberto" é a ausência de uma
 * observação — e esta tela não alcança o host isolado onde essa observação
 * seria feita. As duas frases levam a ações completamente diferentes: cadastrar
 * um perfil, ou ir até a máquina.
 */

export type ValorDaResposta = 'sim' | 'nao' | 'desconhecido';

/** De onde veio a resposta. Esta API só produz `registro`. */
export type ProcedenciaDaResposta = 'registro' | 'sonda';

export interface RespostaDeProntidao {
  valor: ValorDaResposta;
  motivo: string;
  procedencia: ProcedenciaDaResposta;
}

/** As oito perguntas, na ordem em que a tela as lê. */
export const PERGUNTAS = [
  'pagina_de_destino',
  'dono',
  'ativos_relacionados',
  'perfil_de_navegador',
  'onde_esta_a_credencial',
  'referencia_resolvivel',
  'perfil_disponivel',
  'peca_roteavel',
] as const;

export type ChaveDaPergunta = (typeof PERGUNTAS)[number];

export const PERGUNTA_LABEL: Record<ChaveDaPergunta, string> = {
  pagina_de_destino: 'Qual é o destino',
  dono: 'Quem responde por ele',
  ativos_relacionados: 'O que está relacionado',
  perfil_de_navegador: 'Qual perfil o autentica',
  onde_esta_a_credencial: 'Onde a credencial mora',
  referencia_resolvivel: 'A referência já foi resolvida',
  perfil_disponivel: 'O perfil está disponível',
  peca_roteavel: 'Uma peça aprovada pode ser roteada',
};

export const VALOR_LABEL: Record<ValorDaResposta, string> = {
  sim: 'sim',
  nao: 'não',
  desconhecido: 'não se sabe',
};

export interface RetratoDeProntidao {
  estado?: string | null;
  criticidade?: string | null;
  dono_nome?: string | null;
  dono_custodia?: string | null;
  finalidade?: string | null;
  revisao_atual?: number | null;
  atualizado_em?: string | null;
  ultima_revisao_em?: string | null;
  ultima_revisao_resultado?: string | null;
  aposentado_em?: string | null;
}

export interface EngineParaODestino {
  ativo_id: string;
  nome: string;
  modalidade?: string | null;
  estado_operacional?: string | null;
}

export interface ProntidaoDoAtivo {
  ativo_id: string;
  perguntas: Record<ChaveDaPergunta, RespostaDeProntidao>;
  retrato: RetratoDeProntidao;
  producao_possivel: EngineParaODestino[];
  componentes_seguintes: Record<string, { tarefa: string; estado?: string; implementacao?: string; operacao_real?: string }>;
  pronto_para_receber_peca: boolean;
  pronto_para_operar_acesso: boolean;
  pronto_para_publicar: boolean;
  bloqueios: string[];
  bloqueios_por_portao: {
    recebimento: string[];
    acesso: string[];
    publicacao: string[];
  };
  /** Sempre `false`. Publicar é um ato separado, e nenhuma leitura o dispara. */
  publica: boolean;
}

const VALORES = new Set<string>(['sim', 'nao', 'desconhecido']);

function respostaValida(valor: unknown): valor is RespostaDeProntidao {
  if (!valor || typeof valor !== 'object') return false;
  const r = valor as Record<string, unknown>;
  return VALORES.has(String(r.valor)) && typeof r.motivo === 'string';
}

/**
 * Forma inesperada é INDISPONIBILIDADE, nunca uma prontidão vazia.
 *
 * O painel usa este guarda antes de desenhar qualquer coisa. Aceitar um objeto
 * pela metade produziria uma tela que afirma "nada pendente" sobre uma resposta
 * que ninguém entendeu — que é o mesmo defeito de responder `[]` quando o banco
 * caiu, uma camada acima.
 */
export function ehProntidao(valor: unknown): valor is ProntidaoDoAtivo {
  if (!valor || typeof valor !== 'object') return false;
  const p = valor as Record<string, unknown>;
  if (typeof p.pronto_para_receber_peca !== 'boolean') return false;
  if (typeof p.pronto_para_operar_acesso !== 'boolean') return false;
  if (typeof p.pronto_para_publicar !== 'boolean') return false;
  if (!Array.isArray(p.bloqueios) || p.bloqueios.some((b) => typeof b !== 'string')) return false;
  const portoes = p.bloqueios_por_portao as Record<string, unknown> | undefined;
  if (!portoes || typeof portoes !== 'object') return false;
  for (const chave of ['recebimento', 'acesso', 'publicacao']) {
    const lista = portoes[chave];
    if (!Array.isArray(lista) || lista.some((b) => typeof b !== 'string')) return false;
  }
  const perguntas = p.perguntas;
  if (!perguntas || typeof perguntas !== 'object') return false;
  return PERGUNTAS.every((chave) => respostaValida((perguntas as Record<string, unknown>)[chave]));
}

export interface ResumoDeProntidao {
  sim: number;
  nao: number;
  desconhecido: number;
  total: number;
}

export function resumoDeProntidao(prontidao: ProntidaoDoAtivo): ResumoDeProntidao {
  const resumo: ResumoDeProntidao = { sim: 0, nao: 0, desconhecido: 0, total: PERGUNTAS.length };
  for (const chave of PERGUNTAS) resumo[prontidao.perguntas[chave].valor] += 1;
  return resumo;
}

/**
 * A frase de cabeçalho, e ela não arredonda.
 *
 * "6 de 8 respondidas" esconderia que uma das duas restantes é um bloqueio e a
 * outra é uma pergunta que só o broker responde. A frase nomeia as duas.
 */
export function fraseDoResumo(resumo: ResumoDeProntidao): string {
  const partes = [`${resumo.sim} de ${resumo.total} em ordem`];
  if (resumo.nao > 0) partes.push(`${resumo.nao} bloqueando`);
  if (resumo.desconhecido > 0) partes.push(`${resumo.desconhecido} sem observação`);
  return partes.join(' · ');
}
