import React, { useEffect, useRef } from "react";
import { cn } from "@/lib/utils";
import { type IconSvgElement } from "@hugeicons/react";
import { Icone } from "@/components/ui/icone";
import { ICONES } from "@/lib/icones";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import {
  Sparkles,
  User,
} from "lucide-react";
import { Link, useLocation } from "react-router-dom";
import { openCommandPalette } from "@/components/CommandPalette";
import { useAuth } from "@/contexts/AuthContext";
import { useToast } from "@/hooks/use-toast";
import { useIsMobile } from "@/hooks/useIsMobile";

interface NavigationProps {
  isCollapsed: boolean;
  setIsCollapsed: (collapsed: boolean) => void;
  isMobileOpen?: boolean;
  setIsMobileOpen?: (open: boolean) => void;
}

interface NavigationItem {
  title: string;
  href: string;
  icon: any;
  description: string;
  adminOnly?: boolean;
}

const navigationItems: NavigationItem[] = [
  {
    title: "Dashboard Geral",
    href: "/",
    icon: ICONES.visaoGeral,
    description: "Visão geral de todas as campanhas",
    adminOnly: true // Apenas admin vê o dashboard geral
  },
  {
    title: "Projetos",
    href: "/dashboard/projects",
    icon: ICONES.projetos,
    description: "Gerenciar projetos",
    adminOnly: true // Apenas admin vê projetos
  },
  {
    title: "Campanhas",
    href: "/settings/campaigns",
    icon: ICONES.campanhas,
    description: "Ver e configurar campanhas"
  },
  {
    title: "Relatórios",
    href: "/reports",
    icon: ICONES.relatorios,
    description: "Relatórios e análises avançadas",
    adminOnly: true // Apenas admin vê relatórios
  },
  {
    title: "Incubadora",
    href: "/incubator",
    icon: ICONES.incubadora,
    description: "Pipeline de sites para AdSense",
    adminOnly: true
  },
  {
    title: "Pautador Pro",
    href: "/pautador-pro",
    icon: ICONES.pautador,
    description: "Arbitragem de atenção por país",
    adminOnly: true
  },
  {
    title: "Redator",
    href: "/redator",
    icon: ICONES.redator,
    description: "O funil sendo escrito, etapa por etapa",
    adminOnly: true
  },
  {
    // Nome curto no menu, nome inteiro da área no título da página. O Estúdio é
    // uma área de PRODUÇÃO transversal (SPEC §6): Tráfego e Conteúdo são
    // destinos do patrimônio criativo, não donos dele, e por isso ele não entra
    // como subaba de Tráfego nem como item de Configurações.
    title: "Criativos",
    href: "/criativos",
    icon: ICONES.criativos,
    description: "Estúdio Criativo, produção e aprovação",
    adminOnly: true
  },
  {
    title: "Tráfego",
    href: "/trafego",
    icon: ICONES.trafego,
    // ⚠️ Dizia "Subir campanhas de Search no Google Ads" — uma AÇÃO de UM canal,
    // no rótulo de um Hub que hoje responde três perguntas (o que existe, o que
    // pode virar campanha, o que pede atenção). Quem lia isso não sabia que a
    // conferência do que já está no ar mora aqui, e ia procurá-la noutro lugar.
    // A frase nova nomeia as três abas sem prometer Display, Demand Gen ou PMax,
    // que não existem nesta tela.
    description: "Campanhas, preparar e atenção",
    adminOnly: true
  }
];

const configurationItems: NavigationItem[] = [
  {
    title: "Custos",
    href: "/settings/costs",
    icon: ICONES.custos,
    description: "Definir custos e orçamentos",
    adminOnly: true // Apenas admin vê custos
  },
  {
    title: "Integrações",
    href: "/settings/integrations",
    icon: ICONES.integracoes,
    description: "Google Ads e Ad Manager",
    adminOnly: true // Apenas admin vê integrações
  },
  {
    title: "Usuários",
    href: "/settings/users",
    icon: ICONES.usuarios,
    description: "Cadastros, acessos e comissões",
    adminOnly: true
  },
  {
    title: "Cofre de Ativos",
    href: "/settings/cofre-ativos",
    icon: ICONES.cofreDeAtivos,
    description: "Patrimônio, custódia e relações",
    adminOnly: true
  },
  {
    title: "QG Agêntico",
    href: "/settings/qg-agentico",
    icon: ICONES.qgAgentico,
    description: "Roadmap vivo e execução",
    adminOnly: true
  }
];


/**
 * "Você está aqui" tem que sobreviver à rota filha.
 *
 * A comparação era `location.pathname === item.href`, então o menu só acendia
 * na rota exata. Abrir uma campanha (`/trafego/campanhas/:id`), uma tarefa do
 * QG (`/settings/qg-agentico/tarefas/:id`), um site da Incubadora ou qualquer
 * página do Redator apagava o item inteiro do menu — e o operador perdia a
 * única indicação de onde está, que é o quarto item do teste do tronco.
 *
 * O casamento é por SEGMENTO, não por prefixo de string: `/settings/costs` não
 * pode acender `/settings/co`, e `/` só casa com `/`.
 */
const estaNaSecao = (pathname: string, href: string) => {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(href + "/");
};

export const Navigation: React.FC<NavigationProps> = ({
  isCollapsed,
  setIsCollapsed,
  isMobileOpen = false,
  setIsMobileOpen
}) => {
  const location = useLocation();
  const { user, userProfile, signOut } = useAuth();
  const { toast } = useToast();
  const isMobile = useIsMobile();
  const drawerRef = useRef<HTMLDivElement>(null);
  const abridorRef = useRef<HTMLElement | null>(null);

  /**
   * O contrato de teclado de um diálogo: Escape fecha, o foco entra quando
   * abre e VOLTA para quem abriu quando fecha.
   *
   * A terceira parte é a que costuma faltar. Sem ela, fechar o menu joga o
   * foco na raiz do documento e o operador recomeça a tabulação do zero —
   * depois de já ter atravessado o cabeçalho inteiro para chegar ali.
   */
  useEffect(() => {
    if (!isMobile) return;

    if (isMobileOpen) {
      abridorRef.current = document.activeElement as HTMLElement | null;
      // O primeiro foco vai para o painel, não para o primeiro link: quem usa
      // leitor de tela ouve o nome do diálogo antes do conteúdo.
      drawerRef.current?.focus?.();

      const aoTeclar = (e: KeyboardEvent) => {
        if (e.key === "Escape") {
          e.stopPropagation();
          setIsMobileOpen?.(false);
        }
      };
      document.addEventListener("keydown", aoTeclar);
      return () => document.removeEventListener("keydown", aoTeclar);
    }

    abridorRef.current?.focus?.();
    abridorRef.current = null;
  }, [isMobile, isMobileOpen, setIsMobileOpen]);

  // Fechar menu ao navegar em mobile
  useEffect(() => {
    if (isMobile && setIsMobileOpen) {
      setIsMobileOpen(false);
    }
  }, [location.pathname, isMobile, setIsMobileOpen]);

  const handleSignOut = async () => {
    try {
      await signOut();
      toast({
        title: "Logout realizado",
        description: "Você foi desconectado com sucesso.",
      });
    } catch (error) {
      toast({
        title: "Erro ao fazer logout",
        description: "Tente novamente.",
        variant: "destructive",
      });
    }
  };

  /**
   * Um item do menu é UM elemento, não dois.
   *
   * Era `<Link><Button>…</Button></Link>`: um `<button>` dentro de um `<a>`.
   * HTML inválido (conteúdo interativo dentro de âncora), e o estrago é real,
   * não teórico:
   *
   *   • DOIS pontos de parada de teclado por item. Treze itens viravam vinte e
   *     seis tabulações, metade delas indo para um botão que não faz nada.
   *   • O nome acessível saía concatenado — o leitor de tela anunciava
   *     "Dashboard GeralVisão geral de todas as campanhas" como um nome só.
   *   • O `<a>`, sendo `display:inline`, media 287×20 enquanto o botão pintava
   *     287×48. O alvo REAL do link era um quinto do que se via.
   *
   * `asChild` funde os dois: o Slot do Radix aplica as classes do botão no
   * próprio `<a>`. Uma tag, um papel, um foco, e o alvo passa a ser o que a
   * pessoa enxerga.
   */
  const NavItem = ({ item, isActive }: { item: NavigationItem; isActive: boolean }) => (
    <Button
      asChild
      variant="ghost"
      className={cn(
        "group w-full justify-start gap-3 rounded-md transition-colors duration-150 relative overflow-hidden active:scale-100",
        isMobile ? "h-14" : "h-12",
        isActive
          ? "bg-primary/[0.05] text-primary font-medium hover:bg-primary/[0.08] hover:text-primary"
          : "text-foreground/70 hover:bg-muted/60 hover:text-foreground",
        isCollapsed && !isMobile && "justify-center px-2"
      )}
    >
      {/* ⚠️ ACHADO PELA REVISÃO ADVERSARIAL.
          Recolhido, o link contém SÓ o ícone — e o `Icone` decorativo leva
          `aria-hidden`, por contrato. O bloco com título e descrição só
          renderiza quando expandido. Resultado: treze links sem nome acessível
          nenhum, exatamente no estado em que a palavra também sumiu da tela.
          O `title` serve os dois: dá nome ao leitor e tooltip a quem usa mouse
          e não reconhece o glifo. */}
      <Link
        to={item.href}
        aria-current={isActive ? "page" : undefined}
        {...(isCollapsed && !isMobile ? { title: item.title, "aria-label": item.title } : {})}
      >
        {/* Era uma faixa aurora de 3px. Duas proibições de uma vez: o
            `design.md` bane faixa lateral acima de 1px, e bane aurora como
            estado operacional — "selecionado" é estado, não identidade. O
            tinte de fundo + a tinta primária + este fio de 1px já dizem
            "você está aqui" sem gastar a assinatura da marca. */}
        {isActive && (
          <span aria-hidden="true" className="absolute left-0 top-1.5 bottom-1.5 w-px bg-primary" />
        )}
        <Icone
          icon={item.icon}
          className={cn(
            "relative z-10 transition-colors",
            isActive ? "text-primary" : "text-muted-foreground group-hover:text-foreground"
          )}
        />
        {(!isCollapsed || isMobile) && (
          <div className="flex flex-col items-start relative z-10 min-w-0">
            <span className="text-sm font-medium truncate">{item.title}</span>
            <span className="text-[11px] text-muted-foreground truncate">{item.description}</span>
          </div>
        )}
      </Link>
    </Button>
  );

  // Conteúdo da sidebar
  const sidebarContent = (
    <>
      {/* Header */}
      <div className="p-4 border-b border-border relative">
        <span className="pointer-events-none absolute inset-x-0 top-0 h-[3px] bg-gradient-aurora" />
        <div className="flex items-center justify-center w-full">
          {(!isCollapsed || isMobile) ? (
            <div className="animate-fade-in flex-1 flex flex-col items-center justify-center text-center">
              <img
                src="/volc-logo-baixa.png"
                alt="VOLC O.S."
                className="h-12 max-w-full object-contain mb-2"
              />
              <p className="kicker flex items-center gap-1.5">
                <Sparkles className="h-3 w-3" />
                Google Ads & Ad Manager
              </p>
            </div>
          ) : (
            <div className="flex items-center justify-center w-9 h-9 rounded-md bg-gradient-aurora shadow-glow">
              <span className="font-display text-sm font-bold text-white">V</span>
            </div>
          )}
          {/* Botão de toggle - apenas desktop */}
          {!isMobile && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setIsCollapsed(!isCollapsed)}
              className="h-8 w-8 p-0 hover:bg-muted/50 transition-colors absolute top-4 right-4"
              /* ⚠️ Era o único controle da aplicação sem nome acessível: um
                 botão com SVG puro dentro. Quem usa leitor de tela ouvia
                 "botão" e não tinha como saber o que ele faz. O nome diz o
                 ESTADO e a AÇÃO, porque o mesmo botão recolhe e expande. */
              aria-label={isCollapsed ? 'Expandir menu lateral' : 'Recolher menu lateral'}
              aria-expanded={!isCollapsed}
            >
              <Icone icon={isCollapsed ? ICONES.abrirMenu : ICONES.fecharMenu} tamanho="sm" />
            </Button>
          )}
          {/* Botão fechar - apenas mobile */}
          {isMobile && setIsMobileOpen && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setIsMobileOpen(false)}
              className="h-10 w-10 p-0 hover:bg-muted/50 transition-colors absolute top-4 right-4"
              aria-label="Fechar menu"
            >
              <Icone icon={ICONES.fecharMenu} />
            </Button>
          )}
        </div>
      </div>

      {/* Navigation Content */}
      <ScrollArea className="flex-1">
        <div className="p-4 space-y-6">
          {/* Busca / Command palette (⌘K) */}
          <button
            onClick={() => openCommandPalette()}
            title="Buscar (⌘K)"
            className={cn(
              "w-full flex items-center gap-2 h-10 rounded-md border border-border bg-muted/40 text-muted-foreground hover:bg-muted hover:text-foreground hover:border-primary/30 transition-colors text-sm",
              isCollapsed && !isMobile ? "justify-center px-2" : "px-3"
            )}
          >
            <Icone icon={ICONES.buscar} tamanho="sm" />
            {(!isCollapsed || isMobile) && (
              <>
                <span className="flex-1 text-left">Buscar…</span>
                <kbd className="rounded border border-border bg-background px-1.5 py-0.5 text-[10px] leading-none text-muted-foreground">⌘K</kbd>
              </>
            )}
          </button>

          {/* Main Navigation */}
          <div>
            {(!isCollapsed || isMobile) && (
              <h3 className="kicker mb-3 px-1">
                Principal
              </h3>
            )}
            <nav aria-label="Navegação principal" className="space-y-2">
              {navigationItems.map((item) => {
                // Filtrar itens adminOnly para operadores
                if (item.adminOnly && userProfile?.role !== 'ADMIN') {
                  return null;
                }
                return (
                  <NavItem
                    key={item.href}
                    item={item}
                    isActive={estaNaSecao(location.pathname, item.href)}
                  />
                );
              })}
            </nav>
          </div>

          {/* Separator e Configuration - Ocultar seção inteira para OPERATORs */}
          {userProfile?.role !== 'OPERATOR' && (
            <>
              <Separator className="bg-gradient-to-r from-transparent via-border to-transparent" />
            <div>
              {(!isCollapsed || isMobile) && (
                <h3 className="kicker mb-3 px-1">
                  Configurações
                </h3>
              )}
              <nav aria-label="Configurações" className="space-y-2">
                {configurationItems.map((item) => {
                  // Hide admin-only items from non-admin users
                  if (item.adminOnly && userProfile?.role !== 'ADMIN') {
                    return null;
                  }
                  return (
                    <NavItem
                      key={item.href}
                      item={item}
                      isActive={estaNaSecao(location.pathname, item.href)}
                    />
                  );
                })}
              </nav>
            </div>
            </>
          )}
        </div>
      </ScrollArea>

      {/* User Section */}
      <div className="p-4 border-t border-border bg-gradient-to-r from-muted/20 to-background">
        {(!isCollapsed || isMobile) ? (
          <div className="space-y-3 animate-fade-in">
            {/* User Info */}
            <div className="flex items-center gap-3 p-3 rounded-lg bg-muted/50 border border-border">
              <div className="h-8 w-8 rounded-full bg-gradient-aurora flex items-center justify-center shadow-glow">
                <User className="h-4 w-4 text-white" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-xs font-medium text-foreground truncate">
                  {user?.email || "Usuário"}
                </div>
                <div className="text-xs text-muted-foreground">
                  Online
                </div>
              </div>
            </div>

            {/* Logout Button */}
            <Button
              onClick={handleSignOut}
              variant="ghost"
              className={cn(
                "w-full justify-start gap-3 text-destructive hover:text-destructive hover:bg-destructive/10",
                isMobile ? "h-12" : "h-10"
              )}
            >
              <Icone icon={ICONES.sair} tamanho="sm" />
              <span className="text-sm">Sair</span>
            </Button>

            {/* Integration Status - esconder em mobile para economizar espaço */}
            {!isMobile && (
              <div className="text-center">
                {/* ⚠️ Aqui havia dois pontos VERDES PULSANDO com as palavras
                    "Integrado com · Google Ads · Ad Manager". Nada alimentava
                    esses pontos: eram JSX fixo. O sidebar afirmava saúde de
                    integração o tempo inteiro — inclusive na mesma tela em que
                    o Hub de Tráfego dizia "Não consegui ler o inventário".
                    Isso é a proibição número um do PRODUCT.md: criar sensação
                    de controle fictícia.

                    Um rótulo de ESCOPO não mente. Quem quer saber se a conta
                    respondeu tem a leitura datada no Hub, que é medida. */}
                <div className="kicker mb-2">Fontes conectadas</div>
                <p className="text-xs text-muted-foreground">
                  Google Ads · Ad Manager
                </p>
              </div>
            )}
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3">
            <div className="h-8 w-8 rounded-full bg-gradient-aurora flex items-center justify-center">
              <User className="h-4 w-4 text-white" />
            </div>
            <Button
              onClick={handleSignOut}
              variant="ghost"
              size="sm"
              className="h-8 w-8 p-0 text-destructive hover:text-destructive hover:bg-destructive/10"
              aria-label="Sair da conta"
            >
              <Icone icon={ICONES.sair} tamanho="sm" />
            </Button>
            {/* Os mesmos pontos inventados da versão expandida, aqui sem nem
                a palavra ao lado: status comunicado só por cor (WCAG 1.4.1) e
                sem dado por trás. Recolhido, o sidebar não promete nada. */}
          </div>
        )}
      </div>
    </>
  );

  // Mobile: Drawer overlay com backdrop
  if (isMobile) {
    return (
      <>
        {/* Backdrop */}
        {isMobileOpen && (
          <div
            aria-hidden="true"
            className="fixed inset-0 bg-black/50 z-40 transition-opacity duration-200 ease-out motion-reduce:transition-none"
            onClick={() => setIsMobileOpen && setIsMobileOpen(false)}
          />
        )}

        {/*
          O drawer é um DIÁLOGO, e antes não era nenhum.

          Ele ficava sempre montado e só deslizava para fora com
          `-translate-x-full`. Fora da tela, mas ainda na árvore: o teclado
          continuava tabulando por dentro dele — o operador saía do conteúdo e
          caía em treze links invisíveis. Não tinha `role`, então o leitor de
          tela nunca anunciava que algo abriu; não tinha nome; não fechava no
          Escape; e o foco não entrava nem ficava preso.

          `inert` resolve a parte mais grave de um jeito que o browser garante:
          fechado, o drawer sai do foco, do tab e da acessibilidade inteira.
          O Escape e a devolução do foco estão no efeito acima.
        */}
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Menu de navegação"
          aria-hidden={!isMobileOpen}
          {...(!isMobileOpen ? { inert: "" as const } : {})}
          ref={drawerRef}
          tabIndex={-1}
          className={cn(
            "fixed top-0 left-0 h-full w-80 max-w-[88vw] bg-gradient-to-b from-card via-card to-muted/30 border-r border-border flex flex-col shadow-2xl z-50 transition-transform duration-200 ease-out motion-reduce:transition-none",
            isMobileOpen ? "translate-x-0" : "-translate-x-full"
          )}
        >
          {sidebarContent}
        </div>
      </>
    );
  }

  // Desktop: Sidebar normal
  return (
    <div
      className={cn(
        "relative bg-gradient-to-b from-card via-card to-muted/30 border-r border-border transition-[width] duration-200 ease-out flex flex-col shadow-lg",
        isCollapsed ? "w-16" : "w-80"
      )}
    >
      {sidebarContent}
    </div>
  );
};
