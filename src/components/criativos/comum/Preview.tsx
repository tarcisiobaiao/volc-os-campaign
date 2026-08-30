/**
 * A prévia de um ativo, com renovação de link assinado.
 *
 * ## O defeito que este componente fecha
 *
 * `previewUrl` é uma URL assinada que vale CINCO MINUTOS. Uma aba do Estúdio
 * fica aberta muito mais que isso: o operador abre a biblioteca, vai atender o
 * telefone e volta. Na volta, cada `<img>` da tela responde 403 e a biblioteca
 * inteira vira um mural de ícones quebrados, que é indistinguível de "os
 * arquivos sumiram".
 *
 * O remédio é reler o recurso, não acusar defeito: o `onError` pede uma leitura
 * nova, o servidor assina links novos e as imagens voltam. A tentativa é ÚNICA
 * por URL, porque um `onError` que sempre repede vira laço infinito quando o
 * arquivo realmente não existe.
 *
 * ⚠️ Nenhuma URL é montada aqui. Se `previewUrl` chega `null`, a peça não tem
 * arquivo e a tela diz isso; não existe caminho em que este componente componha
 * bucket com chave.
 */
import React from 'react';

import { cn } from '@/lib/utils';
import { SemArquivo } from '@/components/criativos/comum/Estados';

export const Preview: React.FC<{
  url: string | null;
  /** Descreve a imagem para quem não a vê. Nunca "imagem" nem "prévia". */
  alt: string;
  /** Pede ao dono da consulta uma leitura nova, com link novo. */
  aoRenovar?: () => void;
  className?: string;
  classNameImagem?: string;
  motivoSemArquivo?: string;
  /** Miniatura pequena: a indisponibilidade vira glifo mais texto acessível. */
  denso?: boolean;
}> = ({ url, alt, aoRenovar, className, classNameImagem, motivoSemArquivo, denso }) => {
  const [expirou, setExpirou] = React.useState(false);
  const jaPediuPara = React.useRef<string | null>(null);

  React.useEffect(() => {
    setExpirou(false);
  }, [url]);

  if (!url) {
    return <SemArquivo className={className} motivo={motivoSemArquivo} denso={denso} />;
  }

  if (expirou) {
    return (
      <SemArquivo
        className={className}
        denso={denso}
        motivo="O link desta prévia expirou. Estamos pedindo um link novo ao servidor."
      />
    );
  }

  return (
    <img
      src={url}
      alt={alt}
      loading="lazy"
      decoding="async"
      className={cn('bg-muted/40 object-contain', classNameImagem, className)}
      onError={() => {
        setExpirou(true);
        if (jaPediuPara.current === url) return;
        jaPediuPara.current = url;
        aoRenovar?.();
      }}
    />
  );
};
