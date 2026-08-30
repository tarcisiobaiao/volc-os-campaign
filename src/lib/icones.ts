import type { IconSvgElement } from "@hugeicons/react";
import {
  Analytics01Icon,
  Cancel01Icon,
  DollarCircleIcon,
  Folder01Icon,
  Home01Icon,
  LogOutIcon,
  Megaphone01Icon,
  Menu01Icon,
  Notification01Icon,
  PaintBoardIcon,
  PenTool01Icon,
  PlugSocketIcon,
  Radar01Icon,
  Rocket01Icon,
  SafeBoxIcon,
  Search01Icon,
  Settings02Icon,
  Target01Icon,
  UserGroupIcon,
} from "@hugeicons/core-free-icons";

/**
 * O registry semântico de ícones do VOLC O.S.
 *
 * ---------------------------------------------------------------------------
 * POR QUE UM REGISTRY, E NÃO IMPORTS DIRETOS
 * ---------------------------------------------------------------------------
 *
 * O produto importa 196 ícones distintos do `lucide-react` em 206 arquivos,
 * cada um escolhendo o seu. Sem um lugar que diga o que cada glifo SIGNIFICA,
 * duas coisas acontecem — e as duas já aconteceram aqui:
 *
 *   • O MESMO glifo passa a significar coisas diferentes. `Megaphone` era o
 *     ícone de "Campanhas" E de "Tráfego" no mesmo menu lateral: dois destinos
 *     distintos, um glifo só. Quem navega por reconhecimento visual não tem
 *     como separar os dois.
 *   • O mesmo significado ganha glifos diferentes em telas diferentes, e o
 *     operador precisa reaprender o vocabulário a cada sala.
 *
 * As chaves aqui são CONCEITOS do negócio, não nomes de desenho. Quem escreve
 * uma tela pede `ICONES.campanhas`, não "aquele do megafone". O dia em que o
 * desenho de "campanhas" mudar, ele muda uma vez, aqui.
 *
 * ---------------------------------------------------------------------------
 * UM PESO SÓ
 * ---------------------------------------------------------------------------
 *
 * Todo ícone do produto é da família `stroke-rounded` da Hugeicons, em traço
 * 1.5 (ver `Icone`). Peso misto é a coisa que mais denuncia um sistema montado
 * por partes: dois glifos lado a lado com traços diferentes leem como dois
 * produtos.
 *
 * ---------------------------------------------------------------------------
 * ESTADO DA MIGRAÇÃO
 * ---------------------------------------------------------------------------
 *
 * Migrado: o shell (menu lateral e cabeçalho), que aparece nas 38 rotas
 * protegidas — é a superfície onde a inconsistência custava mais.
 *
 * NÃO migrado: o resto do produto continua em `lucide-react`, de propósito. A
 * missão pede migração POR DOMÍNIO, não busca-e-substituição global, e trocar
 * 196 ícones num lote só tornaria impossível provar que nenhum significado se
 * perdeu no caminho. `lucide-react` continua instalado e com consumidores
 * reais; a regra até lá é a que já vale: não misturar as duas famílias na
 * MESMA superfície. O shell é inteiramente Hugeicons; as páginas são
 * inteiramente Lucide.
 */
export const ICONES = {
  // ── Navegação principal ───────────────────────────────────────────────────
  visaoGeral: Home01Icon,
  projetos: Folder01Icon,
  /** O inventário de campanhas: o que já existe e está no ar. */
  campanhas: Megaphone01Icon,
  relatorios: Analytics01Icon,
  incubadora: Rocket01Icon,
  /** Descoberta de atenção por país — o radar varre, não anuncia. */
  pautador: Radar01Icon,
  redator: PenTool01Icon,
  criativos: PaintBoardIcon,
  /**
   * Compra de tráfego. Era `Megaphone`, o MESMO glifo de "Campanhas".
   * Alvo separa a intenção (mirar, comprar atenção) do inventário (o que já
   * está anunciando).
   */
  trafego: Target01Icon,

  // ── Configuração ──────────────────────────────────────────────────────────
  custos: DollarCircleIcon,
  integracoes: PlugSocketIcon,
  usuarios: UserGroupIcon,
  cofreDeAtivos: SafeBoxIcon,
  qgAgentico: Settings02Icon,

  // ── Ações do shell ────────────────────────────────────────────────────────
  buscar: Search01Icon,
  alertas: Notification01Icon,
  sair: LogOutIcon,
  abrirMenu: Menu01Icon,
  fecharMenu: Cancel01Icon,
} as const satisfies Record<string, IconSvgElement>;

export type NomeDeIcone = keyof typeof ICONES;
