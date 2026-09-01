/**
 * A leitura do contrato dos quatro canais. Uma só, cacheada, sem decisão.
 */
import { useQuery } from '@tanstack/react-query';

import { pautadorApi } from '@/lib/pautadorApi';
import type { RespostaDosCanais } from '@/lib/trafego/canais';

export const CHAVE_CANAIS = ['trafego', 'canais'] as const;

/**
 * ⚠️ `staleTime` curto de propósito. A resposta carrega o que ESTA pessoa pode
 * neste servidor agora, e uma permissão revogada precisa sumir da tela — é o
 * mesmo argumento que impede as capacidades de virarem claim de JWT: um
 * retrato do instante, não uma credencial.
 */
export function useCanais() {
  return useQuery<RespostaDosCanais>({
    queryKey: CHAVE_CANAIS,
    queryFn: () => pautadorApi.contratoDosCanais(),
    staleTime: 30_000,
    // Sem `placeholderData`: enquanto a leitura não chega, a tela mostra que
    // está lendo. Um contrato de mentira no lugar do vazio faria os quatro
    // portões aparecerem fechados antes de alguém ter perguntado.
    retry: 1,
  });
}
