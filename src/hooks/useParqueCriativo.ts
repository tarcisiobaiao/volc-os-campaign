/**
 * A leitura do parque criativo.
 *
 * ⚠️ **Sem fallback local, de propósito.** `useCriativosFormatos` cai para
 * `FORMATOS_DE_IMAGEM` quando a leitura falha, e faz certo: aquela constante é a
 * mesma lista que o backend valida. Aqui não existe constante equivalente — o
 * parque só tem uma verdade, que é a tabela. Escrever uma cópia no bundle para a
 * tela não ficar vazia criaria a QUINTA cópia do catálogo, exatamente o defeito
 * que a v11_02 existe para matar. Quando a leitura falha, a tela diz que falhou.
 */
import { useQuery } from '@tanstack/react-query';

import { criativosApi } from '@/lib/criativosApi';
import type { Parque } from '@/types/parqueCriativo';

export const CHAVE_PARQUE = ['criativos', 'parque'] as const;

export interface LeituraDoParque {
  parque: Parque | null;
  carregando: boolean;
  erro: unknown;
  recarregar: () => void;
}

export function useParqueCriativo(): LeituraDoParque {
  const consulta = useQuery({
    queryKey: CHAVE_PARQUE,
    queryFn: () => criativosApi.parque(),
    retry: false,
    staleTime: 5 * 60_000,
  });
  return {
    parque: consulta.data ?? null,
    carregando: consulta.isLoading,
    erro: consulta.error,
    recarregar: () => void consulta.refetch(),
  };
}
