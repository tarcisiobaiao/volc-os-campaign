import { useQuery } from '@tanstack/react-query';

import { pautadorApi } from '@/lib/pautadorApi';
import type { RespostaDoDecisionLab } from '@/types/inteligenciaDecisao';

export const CHAVE_DECISION_LAB = ['trafego', 'decision-intelligence-lab'] as const;

export function useDecisionIntelligenceLab(scenarioId: string): {
  resposta: RespostaDoDecisionLab | null;
  carregando: boolean;
  atualizando: boolean;
  erro: Error | null;
} {
  const idValido = /^[a-z][a-z0-9-]{2,63}$/.test(scenarioId);
  const consulta = useQuery({
    queryKey: [...CHAVE_DECISION_LAB, scenarioId],
    queryFn: () => pautadorApi.decisionIntelligenceLab(scenarioId),
    enabled: idValido,
    retry: false,
    staleTime: Number.POSITIVE_INFINITY,
    refetchOnWindowFocus: false,
  });

  return {
    resposta: consulta.data ?? null,
    carregando: idValido && consulta.isLoading && consulta.data == null,
    atualizando: consulta.isFetching && consulta.data != null,
    erro: !idValido
      ? new Error('Cenário sintético inválido.')
      : consulta.isError
        ? consulta.error instanceof Error
          ? consulta.error
          : new Error('O laboratório não pôde ser lido.')
        : null,
  };
}
