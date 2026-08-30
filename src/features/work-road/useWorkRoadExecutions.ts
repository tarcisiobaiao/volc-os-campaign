import { useQuery } from "@tanstack/react-query";
import { pautadorApi } from "@/lib/pautadorApi";
import { readingFreshness } from "./freshness";

const INTERVALO_EXECUCOES_MS = 5_000;

export function useWorkRoadExecutions(enabled: boolean) {
  const consulta = useQuery({
    queryKey: ["work-road", "executions"],
    queryFn: () => pautadorApi.workRoadExecutions(),
    enabled,
    staleTime: 2_000,
    refetchInterval: enabled ? INTERVALO_EXECUCOES_MS : false,
    refetchOnWindowFocus: true,
    retry: 1,
  });

  const executions = consulta.data ?? null;
  const freshness = readingFreshness({
    dataUpdatedAt: consulta.dataUpdatedAt,
    isError: consulta.isError,
    isPending: consulta.isPending && enabled,
    hasData: Boolean(consulta.data),
  });

  return {
    executions,
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
