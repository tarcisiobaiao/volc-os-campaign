/**
 * A leitura das oportunidades — o quadro de funis e o estado do portão de
 * criação, numa consulta só e compartilhada.
 *
 * ## Por que React Query e não `useState` + `useEffect`
 *
 * Porque o número de funis prontos precisa aparecer no RÓTULO DA ABA, e o
 * quadro precisa aparecer dentro dela. Com estado local, montar o rótulo
 * custaria uma segunda consulta ao mesmo endereço — e as duas divergiriam no
 * dia em que uma atualizasse antes da outra. O cache resolve isso sem que
 * ninguém precise combinar nada.
 *
 * ## Por que o portão é consultado AQUI e não no clique final
 *
 * Descobrir que a criação está fechada depois de montar a campanha inteira
 * desperdiça o trabalho do operador. O estado do portão entra na tela junto com
 * a lista, antes de qualquer decisão.
 *
 * ## Por que o frescor é o da NOSSA leitura
 *
 * Esta resposta não traz data: ela descreve o nosso registro no instante em que
 * foi pedida. O instante do pedido é, portanto, a idade honesta do que está na
 * tela — e ele aparece, porque número sem idade nesta casa não aparece.
 */
import { useQuery } from '@tanstack/react-query';

import { pautadorApi } from '@/lib/pautadorApi';
import type { EstadoDaTrava, QuadroDeTrafego } from '@/types/trafego';

export const CHAVE_OPORTUNIDADES = ['trafego', 'oportunidades'] as const;

/** Mesmo ritmo do inventário: é o nosso registro, não a conta de anúncio. */
export const INTERVALO_OPORTUNIDADES_MS = 5 * 60 * 1000;

export interface LeituraDasOportunidades {
  quadro: QuadroDeTrafego | null;
  /** O estado do portão de criação. `null` quando não deu para consultar. */
  portao: EstadoDaTrava | null;
  /** Primeira leitura desta sessão, ainda sem nada na mão. */
  carregando: boolean;
  /** Há leitura em curso por cima do que já está na tela. */
  atualizando: boolean;
  /** A última tentativa falhou. Não implica ausência de dado. */
  falhou: boolean;
  /** Quando ESTA tela recebeu o que está mostrando. `null` se nunca recebeu. */
  lidoEm: number | null;
  recarregar: () => void;
}

interface RespostaDoQuadro {
  quadro: QuadroDeTrafego;
  portao: EstadoDaTrava | null;
}

export function useOportunidades(): LeituraDasOportunidades {
  const consulta = useQuery({
    queryKey: CHAVE_OPORTUNIDADES,
    queryFn: async (): Promise<RespostaDoQuadro> => {
      const [quadro, portao] = await Promise.all([
        pautadorApi.quadroDeTrafego(),
        // ⚠️ O portão é consultado em paralelo e a falha dele NÃO derruba o
        // quadro: não saber se a criação está liberada é motivo para avisar,
        // não para esconder a lista de funis publicados.
        pautadorApi.estadoDaTrava().catch(() => null),
      ]);
      return { quadro, portao };
    },
    staleTime: INTERVALO_OPORTUNIDADES_MS,
    refetchOnWindowFocus: true,
    retry: 1,
  });

  return {
    quadro: consulta.data?.quadro ?? null,
    portao: consulta.data?.portao ?? null,
    carregando: consulta.isLoading && !consulta.data,
    atualizando: consulta.isFetching,
    falhou: consulta.isError,
    lidoEm: consulta.dataUpdatedAt || null,
    recarregar: () => { void consulta.refetch(); },
  };
}

/**
 * Só o contador de funis prontos, para o rótulo da aba.
 *
 * `null` enquanto não se sabe — nunca `0`. Mostrar zero antes da resposta é
 * afirmar "não há nada", que é exatamente o que ainda não foi apurado.
 */
export function useContadorDeOportunidades(): number | null {
  const { quadro } = useOportunidades();
  return quadro?.prontos.length ?? null;
}
