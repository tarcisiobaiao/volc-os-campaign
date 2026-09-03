/**
 * Contrato da publicação orgânica no navegador — o espelho tipado de
 * `/api/publicacao-organica`, e o lugar onde mora a recusa de pintar verde.
 *
 * ## O vocabulário é do backend, não desta camada
 *
 * `ESTADOS`, `TONS`, `MODOS` e `ESTADOS_EXTERNOS` são a mesma lista que
 * `backend/app/publicacao_organica/dominio.py` declara e que o CHECK da v14_01
 * impõe. Quando as três divergem, o sintoma não é erro de compilação: é um
 * cartão na tela com um estado que ninguém sabe ler.
 *
 * ⚠️ Este arquivo NÃO tem um teste que compare literalmente com `dominio.py` —
 * o backend tem (`test_publicacao_organica_dominio.py` lê a migration). Aqui a
 * defesa é outra e mais barata: qualquer estado fora desta lista cai no ramo
 * "não reconhecido", que nunca é sucesso. Divergir custa um rótulo feio, nunca
 * um verde falso.
 *
 * ## O tom vem do servidor; esta camada só sabe VETAR
 *
 * `leitura.tom` é decidido em `dominio.leitura_do_estado`. Esta camada nunca
 * deriva cor a partir do nome do estado — derivar é como um `className`
 * condicional envelhece sem ninguém perceber, e o sintoma é um operador que
 * viu verde e parou de conferir.
 *
 * O que ela faz é uma escada de VETO, e veto só anda numa direção: tirar o
 * verde, nunca colocá-lo. `tomSeguro` é essa escada. Ela existe porque a tela é
 * o último ponto antes do olho humano, e porque o backend pode ser antigo, o
 * proxy pode truncar o JSON e o campo `leitura` pode chegar pela metade.
 */

// ---------------------------------------------------------------------------
// Vocabulário — espelho de dominio.py
// ---------------------------------------------------------------------------

/** Estados do job, na ordem em que a operação os encontra. */
export const ESTADOS = [
  'rascunho',
  'pronto',
  'em_voo',
  'rascunho_externo',
  'agendado',
  'publicacao_solicitada',
  'publicado',
  'reconciliado',
  'falha',
  'indeterminado',
  'cancelado',
] as const;

export type EstadoDoJob = (typeof ESTADOS)[number];

/**
 * Estados que não são sucesso e não são falha.
 *
 * ⚠️ Isto é um ESPELHO de `dominio.ESTADOS_INCERTOS`, e serve de piso — não de
 * autoridade. O backend manda `leitura.incerto`; este conjunto só é consultado
 * quando esse campo não chegou (backend antigo, proxy que cortou o JSON). Sem
 * ele, um `indeterminado` sem `leitura` herdaria o tom cru e poderia passar.
 */
export const ESTADOS_INCERTOS: ReadonlySet<string> = new Set([
  'em_voo',
  'publicacao_solicitada',
  'indeterminado',
]);

/** Nada mais acontece sem um job novo. */
export const ESTADOS_TERMINAIS: ReadonlySet<string> = new Set(['reconciliado', 'cancelado']);

/** Cinco tons, e nenhum é sinônimo de outro. `sucesso` é o único verde. */
export const TONS = ['neutro', 'aguardando', 'atencao', 'sucesso', 'falha'] as const;
export type TomDaLeitura = (typeof TONS)[number];

export const MODOS = ['draft', 'schedule', 'now'] as const;
export type ModoDePublicacao = (typeof MODOS)[number];

/** Vocabulário de estado do control plane. `DESCONHECIDO` é nosso. */
export const ESTADOS_EXTERNOS = ['DRAFT', 'QUEUE', 'PUBLISHED', 'ERROR', 'DESCONHECIDO'] as const;
export type EstadoExterno = (typeof ESTADOS_EXTERNOS)[number];

export const PLATAFORMAS = [
  'facebook', 'instagram', 'youtube', 'tiktok', 'linkedin', 'x', 'threads', 'pinterest',
] as const;
export type Plataforma = (typeof PLATAFORMAS)[number];

// ---------------------------------------------------------------------------
// A forma que chega do backend
// ---------------------------------------------------------------------------

/**
 * Como o estado deve ser APRESENTADO — decidido no servidor.
 *
 * Todos os campos são obrigatórios no contrato atual. O tipo os declara assim
 * porque é o que a API promete; `tomSeguro` e `rotuloDe` continuam tolerando a
 * ausência deles em tempo de execução, que é onde o contrato pode ser quebrado.
 */
export interface LeituraDoEstado {
  rotulo: string;
  tom: TomDaLeitura;
  proxima_acao: string;
  incerto: boolean;
  terminal: boolean;
}

/**
 * Um destino de publicação.
 *
 * ⚠️ `apto: false` NÃO some da lista. `publicacao_organica_listar_destinos`
 * devolve o inapto com `motivo` preenchido de propósito, e a tela o mostra
 * desabilitado. Filtrar aqui tornaria impossível cumprir a guarda do ADR
 * ("MultiPost nunca mascara a ausência de adapter oficial"): ninguém veria a
 * lacuna, e a ausência de adapter viraria ausência de destino.
 */
export interface DestinoOrganico {
  destino_id: string;
  ativo_id: string;
  nome: string;
  plataforma: string;
  identidade_logica: string;
  provedor: string;
  apto: boolean;
  /** Por que está inapto. `null` quando está apto. */
  motivo: string | null;
  timezone_padrao: string;
  estado: string;
}

/** O destino como ele viaja DENTRO do job — só o que identifica. */
export interface DestinoDoJob {
  destino_id: string;
  plataforma: string;
  identidade_logica: string;
}

/** A revisão exata que foi aprovada. `content_hash` é a prova de qual é. */
export interface PecaDoJob {
  id: string;
  versao: number;
  content_hash: string | null;
}

/**
 * A aprovação que autoriza este job.
 *
 * ⚠️ `ator_id` é um identificador, não um nome. O backend não projeta nome de
 * pessoa aqui, e esta tela não inventa um: mostra o identificador abreviado.
 * `revogada_em` preenchido é um BLOQUEADOR — a v14_01 recusa liberar um job
 * cuja autorização foi revogada depois da criação.
 */
export interface AprovacaoDoJob {
  id: string;
  ator_id: string | null;
  finalidade: string | null;
  decidido_em: string | null;
  revogada_em: string | null;
}

/** O último recibo do control plane para este job. */
export interface ReciboDoJob {
  referencia_externa: string | null;
  estado_externo: string | null;
  url_publicada: string | null;
  publicado_em: string | null;
  observado_em: string | null;
  /** Só no detalhe: `despacho` ou `reconciliacao`. */
  origem?: string | null;
}

/** Uma transição registrada. Append-only no banco. */
export interface TransicaoDoJob {
  de: string | null;
  para: string;
  motivo: string | null;
  criado_em: string;
}

/** Um job como ele aparece na listagem. */
export interface JobOrganico {
  job_id: string;
  estado: EstadoDoJob | string;
  modo: ModoDePublicacao | string;
  /** Como o humano declarou: `AAAA-MM-DD HH:MM:SS`, SEM fuso no texto. */
  horario_local: string | null;
  /** O fuso declarado, nome IANA. É ele que dá sentido a `horario_local`. */
  timezone: string;
  /** O instante convertido NO BANCO. Só existe em `schedule`. */
  instante_utc: string | null;
  tentativas: number;
  ultimo_erro: string | null;
  adapter?: string | null;
  destino: DestinoDoJob;
  peca: PecaDoJob;
  aprovacao: AprovacaoDoJob;
  /** `null` enquanto nada saiu daqui. */
  recibo: ReciboDoJob | null;
  criado_em?: string;
  atualizado_em?: string;
  leitura: LeituraDoEstado;
}

/** O detalhe traz o snapshot imutável e o rastro inteiro. */
export interface DetalheDoJob {
  job_id: string;
  estado: EstadoDoJob | string;
  modo: ModoDePublicacao | string;
  horario_local: string | null;
  timezone: string;
  instante_utc: string | null;
  tentativas: number;
  ultimo_erro: string | null;
  adapter?: string | null;
  consentimento_agora: boolean;
  consentimento_em: string | null;
  /** O snapshot imutável montado pelo banco na criação. Nunca reescrito. */
  solicitacao: Record<string, unknown>;
  criado_em: string;
  atualizado_em: string;
  recibos: ReciboDoJob[];
  historico: TransicaoDoJob[];
  leitura: LeituraDoEstado;
}

/**
 * A sonda do control plane.
 *
 * ⚠️ `fonte` costuma ser `proxy:/integrations` porque a API oficial do Postiz
 * NÃO tem endpoint de health (medido em 02/09/2026). A tela mostra a fonte
 * junto do resultado: chamar isso de "health check" afirmaria uma capacidade
 * que a API não documenta.
 */
export interface ProntidaoDaPublicacao {
  pronto: boolean;
  fonte: string;
  detalhe: string;
  canais_visiveis?: number | null;
}

/**
 * O recibo de uma operação governada.
 *
 * `idempotente: true` significa REPLAY — nada novo foi produzido. ⚠️ Este campo
 * DO CORPO é a fonte: o header `X-Publicacao-Idempotente` diz o mesmo, mas o
 * `CORSMiddleware` de `backend/app/main.py` não declara `expose_headers`, então
 * ele não é legível cross-origin. O cliente o usa só como reforço.
 */
export interface ReciboDeOperacao {
  job_id?: string;
  estado?: string;
  modo?: string;
  desfecho?: string;
  fechou?: boolean;
  motivo?: string;
  referencia_externa?: string | null;
  estado_externo?: string | null;
  url_publicada?: string | null;
  idempotente?: boolean;
}

// ---------------------------------------------------------------------------
// A escada de veto — CONTRAPROVA M
// ---------------------------------------------------------------------------

/**
 * Fragmentos de classe que significam "deu certo" neste tema.
 *
 * Existe como constante exportada para que o teste da contraprova não repita
 * strings: ele varre a classe produzida e falha se qualquer um aparecer onde
 * não pode. `emerald` e `green` estão aqui não porque o tema os use — ele não
 * usa —, mas porque são exatamente o atalho que alguém escreveria à mão num
 * commit apressado.
 */
export const TOKENS_DE_SUCESSO = ['success', 'emerald', 'green'] as const;

/** O que `tomSeguro` recebe: o job, ou qualquer coisa com estado e leitura. */
export interface EntradaDeTom {
  estado?: string | null;
  leitura?: Partial<LeituraDoEstado> | null;
}

function tomConhecido(valor: unknown): valor is TomDaLeitura {
  return typeof valor === 'string' && (TONS as readonly string[]).includes(valor);
}

export function estadoConhecido(estado: unknown): estado is EstadoDoJob {
  return typeof estado === 'string' && (ESTADOS as readonly string[]).includes(estado);
}

/**
 * O tom que a tela pode usar. O servidor propõe; esta função só tira.
 *
 * ⚠️ CONTRAPROVA M. Três vetos, nesta ordem, e nenhum deles CONCEDE `sucesso` —
 * a única forma de um estado ficar verde é o backend ter dito `sucesso` e
 * nenhum veto ter disparado:
 *
 *   1. tom fora do vocabulário (ausente, `null`, `"ok"`, `"green"`) → `atencao`.
 *      O ramo desconhecido nunca herda o benefício da dúvida.
 *   2. `leitura.incerto` verdadeiro → `sucesso` vira `atencao`. Isto protege
 *      contra um backend que se contradiga; `dominio.py` hoje nunca marca um
 *      incerto como sucesso, e este veto é o que garante que continue assim
 *      mesmo se alguém editar a tabela `_LEITURAS` sem pensar.
 *   3. estado fora de `ESTADOS` → `sucesso` vira `atencao`. Um estado que este
 *      contrato não conhece pode ser qualquer coisa; verde afirmaria a única
 *      coisa que ele com certeza não prova.
 *
 * Quando `leitura.incerto` não chega, `ESTADOS_INCERTOS` responde no lugar —
 * é o piso descrito no topo do arquivo.
 */
/**
 * O único estado que pode ficar verde. É um PISO, não a autoridade.
 *
 * ⚠️ ACRESCENTADO EM 02/09/2026 depois de DUAS verificações independentes
 * chegarem ao mesmo furo: a escada de veto olhava (1) tom fora do vocabulário,
 * (2) `incerto` e (3) estado desconhecido — e nenhum degrau acoplava ESTADO a
 * TOM. Um backend que se contradissesse no eixo estado×tom (`estado: 'falha'`
 * com `tom: 'sucesso'` e `incerto: false`) pintava VERDE e o rodapé dizia que
 * acabou. `incerto` não salvava, porque ele é derivado de `ESTADOS_INCERTOS` no
 * servidor e `falha` não está lá.
 *
 * Não é alcançável com o backend entregue (`dominio._LEITURAS['falha'].tom` é
 * `'falha'`). É defesa em profundidade — e é exatamente o eixo que a
 * CONTRAPROVA M existe para cobrir, então a lacuna estava no lugar errado.
 *
 * Este conjunto espelha `dominio.leitura_do_estado`: lá, `reconciliado` é o
 * único `sucesso`, e é o único que exige referência externa, URL e instante
 * para existir. Se o backend passar a ter outro estado verde legítimo, ele
 * entra AQUI junto — e é bom que doa, porque verde novo merece uma decisão.
 */
const ESTADOS_QUE_PODEM_FICAR_VERDES: ReadonlySet<string> = new Set(['reconciliado']);

export function tomSeguro(entrada: EntradaDeTom | null | undefined): TomDaLeitura {
  const leitura = entrada?.leitura;
  const estado = typeof entrada?.estado === 'string' ? entrada.estado : '';

  const proposto: TomDaLeitura = tomConhecido(leitura?.tom) ? leitura!.tom! : 'atencao';
  if (proposto !== 'sucesso') return proposto;

  const incerto = typeof leitura?.incerto === 'boolean'
    ? leitura.incerto
    : ESTADOS_INCERTOS.has(estado);
  if (incerto) return 'atencao';
  if (!estadoConhecido(estado)) return 'atencao';
  // Degrau 4: o estado precisa ser um dos que PODEM ficar verdes. É o veto que
  // faltava — ver o comentário de ESTADOS_QUE_PODEM_FICAR_VERDES.
  if (!ESTADOS_QUE_PODEM_FICAR_VERDES.has(estado)) return 'atencao';
  return 'sucesso';
}

/**
 * Classe do tom. Só `sucesso` carrega o token verde.
 *
 * `aguardando` usa `info` de propósito: azul diz "está acontecendo" sem dizer
 * "deu certo", e é o que `agendado` e `rascunho_externo` merecem — fatos
 * confirmados pelo control plane que ainda não são publicação.
 */
export const CLASSE_DO_TOM: Record<TomDaLeitura, string> = {
  neutro: 'border-border bg-muted text-muted-foreground',
  aguardando: 'border-info/30 bg-info/10 text-info',
  atencao: 'border-warning/35 bg-warning/10 text-warning',
  sucesso: 'border-success/30 bg-success/10 text-success',
  falha: 'border-destructive/35 bg-destructive/10 text-destructive',
};

/** A classe já vetada. É esta que a tela usa — nunca `CLASSE_DO_TOM` direto. */
export function classeDoTom(entrada: EntradaDeTom | null | undefined): string {
  return CLASSE_DO_TOM[tomSeguro(entrada)];
}

/** O rótulo do servidor. Sem ele, um rótulo honesto sobre não reconhecer. */
export function rotuloDe(entrada: EntradaDeTom | null | undefined): string {
  const rotulo = entrada?.leitura?.rotulo;
  if (typeof rotulo === 'string' && rotulo.trim()) return rotulo;
  const estado = typeof entrada?.estado === 'string' && entrada.estado ? entrada.estado : 'sem estado';
  return `Estado não reconhecido (${estado})`;
}

/** A próxima ação do servidor. Sem ela, a instrução de não tratar como pronto. */
export function proximaAcaoDe(entrada: EntradaDeTom | null | undefined): string {
  const acao = entrada?.leitura?.proxima_acao;
  if (typeof acao === 'string' && acao.trim()) return acao;
  return 'Este estado não existe no contrato desta versão. Não trate como publicado; '
    + 'confira no painel do control plane antes de qualquer ação.';
}

/**
 * A incerteza EFETIVA — a que a tela usa, não a que o backend afirmou.
 *
 * ⚠️ Ela só sabe SOMAR incerteza, nunca tirar; é a mesma direção de veto de
 * `tomSeguro`, do outro lado do sinal. Três fontes, e basta uma:
 *
 *   1. o servidor admitiu (`leitura.incerto === true`);
 *   2. o piso do contrato (`ESTADOS_INCERTOS`), para quando o campo não chegou
 *      — backend antigo, proxy que cortou o JSON;
 *   3. o estado não existe neste contrato: não conhecer é a forma mais pura de
 *      não saber.
 *
 * ⚠️ DEFEITO MEDIDO (revisão de 02/09/2026): o selo publicava em `data-incerto`
 * o valor CRU de `leitura.incerto`. Um `em_voo` vindo de um backend sem o campo
 * saía com `data-incerto="false"` — e a varredura do DOM, que filtra por esse
 * atributo, pulava exatamente a linha que o piso existe para proteger.
 */
export function incertoSeguro(entrada: EntradaDeTom | null | undefined): boolean {
  const declarado = entrada?.leitura?.incerto;
  if (declarado === true) return true;
  const estado = typeof entrada?.estado === 'string' ? entrada.estado : '';
  if (ESTADOS_INCERTOS.has(estado)) return true;
  return !estadoConhecido(estado);
}

/**
 * O pedido já saiu e a resposta do destino ainda não chegou — esperar é o ato.
 *
 * Diferente de `incertoSeguro` num ponto só, e o ponto importa: um estado que
 * este contrato NÃO conhece é incerto, mas ninguém sabe se há algo em trânsito.
 * Mandar "espere a resposta do destino" nesse caso seria inventar um fato. Por
 * isso a tela usa esta função para decidir se manda esperar, e a outra para
 * decidir se pode pintar de verde.
 */
export function aguardaODestino(entrada: EntradaDeTom | null | undefined): boolean {
  return estadoConhecido(entrada?.estado) && incertoSeguro(entrada);
}

/**
 * Terminal quer dizer: nada mais acontece sem um job novo.
 *
 * ⚠️ MESMA ESCADA DE VETO DE `tomSeguro`, e pelo mesmo motivo. "Nada a fazer
 * neste job" é o equivalente TEXTUAL do verde proibido: quem lê isso para de
 * conferir. Então o campo do servidor só é aceito quando nada o contradiz —
 * e, como no tom, o veto só anda numa direção (tirar o terminal, nunca dá-lo):
 *
 *   1. estado fora de `ESTADOS` → nunca terminal. Um estado que este contrato
 *      não conhece pode ser qualquer coisa, inclusive um job vivo.
 *   2. estado incerto → nunca terminal. `terminal: true` junto de `incerto`
 *      é backend se contradizendo, e a contradição não ganha o benefício da
 *      dúvida.
 *
 * Sem o campo, o espelho `ESTADOS_TERMINAIS` responde — e ele já contém apenas
 * estados conhecidos e certos, então o piso não precisa de veto.
 */
export function ehTerminal(entrada: EntradaDeTom | null | undefined): boolean {
  const estado = typeof entrada?.estado === 'string' ? entrada.estado : '';
  const terminal = entrada?.leitura?.terminal;
  if (typeof terminal === 'boolean') {
    if (!terminal) return false;
    if (!estadoConhecido(estado)) return false;
    if (incertoSeguro(entrada)) return false;
    // Mesmo piso do verde, pelo mesmo motivo: `estado: 'falha'` com
    // `terminal: true` fazia o rodapé imprimir "Nada a fazer neste job" —
    // a versão textual do verde proibido, e num estado que manda AGIR.
    if (!ESTADOS_TERMINAIS.has(estado)) return false;
    return true;
  }
  return ESTADOS_TERMINAIS.has(estado);
}

// ---------------------------------------------------------------------------
// O que o formulário precisa recusar ANTES da confirmação
// ---------------------------------------------------------------------------

/**
 * O que o humano digitou, ainda como TEXTO.
 *
 * ⚠️ `peca_versao` é `string` de propósito: é o que um `<input>` entrega, e
 * fingir que já é `number` foi exatamente o que permitiu o campo vazio virar `1`
 * numa conversão escondida. A travessia de texto para contrato acontece num
 * lugar só — `paraPedido`, no cliente — e ela recusa em vez de adivinhar.
 */
export interface RascunhoDoFormulario {
  peca_id: string;
  peca_versao: string;
  autorizacao_id: string;
  destino_id: string;
  modo: ModoDePublicacao;
  timezone: string;
  horario_local: string;
  texto: string;
}

/** Só dígitos. `3.7`, `-1`, `1e3` e `  ` não são versão de peça. */
const _FORMA_DA_VERSAO = /^\s*\d+\s*$/;

/**
 * A versão da peça, ou `null` quando o que foi digitado não é uma versão.
 *
 * ⚠️ DEFEITO MEDIDO (revisão de 02/09/2026): a conversão era
 * `Math.max(1, parseInt(texto, 10) || 1)`. Campo vazio virava `1` em silêncio —
 * o diálogo MOSTRAVA "versão " (vazio) e o corpo ENVIAVA `1`. Num contrato cuja
 * premissa inteira é "a revisão EXATA que a aprovação cobre", publicar a v1
 * porque o campo estava em branco é publicar a peça errada com a aprovação de
 * outra. `rotas.JobEntrada` exige `ge=1` e `dominio.montar_pedido` recusa
 * `peca_versao < 1`: o backend recusaria o zero, mas nunca veria o vazio, porque
 * a tela o convertia antes.
 *
 * Devolver `null` obriga quem chama a decidir. Ninguém normaliza em silêncio.
 */
export function versaoDaPeca(texto: string | number | null | undefined): number | null {
  if (typeof texto === 'number') {
    return Number.isSafeInteger(texto) && texto >= 1 ? texto : null;
  }
  if (typeof texto !== 'string' || !_FORMA_DA_VERSAO.test(texto)) return null;
  const numero = Number.parseInt(texto, 10);
  return Number.isSafeInteger(numero) && numero >= 1 ? numero : null;
}

/**
 * O horário local na forma que o domínio aceita — conferido AQUI, antes do sim.
 *
 * ⚠️ A autoridade continua sendo `dominio.validar_horario_local`; isto é uma
 * cópia do MESMO formato (`AAAA-MM-DD HH:MM[:SS]`, sem fuso no texto) para que a
 * recusa aconteça no formulário e não depois da confirmação. Deixar passar
 * "amanhã cedo" significava abrir o diálogo, mostrar "amanhã cedo (America/
 * Sao_Paulo)" como se fosse um horário, colher o "sim" do humano e só então
 * receber 400 `horario_invalido`. O consentimento teria sido dado para um
 * horário que não existe.
 *
 * ⚠️ A conferência de calendário é feita em `Date.UTC` de propósito: construir
 * `new Date('2026-02-30 10:00')` cairia no fuso de quem lê — a mesma armadilha
 * que `horarioLocalLegivel` evita. Aqui o UTC é só uma calculadora de dias do
 * mês; nenhum instante é derivado dele.
 */
export function horarioLocalValido(texto: string | null | undefined): boolean {
  if (typeof texto !== 'string') return false;
  const achado = _FORMA_DE_HORARIO_LOCAL.exec(texto.trim());
  if (!achado) return false;
  const [, ano, mes, dia, hora, minuto, segundo] = achado.map(Number);
  if (mes < 1 || mes > 12 || dia < 1 || hora > 23 || minuto > 59) return false;
  if (Number.isFinite(segundo) && segundo > 59) return false;
  // ⚠️ `new Date(Date.UTC(50, …))` viraria 1950 — anos de dois dígitos são
  // remapeados. `setUTCFullYear` não faz isso, e a recusa da tela não pode
  // divergir do que `dominio.validar_horario_local` aceitaria.
  const conferencia = new Date(0);
  conferencia.setUTCFullYear(ano, mes - 1, dia);
  return conferencia.getUTCFullYear() === ano
    && conferencia.getUTCMonth() === mes - 1
    && conferencia.getUTCDate() === dia;
}

// ---------------------------------------------------------------------------
// Rótulos e formatação
// ---------------------------------------------------------------------------

export const MODO_ROTULO: Record<string, string> = {
  draft: 'Rascunho no destino',
  schedule: 'Agendado',
  now: 'Publicar agora',
};

/** O que cada modo FAZ, em uma frase, para o diálogo de confirmação. */
export const MODO_CONSEQUENCIA: Record<string, string> = {
  draft: 'Cria um rascunho no destino. Nada fica público, e ninguém vê fora da sua conta.',
  schedule: 'Entrega o post ao destino com data e hora marcadas. Ele sai sozinho no horário.',
  now: 'Publica imediatamente. O post fica visível para o público do canal e não há desfazer '
    + 'que devolva quem já viu.',
};

export const PLATAFORMA_ROTULO: Record<string, string> = {
  facebook: 'Facebook',
  instagram: 'Instagram',
  youtube: 'YouTube',
  tiktok: 'TikTok',
  linkedin: 'LinkedIn',
  x: 'X',
  threads: 'Threads',
  pinterest: 'Pinterest',
};

export const ESTADO_EXTERNO_ROTULO: Record<string, string> = {
  DRAFT: 'Rascunho no destino',
  QUEUE: 'Na fila do destino',
  PUBLISHED: 'Publicado (declarado pelo destino)',
  ERROR: 'Erro no destino',
  DESCONHECIDO: 'Não reconhecido',
};

export function plataformaLegivel(valor?: string | null): string {
  if (!valor) return 'sem plataforma';
  return PLATAFORMA_ROTULO[valor] ?? valor;
}

/** `sha256:a1b2…` ou hex cru viram doze caracteres com reticências. */
export function hashAbreviado(hash?: string | null): string {
  if (!hash) return 'sem hash';
  const separador = hash.indexOf(':');
  const limpo = separador >= 0 ? hash.slice(separador + 1) : hash;
  return limpo.length <= 14 ? limpo : `${limpo.slice(0, 12)}…`;
}

/** Identificador longo (uuid) reduzido ao que um humano consegue conferir. */
export function idAbreviado(id?: string | null): string {
  if (!id) return '—';
  return id.length <= 12 ? id : `${id.slice(0, 8)}…${id.slice(-4)}`;
}

/** `v3 · a1b2c3d4e5f6…` — a revisão exata que a aprovação cobre. */
export function revisaoLegivel(peca?: PecaDoJob | null): string {
  if (!peca) return 'sem peça';
  return `v${peca.versao} · ${hashAbreviado(peca.content_hash)}`;
}

// ⚠️ Os segundos entram como GRUPO (e não como `(?:…)`) porque
// `horarioLocalValido` precisa conferi-los; `horarioLocalLegivel` lê só os
// cinco primeiros grupos e não muda de comportamento com o sexto.
const _FORMA_DE_HORARIO_LOCAL = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?$/;

/**
 * O horário local COMO FOI DECLARADO, com o fuso ao lado.
 *
 * ⚠️ ARMADILHA MEDIDA NO CONTRATO: `new Date('2026-09-05 14:30:00')` interpreta
 * a string no fuso do NAVEGADOR. Um operador em Lisboa veria "18:30" para um
 * job declarado às 14:30 em `America/Sao_Paulo` — o mesmo defeito de duas
 * conversões independentes que a v14_01 evita fazendo `AT TIME ZONE` só no
 * banco. Por isso esta função não constrói `Date` nenhum: ela reordena os
 * dígitos da string e imprime o fuso declarado junto, sempre.
 */
export function horarioLocalLegivel(horario?: string | null, timezone?: string | null): string {
  if (!horario) return 'sem horário declarado';
  const achado = _FORMA_DE_HORARIO_LOCAL.exec(horario.trim());
  const fuso = timezone && timezone.trim() ? timezone : 'fuso não declarado';
  if (!achado) return `${horario} (${fuso})`;
  const [, ano, mes, dia, hora, minuto] = achado;
  return `${dia}/${mes}/${ano} ${hora}:${minuto} (${fuso})`;
}

/**
 * Um instante ABSOLUTO (UTC vindo do banco) no fuso de quem está lendo.
 *
 * Aqui `Date` é correto e necessário: o valor carrega offset, e a pergunta é
 * "que horas eram aqui quando isso aconteceu". É o oposto do caso acima, e a
 * diferença entre as duas funções é a diferença entre um horário DECLARADO e
 * um instante OBSERVADO.
 */
export function instanteLegivel(iso?: string | null): string {
  if (!iso) return '—';
  const data = new Date(iso);
  if (Number.isNaN(data.getTime())) return iso;
  return new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeStyle: 'short' }).format(data);
}
