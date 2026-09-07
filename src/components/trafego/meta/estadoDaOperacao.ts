/**
 * O estado HONESTO de uma operação de nascimento Meta, derivado do recibo durável.
 *
 * ## O defeito que este módulo existe para consertar
 *
 * A tela decidia o desfecho com `steps.every((p) => p.state === 'CREATED')`.
 * `steps` é a lista dos passos que JÁ APARECERAM no livro — não a lista dos
 * passos APROVADOS. Uma Campaign criada de quatro objetos esperados satisfazia
 * o `every()` sozinha, e a bancada escrevia "Criada pausada · 1 de 1" sobre uma
 * campanha que nasceu pela metade.
 *
 * O denominador não pode sair do numerador. Aqui ele vem do manifesto aprovado
 * (`steps_expected` / `operations_expected`), e quando o recibo não o declara a
 * resposta é DESCONHECIDO — nunca sucesso.
 *
 * ## Por que é um módulo puro
 *
 * Toda a matriz — 0/4, 1/4, 3/4, quatro ids sem leitura, divergência, 4/4 — é
 * provável sem DOM, sem React e sem jsdom. O precedente é `rascunho.ts`, que já
 * guarda a lógica pura desta bancada.
 */
import type { TomDoChip } from '@/components/trafego/bancada';
import type {
  EvidenciaDeLeituraMeta,
  PassoDoReciboMeta,
  ReciboCriacaoMeta,
} from '@/lib/pautadorApi';

/** Os estados de um passo, no vocabulário de `MASTER-SPEC.json →
 *  contracts.recovery.step_states`. */
export type EstadoDoPasso =
  | 'NAO_DESPACHADO'      // PREPARED_NOT_DISPATCHED: aprovado, sem linha no livro
  | 'EM_VOO'              // IN_FLIGHT
  | 'CRIADO_SEM_LEITURA'  // CREATED_ID_RECORDED, e nada além disso
  | 'CONFIRMADO'          // READBACK_CONFIRMED
  | 'DIVERGENTE'          // READBACK_DIVERGENT
  | 'AMBIGUO'             // AMBIGUOUS
  | 'RECUSADO'            // REJECTED_PROVEN
  | 'NAO_RECONHECIDO';    // o livro disse algo que esta tela não sabe ler

export interface PassoDaOperacao {
  nome: string;
  estado: EstadoDoPasso;
  /** O livro tem este passo e o manifesto aprovado não o previa. */
  foraDoManifesto: boolean;
  leitura: EvidenciaDeLeituraMeta | null;
  /** `null` = ausência. Nunca "agora": carimbar frescor inventado seria afirmar
   *  uma conferência que ninguém fez. */
  conferidoEm: string | null;
  erroDeLeitura: string | null;
  codigoDeErro: string | null;
  /** Quantos ids um trabalhador SEM autoridade viu neste passo. O número
   *  denuncia a ambiguidade; os ids nunca saem do servidor. */
  idsObservados: number;
}

export type EstadoDaOperacao =
  | { tipo: 'SEM_RECIBO' }
  | { tipo: 'DESCONHECIDO'; motivo: string }
  | { tipo: 'NAO_DESPACHADA' }
  | { tipo: 'EM_CURSO' }
  | { tipo: 'PARCIAL' }
  | { tipo: 'AMBIGUA' }
  | { tipo: 'DIVERGENTE' }
  | { tipo: 'RECUSADA' }
  | { tipo: 'CRIADA_SEM_LEITURA' }
  | { tipo: 'CONFIRMADA' };

export interface LeituraDaOperacao {
  estado: EstadoDaOperacao;
  /** O denominador APROVADO. `null` quando o recibo não o declara — e é esse
   *  `null` que impede a tela de escrever "de 1" e chamar isso de completo. */
  esperados: number | null;
  confirmados: number;
  comIdGravado: number;
  emVoo: number;
  ambiguos: number;
  divergentes: number;
  recusados: number;
  naoDespachados: number;
  passos: PassoDaOperacao[];
}

/** Só estes três nós VEICULAM. O AdCreative nasce ACTIVE por construção e a
 *  Meta nunca o pausa; afirmar "pausado" sobre ele inventaria um fato. */
const VEICULAVEIS = new Set(['campaign', 'adset', 'ad']);

/** `ad:variation-001` → `ad`. O tipo mora antes dos dois pontos. */
export const tipoDoPasso = (nome: string): string => nome.split(':')[0];

export const passoVeicula = (passo: PassoDaOperacao): boolean =>
  VEICULAVEIS.has(passo.leitura?.tipo ?? tipoDoPasso(passo.nome));

/** ⚠️ CONFIRMADO exige AS DUAS coisas: o carimbo de QUANDO se leu e a
 *  afirmação de que a leitura BATEU. Faltando uma, o objeto existe e ninguém
 *  conferiu — e isso é desconhecido, nunca sucesso.
 *
 *  A derivação é a MESMA que o banco publica em `readback_confirmed`. Ela é
 *  refeita aqui a partir dos fatos crus para que um recibo de uma projeção
 *  anterior — sem aquele campo — ainda produza a resposta honesta, em vez de
 *  cair em `undefined` e ser lido como "não confirmado por engano".
 */
function confirmado(linha: PassoDoReciboMeta): boolean {
  if (linha.readback_error) return false;
  return Boolean(linha.readback_at) && linha.readback_evidence?.matched === true;
}

function estadoDoPasso(linha: PassoDoReciboMeta | undefined): EstadoDoPasso {
  // Ausência de linha é ausência de despacho — e é um FATO do manifesto, não
  // uma omissão da tela. O recibo do passo commita ANTES do POST, então não
  // haver linha prova que nenhuma rede saiu por ali.
  if (!linha) return 'NAO_DESPACHADO';
  if (linha.state === 'FAILED') return 'RECUSADO';
  if (linha.state === 'AMBIGUOUS') return 'AMBIGUO';
  if (linha.state === 'IN_FLIGHT') return 'EM_VOO';
  if (linha.state !== 'CREATED') return 'NAO_RECONHECIDO';
  // CREATED sem id é o livro se contradizendo. Não é sucesso e não é rotina.
  if (!linha.has_external_id) return 'NAO_RECONHECIDO';
  if (linha.readback_error || linha.readback_evidence?.matched === false) {
    return 'DIVERGENTE';
  }
  return confirmado(linha) ? 'CONFIRMADO' : 'CRIADO_SEM_LEITURA';
}

export function lerOperacao(recibo: ReciboCriacaoMeta | null): LeituraDaOperacao {
  const vazio = {
    esperados: null as number | null,
    confirmados: 0, comIdGravado: 0, emVoo: 0,
    ambiguos: 0, divergentes: 0, recusados: 0, naoDespachados: 0,
    passos: [] as PassoDaOperacao[],
  };
  if (!recibo) return { ...vazio, estado: { tipo: 'SEM_RECIBO' } };

  const linhas = new Map((recibo.steps ?? []).map((passo) => [passo.name, passo]));
  const manifesto = recibo.steps_expected ?? [];
  const declarado = typeof recibo.operations_expected === 'number'
    ? recibo.operations_expected
    : null;
  // ⚠️ O denominador só existe se o RECIBO o declarar. `steps.length` nunca
  // serve: era exatamente ele que transformava "1 de 4" em "1 de 1".
  const esperados = manifesto.length > 0
    ? manifesto.length
    : (declarado !== null && declarado > 0 ? declarado : null);

  // Primeiro o manifesto aprovado, na ordem aprovada — inclusive os passos que
  // nunca despacharam. Depois qualquer passo que o livro tenha e o manifesto
  // não previa: ele APARECE, e nunca é escondido.
  const extras = (recibo.steps ?? [])
    .map((passo) => passo.name)
    .filter((nome) => !manifesto.includes(nome));
  const nomes = manifesto.length > 0 ? [...manifesto, ...extras] : extras;

  const passos: PassoDaOperacao[] = nomes.map((nome) => {
    const linha = linhas.get(nome);
    return {
      nome,
      estado: estadoDoPasso(linha),
      foraDoManifesto: manifesto.length > 0 && !manifesto.includes(nome),
      leitura: linha?.readback_evidence ?? null,
      conferidoEm: linha?.readback_at ?? null,
      erroDeLeitura: linha?.readback_error ?? null,
      codigoDeErro: linha?.error_code ?? null,
      idsObservados: linha?.observed_external_id_count ?? 0,
    };
  });

  const conta = (alvo: EstadoDoPasso) =>
    passos.filter((passo) => passo.estado === alvo).length;
  // Sem os NOMES do manifesto ainda existe o NÚMERO: a diferença entre o
  // aprovado e o que tem linha no livro é passo não despachado do mesmo jeito.
  // Ele some da tabela sem sumir da conta, e a contagem precisa dizê-lo.
  const semLinha = esperados === null ? 0 : Math.max(0, esperados - passos.length);
  const confirmados = conta('CONFIRMADO');
  const divergentes = conta('DIVERGENTE');
  const base: Omit<LeituraDaOperacao, 'estado'> = {
    esperados,
    confirmados,
    comIdGravado: confirmados + conta('CRIADO_SEM_LEITURA') + divergentes,
    emVoo: conta('EM_VOO'),
    ambiguos: conta('AMBIGUO'),
    divergentes,
    recusados: conta('RECUSADO'),
    naoDespachados: conta('NAO_DESPACHADO') + semLinha,
    passos,
  };

  // ⚠️ A ORDEM DAS PERGUNTAS É A CORREÇÃO. Ela vai do que PROÍBE reenviar para
  // o que autoriza descansar, e nunca o contrário: o primeiro `if` que acerta é
  // a frase que o operador lê. Perguntar "está tudo criado?" primeiro é o que
  // fazia órfão, ambiguidade e divergência sumirem atrás de uma frase verde.
  if (esperados === null) {
    return {
      ...base,
      estado: {
        tipo: 'DESCONHECIDO',
        motivo: 'o recibo não declara quantas operações foram aprovadas',
      },
    };
  }
  if (manifesto.length > 0 && declarado !== null && declarado !== manifesto.length) {
    return {
      ...base,
      estado: {
        tipo: 'DESCONHECIDO',
        motivo: 'o recibo se contradiz sobre quantas operações foram aprovadas',
      },
    };
  }
  if (passos.some((p) => p.foraDoManifesto || p.estado === 'NAO_RECONHECIDO')) {
    return {
      ...base,
      estado: {
        tipo: 'DESCONHECIDO',
        motivo: 'o livro tem passo que o manifesto aprovado não previa',
      },
    };
  }
  if (base.ambiguos > 0) return { ...base, estado: { tipo: 'AMBIGUA' } };
  if (base.divergentes > 0) return { ...base, estado: { tipo: 'DIVERGENTE' } };
  if (base.recusados > 0) return { ...base, estado: { tipo: 'RECUSADA' } };
  if (base.emVoo > 0) return { ...base, estado: { tipo: 'EM_CURSO' } };
  if (base.naoDespachados === esperados) {
    return { ...base, estado: { tipo: 'NAO_DESPACHADA' } };
  }
  if (base.confirmados === esperados) return { ...base, estado: { tipo: 'CONFIRMADA' } };
  if (base.comIdGravado === esperados) {
    return { ...base, estado: { tipo: 'CRIADA_SEM_LEITURA' } };
  }
  return { ...base, estado: { tipo: 'PARCIAL' } };
}

/** A frase do desfecho. Uma por estado — e a CONTAGEM não entra aqui: ela mora
 *  nas linhas de fato. Misturar as duas faria "4 de 4" existir em dois lugares,
 *  e nenhum dos dois dizendo exatamente o que o outro diz. */
export function fraseDaOperacao(leitura: LeituraDaOperacao): string {
  const estado = leitura.estado;
  switch (estado.tipo) {
    case 'SEM_RECIBO': return 'Sem recibo desta operação';
    case 'DESCONHECIDO': return `Estado desconhecido · ${estado.motivo}`;
    case 'NAO_DESPACHADA': return 'Aprovada · nenhum passo despachado ainda';
    case 'EM_CURSO': return 'Em curso · há despacho sem conclusão registrada';
    case 'PARCIAL': return 'Parcial · nem todos os passos aprovados existem';
    case 'AMBIGUA': return 'Ambígua · há passo que pode existir sem prova';
    case 'DIVERGENTE': return 'Divergente · existe e não confere com o aprovado';
    case 'RECUSADA': return 'Recusada pela Meta · está provado que não nasceu';
    case 'CRIADA_SEM_LEITURA': return 'Criada pausada · leitura de volta não conferida';
    case 'CONFIRMADA': return 'Criada pausada e conferida';
  }
}

/** ⚠️ SÓ `CONFIRMADA` é `verificado`. Verificado afirma que a fonte foi
 *  OBSERVADA — quatro ids gravados sem leitura é o que a conta devolveu, não o
 *  que alguém conferiu. */
export const TOM_DA_OPERACAO: Record<EstadoDaOperacao['tipo'], TomDoChip> = {
  SEM_RECIBO: 'neutro',
  DESCONHECIDO: 'atencao',
  NAO_DESPACHADA: 'neutro',
  EM_CURSO: 'atencao',
  PARCIAL: 'atencao',
  AMBIGUA: 'atencao',
  DIVERGENTE: 'atencao',
  RECUSADA: 'ruim',
  CRIADA_SEM_LEITURA: 'atencao',
  CONFIRMADA: 'verificado',
};

/** Estado de cada passo, em palavra e tom — nunca só por cor.
 *
 * ⚠️ `AMBIGUO` NÃO é um erro, e a palavra tem de dizer isso: o objeto pode
 * existir na conta. Chamá-lo de "falhou" convidaria exatamente a reação errada,
 * que é tentar de novo. As frases de `AMBIGUO` e `RECUSADO` vieram da bancada
 * palavra por palavra: elas já impediam a reação errada. */
export const PALAVRA_DO_PASSO: Record<EstadoDoPasso, string> = {
  NAO_DESPACHADO: 'não despachado',
  EM_VOO: 'despachado, sem conclusão',
  CRIADO_SEM_LEITURA: 'criado · leitura não conferida',
  CONFIRMADO: 'criado pausado e conferido',
  DIVERGENTE: 'existe e não confere',
  AMBIGUO: 'ambíguo · pode existir',
  RECUSADO: 'recusado pela Meta',
  NAO_RECONHECIDO: 'estado não reconhecido',
};

export const TOM_DO_PASSO: Record<EstadoDoPasso, TomDoChip> = {
  NAO_DESPACHADO: 'neutro',
  EM_VOO: 'atencao',
  CRIADO_SEM_LEITURA: 'atencao',
  CONFIRMADO: 'verificado',
  DIVERGENTE: 'atencao',
  AMBIGUO: 'atencao',
  RECUSADO: 'ruim',
  NAO_RECONHECIDO: 'atencao',
};

/** O que a palavra AFIRMA — vai para o leitor de tela, não só para o `title`.
 *
 * ⚠️ Cada frase existe para impedir a reação errada. "Ambíguo" sem explicação
 * convida a tentar de novo; com a explicação, convida a reconciliar. */
export const DESCRICAO_DO_PASSO: Record<EstadoDoPasso, string> = {
  NAO_DESPACHADO:
    'este passo foi aprovado e não tem linha no livro; nada saiu por ele',
  EM_VOO:
    'o pedido saiu e a conclusão não foi registrada; o objeto pode existir na conta',
  CRIADO_SEM_LEITURA:
    'o objeto existe na conta e a leitura que confirmaria o que ele é não foi '
    + 'gravada; existir não é o mesmo que estar conferido',
  CONFIRMADO:
    'o objeto existe na conta, nasceu pausado, e a leitura ficou gravada com horário',
  DIVERGENTE:
    'o objeto existe e não é o que foi aprovado; não criar substituto, não ativar '
    + 'e não esconder a divergência',
  AMBIGUO:
    'não está provado se o objeto existe; reconciliar por leitura é o caminho, '
    + 'e reenviar duplicaria',
  RECUSADO: 'a Meta recusou o pedido, então está provado que nada foi criado',
  NAO_RECONHECIDO:
    'o livro devolveu um estado que esta tela não sabe ler; nada pode ser '
    + 'concluído a partir dele',
};
