import { HugeiconsIcon, type IconSvgElement } from "@hugeicons/react";

import { cn } from "@/lib/utils";

/**
 * O ícone canônico do VOLC O.S.
 *
 * Existe para tornar difícil errar as quatro coisas que um ícone erra sozinho:
 *
 * 1. NOME ACESSÍVEL. O padrão aqui é DECORATIVO (`aria-hidden`), porque a
 *    esmagadora maioria dos ícones do produto acompanha uma palavra que já diz
 *    a mesma coisa — e o leitor de tela anunciando "ícone de megafone,
 *    Campanhas" só atrapalha. Quando o ícone é o único portador do
 *    significado — um botão só de glifo —, `rotulo` o torna uma imagem com
 *    nome. Não existe estado intermediário: ou tem palavra ao lado, ou tem
 *    rótulo.
 *
 * 2. TAMANHO. Três degraus e só. A auditoria achou ícones de 12, 14, 16, 18,
 *    20 e 24px na mesma tela, e uma escala aberta é como isso acontece.
 *
 * 3. PESO. Traço 1.5 fixo, e `absoluteStrokeWidth` para o traço não engordar
 *    junto com o tamanho — sem isso, o ícone grande fica visivelmente mais
 *    gordo que o pequeno ao lado dele.
 *
 * 4. ALINHAMENTO ÓPTICO. `shrink-0` impede o ícone de ser esmagado dentro de
 *    um flex apertado, e `block` tira o espaço fantasma de baseline que faz um
 *    glifo inline parecer 1px mais alto que o texto vizinho.
 *
 * O alvo de toque NÃO mora aqui: quem tem tamanho de alvo é o botão que
 * envolve o ícone. Um ícone de 20px dentro de um botão de 40px está certo; o
 * erro é o botão de 20px. Use `touch-target` no controle.
 */

const TAMANHOS = {
  /** Dentro de chip, tabela densa, metadado. */
  sm: 16,
  /** Padrão: botão, item de menu, cabeçalho de seção. */
  md: 20,
  /** Estado vazio, marco de página. */
  lg: 24,
} as const;

type Props = {
  icon: IconSvgElement;
  tamanho?: keyof typeof TAMANHOS;
  className?: string;
} & (
  | {
      /** O ícone É o significado (botão só de glifo). Vira imagem com nome. */
      rotulo: string;
    }
  | {
      /** Decorativo: existe uma palavra ao lado dizendo a mesma coisa. */
      rotulo?: undefined;
    }
);

export const Icone: React.FC<Props> = ({ icon, tamanho = "md", rotulo, className }) => (
  <HugeiconsIcon
    icon={icon}
    size={TAMANHOS[tamanho]}
    strokeWidth={1.5}
    absoluteStrokeWidth
    className={cn("block shrink-0", className)}
    {...(rotulo
      ? { role: "img", "aria-label": rotulo }
      : { "aria-hidden": true, focusable: false })}
  />
);
