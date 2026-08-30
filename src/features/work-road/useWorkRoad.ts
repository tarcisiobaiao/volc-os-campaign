import { useQuery } from "@tanstack/react-query";
import { pautadorApi } from "@/lib/pautadorApi";
import { readingFreshness } from "./freshness";

const INTERVALO_ATUALIZACAO_MS = 15_000;

export function useWorkRoad() {
  const consulta = useQuery({
    queryKey: ["work-road", "live"],
    queryFn: () => pautadorApi.workRoad(),
    staleTime: 10_000,
    refetchInterval: INTERVALO_ATUALIZACAO_MS,
    refetchOnWindowFocus: true,
    retry: 1,
  });

  const workRoad = consulta.data ?? null;
  const freshness = readingFreshness({
    dataUpdatedAt: consulta.dataUpdatedAt,
    isError: consulta.isError,
    isPending: consulta.isPending,
    hasData: Boolean(consulta.data),
  });

  return {
    workRoad,
    carregando: freshness === "carregando",
    atualizando: consulta.isFetching,
    falhou: freshness === "erro",
    desatualizado: freshness === "desatualizado",
    ausente: freshness === "ausente",
    freshness,
    lidoEm: consulta.dataUpdatedAt || null,
    erro: consulta.error instanceof Error ? consulta.error.message : null,
    recarregar: () => { void consulta.refetch(); },
  };
}
