/**
 * O tri-state de conversão, num lugar só (`A12`).
 *
 * ## Por que dois eixos, e não um selo
 *
 * `trafego/meta/dominio.py` separa três respostas que o código antigo achatava
 * em duas: SIM, NÃO e NÃO SEI. E separa ainda um quarto fato — o FRESCOR — que
 * é ortogonal à elegibilidade:
 *
 *   · ELEGIBILIDADE  — a conversão pode ser escolhida para otimizar?
 *   · FRESCOR        — a Meta já viu esse evento disparar, e quando?
 *
 * `UNKNOWN_FRESHNESS` é o caso que prova a separação: o objeto EXISTE e é
 * elegível; o que falta é o carimbo do último disparo. Fundir os dois eixos num
 * selo só faria essa conversão parecer inelegível — e faria `UNKNOWN`, que é
 * "a Meta não devolveu a flag", parecer só mais um amarelo entre amarelos.
 *
 * ## ⚠️ A LISTA DE ELEGÍVEIS É POSITIVA
 *
 * "Tudo menos ARCHIVED" transformaria cada estado novo do provedor em elegível
 * por omissão. Um estado que este arquivo não conhece cai no ramo desconhecido,
 * que é o ramo seguro: exibido, contado, e nunca oferecido.
 */
import { CircleAlert, CircleCheck, CircleDot, CircleHelp, TriangleAlert } from 'lucide-react';
import type React from 'react';

import type { TomDoChip } from '@/components/trafego/bancada';
import type { ConversaoPersonalizadaMetaLocal, EstadoDaConversaoMeta } from '@/lib/pautadorApi';

export interface LeituraDaConversao {
  /** Palavra do estado. Nunca só cor. */
  palavra: string;
  /** O que a palavra AFIRMA — vai para o leitor de tela, não só para o `title`. */
  descricao: string;
  tom: TomDoChip;
  glifo: React.ComponentType<{ className?: string }>;
  /** Pode ser escolhida para OPTIMIZE? */
  elegivel: boolean;
  /** O eixo do frescor, separado. `null` = o frescor não se aplica a este estado. */
  frescor: string | null;
}

const VOCABULARIO: Record<EstadoDaConversaoMeta, LeituraDaConversao> = {
  /** O estado dos catálogos que não têm eixo de frescor — público e lugar.
   *  `frescor: null` aqui não é omissão: é a afirmação de que o eixo não se
   *  aplica a este objeto, e por isso a linha de frescor nem aparece. */
  AVAILABLE: {
    palavra: 'disponível',
    descricao: 'a Meta declarou este item disponível nesta conta',
    tom: 'bom',
    glifo: CircleCheck,
    elegivel: true,
    frescor: null,
  },
  AVAILABLE_FIRED: {
    palavra: 'disparando',
    descricao: 'a Meta registrou disparos deste evento nesta conta',
    tom: 'bom',
    glifo: CircleCheck,
    elegivel: true,
    frescor: 'disparo registrado',
  },
  AVAILABLE_NEVER_FIRED: {
    palavra: 'disponível, nunca disparou',
    descricao:
      'a conversão existe e pode ser escolhida, mas a Meta nunca viu este evento '
      + 'acontecer; otimizar por ela é otimizar por algo sem histórico',
    tom: 'atencao',
    glifo: TriangleAlert,
    elegivel: true,
    frescor: 'nunca disparou',
  },
  UNKNOWN_FRESHNESS: {
    palavra: 'disponível, frescor desconhecido',
    descricao:
      'a conversão existe e é elegível; o que não se sabe é QUANDO ela disparou '
      + 'pela última vez — a Meta não devolveu o carimbo',
    tom: 'atencao',
    glifo: TriangleAlert,
    // ⚠️ Elegível. A elegibilidade e o frescor são eixos separados, e rebaixar
    // esta conversão por causa de um carimbo ausente esconderia uma escolha
    // legítima do operador.
    elegivel: true,
    frescor: 'último disparo não informado',
  },
  ARCHIVED: {
    palavra: 'arquivada',
    descricao: 'a conversão foi arquivada na conta e não pode ser usada',
    tom: 'neutro',
    glifo: CircleDot,
    elegivel: false,
    frescor: null,
  },
  UNAVAILABLE: {
    palavra: 'indisponível',
    descricao: 'a Meta declarou esta conversão indisponível para uso nesta conta',
    tom: 'ruim',
    glifo: CircleAlert,
    elegivel: false,
    frescor: null,
  },
  UNKNOWN: {
    palavra: 'não sei dizer',
    descricao:
      'a Meta não devolveu a informação que diz se esta conversão está disponível. '
      + 'Não é "disponível" nem "arquivada": é uma resposta que não permitiu concluir, '
      + 'e por isso ela não pode ser escolhida para otimizar',
    tom: 'neutro',
    glifo: CircleHelp,
    elegivel: false,
    frescor: null,
  },
  INVALID: {
    palavra: 'item ilegível',
    descricao:
      'o item veio malformado na resposta da Meta. Ele é contado e mostrado em vez '
      + 'de sumir — sumir faria a lista parecer menor do que é',
    tom: 'ruim',
    glifo: CircleAlert,
    elegivel: false,
    frescor: null,
  },
};

/** O ramo SEGURO para um estado que este arquivo ainda não conhece.
 *
 * ⚠️ Um enum novo do provedor não pode virar "disponível" por não ter `case`.
 * Ele é exibido, dito por extenso e mantido fora do que se pode escolher. */
const DESCONHECIDO: LeituraDaConversao = {
  palavra: 'estado não reconhecido',
  descricao:
    'a Meta devolveu um estado que esta bancada não conhece. Ele é mostrado como '
    + 'veio e não pode ser escolhido para otimizar até alguém adjudicá-lo',
  tom: 'neutro',
  glifo: CircleHelp,
  elegivel: false,
  frescor: null,
};

export function lerConversao(estado: EstadoDaConversaoMeta | string): LeituraDaConversao {
  return VOCABULARIO[estado as EstadoDaConversaoMeta] ?? DESCONHECIDO;
}

/** O motivo fechado do desconhecimento, em linguagem de operador.
 *
 * O backend manda um vocabulário FECHADO (`MOTIVO_IS_ARCHIVED_AUSENTE`,
 * `MOTIVO_DELIVERY_STATUS_AUSENTE`, …) justamente para poder ser contado. A
 * tela traduz o que conhece e ecoa o que não conhece — nunca engole. */
export function motivoLegivel(motivo: string | null | undefined): string | null {
  const bruto = String(motivo ?? '').trim();
  if (!bruto) return null;
  const conhecidos: Record<string, string> = {
    IS_ARCHIVED_AUSENTE: 'a resposta não trouxe a marca de arquivamento',
    IS_UNAVAILABLE_AUSENTE: 'a resposta não trouxe a marca de indisponibilidade',
    LAST_FIRED_TIME_AUSENTE: 'a resposta não trouxe a data do último disparo',
    DELIVERY_STATUS_AUSENTE: 'a resposta não trouxe o status de entrega',
    CONTRATO_DO_ITEM_INVALIDO: 'o item veio malformado na resposta',
  };
  const chave = bruto.replace(/^MOTIVO_/, '').toUpperCase();
  return conhecidos[chave] ?? bruto;
}

export function conversaoSelecionavel(item: ConversaoPersonalizadaMetaLocal): boolean {
  return lerConversao(item.estado).elegivel;
}
