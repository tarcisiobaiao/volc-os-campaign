/**
 * Vocabulário de ícones da Bia. Fica na feature (e não em `src/lib/icones.ts`,
 * que é do shell) até haver um segundo consumidor. Mesma família do produto:
 * Hugeicons stroke-rounded, renderizada por `Icone`.
 */
import {
  Alert02Icon,
  ArrowDown01Icon,
  ArrowLeft01Icon,
  ArrowUp02Icon,
  Attachment01Icon,
  BubbleChatAddIcon,
  Cancel01Icon,
  Clock01Icon,
  Copy01Icon,
  File01Icon,
  Image01Icon,
  LinkSquare02Icon,
  Loading03Icon,
  Message01Icon,
  MinusSignIcon,
  Pdf01Icon,
  RefreshIcon,
  SlashIcon,
  Tick02Icon,
} from '@hugeicons/core-free-icons';

export const ICONES_BIA = {
  lancador: Message01Icon,
  anexar: Attachment01Icon,
  comandos: SlashIcon,
  enviar: ArrowUp02Icon,
  enviando: Loading03Icon,
  copiar: Copy01Icon,
  copiado: Tick02Icon,
  novaConversa: BubbleChatAddIcon,
  conversas: Clock01Icon,
  minimizar: MinusSignIcon,
  fechar: Cancel01Icon,
  voltar: ArrowLeft01Icon,
  remover: Cancel01Icon,
  repetir: RefreshIcon,
  alerta: Alert02Icon,
  linkExterno: LinkSquare02Icon,
  irParaOFim: ArrowDown01Icon,
  imagem: Image01Icon,
  pdf: Pdf01Icon,
  documento: File01Icon,
} as const;
