/**
 * A leitura do veredito da sentinela — puro, sem React e sem HTTP.
 *
 * ## A lei desta tela, em uma frase
 *
 * Nenhum estado que esta versão não conhece pode sair `bom`. É a mesma regra
 * que `vocabulario.ts` já aplica aos degraus, e ela existe porque o servidor
 * pode ganhar um estado antes deste pacote: uma tela que degrada o
 * desconhecido para verde é a forma mais silenciosa desta superfície mentir.
 *
 * ## O que este módulo NÃO faz
 *
 * Não decide veredito. `vereditoDaEscada` (em `./escada`) continua existindo e
 * responde outra pergunta — *até onde a escada foi lida com confiança* — que é
 * sobre os degraus, não sobre a campanha. Reimplementar aqui a precedência
 * causal que o backend já aplica é como a tela e o alerta passam a discordar
 * sem que exista resposta certa entre os dois.
 */
import type {
  CausaDaSentinela,
  DenominadorDaSentinela,
  JanelaDoGuardiao,
  QuadroDeRecomendacoes,
  SeveridadeDaSentinela,
  StatusDaSentinela,
  VeredictoDaSentinela,
} from '@/types/diagnostico';
import type { Tom } from '@/components/trafego/inventario/Selos';

/** O que cada status AFIRMA, em linguagem de operação. */
export interface LeituraDoStatus {
  /** O título. Uma frase curta que o operador lê primeiro. */
  titulo: string;
  /** O que este status afirma — e o que ele não afirma. */
  afirma: string;
  tom: Tom;
  /** `true` quando o estado pede alguém agora. */
  pedeAlguem: boolean;
}

export const STATUS: Record<string, LeituraDoStatus> = {
  ACCOUNT_BLOCKED: {
    titulo: 'Conta de anúncio bloqueada',
    afirma:
      'a conta não pode veicular. Lance, orçamento e Quality Score desta ' +
      'campanha são história enquanto isto não mudar — nenhum ajuste aqui a ' +
      'faz voltar a entregar.',
    tom: 'ruim',
    pedeAlguem: true,
  },
  ACCESS_UNAVAILABLE: {
    titulo: 'Sem acesso à conta',
    afirma:
      'a conta recusou a leitura. Não sabemos nada sobre esta campanha agora, ' +
      'e não saber não é o mesmo que estar bem.',
    tom: 'ruim',
    pedeAlguem: true,
  },
  POLICY_BLOCKED: {
    titulo: 'Bloqueado por política',
    afirma:
      'algo foi reprovado — destino, anúncio ou keyword. Ajustar campanha não ' +
      'resolve reprovação.',
    tom: 'ruim',
    pedeAlguem: true,
  },
  POLICY_REVIEW: {
    titulo: 'Em revisão pelo Google',
    afirma:
      'não está aprovado e não está reprovado. Afirmar qualquer um dos dois ' +
      'seria inventar um veredito que o Google ainda não deu.',
    tom: 'atencao',
    pedeAlguem: true,
  },
  DATA_UNAVAILABLE: {
    titulo: 'Não foi possível apurar',
    afirma:
      'a leitura falhou, está velha ou nunca aconteceu. Isto NÃO afirma que a ' +
      'campanha esteja bem.',
    tom: 'atencao',
    pedeAlguem: true,
  },
  CAMPAIGN_OFF: {
    titulo: 'Campanha desligada',
    afirma:
      'alguém desligou. Não gastar é o comportamento esperado de uma campanha ' +
      'desligada, e não é falha.',
    tom: 'neutro',
    pedeAlguem: false,
  },
  ADS_NOT_READY: {
    titulo: 'Nenhum anúncio apto',
    afirma:
      'sem anúncio o leilão nem começa. Mexer em lance antes disto é consertar ' +
      'o telhado de uma casa sem parede.',
    tom: 'ruim',
    pedeAlguem: true,
  },
  NO_DELIVERY: {
    titulo: 'Ligada e sem entregar',
    afirma:
      'a campanha está ligada, já passou da carência, a leitura é fresca e a ' +
      'conta mediu zero impressões.',
    tom: 'ruim',
    pedeAlguem: true,
  },
  LIMITED_BY_BUDGET: {
    titulo: 'Limitada por orçamento',
    afirma: 'a conta MEDIU perda de participação por verba.',
    tom: 'atencao',
    pedeAlguem: true,
  },
  LIMITED_BY_RANK: {
    titulo: 'Limitada por classificação',
    afirma:
      'a campanha entra no leilão e perde posição. Lance e qualidade decidem ' +
      'isto, não verba.',
    tom: 'atencao',
    pedeAlguem: true,
  },
  KEYWORD_STRUCTURE_RISK: {
    titulo: 'Estrutura de keywords em risco',
    afirma:
      'há redundância, baixa qualidade ou keywords raramente servidas. É risco ' +
      'observado, não causa provada de não entregar.',
    tom: 'atencao',
    pedeAlguem: true,
  },
  MEASUREMENT_NOT_READY: {
    titulo: 'Medição incompatível com o lance',
    afirma:
      'a estratégia depende de conversão medida, e a medição não está pronta. ' +
      'O lance automático otimiza contra um sinal que não existe.',
    tom: 'atencao',
    pedeAlguem: true,
  },
  LOW_DEMAND: {
    titulo: 'Demanda baixa',
    afirma:
      'há pouca busca para o que esta campanha disputa. Nada está travado, e ' +
      'não há muito a ganhar aqui.',
    tom: 'neutro',
    pedeAlguem: true,
  },
  LEARNING: {
    titulo: 'Em aprendizado',
    afirma:
      'a estratégia de lance está aprendendo. Alterar lance agora reinicia o ' +
      'aprendizado.',
    tom: 'neutro',
    pedeAlguem: false,
  },
  OBSERVING: {
    titulo: 'Em observação',
    afirma:
      'ainda dentro da janela em que zero entrega é esperado. Não há conclusão ' +
      'aqui — e não há problema declarado.',
    tom: 'neutro',
    pedeAlguem: false,
  },
  HEALTHY: {
    titulo: 'Nada pede atenção',
    afirma:
      'a evidência está completa e fresca, e nenhuma das causas conhecidas se ' +
      'aplica nesta janela.',
    tom: 'bom',
    pedeAlguem: false,
  },
};

/**
 * Consulta tolerante ao vocabulário novo.
 *
 * ⚠️ O fallback é `atencao`, NUNCA `bom`. O comentário existe porque o inverso
 * é tentador e errado: um veredito que a tela não conhece degradando para
 * "nada pede atenção" transforma a chegada de um estado novo num apagão de
 * alerta silencioso.
 */
export function leituraDoStatus(valor: string): LeituraDoStatus {
  return (
    STATUS[valor] ?? {
      titulo: 'Estado não reconhecido',
      afirma:
        `o sistema informou "${valor}", que esta versão da tela não conhece. ` +
        'Isto não afirma que a campanha esteja bem.',
      tom: 'atencao' as Tom,
      pedeAlguem: true,
    }
  );
}

/** O escopo, em português. Ele diz QUEM age, não só onde dói. */
export const ESCOPO: Record<string, string> = {
  account: 'conta de anúncio',
  campaign: 'campanha',
  ad_group: 'grupo de anúncios',
  ad: 'anúncio',
  keyword: 'keyword',
  measurement: 'medição',
  destination: 'destino',
};

export function escopoLegivel(valor: string): string {
  return ESCOPO[valor] ?? `nível não reconhecido ("${valor}")`;
}

/** A janela do guardião, dita como fase da vida da campanha. */
export const JANELA: Record<string, { rotulo: string; descricao: string }> = {
  nascimento: {
    rotulo: 'nascendo',
    descricao: 'dentro da carência: zero entrega aqui é o esperado',
  },
  ate_24h: {
    rotulo: 'primeiras 24 horas',
    descricao: 'já saiu da carência e ainda não é hora de concluir',
  },
  '24_72h': {
    rotulo: '24 a 72 horas',
    descricao: 'a janela em que a ausência de entrega passa a ser incidente',
  },
  apos_72h: {
    rotulo: 'operação contínua',
    descricao: 'passou das primeiras 72 horas',
  },
  indeterminada: {
    rotulo: 'idade desconhecida',
    descricao:
      'não sabemos desde quando está ligada — e isso NÃO é o mesmo que ' +
      'recém-criada. Sem esse número, ausência de entrega não vira incidente',
  },
};

export function janelaLegivel(valor: JanelaDoGuardiao | string): {
  rotulo: string;
  descricao: string;
} {
  return (
    JANELA[valor] ?? {
      rotulo: 'janela não reconhecida',
      descricao: `o sistema informou "${valor}", que esta versão não conhece`,
    }
  );
}

/** A severidade, com o tom que ela pede. Desconhecida nunca é `bom`. */
export function tomDaSeveridade(valor: SeveridadeDaSentinela | string): Tom {
  switch (valor) {
    case 'critica':
    case 'alta':
      return 'ruim';
    case 'media':
    case 'baixa':
      return 'atencao';
    case 'informativa':
      return 'neutro';
    default:
      return 'atencao';
  }
}

/**
 * O veredito pode ser lido como boa notícia?
 *
 * ⚠️ TRÊS condições, e as três são necessárias.
 *
 * A versão anterior tinha duas e um comentário que prometia uma "tranca do
 * frescor" que não existia no código: `HEALTHY` + `apurada` + `frescor:'velho'`
 * saía verde. É o falso verde mais caro possível — a conclusão certa, com a
 * prova completa, sobre um retrato de ontem. O próprio `types/diagnostico.ts`
 * já dizia a regra em prosa: *"Leitura velha ou sem carimbo nunca autoriza um
 * degrau `ok`"*. Agora ela é código.
 *
 * `nao_apurado` cai fora junto com `velho`: um frescor que não se sabe não é
 * um frescor bom.
 */
export function podeSerLidoComoBom(v: VeredictoDaSentinela): boolean {
  return (
    v.status === 'HEALTHY' &&
    v.estado_da_evidencia === 'apurada' &&
    v.frescor === 'recente'
  );
}

/** O tom final do veredito, já com a tranca do frescor aplicada. */
export function tomDoVeredito(v: VeredictoDaSentinela): Tom {
  if (podeSerLidoComoBom(v)) return 'bom';
  const doStatus = leituraDoStatus(v.status).tom;
  return doStatus === 'bom' ? 'atencao' : doStatus;
}

/** Todas as causas em ordem: a primária primeiro, depois as secundárias. */
export function causasEmOrdem(v: VeredictoDaSentinela): CausaDaSentinela[] {
  return v.causa_primaria ? [v.causa_primaria, ...v.causas_secundarias] : [...v.causas_secundarias];
}

/**
 * A frase de uma contagem, sempre com o denominador visível.
 *
 * O backend já a monta; esta função existe para o caso de `frase` vir vazia de
 * uma versão futura — e mesmo aí ela NÃO emite percentual sem denominador.
 */
export function fraseDoDenominador(d: DenominadorDaSentinela): string {
  if (d.frase) return d.frase;
  const base = `${d.quantos} de ${d.de_quantos} ${d.unidade} ${d.rotulo}`;
  return d.fora_da_conta
    ? `${base}; ${d.fora_da_conta} sem dado suficiente, fora desta conta`
    : base;
}

/**
 * O que dizer sobre as recomendações do Google — sem transformar ausência de
 * leitura em ausência de recomendação.
 */
export function fraseDasRecomendacoes(q: QuadroDeRecomendacoes): string {
  if (!q.apurado) {
    return (
      'não foi possível apurar as recomendações do Google nesta leitura — ' +
      'isto NÃO significa que não haja nenhuma'
    );
  }
  if (!q.quantidade) return 'o Google não sugeriu nada nesta leitura';
  const plural = q.quantidade === 1 ? 'recomendação registrada' : 'recomendações registradas';
  return `${q.quantidade} ${plural}, nenhuma aplicada`;
}

/** Os status que a fila de atenção deve destacar. */
export function ehIncidente(v: VeredictoDaSentinela): boolean {
  return v.incidente;
}

export type { StatusDaSentinela, VeredictoDaSentinela };
