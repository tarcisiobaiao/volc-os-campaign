/**
 * O acumulador de eventos do job. Puro, sem rede e sem React.
 *
 * ## O defeito que este arquivo existe para não cometer
 *
 * O fluxo cai. Wi-Fi troca de rádio, o proxy corta a conexão ociosa, a aba
 * dorme. Quando isso acontece, o cliente reabre `?desde=<seq>` — e o servidor
 * pode reenviar o evento de número `seq` (limite inclusivo) ou uma janela
 * inteira. Sem cursor, cada reconexão duplicaria linhas na tela, e a tela do
 * job é justamente onde alguém confere se uma peça foi gerada uma vez ou duas.
 *
 * A regra é uma linha: **um evento só entra se `seq` for maior que o cursor**.
 * `seq` é ordem total e estável (é para isso que ele existe no contrato), então
 * o cursor é o maior `seq` já ACEITO, e não o maior recebido nem um relógio.
 *
 * ## Por que o cursor começa em `job.cursorEventos`
 *
 * Porque a página carrega o job primeiro, por HTTP, e só depois abre o fluxo.
 * O job já traz a última `seq` conhecida. Abrir o fluxo em zero repetiria todo
 * o histórico como se fosse novidade.
 */
import type { EventoDoJob } from '@/types/criativos';

export interface EstadoDoFluxo {
  /** Em ordem de chegada aceita, que é a ordem de `seq`. */
  eventos: EventoDoJob[];
  /** Maior `seq` aceito. É o ponto de retomada. */
  cursor: number;
  /** Quantos eventos foram descartados por repetição. Diagnóstico, não enfeite. */
  repetidos: number;
}

export function fluxoInicial(cursor: number, eventos: EventoDoJob[] = []): EstadoDoFluxo {
  return { eventos, cursor, repetidos: 0 };
}

/**
 * Aceita um evento, ou o descarta por já ter sido visto.
 *
 * Devolve o MESMO objeto quando descarta, para que um `useSyncExternalStore` ou
 * um `setState` de comparação por referência não re-renderize à toa durante uma
 * retomada que só trouxe repetição.
 */
export function receberEvento(estado: EstadoDoFluxo, evento: EventoDoJob): EstadoDoFluxo {
  if (!Number.isFinite(evento.seq) || evento.seq <= estado.cursor) {
    return { ...estado, repetidos: estado.repetidos + 1 };
  }
  return {
    eventos: [...estado.eventos, evento],
    cursor: evento.seq,
    repetidos: estado.repetidos,
  };
}

export function receberLote(estado: EstadoDoFluxo, eventos: EventoDoJob[]): EstadoDoFluxo {
  return eventos.reduce(receberEvento, estado);
}

/** Os últimos `n` eventos, do mais recente para o mais antigo. */
export function ultimos(estado: EstadoDoFluxo, n: number): EventoDoJob[] {
  return estado.eventos.slice(-n).reverse();
}
