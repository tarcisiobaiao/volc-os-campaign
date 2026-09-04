/**
 * A correspondência ÚNICA entre estado de portão e como ele aparece.
 *
 * ## Por que ela precisa existir num lugar só
 *
 * Havia dois renderizadores de portão discordando de cor sobre o MESMO veredito:
 * `canais/PortoesDoCanal.tsx:57-62` pintava BLOQUEADO de âmbar e INDETERMINADO
 * de ardósia; `canais/PainelDaMensuracao.tsx:67-74` pintava BLOQUEADO de
 * vermelho e INDETERMINADO de âmbar. Os dois módulos que os alimentam
 * (`lib/trafego/canais.ts` e `lib/trafego/portoes.ts`) exportam os MESMOS nomes
 * — `ORDEM_DOS_PORTOES`, `ROTULO_DO_PORTAO`, `EstadoDePortao`, `tomDoEstado` —
 * com significados diferentes, o que torna a colisão fácil de não perceber.
 *
 * O operador que aprende "âmbar = bloqueado" numa aba e vê "vermelho =
 * bloqueado" na outra deixa de confiar na cor, que era o ponto de usá-la.
 *
 * ## A regra inegociável
 *
 * **Só `PRONTO`/`PERMITIDO` pinta positivo.** `PARCIAL` não é "quase pronto": é
 * "li alguma coisa verdadeira e não o bastante". `INDETERMINADO` é ignorância, e
 * ignorância nunca é uma cor boa. As duas são âmbar — a cor de "não sei" —, e
 * nunca verde-claro, que faria o operador tratá-las como degrau vencido.
 */
import { CircleCheck, CircleHelp, CircleOff, Lock, Minus, TriangleAlert } from 'lucide-react';

import type { TomDoChip } from '../ChipDeEstado';
import type { EstadoDePortao as EstadoDaMensuracao } from '@/lib/trafego/portoes';
import type { EstadoDePortao as EstadoDoCanal } from '@/lib/trafego/canais';

type Glifo = React.ComponentType<{ className?: string }>;

/** Os sete portões de mensuração: PRONTO · PARCIAL · NAO_PRONTO · … */
export const TOM_DO_ESTADO: Record<EstadoDaMensuracao, TomDoChip> = {
  PRONTO: 'bom',
  // ⚠️ Âmbar, não verde-claro. Ver o ⚠️ do topo.
  PARCIAL: 'atencao',
  NAO_PRONTO: 'ruim',
  INDETERMINADO: 'atencao',
  NAO_APLICAVEL: 'neutro',
};

export const GLIFO_DO_ESTADO: Record<EstadoDaMensuracao, Glifo> = {
  PRONTO: CircleCheck,
  PARCIAL: TriangleAlert,
  NAO_PRONTO: CircleOff,
  INDETERMINADO: CircleHelp,
  NAO_APLICAVEL: Minus,
};

/** Os quatro portões de canal: PERMITIDO · BLOQUEADO · INDETERMINADO · … */
export const TOM_DO_PORTAO_DE_CANAL: Record<EstadoDoCanal, TomDoChip> = {
  PERMITIDO: 'bom',
  // Vermelho, e não âmbar: um portão de canal fechado é uma recusa declarada
  // pelo servidor, não uma dúvida.
  BLOQUEADO: 'ruim',
  INDETERMINADO: 'atencao',
  NAO_APLICAVEL: 'neutro',
};

export const GLIFO_DO_PORTAO_DE_CANAL: Record<EstadoDoCanal, Glifo> = {
  PERMITIDO: CircleCheck,
  BLOQUEADO: Lock,
  INDETERMINADO: CircleHelp,
  NAO_APLICAVEL: Minus,
};

export const PALAVRA_DO_PORTAO_DE_CANAL: Record<EstadoDoCanal, string> = {
  PERMITIDO: 'permitido',
  BLOQUEADO: 'bloqueado',
  INDETERMINADO: 'não se sabe',
  NAO_APLICAVEL: 'não se aplica',
};
