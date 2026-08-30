/**
 * A escolha entre imagem e vídeo, revelada só quando `Criar` é acionado.
 *
 * SPEC §7: "seletor Imagem ou Vídeo apenas quando a ação for iniciada". E não é
 * modal de propósito: o DESIGN.md proíbe modal para fluxo longo, e um modal que
 * abre para dar dois botões e fecha para abrir um formulário é uma camada a
 * mais entre a intenção e o trabalho.
 *
 * ⚠️ A opção de vídeo NÃO promete render. Ela leva ao briefing, que declara a
 * limitação com o texto que o servidor manda. Um botão que parece funcionar e
 * termina em "ainda não dá" gasta o tempo de quem clicou.
 */
import React from 'react';
import { Image, Video } from 'lucide-react';
import { Link } from 'react-router-dom';

import { cn } from '@/lib/utils';

const OPCAO = cn(
  'flex min-h-[5.5rem] flex-1 items-start gap-3 rounded-md border border-border bg-card px-4 py-3 text-left',
  'transition-colors duration-150 ease-out hover:border-primary/50 hover:bg-primary/[0.05]',
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
);

export const SeletorDeCriacao: React.FC<{
  id?: string;
  /**
   * O servidor tem leitura de vídeo neste ambiente. `null` é "ainda não sei", e
   * ignorância não vira promessa: a opção continua visível e a frase diz que a
   * capacidade não foi confirmada.
   */
  videoDisponivel?: boolean | null;
  className?: string;
}> = ({ id, videoDisponivel = null, className }) => (
  <div
    id={id}
    className={cn('flex flex-col gap-3 sm:flex-row', className)}
    role="group"
    aria-label="O que você quer criar"
  >
    <Link to="/criativos/imagens/novo" className={OPCAO}>
      <Image className="mt-0.5 h-5 w-5 shrink-0 text-primary" aria-hidden />
      <span className="min-w-0">
        <span className="block font-display text-sm font-semibold text-foreground">
          Criar imagem
        </span>
        <span className="mt-1 block text-[13px] leading-relaxed text-muted-foreground">
          Briefing guiado. Uma peça por formato escolhido, com custo apurado por peça.
        </span>
      </span>
    </Link>
    <Link to="/criativos/videos/novo" className={OPCAO}>
      <Video className="mt-0.5 h-5 w-5 shrink-0 text-primary" aria-hidden />
      <span className="min-w-0">
        <span className="block font-display text-sm font-semibold text-foreground">
          Criar vídeo
        </span>
        <span className="mt-1 block text-[13px] leading-relaxed text-muted-foreground">
          {videoDisponivel === false
            ? 'Este ambiente não tem leitura de build de vídeo. O briefing explica o que falta.'
            : 'Abre o briefing de vídeo, que declara o que ainda não é possível iniciar por aqui.'}
        </span>
      </span>
    </Link>
  </div>
);
