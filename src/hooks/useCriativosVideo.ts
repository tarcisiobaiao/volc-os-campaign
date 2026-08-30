/**
 * A leitura de builds de vídeo observados.
 *
 * ## A chave é o SLUG do build, não o id do job
 *
 * `GET /video/{slug}` recebe o identificador que a fábrica externa deu ao build
 * (`short_odete`). O job observado carrega esse slug em
 * `origemExterna.identificadorDoBuild`; quando ele não existe, a leitura não
 * pode ser montada, e a tela declara isso em vez de chamar a rota com um id que
 * o servidor não conhece.
 *
 * ⚠️ `limitacaoDeclarada` vem do SERVIDOR e a tela a exibe como veio. Escrever a
 * limitação no frontend faria a interface inventar o motivo técnico pelo qual o
 * VOLC O.S. ainda não renderiza vídeo, e esse motivo muda no dia em que a
 * isolação avançar. Uma frase congelada no bundle continuaria dizendo a versão
 * antiga da verdade.
 */
import { useQuery } from '@tanstack/react-query';

import { criativosApi, type CatalogoDeVideos } from '@/lib/criativosApi';
import type { VideoObservado } from '@/types/criativos';

export const chaveDoVideo = (slug: string) => ['criativos', 'video', slug] as const;
export const CHAVE_VIDEOS = ['criativos', 'videos'] as const;

export function useCriativosVideo(buildSlug: string | undefined, habilitado = true) {
  return useQuery<VideoObservado>({
    queryKey: chaveDoVideo(buildSlug ?? ''),
    queryFn: () => criativosApi.video(buildSlug as string),
    enabled: Boolean(buildSlug) && habilitado,
    retry: false,
    // `videoUrl` e `posterUrl` são assinadas e curtas: cinco minutos. Meia hora
    // de cache devolveria um link morto a quem voltasse para a aba.
    staleTime: 60_000,
    gcTime: 5 * 60_000,
  });
}

export function useCriativosVideos() {
  return useQuery<CatalogoDeVideos>({
    queryKey: CHAVE_VIDEOS,
    queryFn: () => criativosApi.videos(),
    retry: false,
    staleTime: 60_000,
  });
}
