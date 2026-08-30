/**
 * A biblioteca global: lista filtrada, detalhe do ativo e decisão de aprovação.
 *
 * `total` e `universo` chegam do servidor porque só ele sabe os dois: `total` é
 * quantos casam com o filtro, `universo` é quantos existem. A tela precisa dos
 * dois para dizer "12 de 48" e, quando o recorte vem vazio, para separar
 * "a biblioteca está vazia" de "este filtro não alcança nada".
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { criativosApi, type DetalheDoAsset, type PaginaDeAssets } from '@/lib/criativosApi';
import { CHAVE_RESUMO } from '@/hooks/useCriativosResumo';
import type { FiltrosDaBiblioteca } from '@/components/criativos/biblioteca/filtros';
import type { PedidoDeAprovacao } from '@/types/criativos';

export const chaveDaBiblioteca = (f: FiltrosDaBiblioteca, offset: number) =>
  ['criativos', 'assets', f, offset] as const;

export const chaveDoAsset = (id: string) => ['criativos', 'asset', id] as const;

export const PAGINA = 24;

export function useCriativosBiblioteca(filtros: FiltrosDaBiblioteca, offset = 0) {
  return useQuery<PaginaDeAssets>({
    queryKey: chaveDaBiblioteca(filtros, offset),
    queryFn: () =>
      criativosApi.assets({
        busca: filtros.busca || undefined,
        kind: filtros.kind || undefined,
        estado: filtros.estado || undefined,
        brandPack: filtros.brandPack || undefined,
        destino: filtros.destino || undefined,
        desde: filtros.desde || undefined,
        ate: filtros.ate || undefined,
        limite: PAGINA,
        offset,
      }),
    retry: false,
    // A leitura anterior fica na tela enquanto a nova não chega: trocar filtro
    // não pode apagar o que já estava visível e fazer a página saltar.
    placeholderData: (anterior) => anterior,
    staleTime: 30_000,
  });
}

export function useCriativosAsset(id: string | undefined) {
  return useQuery<DetalheDoAsset>({
    queryKey: chaveDoAsset(id ?? ''),
    queryFn: () => criativosApi.asset(id as string),
    enabled: Boolean(id),
    retry: false,
  });
}

/**
 * Registra a decisão de aprovação.
 *
 * ⚠️ Ator e instante são gravados pelo SERVIDOR, a partir da sessão. A tela não
 * manda quem decidiu: se mandasse, o registro de quem autorizou uma peça seria
 * um campo editável pelo navegador.
 */
export function useDecidirAprovacao(assetId: string | undefined) {
  const cliente = useQueryClient();
  return useMutation({
    mutationFn: (pedido: PedidoDeAprovacao) => criativosApi.decidir(assetId as string, pedido),
    onSuccess: () => {
      void cliente.invalidateQueries({ queryKey: chaveDoAsset(assetId ?? '') });
      void cliente.invalidateQueries({ queryKey: ['criativos', 'assets'] });
      void cliente.invalidateQueries({ queryKey: CHAVE_RESUMO });
    },
  });
}
