/**
 * Uma imagem servida pelo backend, buscada com credencial.
 *
 * `<img src="https://api/…">` é uma requisição que o navegador dispara sozinho,
 * e ele não permite acrescentar cabeçalho. Enquanto a rota de artefatos era
 * aberta isso funcionava. Desde 24/08/2026 ela exige identidade, e a imagem
 * simplesmente não carregaria — silenciosamente, como imagem quebrada.
 *
 * Aqui o arquivo vem por `fetch` com Bearer e vira um `blob:`. O componente
 * mostra os três estados que a tag `<img>` esconde: carregando, carregado e
 * falhou. Uma prova visual que não carregou precisa ser distinguível de uma
 * página em branco — é a diferença entre "não deu para ver" e "está vazio".
 */
import React from 'react';
import { ImageOff, Loader2 } from 'lucide-react';

import { useArtefatoAutenticado } from '@/hooks/useArtefatoAutenticado';
import { cn } from '@/lib/utils';

interface ImagemDoArtefatoProps {
  runId: number;
  arquivo: string;
  versao?: string | number;
  alt?: string;
  className?: string;
  /** Classe do quadro que ocupa o lugar enquanto carrega ou quando falha. */
  classNameEstado?: string;
}

export const ImagemDoArtefato: React.FC<ImagemDoArtefatoProps> = ({
  runId,
  arquivo,
  versao,
  alt = '',
  className,
  classNameEstado,
}) => {
  const artefato = useArtefatoAutenticado(runId, arquivo, versao);

  if (artefato.carregando) {
    return (
      <div
        className={cn('flex items-center justify-center bg-muted/50 py-6', classNameEstado, className)}
        role="status"
        aria-label="Carregando imagem"
      >
        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" aria-hidden />
      </div>
    );
  }

  if (!artefato.url) {
    return (
      <div
        className={cn(
          'flex flex-col items-center justify-center gap-1 bg-muted/50 px-3 py-6 text-center',
          classNameEstado,
          className,
        )}
        role="status"
      >
        <ImageOff className="h-4 w-4 text-muted-foreground" aria-hidden />
        <span className="text-[11px] leading-relaxed text-muted-foreground">
          {artefato.erro ?? 'Imagem indisponível'}
        </span>
      </div>
    );
  }

  return <img src={artefato.url} alt={alt} className={className} />;
};

/**
 * Abre o artefato em tamanho real, em nova aba.
 *
 * Substitui o `<a href>` que apontava direto para a API: navegação de topo não
 * manda credencial, então o link levava a um 401 numa aba em branco.
 */
export async function abrirArtefato(
  runId: number,
  arquivo: string,
  versao?: string | number,
): Promise<void> {
  const { pautadorApi } = await import('@/lib/pautadorApi');
  const blob = await pautadorApi.artefatoBlobUrl(runId, arquivo, versao);
  window.open(blob, '_blank', 'noreferrer');
  // Tempo de a aba carregar antes de soltar a memória.
  window.setTimeout(() => URL.revokeObjectURL(blob), 60_000);
}
