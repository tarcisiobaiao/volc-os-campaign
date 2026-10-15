import React, { useEffect, useRef } from "react";
import { cn } from "@/lib/utils";
import { Icone } from "@/components/ui/icone";
import { ICONES } from "@/lib/icones";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Link, useLocation } from "react-router-dom";
import { openCommandPalette } from "@/components/CommandPalette";
import { useAuth } from "@/contexts/AuthContext";
import { useIsMobile } from "@/hooks/useIsMobile";
import { type Destino, estaNaSecao, gruposVisiveis } from "./destinos";
import { nomeDoPapel, useSair } from "./MenuDoUsuario";
import { AvatarDeIniciais } from "@/components/sistema/AvatarDeIniciais";

interface NavigationProps {
  isCollapsed: boolean;
  setIsCollapsed: (collapsed: boolean) => void;
  isMobileOpen?: boolean;
  setIsMobileOpen?: (open: boolean) => void;
}

export const Navigation: React.FC<NavigationProps> = ({
  isCollapsed,
  setIsCollapsed,
  isMobileOpen = false,
  setIsMobileOpen
}) => {
  const location = useLocation();
  const { user, userProfile } = useAuth();
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

  const sair = useSair();
  const grupos = gruposVisiveis(userProfile?.role);
  const recolhido = isCollapsed && !isMobile;

  /**
   * Um item do menu é UM elemento, não dois.
   *
   * Era `<Link><Button>…</Button></Link>`: HTML inválido, dois pontos de
   * parada de teclado por item e um alvo real cinco vezes menor que o
   * desenhado. `asChild` funde os dois: uma tag, um papel, um foco.
   *
   * Uma linha só (36px no desktop, 44px no telefone). A descrição, que ocupava
   * uma segunda linha em cada item e empurrava "Sistema" para baixo da dobra,
   * vira dica de mouse. Recolhido, o `aria-label` dá nome ao link, porque o
   * ícone decorativo leva `aria-hidden` por contrato.
   */
  const NavItem = ({ item, isActive }: { item: Destino; isActive: boolean }) => (
    <Button
      asChild
      variant="ghost"
      className={cn(
        "nav-item-volc group w-full justify-start gap-3 rounded-md px-3 relative active:scale-100 hover:bg-transparent hover:text-inherit",
        isActive && "nav-item-volc-active font-semibold",
        !isActive && "text-sidebar-foreground",
        isMobile ? "h-11" : "h-9",
        recolhido && "justify-center px-0"
      )}
    >
      <Link
        to={item.href}
        aria-current={isActive ? "page" : undefined}
        title={recolhido ? item.title : item.description}
        {...(recolhido ? { "aria-label": item.title } : {})}
      >
        {/* Fio aurora + wash navy/roxo: o mesmo eixo do "Pro" no Pautador. O
            título fica navy sólido — aurora em 14px reprova AA no stop ciano. */}
        {isActive && <span aria-hidden="true" className="nav-item-volc-rail" />}
        <Icone
          icon={item.icon}
          tamanho="sm"
          className={cn(
            "nav-item-icon relative z-10",
            isActive ? "text-primary" : "text-muted-foreground group-hover:text-primary"
          )}
        />
        {!recolhido && (
          <span className="nav-item-title relative z-10 min-w-0 truncate text-sm font-medium">{item.title}</span>
        )}
      </Link>
    </Button>
  );

  const sidebarContent = (
    <>
      {/* Marca. O PNG escuro sumia no tema escuro; agora cada tema tem o seu. */}
      <div className={cn("relative flex h-14 shrink-0 items-center border-b border-sidebar-border", recolhido ? "justify-center px-2" : "px-4")}>
        <span className="pointer-events-none absolute inset-x-0 top-0 h-[3px] bg-gradient-aurora" />
        <Link to="/" className="flex min-w-0 items-center gap-2 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" aria-label="VOLC O.S., início">
          {recolhido ? (
            <>
              <img src="/volc-v.png" alt="" className="h-7 w-auto dark:hidden" />
              <img src="/volc-v-light.png" alt="" className="hidden h-7 w-auto dark:block" />
            </>
          ) : (
            <>
              <img src="/volc-logo-baixa.png" alt="" className="h-8 w-auto dark:hidden" />
              <img src="/volc-logo-light.png" alt="" className="hidden h-8 w-auto dark:block" />
              <span className="kicker mt-1 border-l border-sidebar-border pl-2 leading-none">O.S.</span>
            </>
          )}
        </Link>
        {!isMobile && !recolhido && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setIsCollapsed(true)}
            className="ml-auto h-8 w-8 p-0 text-muted-foreground hover:bg-muted/50"
            aria-label="Recolher menu lateral"
            aria-expanded
          >
            <Icone icon={ICONES.fecharMenu} tamanho="sm" />
          </Button>
        )}
        {isMobile && setIsMobileOpen && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setIsMobileOpen(false)}
            className="ml-auto h-10 w-10 p-0 hover:bg-muted/50"
            aria-label="Fechar menu"
          >
            <Icone icon={ICONES.fecharMenu} />
          </Button>
        )}
      </div>

      <ScrollArea className="flex-1">
        <div className={cn("space-y-5 py-4", recolhido ? "px-2" : "px-3")}>
          {/* Recolhido, o botão de expandir mora no topo da coluna de ícones. */}
          {recolhido && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setIsCollapsed(false)}
              className="h-9 w-full p-0 text-muted-foreground hover:bg-muted/50"
              aria-label="Expandir menu lateral"
              aria-expanded={false}
            >
              <Icone icon={ICONES.abrirMenu} tamanho="sm" />
            </Button>
          )}

          {/* No telefone a busca mora no cabeçalho; aqui ela repetiria. */}
          {!isMobile && recolhido && (
            <button
              onClick={() => openCommandPalette()}
              title="Buscar (⌘K)"
              aria-label="Buscar"
              className="nav-search flex h-9 w-full items-center justify-center rounded-md border border-sidebar-border bg-raised text-muted-foreground hover:text-foreground"
            >
              <Icone icon={ICONES.buscar} tamanho="sm" />
            </button>
          )}

          {grupos.map((grupo) => (
            <div key={grupo.id}>
              {recolhido ? (
                <div aria-hidden className="mx-auto mb-2 h-px w-6 bg-sidebar-border" />
              ) : (
                <h3 id={`nav-grupo-${grupo.id}`} className="kicker mb-1.5 px-3">
                  {grupo.titulo}
                </h3>
              )}
              <nav
                aria-label={grupo.titulo}
                {...(!recolhido ? { "aria-labelledby": `nav-grupo-${grupo.id}` } : {})}
                className="space-y-0.5"
              >
                {grupo.itens.map((item) => (
                  <NavItem key={item.href} item={item} isActive={estaNaSecao(location.pathname, item.href)} />
                ))}
              </nav>
            </div>
          ))}
        </div>
      </ScrollArea>

      {/* No desktop, conta e "Sair" moram no menu do usuário do cabeçalho. No
          telefone o cabeçalho não tem espaço, então a conta fica no rodapé da
          gaveta — compacta, uma linha. */}
      {isMobile && (
        <div className="flex items-center gap-3 border-t border-sidebar-border px-4 py-3">
          <AvatarDeIniciais nome={userProfile?.name} email={user?.email} />
          <div className="min-w-0 flex-1">
            <div className="truncate text-xs font-medium text-foreground">{userProfile?.name || user?.email || "Conta"}</div>
            <div className="text-xs text-muted-foreground">{nomeDoPapel(userProfile?.role)}</div>
          </div>
          <Button
            onClick={() => void sair()}
            variant="ghost"
            className="h-11 gap-2 px-3 text-destructive hover:bg-destructive/10 hover:text-destructive"
          >
            <Icone icon={ICONES.sair} tamanho="sm" />
            Sair
          </Button>
        </div>
      )}
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
            "fixed top-0 left-0 z-[50] flex h-full w-80 max-w-[88vw] flex-col border-r border-sidebar-border bg-sidebar shadow-elevated transition-transform duration-[280ms] ease-[cubic-bezier(0.25,1,0.5,1)] motion-reduce:transition-none",
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
        // Fixa na altura da janela: com a página rolando no documento, o menu
        // subia junto e o operador perdia a navegação no meio de uma tabela.
        // Largura sem transição: o design.md proíbe animar `width`.
        "sticky top-0 flex h-screen shrink-0 flex-col self-start border-r border-sidebar-border bg-sidebar",
        isCollapsed ? "w-16" : "w-[248px]"
      )}
    >
      {sidebarContent}
    </div>
  );
};
