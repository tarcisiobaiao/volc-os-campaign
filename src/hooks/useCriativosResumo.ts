/**
 * O resumo da Home do Estúdio.
 *
 * ⚠️ Sem `placeholderData` e sem valor inicial fabricado. Enquanto a leitura
 * não chega, quem consome recebe `undefined` e desenha o esqueleto: um zero
 * exibido durante o carregamento é uma AFIRMAÇÃO ("não há trabalho em
 * andamento") feita antes de o servidor ter respondido.
 */
import { useQuery } from '@tanstack/react-query';

import { criativosApi, type ResumoDoEstudio } from '@/lib/criativosApi';

export const CHAVE_RESUMO = ['criativos', 'resumo'] as const;

export function useCriativosResumo() {
  return useQuery<ResumoDoEstudio>({
    queryKey: CHAVE_RESUMO,
    queryFn: () => criativosApi.resumo(),
    // 401 e 403 não melhoram com insistência, e esta é a primeira chamada da área.
    retry: false,
    staleTime: 15_000,
    refetchOnWindowFocus: true,
  });
}
