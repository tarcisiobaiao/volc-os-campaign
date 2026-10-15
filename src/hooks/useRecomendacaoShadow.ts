import { useQuery } from '@tanstack/react-query';

import { pautadorApi } from '@/lib/pautadorApi';
import type { RecomendacaoShadow } from '@/types/recomendacaoShadow';

export const CHAVE_RECOMENDACAO_SHADOW = ['trafego', 'recomendacao-shadow'] as const;

/**
 * Os estados da leitura, cada forma de não saber com nome próprio.
 *
 * ⚠️ `ausente` (404) não é "manter": é que nenhum experimento olhou esta
 * campanha. `integridade` (409) não é ausência: o experimento existe e um
 * artefato não bate com o próprio manifesto.
 */
export type LeituraShadow =
  | { estado: 'sem_id' }
  | { estado: 'carregando' }
  | { estado: 'ausente' }
  | { estado: 'integridade'; mensagem: string }
  | { estado: 'falhou'; mensagem: string; status: number | null }
  | { estado: 'pronta'; recomendacao: RecomendacaoShadow };

function statusDe(erro: unknown): number | null {
  const s = (erro as { status?: unknown } | null)?.status;
  return typeof s === 'number' ? s : null;
}

function codigoDe(erro: unknown): string | null {
  const c = (erro as { corpo?: { codigo?: unknown } } | null)?.corpo?.codigo;
  return typeof c === 'string' ? c : null;
}

export function useRecomendacaoShadow(idExterno: string | null | undefined): LeituraShadow {
  const id = String(idExterno ?? '').trim();
  const valido = /^[0-9]{6,20}$/.test(id);
  const consulta = useQuery({
    queryKey: [...CHAVE_RECOMENDACAO_SHADOW, id],
    queryFn: () => pautadorApi.recomendacaoShadow(id),
    enabled: valido,
    retry: false,
    staleTime: Number.POSITIVE_INFINITY,
    refetchOnWindowFocus: false,
  });

  if (!valido) return { estado: 'sem_id' };
  if (consulta.data) return { estado: 'pronta', recomendacao: consulta.data };
  if (consulta.isError) {
    const status = statusDe(consulta.error);
    // Só o 404 com o código do contrato é ausência. Um 404 sem ele é rota que
    // não existe (backend antigo) — isso é falha, não "nenhum experimento".
    if (status === 404 && codigoDe(consulta.error) === 'sem_recomendacao_shadow') {
      return { estado: 'ausente' };
    }
    const mensagem =
      consulta.error instanceof Error ? consulta.error.message : 'A leitura não pôde ser feita.';
    if (status === 409 && codigoDe(consulta.error) === 'integridade_quebrada') {
      return { estado: 'integridade', mensagem };
    }
    return { estado: 'falhou', mensagem, status };
  }
  return { estado: 'carregando' };
}
