import { useQuery } from '@tanstack/react-query';
import { ImageIcon } from 'lucide-react';
import { criativosApi } from '@/lib/criativosApi';
import type { CreativePack } from '../api';

export type ItemPack = CreativePack['manifest']['items'][number];

/** Resolve only the saved master, never a different rendition from its job. */
export function useImagemPack(item: ItemPack | undefined) {
  return useQuery({
    queryKey: ['creative-pack-image', item?.job_id, item?.master_ref, item?.content_hash],
    enabled: Boolean(item?.job_id && item?.master_ref),
    staleTime: 0,
    gcTime: 0,
    retry: 1,
    queryFn: async () => {
      const job = await criativosApi.job(item!.job_id!);
      const image = job.renditions.find(r => r.masterId === item!.master_ref && r.estado === 'pronta'
        && (!item!.content_hash || r.contentHash === item!.content_hash));
      if (!image?.previewUrl) throw new Error('Imagem indisponível.');
      return image;
    },
  });
}

export function CapaPack({ item, nome }: { item: ItemPack | undefined; nome: string }) {
  const image = useImagemPack(item);
  return <div className="flex aspect-[4/3] items-center justify-center overflow-hidden bg-muted">
    {image.data?.previewUrl ? <img src={image.data.previewUrl} alt={`Capa do pack ${nome}`} loading="lazy" className="h-full w-full object-contain transition-transform duration-200 motion-reduce:transition-none group-hover:scale-[1.02]" />
      : <div className="p-5 text-center text-sm text-muted-foreground"><ImageIcon className="mx-auto mb-2 h-8 w-8" aria-hidden />{image.isFetching ? 'Carregando capa…' : 'Prévia indisponível'}</div>}
  </div>;
}

export const caminhoPack = (id: string) => `/trafego/meta/packs/${encodeURIComponent(id)}`;
