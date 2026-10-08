/**
 * React Query sobre `/api/trafego/gestao` — fila, recomendações e os gestos.
 *
 * Toda mutação invalida a fila da conta: o estado que vale é o do ledger
 * relido, nunca o que a tela supôs depois do clique.
 *
 * ⚠️ Sem `retry` nas mutações. Aplicar duas vezes porque a primeira "falhou"
 * é exatamente o que `verificar_antes` existe para impedir.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { gestaoApi } from '@/lib/trafego/gestaoApi';
import type {
  PedidoDeAprovacao,
  PedidoDeImportacao,
  PedidoDeProposta,
  PedidoDeRecusa,
  PedidoDeReversao,
} from '@/types/gestao';

export const CHAVE_GESTAO = ['trafego', 'gestao'] as const;

export const chaveDaFila = (customerId: string) => [...CHAVE_GESTAO, 'propostas', customerId] as const;
export const chaveDasRecomendacoes = (customerId: string) =>
  [...CHAVE_GESTAO, 'recomendacoes', customerId] as const;

export function usePropostasDaConta(customerId: string | null, opcoes: { limite?: number } = {}) {
  return useQuery({
    queryKey: [...chaveDaFila(customerId ?? ''), opcoes.limite ?? 50],
    queryFn: () => gestaoApi.propostas(customerId as string, { limite: opcoes.limite ?? 50 }),
    enabled: Boolean(customerId),
    retry: false,
    staleTime: 30 * 1000,
    refetchOnWindowFocus: true,
  });
}

/**
 * Recomendações LEEM o Google. Por isso só quando pedido (`ligado`): abrir a
 * página da campanha não deve, sozinho, gastar cota de leitura da conta.
 */
export function useRecomendacoes(customerId: string | null, ligado: boolean) {
  return useQuery({
    queryKey: chaveDasRecomendacoes(customerId ?? ''),
    queryFn: () => gestaoApi.recomendacoes(customerId as string),
    enabled: Boolean(customerId) && ligado,
    retry: false,
    staleTime: 5 * 60 * 1000,
    refetchOnWindowFocus: false,
  });
}

function useInvalidarFila(customerId: string | null) {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: chaveDaFila(customerId ?? '') });
}

export function usePropor(customerId: string | null) {
  const invalidar = useInvalidarFila(customerId);
  return useMutation({
    mutationFn: (pedido: PedidoDeProposta) => gestaoApi.propor(pedido),
    onSettled: invalidar,
    retry: false,
  });
}

export function useAprovar(customerId: string | null) {
  const invalidar = useInvalidarFila(customerId);
  return useMutation({
    mutationFn: (v: { propostaId: string; pedido: PedidoDeAprovacao }) =>
      gestaoApi.aprovar(v.propostaId, v.pedido),
    onSettled: invalidar,
    retry: false,
  });
}

export function useRecusar(customerId: string | null) {
  const invalidar = useInvalidarFila(customerId);
  return useMutation({
    mutationFn: (v: { propostaId: string; pedido: PedidoDeRecusa }) =>
      gestaoApi.recusar(v.propostaId, v.pedido),
    onSettled: invalidar,
    retry: false,
  });
}

export function useAplicar(customerId: string | null) {
  const invalidar = useInvalidarFila(customerId);
  return useMutation({
    mutationFn: (propostaId: string) => gestaoApi.aplicar(propostaId),
    onSettled: invalidar,
    retry: false,
  });
}

export function useVerificar(customerId: string | null) {
  const invalidar = useInvalidarFila(customerId);
  return useMutation({
    mutationFn: (aplicacaoId: string) => gestaoApi.verificar(aplicacaoId),
    onSettled: invalidar,
    retry: false,
  });
}

export function useReverter(customerId: string | null) {
  const invalidar = useInvalidarFila(customerId);
  return useMutation({
    mutationFn: (v: { aplicacaoId: string; pedido: PedidoDeReversao }) =>
      gestaoApi.reverter(v.aplicacaoId, v.pedido),
    onSettled: invalidar,
    retry: false,
  });
}

export function useImportarCampanha(customerId: string | null) {
  const invalidar = useInvalidarFila(customerId);
  return useMutation({
    mutationFn: (pedido: PedidoDeImportacao) => gestaoApi.importarCampanha(pedido),
    onSettled: invalidar,
    retry: false,
  });
}
