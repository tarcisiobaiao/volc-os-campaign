/**
 * O player do build observado.
 *
 * Controles NATIVOS de propósito: o `<video controls>` do navegador já traz
 * teclado, legenda, velocidade, tela cheia e picture-in-picture, e cada um
 * desses é um item que uma barra de controles caseira erra.
 *
 * ⚠️ Sem `autoPlay`, sem `muted` automático e com `preload="none"`. SPEC §17:
 * "Nenhum vídeo inicia som automaticamente". `preload="none"` também é decisão
 * de custo: a biblioteca não baixa o master inteiro só para desenhar a lista.
 */
import React from 'react';

import { cn } from '@/lib/utils';
import { SemArquivo } from '@/components/criativos/comum/Estados';

export const PlayerDoVideo: React.FC<{
  videoUrl: string | null;
  posterUrl: string | null;
  titulo: string;
  className?: string;
}> = ({ videoUrl, posterUrl, titulo, className }) => {
  if (!videoUrl) {
    return (
      <SemArquivo
        className={className}
        motivo="O arquivo de vídeo não está disponível nesta leitura. O build existe e o contrato abaixo continua válido."
      />
    );
  }
  return (
    <div className={cn('overflow-hidden rounded-md border border-border bg-black/90', className)}>
      <video
        controls
        preload="none"
        poster={posterUrl ?? undefined}
        src={videoUrl}
        aria-label={`Vídeo do build ${titulo}`}
        className="mx-auto max-h-[70vh] w-full"
      >
        Seu navegador não reproduz vídeo embutido. Use o link de download para abrir o arquivo.
      </video>
    </div>
  );
};
