/**
 * A leitura de progresso, com uma proibição no centro.
 *
 * SPEC §7: "Não usar percentual quando o motor não medir progresso
 * determinístico." O contrato guarda `percentual: number | null` para que a
 * interface não tenha onde inventar um número, e este módulo é o único lugar
 * que decide se existe barra.
 *
 * A regra: **barra só quando o ÚLTIMO evento trouxe percentual**. Reaproveitar
 * o percentual de um evento anterior seria pior que não mostrar nada: a barra
 * ficaria parada num número que já não descreve a etapa atual, e uma barra
 * parada lê-se como travamento.
 */
import type { EventoDoJob } from '@/types/criativos';

/**
 * Fases que a fábrica emite hoje, traduzidas para o que o operador entende.
 *
 * O mapa é tolerante de propósito: o motor pode ganhar uma fase antes deste
 * bundle ser publicado, e uma tela que mostra `gerando_voz` cru fala a língua
 * da máquina exatamente no momento em que o operador procura a resposta.
 */
export const FASE_LEGIVEL: Record<string, string> = {
  aceito: 'Pedido aceito e registrado.',
  enfileirado: 'Na fila, aguardando o motor começar.',
  resolvendo_contrato: 'Resolvendo o contrato do pedido.',
  aguardando_fatos: 'Aguardando fatos e fontes.',
  preparando_roteiro: 'Preparando o roteiro.',
  preparando_insumo: 'Preparando o insumo do motor.',
  chamando_motor: 'Chamando o motor de geração.',
  gerando: 'Gerando as peças.',
  gerando_voz: 'Gerando a voz.',
  produzindo_assets: 'Produzindo os assets.',
  renderizando: 'Renderizando.',
  compondo_som: 'Compondo o som.',
  normalizando: 'Normalizando e medindo os arquivos.',
  medindo: 'Medindo dimensões e tamanho.',
  guardando: 'Guardando os arquivos.',
  qa_tecnico: 'Executando o QA técnico.',
  qa_visual: 'Executando o QA visual.',
  aguardando_revisao: 'Aguardando revisão humana.',
  concluido: 'Concluído.',
  falhou: 'Falhou.',
  cancelado: 'Cancelado.',
};

export function faseLegivel(fase: string): string {
  const conhecida = FASE_LEGIVEL[fase];
  if (conhecida) return conhecida;
  const humanizada = fase.replace(/[_-]+/g, ' ').trim();
  return humanizada ? `Etapa informada pelo motor: ${humanizada}.` : 'Etapa não informada.';
}

export interface LeituraDeProgresso {
  /** Identificador cru da fase, para teste e log. `null` quando não houve evento. */
  fase: string | null;
  /** A frase que vai para a tela. Sempre existe. */
  frase: string;
  /** Detalhe que o motor mandou junto, quando mandou. */
  detalhe: string | null;
  /**
   * `null` significa: NÃO DESENHE BARRA. Não é zero, e não é "ainda não sei".
   * É "este motor não mede progresso", e a tela mostra a etapa em vez disso.
   */
  percentual: number | null;
  /** Slot afetado, quando o evento é de uma peça específica. */
  slot: string | null;
}

const SEM_EVENTO: LeituraDeProgresso = {
  fase: null,
  frase: 'Ainda não houve nenhum evento deste trabalho.',
  detalhe: null,
  percentual: null,
  slot: null,
};

export function lerProgresso(eventos: EventoDoJob[]): LeituraDeProgresso {
  const ultimo = eventos.length ? eventos[eventos.length - 1] : null;
  if (!ultimo) return SEM_EVENTO;
  return {
    fase: ultimo.fase,
    frase: faseLegivel(ultimo.fase),
    detalhe: ultimo.mensagem,
    percentual: percentualUtil(ultimo.percentual),
    slot: ultimo.slot,
  };
}

/**
 * Normaliza o percentual, recusando tudo que não seja medida honesta.
 *
 * `null`, `NaN` e valores fora de 0..100 devolvem `null`: melhor não ter barra
 * que ter uma barra errada num painel que fala de custo.
 */
export function percentualUtil(bruto: number | null): number | null {
  if (bruto === null || !Number.isFinite(bruto)) return null;
  if (bruto < 0 || bruto > 100) return null;
  return bruto;
}
