/**
 * A leitura da escada de entrega: quem decide o veredito, e por quê.
 *
 * A escada é causal. Um degrau baixo que bloqueia torna todos os degraus acima
 * dele irrelevantes — e um degrau baixo que NÃO PÔDE SER APURADO torna todos os
 * degraus acima dele indignos de confiança. As duas regras são a mesma ideia:
 * a tela não pode afirmar sobre o leilão enquanto não souber se a conta paga.
 *
 * Este módulo é puro. Não conhece React, não conhece HTTP, não formata nada.
 */
import {
  EIXOS_DE_ENTREGA,
  type DegrauDeEntrega,
  type EixoDeEntrega,
  type VereditoDaEscada,
} from '@/types/diagnostico';

/** Índice causal de um eixo. Eixo desconhecido vai para o fim, nunca para o topo. */
export function ordemDoEixo(eixo: EixoDeEntrega): number {
  const i = EIXOS_DE_ENTREGA.indexOf(eixo);
  return i === -1 ? EIXOS_DE_ENTREGA.length : i;
}

/** Os degraus na ordem causal, independente da ordem em que chegaram. */
export function emOrdemCausal(degraus: DegrauDeEntrega[]): DegrauDeEntrega[] {
  return [...degraus].sort((a, b) => ordemDoEixo(a.eixo) - ordemDoEixo(b.eixo));
}

/**
 * O veredito da escada.
 *
 * Percorre de baixo para cima e para no PRIMEIRO degrau que impede a leitura
 * dos de cima:
 *
 *  - `bloqueia` → a campanha não entrega, e este é o motivo de baixo.
 *  - `nao_apurado` → não dá para afirmar nada acima daqui. ⚠️ Não continuar é o
 *    ponto: seguir e devolver `sem_impedimento` porque os degraus acima vieram
 *    `ok` seria dizer "está tudo bem" apoiado numa prova que falhou.
 *
 * Se a varredura chega ao fim, `limita` mais baixo decide; senão, sem
 * impedimento. Uma escada vazia é `nao_apurado` no primeiro eixo: nenhuma
 * medida nenhuma nunca é boa notícia.
 */
export function vereditoDaEscada(degraus: DegrauDeEntrega[]): VereditoDaEscada {
  const ordenados = emOrdemCausal(degraus);
  if (ordenados.length === 0) {
    return { tipo: 'nao_apurado', eixo: EIXOS_DE_ENTREGA[0] };
  }

  for (const d of ordenados) {
    if (d.estado === 'bloqueia') return { tipo: 'bloqueada', eixo: d.eixo };
    if (d.estado === 'nao_apurado') return { tipo: 'nao_apurado', eixo: d.eixo };
  }

  const limitante = ordenados.find((d) => d.estado === 'limita');
  if (limitante) return { tipo: 'limitada', eixo: limitante.eixo };
  return { tipo: 'sem_impedimento' };
}

/**
 * Até onde a escada foi lida com confiança.
 *
 * Os degraus ABAIXO do veredito foram apurados e não impedem nada. Os degraus
 * a partir dele são leitura suspensa — a tela mostra, e diz que são leitura
 * suspensa, em vez de deixá-los parecendo conclusões.
 */
export function degrausConfiaveis(
  degraus: DegrauDeEntrega[],
  veredito: VereditoDaEscada,
): { confiaveis: DegrauDeEntrega[]; suspensos: DegrauDeEntrega[] } {
  const ordenados = emOrdemCausal(degraus);
  if (veredito.tipo === 'sem_impedimento' || veredito.tipo === 'limitada') {
    return { confiaveis: ordenados, suspensos: [] };
  }
  const corte = ordemDoEixo(veredito.eixo);
  return {
    confiaveis: ordenados.filter((d) => ordemDoEixo(d.eixo) < corte),
    // O degrau do corte entra em `suspensos` junto com os de cima: é ele que
    // interrompe a leitura, e mostrá-lo do lado "confiável" sugeriria que a
    // conclusão dele é final quando ela é justamente a que falta.
    suspensos: ordenados.filter((d) => ordemDoEixo(d.eixo) >= corte),
  };
}

/** `true` quando algum degrau não pôde ser apurado. */
export function escadaParcial(degraus: DegrauDeEntrega[]): boolean {
  return degraus.some((d) => d.estado === 'nao_apurado');
}
