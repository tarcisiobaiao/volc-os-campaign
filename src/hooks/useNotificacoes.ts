/**
 * Uma única leitura compartilhada para toda a central de notificações.
 *
 * O sino e a aba Atenção ficam montados ao mesmo tempo e mostram a MESMA
 * condição. Se cada um tivesse `fetch` e cronômetro próprios, existiriam duas
 * verdades sobre o mesmo fato — e elas divergiriam exatamente quando importa,
 * porque uma teria atualizado e a outra não. O React Query deduplica, guarda o
 * último resultado utilizável, e qualquer superfície pode pedir atualização
 * sem criar uma segunda fonte.
 *
 * O sino é PROJEÇÃO: ele não varre nada por conta própria e não mantém estado
 * paralelo. Clicar leva à aba Atenção com foco na campanha; a lista completa
 * mora lá, não nos dois lugares ao mesmo tempo.
 */
import { useQuery } from '@tanstack/react-query';

import { pautadorApi } from '@/lib/pautadorApi';

/**
 * Escolha operacional, não medição do Google: a condição observada não muda em
 * segundos.
 *
 * Até a Fase 1B esta leitura executava consultas ao Google Ads a cada abertura
 * de tela — abrir o app custava cota da conta de anúncios. Agora ela projeta o
 * SNAPSHOT que o sincronizador gravou, então o intervalo deixou de ser um
 * limite de custo e passou a ser só o ritmo em que faz sentido reperguntar ao
 * nosso próprio banco.
 */
export const INTERVALO_NOTIFICACOES_MS = 10 * 60 * 1000;
export const CHAVE_NOTIFICACOES = ['notificacoes', 'trafego'] as const;

export function useNotificacoes(opcoes?: { habilitado?: boolean }) {
  const habilitado = opcoes?.habilitado ?? true;
  return useQuery({
    queryKey: CHAVE_NOTIFICACOES,
    queryFn: () => pautadorApi.alertasDeTrafego(),
    staleTime: INTERVALO_NOTIFICACOES_MS,
    refetchInterval: habilitado ? INTERVALO_NOTIFICACOES_MS : false,
    refetchOnWindowFocus: habilitado,
    enabled: habilitado,
    retry: 1,
  });
}
