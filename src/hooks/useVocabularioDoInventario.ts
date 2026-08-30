/**
 * O vocabulário fechado do contrato, e os manifestos de todos os canais.
 *
 * ## Por que a tela pergunta em vez de saber
 *
 * Divergência de vocabulário entre front e back foi medida em cinco lugares
 * (E-21) — e o caso mais caro foi PMax: o cliente listava o canal, o engine
 * levantava exceção, e o operador descobria depois de montar o pedido. Uma
 * segunda cópia da lista no cliente é uma verdade que envelhece sozinha.
 *
 * ⚠️ Enquanto a leitura não chega, `manifestos` é uma lista VAZIA — e quem
 * consome trata vazio como "ainda não sei", nunca como "não há canal". Um
 * estúdio que desenhasse os canais que ele conhece por conta própria enquanto
 * espera seria exatamente a segunda cópia que este hook existe para não ter.
 */
import { useQuery } from '@tanstack/react-query';

import { pautadorApi } from '@/lib/pautadorApi';
import type { ManifestoDeCanal, VocabularioDoInventario } from '@/types/trafego';

export const CHAVE_VOCABULARIO = ['trafego', 'vocabulario'] as const;

export interface LeituraDoVocabulario {
  vocabulario: VocabularioDoInventario | null;
  /** Vazio enquanto não se sabe. Nunca uma lista inventada aqui. */
  manifestos: ManifestoDeCanal[];
  carregando: boolean;
  falhou: boolean;
}

export function useVocabularioDoInventario(): LeituraDoVocabulario {
  const consulta = useQuery({
    queryKey: CHAVE_VOCABULARIO,
    queryFn: () => pautadorApi.vocabularioDoInventario(),
    retry: false,
    // Longo: o vocabulário muda com um deploy, não com o uso. Repetir esta
    // leitura a cada tela custaria uma ida ao servidor para receber a mesma
    // resposta.
    staleTime: 30 * 60 * 1000,
  });

  return {
    vocabulario: consulta.data ?? null,
    manifestos: consulta.data?.manifestos ?? [],
    carregando: consulta.isLoading && consulta.data == null,
    falhou: consulta.isError,
  };
}
