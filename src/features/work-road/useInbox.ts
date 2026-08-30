import { useQuery } from "@tanstack/react-query";
import { pautadorApi } from "@/lib/pautadorApi";
import { readingFreshness } from "./freshness";

export function useWorkRoadInbox() {
  const consulta = useQuery({
    queryKey: ["work-road", "inbox"],
    queryFn: () => pautadorApi.workRoadInbox(),
    staleTime: 10_000,
    refetchInterval: 15_000,
    retry: 1,
  });
  const freshness = readingFreshness({
    dataUpdatedAt: consulta.dataUpdatedAt,
    isError: consulta.isError,
    isPending: consulta.isPending,
    hasData: Boolean(consulta.data),
  });
  return {
    inbox: consulta.data ?? null,
    carregando: freshness === "carregando",
    falhou: freshness === "erro",
    desatualizado: freshness === "desatualizado",
    erro: consulta.error instanceof Error ? consulta.error.message : null,
    recarregar: () => { void consulta.refetch(); },
  };
}

export function useGraphStatus() {
  const consulta = useQuery({
    queryKey: ["work-road", "graph-status"],
    queryFn: () => pautadorApi.workRoadGraphStatus(),
    staleTime: 30_000,
    retry: 1,
  });
  return {
    status: consulta.data ?? null,
    carregando: consulta.isPending && !consulta.data,
    falhou: consulta.isError && !consulta.data,
    recarregar: () => { void consulta.refetch(); },
  };
}
