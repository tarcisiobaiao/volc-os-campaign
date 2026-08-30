/**
 * O job por HTTP: carga inicial, retry e cancelamento.
 *
 * ## A ordem importa e é a razão de o job não vir do fluxo
 *
 * A página carrega o job por `GET /jobs/{id}` PRIMEIRO, e só então abre o
 * fluxo de eventos a partir de `job.cursorEventos`. Se o fluxo abrisse antes, a
 * tela teria que reconstruir o estado a partir dos eventos, e uma reconexão que
 * perdesse o começo deixaria a tela sem saber quantas peças foram pedidas.
 * O job é a autoridade; o fluxo é a atualização.
 *
 * ⚠️ Nada disto passa por `localStorage`. Um job é dinheiro gasto no servidor;
 * uma cópia no navegador que discorde do servidor é pior que não ter cópia.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { criativosApi } from '@/lib/criativosApi';
import { CHAVE_RESUMO } from '@/hooks/useCriativosResumo';
import { jobTerminou, type CreativeJob } from '@/types/criativos';

export const chaveDoJob = (id: string) => ['criativos', 'job', id] as const;

export function useCriativosJob(id: string | undefined) {
  return useQuery<CreativeJob>({
    queryKey: chaveDoJob(id ?? ''),
    queryFn: () => criativosApi.job(id as string),
    enabled: Boolean(id),
    retry: false,
    // O fluxo de eventos é quem mantém a tela viva. Um `refetchInterval` aqui
    // duplicaria a leitura e faria dois donos disputarem o mesmo estado.
    refetchOnWindowFocus: false,
    staleTime: Infinity,
  });
}

export function useAcoesDoJob(id: string | undefined) {
  const cliente = useQueryClient();

  const aplicar = (job: CreativeJob) => {
    cliente.setQueryData(chaveDoJob(job.id), job);
    if (jobTerminou(job.estado)) {
      void cliente.invalidateQueries({ queryKey: CHAVE_RESUMO });
    }
  };

  const retentar = useMutation({
    mutationFn: () => criativosApi.retentarJob(id as string),
    onSuccess: aplicar,
  });

  const cancelar = useMutation({
    mutationFn: () => criativosApi.cancelarJob(id as string),
    onSuccess: aplicar,
  });

  return { retentar, cancelar };
}

/**
 * Cria um job de imagem.
 *
 * ⚠️ O formulário NÃO é destruído aqui e não é destruído por quem chama: a SPEC
 * §8.2 lista "formulário destruído ao iniciar geração" como padrão rejeitado.
 * A tela navega para o job; se a navegação falhar ou o operador voltar, o
 * rascunho continua onde estava.
 */
export function useCriarJobDeImagem() {
  const cliente = useQueryClient();
  return useMutation({
    mutationFn: criativosApi.criarJobDeImagem,
    onSuccess: ({ job }) => {
      cliente.setQueryData(chaveDoJob(job.id), job);
      void cliente.invalidateQueries({ queryKey: CHAVE_RESUMO });
    },
  });
}
