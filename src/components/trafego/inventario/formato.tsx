/**
 * Como um fato do inventário vira texto na tela.
 *
 * Tudo que decide COMO um número aparece mora aqui, e não espalhado pelas
 * linhas, por um motivo só: as três regras do módulo são regras de
 * APRESENTAÇÃO, e se cada componente formatar do seu jeito uma delas some sem
 * ninguém perceber.
 *
 *  1. ausência é `null` e aparece como `—`; zero aparece como `0`;
 *  2. medida sem data de leitura não é medida — não é exibida como se fosse;
 *  3. moeda não declarada é dita, nunca assumida como real.
 *
 * Nenhuma função daqui inventa valor. `—` é o resultado honesto de "não sei".
 */
import { canalCanonico, type Canal } from '@/types/trafego';
import type {
  EstadoDePresenca,
  EstrategiaDeLance,
  Frescor,
  Procedencia,
} from '@/types/trafego';

/** O travessão que significa "não foi possível medir". Nunca `0`, nunca vazio. */
export const AUSENTE = '—';

/** A marca de que o valor é real e a UNIDADE dele é que não foi declarada. */
export const SEM_MOEDA = '(sem moeda declarada)';

/** O `Intl` de moeda usa espaço fino inquebrável; ele atrapalha busca e cópia. */
const semEspacoDuro = (s: string): string => s.replace(/[  ]/g, ' ');

/**
 * Micros viram dinheiro legível.
 *
 * A conta guarda micros porque centavo em ponto flutuante some. A divisão por
 * um milhão acontece aqui, uma vez, e o resultado sai com a moeda da conta —
 * ou com o aviso de que ela não foi declarada, que é diferente de ser real.
 */
export function dinheiro(micros: number | null, moeda: string | null): string {
  if (micros == null) return AUSENTE;
  const valor = micros / 1_000_000;
  if (!moeda) {
    // ⚠️ O número puro era mentira por omissão: `0,12` ao lado de `R$ 10,00` na
    // mesma coluna lê-se como reais, e ninguém repara que aquela linha veio sem
    // unidade. Como o valor É fato (a conta informou o micros) e a moeda NÃO é,
    // os dois viajam juntos e a falta fica dita na própria célula — o mesmo
    // princípio de `—` para ausência, aplicado à unidade em vez do valor.
    return `${semEspacoDuro(
      new Intl.NumberFormat('pt-BR', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }).format(valor),
    )} ${SEM_MOEDA}`;
  }
  try {
    return semEspacoDuro(
      new Intl.NumberFormat('pt-BR', {
        style: 'currency',
        currency: moeda,
        minimumFractionDigits: 2,
      }).format(valor),
    );
  } catch {
    // Código de moeda que o navegador não conhece não pode derrubar a linha
    // inteira: o número é fato, o símbolo é enfeite.
    //
    // ⚠️ `maximumFractionDigits` é obrigatório aqui. Sem ele o `Intl` usa o
    // padrão de número decimal — TRÊS casas — e a mesma coluna passava a ter
    // linhas com duas e linhas com três casas, dependendo só de o navegador
    // conhecer o código da moeda. Numa coluna de custo isso lê-se como valor
    // dez vezes maior por um instante, que é tempo suficiente para uma decisão
    // de gasto errada.
    return `${semEspacoDuro(
      new Intl.NumberFormat('pt-BR', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }).format(valor),
    )} ${moeda}`;
  }
}

/** Contagem inteira. `0` sobrevive; `null` vira travessão. */
export function contagem(n: number | null): string {
  if (n == null) return AUSENTE;
  return new Intl.NumberFormat('pt-BR').format(n);
}

/**
 * Idade em linguagem de operação.
 *
 * O operador não quer o carimbo ISO: ele quer saber se pode confiar no número
 * agora. "há 6 min" responde isso; "2026-08-24T17:03:11Z" obriga a fazer a
 * conta de cabeça no meio de uma decisão de gasto.
 */
export function idade(segundos: number | null): string {
  if (segundos == null) return 'sem data de leitura';
  // ⚠️ Idade negativa é relógio fora de sincronia, e ela NÃO pode cair no ramo
  // do `agora`: um carimbo de leitura duas horas no futuro daria a resposta
  // mais tranquilizadora possível — "agora" — para o caso em que a data não
  // vale nada. É a mesma lei do módulo aplicada ao tempo: desconhecido nunca
  // degrada para recente. A tolerância de dois minutos existe porque diferença
  // pequena entre o relógio do servidor e o desta máquina é normal e não
  // muda decisão nenhuma.
  if (segundos < -120) return 'em data futura — relógio fora de sincronia';
  if (segundos < 90) return 'agora';
  const minutos = Math.round(segundos / 60);
  if (minutos < 60) return `há ${minutos} min`;
  const horas = Math.round(segundos / 3600);
  if (horas < 36) return `há ${horas} h`;
  return `há ${Math.round(segundos / 86400)} dias`;
}

/** "lido há 6 min" — a frase que acompanha todo número desta tela. */
export function lidoHa(segundos: number | null): string {
  return segundos == null ? 'sem data de leitura' : `lido ${idade(segundos)}`;
}

/** Hora local curta, para quando o operador quer o instante e não a distância. */
export function horaDeLeitura(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return semEspacoDuro(
    d.toLocaleString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    }),
  );
}

/**
 * O instante completo, com segundos — para o texto que sai da tela.
 *
 * `horaDeLeitura` é o que o operador LÊ: dia, mês e hora bastam para decidir se
 * confia num número. Este aqui é o que ele COPIA quando pede ajuda, e do outro
 * lado alguém vai procurar a ocorrência num log onde cabem muitas linhas dentro
 * do mesmo minuto. Ano e segundos não ajudam a decidir gasto e por isso não
 * aparecem na tela; ajudam a achar a linha e por isso existem aqui.
 */
export function horaExata(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return semEspacoDuro(
    d.toLocaleString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    }),
  );
}

// ── vocabulário ─────────────────────────────────────────────────────────────
// Mapas, não `if`. Um `switch (canal)` dentro do layout é o começo de uma tela
// por canal — e a arquitetura do Hub proíbe isso: o núcleo é canal-agnóstico e
// o canal só injeta o próprio valor.

export const PALAVRA_DO_CANAL: Record<Canal, string> = {
  SEARCH: 'busca',
  DISPLAY: 'display',
  DEMAND_GEN: 'demand gen',
  PERFORMANCE_MAX: 'performance max',
  VIDEO: 'vídeo',
  SHOPPING: 'shopping',
};

export const PALAVRA_DA_ESTRATEGIA: Record<EstrategiaDeLance, string> = {
  MANUAL_CPC: 'CPC manual',
  MAXIMIZE_CONVERSIONS: 'maximizar conversões',
};

/**
 * ⚠️ POR QUE TODO ACESSO A ESTES MAPAS PASSA POR UMA FUNÇÃO.
 *
 * Os mapas são `Record<UniãoFechada, …>` e o TypeScript garante a completude —
 * em tempo de COMPILAÇÃO. Em tempo de execução o valor vem do servidor, e o
 * servidor pode ganhar um canal, uma estratégia ou um estado novo antes deste
 * pacote ser publicado. `MAPA[valor]` devolveria `undefined`, e `undefined` no
 * JSX não quebra a tela: some caladinho. Uma campanha de canal desconhecido
 * apareceria sem canal nenhum, indistinguível de uma campanha sem canal.
 *
 * Estas funções trocam esse silêncio por uma frase: o valor cru aparece, dito
 * como não reconhecido. É a mesma escolha do resto do módulo — declarar o que
 * não se sabe em vez de apagar.
 */
export function palavraDoCanal(canal: string | null): string | null {
  if (!canal) return null;
  const conhecido = canalCanonico(canal);
  if (conhecido) return PALAVRA_DO_CANAL[conhecido];
  return `canal ${canal.toLowerCase()} (não reconhecido)`;
}

export function palavraDaEstrategia(estrategia: string | null): string {
  if (!estrategia) return AUSENTE;
  return (
    PALAVRA_DA_ESTRATEGIA[estrategia as EstrategiaDeLance] ??
    `${estrategia.toLowerCase()} (estratégia não reconhecida)`
  );
}

export function palavraDaVeiculacao(veiculacao: string | null): string | null {
  if (!veiculacao) return null;
  return PALAVRA_DA_VEICULACAO[veiculacao] ?? `${veiculacao.toLowerCase()} (não reconhecida)`;
}

/**
 * Estado do lado do Google, na palavra do Google.
 *
 * `ENABLED` fica `ENABLED` de propósito: é exatamente o que o operador lê no
 * painel do Google, e traduzir criaria dois vocabulários para o mesmo fato.
 * A descrição em português vem junto, para o estado não depender de decorar.
 */
export const DESCRICAO_DO_ESTADO_EXTERNO: Record<string, string> = {
  ENABLED: 'ligada no Google',
  PAUSED: 'pausada no Google',
  REMOVED: 'removida no Google',
};

/** Se está de fato entregando, quando a conta informa. */
export const PALAVRA_DA_VEICULACAO: Record<string, string> = {
  SERVING: 'entregando',
  NOT_SERVING: 'não entrega',
  ELIGIBLE: 'elegível',
  PENDING: 'ainda não começou',
  ENDED: 'encerrada',
  PAUSED: 'pausada',
  REMOVED: 'removida',
  SUSPENDED: 'suspensa',
};

/** Estado de presença: palavra curta + o que ela afirma, e só o que ela afirma. */
export const PRESENCA: Record<EstadoDePresenca, { palavra: string; descricao: string }> = {
  presente: {
    palavra: 'presente',
    descricao: 'a conta respondeu e esta campanha estava na resposta',
  },
  removida: {
    palavra: 'removida',
    descricao: 'a conta respondeu e declara esta campanha como removida',
  },
  nao_encontrada: {
    palavra: 'não encontrada',
    descricao: 'a conta foi lida com sucesso e esta campanha não estava na resposta',
  },
  conta_nao_identificada: {
    palavra: 'conta não identificada',
    descricao: 'a linha existe no nosso registro sem conta utilizável — não sabemos onde procurar',
  },
  fora_de_escopo: {
    palavra: 'fora de escopo',
    descricao: 'a conta existe, mas não é uma das contas da casa',
  },
  sincronizacao_falhou: {
    palavra: 'sincronização falhou',
    descricao: 'não foi possível ler a conta — não dá para afirmar presença nem ausência',
  },
  legado_nao_reconciliado: {
    palavra: 'legado não reconciliado',
    descricao: 'veio de antes do inventário e nunca foi conferido contra a conta',
  },
};

/** Selo de procedência, no vocabulário do SPEC: registrada · sem procedência. */
export const PROCEDENCIA: Record<Procedencia, { palavra: string; descricao: string }> = {
  volc_os: {
    palavra: 'registrada',
    descricao: 'nasceu por aqui, com recibo de lançamento',
  },
  descoberta: {
    palavra: 'encontrada na conta',
    descricao: 'apareceu numa leitura da conta; não foi criada por aqui',
  },
  legado: {
    palavra: 'legado',
    descricao: 'veio do sistema antigo, sem recibo de origem',
  },
  desconhecida: {
    palavra: 'sem procedência',
    descricao: 'não sabemos como esta campanha entrou no registro',
  },
};

/** Frescor da conta. `nunca lido` e `nenhuma campanha` NÃO são a mesma coisa. */
export const FRESCOR: Record<Frescor, { palavra: string; descricao: string }> = {
  recente: {
    palavra: 'leitura recente',
    descricao: 'a conta respondeu e o dado é atual',
  },
  velho: {
    palavra: 'leitura antiga',
    descricao: 'a última leitura boa já tem idade — confira antes de decidir gasto',
  },
  parcial: {
    palavra: 'leitura parcial',
    descricao: 'parte do que esta conta tem não pôde ser lida',
  },
  falhou: {
    palavra: 'sincronização falhou',
    descricao: 'a última tentativa de ler esta conta não deu certo',
  },
  nunca_lido: {
    palavra: 'nunca lido',
    descricao: 'ainda não perguntamos nada a esta conta — não é o mesmo que estar vazia',
  },
  vazio_confirmado: {
    palavra: 'nenhuma campanha',
    descricao: 'a conta respondeu e não há campanha nenhuma nela — isto é um fato medido',
  },
};

/**
 * ⚠️ POR QUE ESTAS TRÊS FUNÇÕES EXISTEM, E POR QUE `presente` MORA NO MAPA.
 *
 * Houve um período em que `presente` era o SÉTIMO estado: o contrato fechava em
 * seis valores, todos descrevendo ausência ou dúvida, e nenhum nomeava o caso
 * normal. `presencaLegivel` resolvia isso com um `if` antes do mapa. O contrato
 * ganhou a sétima linha (`EstadoDePresenca` inclui `presente`), o mapa ganhou a
 * entrada — e o `if` ficou, respondendo `presente` enquanto o mapa dizia
 * `na conta`. Duas respostas para o mesmo estado, uma delas inalcançável: o
 * jeito mais discreto de um vocabulário fechado passar a ter duas palavras.
 *
 * Agora o mapa é a única fonte, e a função existe por outro motivo — o mesmo
 * dos `palavraDo*` acima: o servidor pode mandar uma palavra que este pacote
 * ainda não conhece, e a tela precisa dizer isso em vez de quebrar ou apagar a
 * linha. A campanha desconhecida continua visível; as outras quarenta ao lado
 * dela também.
 */
export function presencaLegivel(valor: string): { palavra: string; descricao: string } {
  return (
    PRESENCA[valor as EstadoDePresenca] ?? {
      palavra: 'presença não reconhecida',
      descricao: `o servidor informou "${valor}", que não está no vocabulário desta tela`,
    }
  );
}

export function procedenciaLegivel(valor: string): { palavra: string; descricao: string } {
  return (
    PROCEDENCIA[valor as Procedencia] ?? {
      palavra: 'procedência não reconhecida',
      descricao: `o servidor informou "${valor}", que não está no vocabulário desta tela`,
    }
  );
}

/**
 * ⚠️ Frescor desconhecido NUNCA degrada para `recente`.
 *
 * É a degradação mais cara do módulo: um estado de leitura que esta tela não
 * conhece, tratado como recente, faz o operador decidir gasto olhando para um
 * número de idade desconhecida achando que olha para agora. Desconhecido aqui
 * significa "não sei quando isto foi lido", e é assim que precisa ser lido.
 */
export function frescorLegivel(valor: string): { palavra: string; descricao: string } {
  return (
    FRESCOR[valor as Frescor] ?? {
      palavra: 'leitura não reconhecida',
      descricao:
        `o servidor informou o estado de leitura "${valor}", que esta tela não conhece — ` +
        'não dá para afirmar que este número é recente',
    }
  );
}

export function ehFrescorConhecido(valor: string): valor is Frescor {
  return Object.prototype.hasOwnProperty.call(FRESCOR, valor);
}
