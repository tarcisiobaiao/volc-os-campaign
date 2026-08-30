/**
 * Uma falha de leitura vira frase de operação — e nunca o contrário.
 *
 * ## O defeito que este arquivo fecha
 *
 * O cliente HTTP monta mensagens para quem CONSERTA o sistema, não para quem
 * opera com ele: o 404 sai com a URL do backend e o nome da variável de
 * ambiente que pode estar errada; o erro de rede sai citando CORS e a variável
 * de origens permitidas; o 5xx repassa o `detail` do servidor, que hoje é uma
 * exceção Python recortada em 300 caracteres. Tudo isso chegava cru à tela do
 * operador, que não tem como agir sobre nada disso — e sai da tela sem saber
 * nem o que aconteceu nem o que fazer.
 *
 * ## A regra: vocabulário FECHADO
 *
 * A tela só pode dizer uma das frases de `FRASES_DE_FALHA`. Não existe caminho
 * em que texto vindo do servidor seja renderizado. Isso não é excesso de zelo:
 * é a única forma de a promessa valer também para o erro que ninguém previu —
 * um status novo, um proxy no meio do caminho, um corpo em HTML. Se a única
 * defesa fosse uma lista de palavras proibidas, bastaria uma palavra nova para
 * o vazamento voltar.
 *
 * ## Por que existe um código copiável
 *
 * Uma frase curta sozinha é um beco sem saída para quem for investigar: o
 * operador diz "deu erro" e ninguém consegue achar a ocorrência no log. O
 * código é o que liga a tela ao log. Ele é COPIÁVEL por botão, e não "selecione
 * e copie", porque quem está no meio de uma conferência não vai transcrever à
 * mão um identificador de seis caracteres — e transcrever errado é pior que não
 * transcrever.
 *
 * ⚠️ Enquanto o servidor não emitir um identificador próprio, o código nasce
 * aqui e o que liga tela e log é o par (instante, etapa) que viaja junto dele
 * no texto copiado. Quando o backend passar a mandar o seu, `idDoServidor()` o
 * adota sozinho e o par vira redundância — nenhuma tela precisa mudar.
 *
 * ## O detalhe técnico não é jogado fora, só não vai para a tela
 *
 * Ele fica no console do navegador, que é onde quem está depurando já olha, e
 * fora do alcance de quem só quer saber se pode mexer na campanha.
 */
import { horaExata } from './formato';

// ── vocabulário fechado do que a tela pode dizer ─────────────────────────────

export type MotivoDeFalha =
  | 'sem_resposta'
  | 'pedido_invalido'
  | 'sessao_expirada'
  | 'sem_permissao'
  | 'indisponivel_nesta_versao'
  | 'leitura_recente_demais'
  | 'sistema_fora_do_ar'
  | 'nao_prevista';

export interface FraseDeFalha {
  /** Uma linha, no tempo do operador. É o que ele lê primeiro. */
  mensagem: string;
  /**
   * O passo seguro seguinte.
   *
   * Nunca "tente de novo" sozinho: a pergunta que fica depois de uma falha é
   * "e agora, o que eu faço?", e metade das vezes a resposta certa é não fazer
   * nada na conta de anúncio — o que também precisa ser dito.
   */
  proximoPasso: string;
}

export const FRASES_DE_FALHA: Record<MotivoDeFalha, FraseDeFalha> = {
  sem_resposta: {
    mensagem: 'Não consegui falar com o sistema.',
    proximoPasso:
      'Confira a conexão desta máquina e tente de novo. Nenhuma campanha foi alterada.',
  },
  pedido_invalido: {
    mensagem: 'O sistema não aceitou esta consulta.',
    proximoPasso:
      'Desfaça o último filtro e tente de novo. Se repetir, envie o código desta ' +
      'ocorrência a quem cuida do sistema.',
  },
  sessao_expirada: {
    mensagem: 'Sua sessão expirou.',
    proximoPasso: 'Entre novamente para continuar. Nenhuma campanha foi alterada.',
  },
  sem_permissao: {
    mensagem: 'Sua conta não tem permissão para esta consulta.',
    proximoPasso:
      'Peça acesso a um administrador da VOLC. Nenhuma campanha foi alterada.',
  },
  indisponivel_nesta_versao: {
    mensagem: 'Esta consulta não existe nesta versão do sistema.',
    proximoPasso:
      'Recarregue a página; se continuar, envie o código desta ocorrência a quem ' +
      'cuida do sistema. Não há nada a corrigir nas campanhas.',
  },
  leitura_recente_demais: {
    mensagem: 'Esta conta foi lida há pouco tempo.',
    proximoPasso:
      'Aguarde antes de pedir outra leitura — cada pedido consome cota da conta ' +
      'de anúncio do cliente.',
  },
  sistema_fora_do_ar: {
    mensagem: 'O registro de campanhas não respondeu.',
    proximoPasso:
      'Tente de novo em alguns minutos. Enquanto isso, não decida gasto por esta ' +
      'tela: o que está na conta de anúncio continua como estava.',
  },
  nao_prevista: {
    mensagem: 'A leitura não terminou, e o sistema não soube dizer por quê.',
    proximoPasso:
      'Tente de novo. Se repetir, envie o código desta ocorrência a quem cuida do ' +
      'sistema — é por ele que a ocorrência é encontrada.',
  },
};

/** A etapa em que a falha aconteceu, na palavra do operador. */
export const ETAPAS = {
  inventario: 'conferência do inventário de campanhas',
  leitura_de_conta: 'pedido de leitura de uma conta',
  correspondencias: 'comparação desta campanha com os funis internos',
  // Acrescentada pela aba Oportunidades: a etapa aparece no texto COPIADO, e
  // "conferência do inventário" mandaria quem for investigar procurar a
  // ocorrência na leitura errada.
  oportunidades: 'conferência dos funis prontos para anunciar',
  campanha_canonica: 'leitura de uma campanha pelo identificador interno',
} as const;

export type EtapaDaOperacao = keyof typeof ETAPAS;

export interface OcorrenciaOperacional {
  motivo: MotivoDeFalha;
  mensagem: string;
  proximoPasso: string;
  /**
   * Fato adicional extraído de CAMPO ESTRUTURADO do servidor — nunca de texto
   * livre. Hoje só o instante em que a próxima leitura será aceita.
   */
  complemento: string | null;
  etapa: EtapaDaOperacao;
  /** O código que o operador copia. Curto o bastante para caber num recado. */
  id: string;
  /** Instante em que a TELA viu a falha, já formatado para o texto copiado. */
  quando: string;
  /** Exatamente o que vai para a área de transferência. */
  paraCopiar: string;
}

// ── leitura defensiva do erro ────────────────────────────────────────────────

/**
 * ⚠️ O status é lido por FORMATO, não por `instanceof PautadorApiError`.
 *
 * Importar a classe traria o cliente HTTP inteiro — e com ele o cliente do
 * Supabase, que se constrói ao carregar o módulo — para dentro de qualquer
 * arquivo que só queira transformar um erro em frase, testes inclusive. Pior:
 * amarraria este módulo a UM emissor de erro, quando o que chega aqui pode vir
 * de um `fetch` abortado, de um proxy ou de uma biblioteca de terceiros. O que
 * interessa é se existe um número de status; quem o produziu não importa.
 */
export function statusDe(erro: unknown): number | null {
  if (typeof erro !== 'object' || erro === null) return null;
  const bruto = (erro as { status?: unknown }).status;
  return typeof bruto === 'number' && Number.isFinite(bruto) ? bruto : null;
}

/** O corpo estruturado que o servidor anexou ao erro, quando anexou um. */
function corpoDe(erro: unknown): Record<string, unknown> | null {
  if (typeof erro !== 'object' || erro === null) return null;
  const corpo = (erro as { corpo?: unknown }).corpo;
  if (typeof corpo !== 'object' || corpo === null || Array.isArray(corpo)) return null;
  return corpo as Record<string, unknown>;
}

/**
 * O identificador que o SERVIDOR deu à ocorrência, se ele deu algum.
 *
 * Hoje nenhuma rota do inventário emite um; o dia em que emitir, a tela passa a
 * mostrar o mesmo código que está no log, e o par (instante, etapa) deixa de
 * ser necessário para achar a ocorrência. Aceitar os três nomes usuais evita
 * que essa passagem dependa de as duas pontas combinarem a grafia antes.
 */
export function idDoServidor(erro: unknown): string | null {
  const corpo = corpoDe(erro);
  if (!corpo) return null;
  for (const chave of ['correlation_id', 'id_da_ocorrencia', 'request_id', 'trace_id']) {
    const valor = corpo[chave];
    // ⚠️ O formato é conferido, não só o tamanho.
    //
    // Um identificador é curto, sem espaço e sem pontuação de prosa. Um campo
    // com o nome certo carregando um texto qualquer — um trecho de exceção, uma
    // frase de log — seria um vazamento pela porta lateral, entrando na tela
    // por um caminho que ninguém está olhando justamente porque o nome do campo
    // parece inofensivo.
    if (typeof valor === 'string' && /^[A-Za-z0-9][A-Za-z0-9._:-]{2,63}$/.test(valor.trim())) {
      return valor.trim();
    }
  }
  return null;
}

// ── status → motivo ──────────────────────────────────────────────────────────

/**
 * ⚠️ O `default` NÃO é `sem_resposta` nem `sistema_fora_do_ar`.
 *
 * Os dois afirmam uma causa, e afirmar causa errada é o que o produto inteiro
 * recusa fazer: "o registro não respondeu" diante de um 418 seria um
 * diagnóstico inventado, e o operador iria esperar passar sozinho algo que não
 * passa. `nao_prevista` diz a verdade — aconteceu, não sabemos o quê — e manda
 * o código adiante, que é a única ação útil nesse caso.
 */
export function motivoDaFalha(erro: unknown): MotivoDeFalha {
  const status = statusDe(erro);

  // Sem status: ou o `fetch` nem chegou a receber resposta, ou o erro nasceu
  // antes da rede. Os dois são "não falei com o sistema" para quem opera.
  if (status === null) return 'sem_resposta';
  if (status === 0) return 'sem_resposta';

  switch (status) {
    case 400:
    case 409:
    case 422:
      return 'pedido_invalido';
    case 401:
      return 'sessao_expirada';
    case 403:
      return 'sem_permissao';
    case 404:
    case 405:
    case 410:
      return 'indisponivel_nesta_versao';
    case 408:
      return 'sem_resposta';
    case 429:
      return 'leitura_recente_demais';
    default:
      break;
  }
  if (status >= 500 && status <= 599) return 'sistema_fora_do_ar';
  return 'nao_prevista';
}

/**
 * O único fato do corpo do servidor que a tela repassa — e ele é um INSTANTE,
 * não uma frase.
 *
 * O 429 do inventário traz `proxima_em`, que responde exatamente a pergunta que
 * o operador faz depois de "esta conta foi lida há pouco tempo": quando posso
 * pedir de novo. Um instante não tem como carregar caminho de arquivo, nome de
 * tabela nem pilha de exceção — por isso ele passa e o texto ao lado dele não.
 */
function complementoDe(erro: unknown, motivo: MotivoDeFalha): string | null {
  if (motivo !== 'leitura_recente_demais') return null;
  const corpo = corpoDe(erro);
  const proxima = corpo?.proxima_em;
  if (typeof proxima !== 'string') return null;
  const hora = horaExata(proxima);
  return hora ? `A próxima leitura desta conta será aceita a partir de ${hora}.` : null;
}

// ── o código copiável ────────────────────────────────────────────────────────

/**
 * Alfabeto sem `0`, `O`, `1`, `I` e `L`.
 *
 * O código vai ser lido em voz alta no telefone e digitado de novo do outro
 * lado. Os pares que se confundem nessa travessia saem do alfabeto em vez de
 * virarem uma nota de rodapé pedindo atenção.
 */
const ALFABETO = '23456789ABCDEFGHJKMNPQRSTUVWXYZ';

function sortear(quantidade: number): number[] {
  const cripto = globalThis.crypto;
  if (cripto && typeof cripto.getRandomValues === 'function') {
    return Array.from(cripto.getRandomValues(new Uint32Array(quantidade)));
  }
  return Array.from({ length: quantidade }, () => Math.floor(Math.random() * 0xffffffff));
}

export function novoCodigoDeOcorrencia(): string {
  const letras = sortear(6).map((n) => ALFABETO[n % ALFABETO.length]);
  return `VOLC-${letras.join('')}`;
}

// ── montagem ─────────────────────────────────────────────────────────────────

export interface OpcoesDaOcorrencia {
  /** Injetável para o teste ter código estável; em produção nasce sorteado. */
  id?: string;
  /** Injetável pela mesma razão. */
  agora?: Date;
}

function montar(
  motivo: MotivoDeFalha,
  etapa: EtapaDaOperacao,
  complemento: string | null,
  id: string,
  agora: Date,
): OcorrenciaOperacional {
  const frase = FRASES_DE_FALHA[motivo];
  const quando = horaExata(agora.toISOString()) ?? '';
  const paraCopiar = [
    id,
    `o que aconteceu: ${frase.mensagem}`,
    `etapa: ${ETAPAS[etapa]}`,
    `quando: ${quando}`,
  ].join('\n');

  return {
    motivo,
    mensagem: frase.mensagem,
    proximoPasso: frase.proximoPasso,
    complemento,
    etapa,
    id,
    quando,
    paraCopiar,
  };
}

/**
 * A porta de entrada: qualquer coisa lançada vira uma ocorrência exibível.
 *
 * `erro` é `unknown` de propósito — o que chega aqui pode ser um `Error`, um
 * objeto do cliente HTTP, uma string ou `undefined`, e nenhum desses casos pode
 * derrubar a tela que existe justamente para relatar que algo deu errado.
 */
export function descreverFalha(
  erro: unknown,
  etapa: EtapaDaOperacao,
  opcoes?: OpcoesDaOcorrencia,
): OcorrenciaOperacional {
  const motivo = motivoDaFalha(erro);
  const id = opcoes?.id ?? idDoServidor(erro) ?? novoCodigoDeOcorrencia();
  const agora = opcoes?.agora ?? new Date();
  return montar(motivo, etapa, complementoDe(erro, motivo), id, agora);
}

/**
 * Registra o detalhe técnico onde ele serve para alguma coisa: o console.
 *
 * Separado de `descreverFalha` porque descrever é puro e registrar é efeito —
 * e porque um teste que verifica a frase não deve sujar a saída da suíte.
 */
export function registrarDetalhe(erro: unknown, ocorrencia: OcorrenciaOperacional): void {
  if (typeof console === 'undefined' || typeof console.error !== 'function') return;
  console.error(`[volc] ${ocorrencia.id} · ${ETAPAS[ocorrencia.etapa]}`, {
    status: statusDe(erro),
    erro,
  });
}

// ── caminho legado: uma frase JÁ do vocabulário, sem o erro original ─────────

const MOTIVO_POR_MENSAGEM = new Map<string, MotivoDeFalha>(
  (Object.keys(FRASES_DE_FALHA) as MotivoDeFalha[]).map((m) => [FRASES_DE_FALHA[m].mensagem, m]),
);

/** Verdadeiro só para as frases que ESTA tela é dona de dizer. */
export function ehFraseConhecida(texto: string | null | undefined): boolean {
  return typeof texto === 'string' && MOTIVO_POR_MENSAGEM.has(texto);
}

/**
 * Reconstrói a ocorrência a partir da frase, para o componente que só recebeu
 * texto.
 *
 * ⚠️ O parâmetro é tratado como NÃO CONFIÁVEL: se a frase não estiver no
 * vocabulário, ela é descartada inteira e o resultado é `nao_prevista`. É o que
 * mantém a promessa mesmo quando alguém, um dia, passar por aqui uma string
 * vinda direto do servidor — o texto some, e o operador ganha uma frase útil no
 * lugar dele em vez de um pedaço de exceção.
 */
export function ocorrenciaDaFrase(
  texto: string | null | undefined,
  etapa: EtapaDaOperacao,
  opcoes?: OpcoesDaOcorrencia,
): OcorrenciaOperacional {
  const motivo = (typeof texto === 'string' && MOTIVO_POR_MENSAGEM.get(texto)) || 'nao_prevista';
  return montar(
    motivo,
    etapa,
    null,
    opcoes?.id ?? novoCodigoDeOcorrencia(),
    opcoes?.agora ?? new Date(),
  );
}
