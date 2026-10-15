/**
 * A fila de propostas: o que cada linha oferece, e a quem.
 *
 * ## Permissão é do servidor; a tela só não oferece o que ele recusaria
 *
 * Papel por rota (§1 do contrato): aprovar/recusar e aplicar/reverter são de
 * admin; propor, verificar e importar são de qualquer usuário. A capacidade
 * vem de `useCapacidades` — `is_admin` para decidir, `google_mutate` para
 * escrever. Enquanto não se sabe, não se pode (`null` = não).
 *
 * `proximo_passo` vem da view `trafego_proposta_painel` e é a autoridade do
 * que a linha pede agora. ⚠️ `verificar` NUNCA oferece reaplicar: a tentativa
 * anterior pode ter chegado à conta.
 *
 * Módulo puro: sem React, sem HTTP.
 */
import type { CapacidadesDoOperador } from '@/types/trafego';
import type { Proposta as PropostaDoDiagnostico, DependenciaDeAplicacao } from '@/types/diagnostico';
import type { GrupoDeAcao, PropostaDoPainel, StatusGerivel } from '@/types/gestao';
import type { EstadoDeProposta } from '@/lib/instrumento';

import { alvoDaEstrategia, semAlvoPorque } from './acoes';

export interface Permissoes {
  /** Aprovar/recusar: autoriza gasto. */
  decidir: boolean;
  /** Aplicar/reverter: escreve no Google. */
  escrever: boolean;
  /** Por que `escrever` está fechado para um admin (trava do servidor). */
  porqueSemEscrita: string | null;
}

export function permissoesDe(c: CapacidadesDoOperador | null): Permissoes {
  const admin = c?.is_admin ?? false;
  const mutar = c?.google_mutate ?? false;
  return {
    decidir: admin,
    escrever: admin && mutar,
    porqueSemEscrita: admin && !mutar ? (c?.porque_sem_mutacao ?? 'a escrita na conta está fechada no servidor') : null,
  };
}

export type GestoDaFila = 'aprovar' | 'recusar' | 'aplicar' | 'verificar' | 'reverter';

export interface OfertaDaLinha {
  gestos: GestoDaFila[];
  /** Gesto que existe mas está fechado para esta pessoa, e por quê. */
  fechados: Array<{ gesto: GestoDaFila; porque: string }>;
  /** O que a linha diz quando não há gesto. */
  aviso: string | null;
}

export function ofertaDaLinha(p: PropostaDoPainel, perm: Permissoes): OfertaDaLinha {
  const gestos: GestoDaFila[] = [];
  const fechados: OfertaDaLinha['fechados'] = [];
  let aviso: string | null = null;

  const exigirEscrita = (g: GestoDaFila) => {
    if (perm.escrever) gestos.push(g);
    else if (perm.decidir && perm.porqueSemEscrita) fechados.push({ gesto: g, porque: perm.porqueSemEscrita });
  };

  switch (p.proximo_passo) {
    case 'aguardar_humano':
      if (p.vencida) {
        aviso = 'venceu sem decisão; proponha de novo';
      } else if (perm.decidir) {
        gestos.push('aprovar', 'recusar');
      } else {
        aviso = 'aguardando decisão de um administrador';
      }
      break;
    case 'aplicar':
      exigirEscrita('aplicar');
      if (!perm.decidir) aviso = 'aprovada; aguardando um administrador aplicar';
      break;
    case 'verificar':
      // Qualquer usuário verifica. Reaplicar NUNCA é oferecido aqui.
      if (p.aplicacao_id) gestos.push('verificar');
      aviso = 'a última tentativa não tem desfecho conhecido: verifique antes de qualquer outra coisa';
      break;
    case 'acompanhar':
      if (p.aplicacao_id) gestos.push('verificar');
      if (p.aplicacao_id && p.aplicacao_desfecho === 'sucesso') exigirEscrita('reverter');
      break;
    case 'expirar':
      aviso = 'venceu; proponha de novo sobre o estado atual da conta';
      break;
    default:
      break;
  }
  return { gestos, fechados, aviso };
}

/** A proposta é desta campanha? (ou da conta, quando o alvo é a conta). */
export function daCampanha(
  p: PropostaDoPainel,
  campanha: { volcCampaignId: string; campaignId: string; customerId: string },
): boolean {
  if (p.volc_campaign_id && p.volc_campaign_id === campanha.volcCampaignId) return true;
  return p.alvo_chave === `google_ads:${campanha.customerId}:campanha:${campanha.campaignId}`;
}

export const ESTADO_LEGIVEL: Record<string, string> = {
  aguardando_aprovacao: 'aguardando aprovação',
  aprovada: 'aprovada',
  recusada: 'recusada',
  aplicada: 'aplicada',
  revertida: 'revertida',
  expirada: 'expirada',
  cancelada: 'cancelada',
};

/**
 * O estado do ledger no vocabulário do selo V3 (`SeloDeProposta`), ou `null`
 * quando o selo afirmaria mais do que o ledger sabe.
 *
 * ⚠️ `aplicada` NUNCA vira o selo "Aplicada · com recibo": o selo diz que a
 * mudança foi lida de volta, e o painel não recebe essa prova. O backend marca
 * `aplicada` quando o mutate responde sucesso, sem `verificar`, e a view devolve
 * `acompanhar` sem olhar `confere`. Fica com `TEXTO_SEM_SELO`.
 *
 * Vencida ganha do estado: a view só marca `vencida` em `aguardando_aprovacao`,
 * mas uma aprovada que passou do prazo chega com `proximo_passo = expirar`, e o
 * gatilho recusa aplicá-la. Nenhuma das duas autoriza mais nada.
 * `cancelada` não tem palavra no ciclo P09 e fica com o texto do ledger.
 */
export function seloDoLedger(
  p: Pick<PropostaDoPainel, 'estado' | 'vencida' | 'proximo_passo'>,
): EstadoDeProposta | null {
  if (p.vencida || p.estado === 'expirada' || p.proximo_passo === 'expirar') return 'vencida';
  switch (p.estado) {
    case 'aguardando_aprovacao':
      return 'aguardando';
    case 'aprovada':
      return 'aprovada';
    case 'recusada':
      return 'recusada';
    case 'revertida':
      return 'revertida';
    default:
      return null;
  }
}

/** O texto de quem não tem selo: aplicada diz que ninguém conferiu na conta. */
export function textoSemSelo(p: Pick<PropostaDoPainel, 'estado' | 'vencida'>): string {
  if (p.estado === 'aplicada') return 'aplicada · sem conferência na conta';
  return `${ESTADO_LEGIVEL[p.estado] ?? p.estado}${p.vencida ? ' · vencida' : ''}`;
}

export const DESFECHO_LEGIVEL: Record<string, string> = {
  em_voo: 'em voo — enviada, sem resposta ainda',
  sucesso: 'aplicada com sucesso',
  erro: 'recusada pelo Google ou pela trava; nada mudou',
  sem_resposta: 'sem resposta — a conta pode ter mudado',
  pendente: 'pendente',
};

export function confereLegivel(confere: boolean | null): string {
  if (confere === true) return 'a conta confere com o proposto';
  if (confere === false) return 'a conta NÃO confere com o proposto';
  return 'não dá para saber pela leitura';
}

// ── ponte: caixa de propostas do diagnóstico → formulário da gestão ─────────

export interface Preenchimento {
  grupo: GrupoDeAcao;
  /** De onde veio: id da proposta do diagnóstico. */
  origem: string;
  motivo: string;
  status?: StatusGerivel;
}

/**
 * O que a proposta do diagnóstico vira na gestão. `null` quando não há ação
 * de gestão que a realize — e então `bloqueioDaPonte` diz por quê.
 */
export function preenchimentoDaCaixa(
  proposta: PropostaDoDiagnostico,
  estrategia: string | null,
): Preenchimento | null {
  const motivo = `${proposta.titulo}: ${proposta.frase}`;
  if (proposta.alvo === 'status') {
    return { grupo: 'status', origem: proposta.id, motivo, status: 'ENABLED' };
  }
  if (proposta.alvo === 'orcamento') return { grupo: 'orcamento', origem: proposta.id, motivo };
  if (proposta.alvo === 'lance' && alvoDaEstrategia(estrategia)) {
    return { grupo: 'alvo_de_lance', origem: proposta.id, motivo };
  }
  return null;
}

/**
 * A caixa do diagnóstico com a dependência REAL de hoje: o que a gestão
 * realiza sai liberado (o botão passa a abrir o formulário); o resto conta
 * por que não.
 */
export function caixaLigadaAGestao<C extends { propostas: PropostaDoDiagnostico[] }>(
  caixa: C,
  estrategia: string | null,
): C {
  return {
    ...caixa,
    propostas: caixa.propostas.map((p) => ({ ...p, bloqueio: bloqueioDaPonte(p, estrategia) })),
  };
}

export function bloqueioDaPonte(
  proposta: PropostaDoDiagnostico,
  estrategia: string | null,
): DependenciaDeAplicacao | null {
  if (preenchimentoDaCaixa(proposta, estrategia)) return null;
  if (proposta.alvo === 'lance') {
    return { dependencia: semAlvoPorque(estrategia), destrava: 'endpoint' };
  }
  return proposta.bloqueio;
}
