/**
 * O que ESTA pessoa pode, perguntado ao servidor — nunca derivado do papel.
 *
 * ## Por que não `role === 'ADMIN'`
 *
 * Porque são duas decisões de tamanhos muito diferentes. `useUserRole` responde
 * "esta pessoa administra o VOLC O.S.?", que decide se ela vê a aba de
 * usuários. Gastar na conta de anúncio do cliente é outra pergunta, e ela tem
 * uma segunda trava do lado do servidor (`volc_ads/gads/modo.py`) que o papel
 * não conhece.
 *
 * Derivando uma da outra, a tela desenha o botão de publicar para todo
 * administrador — e o servidor recusa no clique, depois de o operador ter
 * montado o pedido inteiro. O trabalho já foi feito quando a resposta chega, e
 * é exatamente o defeito que `plataforma.py` descreve para canal.
 *
 * ## Enquanto não se sabe, não se pode
 *
 * ⚠️ O estado de carregamento e o de falha devolvem `null`, e quem consome
 * trata `null` como "não pode" — nunca como "pode". Um botão de gasto que
 * aparece por um instante enquanto a leitura não chegou é um botão clicável.
 *
 * Não guarda segredo e não é credencial: é um retrato do instante. Quem recusa
 * continua sendo o servidor, mesmo que esta resposta minta.
 */
import { useQuery } from '@tanstack/react-query';

import { pautadorApi } from '@/lib/pautadorApi';
import { statusDe } from '@/components/trafego/inventario/erros';
import type { CapacidadesDoOperador } from '@/types/trafego';

export const CHAVE_CAPACIDADES = ['trafego', 'capacidades'] as const;

/**
 * O que a tela assume antes de saber: nada.
 *
 * Não é `CapacidadesDoOperador` de propósito — não existe combinação honesta
 * de cinco booleanos para "ainda não perguntei". `null` obriga quem consome a
 * decidir o que fazer com a ignorância, em vez de herdar um padrão.
 */
export interface LeituraDasCapacidades {
  capacidades: CapacidadesDoOperador | null;
  carregando: boolean;
  /** A sessão não vale mais. Distinto de falha de rede: manda entrar de novo. */
  semSessao: boolean;
  falhou: boolean;
  /** Atalhos que já embutem "ausência é não". */
  podeLerGoogle: boolean;
  podeProvar: boolean;
  podeMutar: boolean;
  emLaboratorio: boolean;
}

export function useCapacidades(): LeituraDasCapacidades {
  const consulta = useQuery({
    queryKey: CHAVE_CAPACIDADES,
    queryFn: () => pautadorApi.capacidades(),
    // Não repetir: 401 e 403 não melhoram com insistência, e esta resposta é
    // pedida em toda tela de tráfego.
    retry: false,
    // Curto de propósito. Papel revogado vale no ato do lado do servidor; um
    // cache longo aqui manteria a tela oferecendo o que a rota já recusa.
    staleTime: 60 * 1000,
    refetchOnWindowFocus: true,
  });

  const status = statusDe(consulta.error);
  const semSessao = status === 401;
  const c = consulta.data ?? null;

  return {
    capacidades: c,
    carregando: consulta.isLoading && c == null,
    semSessao,
    falhou: consulta.isError && !semSessao,
    // ⚠️ `?? false` em todos: enquanto não se sabe, não se pode.
    podeLerGoogle: c?.google_read ?? false,
    podeProvar: c?.google_validate_only ?? false,
    podeMutar: c?.google_mutate ?? false,
    emLaboratorio: c?.lab_mode ?? false,
  };
}
