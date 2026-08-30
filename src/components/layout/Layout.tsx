import React, { useState } from "react";
import { Navigation } from "./Navigation";
import { Button } from "@/components/ui/button";
import { Menu, Search } from "lucide-react";
import { useIsMobile } from "@/hooks/useIsMobile";
import { openCommandPalette } from "@/components/CommandPalette";
import SinoDeAlertas from "@/components/layout/SinoDeAlertas";
import { SeletorDeTema } from '@/components/layout/SeletorDeTema';

interface LayoutProps {
  children: React.ReactNode;
}

export const Layout: React.FC<LayoutProps> = ({ children }) => {
  const [isNavigationCollapsed, setIsNavigationCollapsed] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const isMobile = useIsMobile();

  return (
    <div className="min-h-screen bg-background flex">
      {/*
        Skip link — WCAG 2.4.1.

        O sidebar tem treze links, uma busca e um seletor de tema. Sem isto,
        quem navega por teclado atravessa os quinze controles inteiros em TODA
        troca de página antes de chegar ao trabalho. É o tipo de atrito que não
        aparece em screenshot nenhum e custa o dia inteiro de quem depende dele.

        Ele só é visível com foco, então não muda nada para quem usa mouse.
      */}
      <a
        href="#conteudo-principal"
        className="sr-only focus-visible:not-sr-only focus-visible:fixed focus-visible:left-4 focus-visible:top-4 focus-visible:z-[60] focus-visible:rounded-md focus-visible:border focus-visible:border-border focus-visible:bg-card focus-visible:px-4 focus-visible:py-2 focus-visible:text-sm focus-visible:font-medium focus-visible:text-foreground focus-visible:shadow-card"
      >
        Pular para o conteúdo
      </a>

      {/* Navigation Sidebar / Drawer */}
      <Navigation
        isCollapsed={isNavigationCollapsed}
        setIsCollapsed={setIsNavigationCollapsed}
        isMobileOpen={isMobileMenuOpen}
        setIsMobileOpen={setIsMobileMenuOpen}
      />

      {/* Main Content */}
      <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {isMobile ? (
          /* Mobile: sino no cabeçalho, entre a marca e a busca. */
          <header className="sticky top-0 z-30 h-14 glass flex items-center px-4 border-0 border-b border-border/60 relative">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setIsMobileMenuOpen(true)}
              className="h-10 w-10 p-0 touch-target"
              aria-label="Abrir menu"
            >
              <Menu className="h-5 w-5" />
            </Button>
            <div className="ml-3 flex items-center gap-2 flex-1 min-w-0">
              <img
                src="/volc-logo-baixa.png"
                alt="VOLC O.S."
                className="h-7 object-contain max-w-[140px]"
              />
            </div>
            {/* ⚠️ O seletor de tema existe no telefone também.
                Ele nasceu só no cabeçalho de desktop, e quem opera pelo celular
                ficava sem caminho nenhum para o tema escuro — que é
                justamente onde ele mais serve. Alvo de toque de 40px, dentro da
                mesma faixa dos vizinhos. */}
            <SeletorDeTema className="h-10 w-10 touch-target" />
            <SinoDeAlertas
              className="h-10 w-10 touch-target"
              side="bottom"
              align="end"
            />
            <Button
              variant="ghost"
              size="sm"
              onClick={() => openCommandPalette()}
              className="h-10 w-10 p-0 touch-target"
              aria-label="Buscar"
            >
              <Search className="h-5 w-5" />
            </Button>
            {/* fio aurora sob o header */}
            <span className="pointer-events-none absolute inset-x-0 bottom-0 h-px bg-gradient-aurora opacity-70" />
          </header>
        ) : (
          /* Desktop: cabeçalho global. O canto superior direito é o lugar em
             que o operador procura notificações, independentemente da página. */
          <header className="relative z-30 flex h-14 shrink-0 items-center justify-end border-b border-border bg-background px-6">
            <div className="flex items-center gap-2">
              <SeletorDeTema />
              <SinoDeAlertas
                className="h-9 w-9 border border-border bg-card"
                side="bottom"
                align="end"
              />
            </div>
          </header>
        )}

        <div id="conteudo-principal" tabIndex={-1} className="min-h-0 flex-1 overflow-auto">
          <div className={isMobile ? "pb-4" : ""}>
            {children}
          </div>
        </div>
      </main>
    </div>
  );
};
