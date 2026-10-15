import React, { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Navigation } from "./Navigation";
import { Button } from "@/components/ui/button";
import { Icone } from "@/components/ui/icone";
import { ICONES } from "@/lib/icones";
import { useIsMobile } from "@/hooks/useIsMobile";
import { openCommandPalette } from "@/components/CommandPalette";
import SinoDeAlertas from "@/components/layout/SinoDeAlertas";
import { SeletorDeTema } from '@/components/layout/SeletorDeTema';
import { MenuDoUsuario } from "./MenuDoUsuario";
import { localizar } from "./destinos";
import { isBiaEnabled } from "@/features/bia/featureFlag";

// Bia (P09-T04) sob demanda e só com a flag: desligada, o Layout não importa
// nada da Bia (nem a sessão, nem o widget) e o chunk principal não cresce.
const BiaNoLayout = React.lazy(() => import("@/features/bia/BiaNoLayout"));

const CHAVE_RECOLHIDO = "volc.menu.recolhido";

/** Preferência por pessoa e por navegador. Sem armazenamento, o menu abre. */
function lerRecolhido(): boolean {
  try {
    return window.localStorage.getItem(CHAVE_RECOLHIDO) === "1";
  } catch {
    return false;
  }
}

/**
 * "Onde estou", no cabeçalho.
 *
 * Grupo › destino, derivados do mesmo mapa do menu. Numa rota filha
 * (`/settings/qg-agentico/tarefas/:id`) o destino vira link de volta. Rota
 * fora do mapa não ganha trilha inventada.
 */
const Trilha: React.FC = () => {
  const { pathname } = useLocation();
  const onde = localizar(pathname);
  if (!onde) return null;
  return (
    <nav aria-label="Você está em" className="min-w-0">
      <ol className="flex min-w-0 items-center gap-2 text-sm">
        <li className="kicker shrink-0">{onde.grupo.titulo}</li>
        <li aria-hidden className="text-muted-foreground">/</li>
        <li className="min-w-0 truncate">
          {onde.profundo ? (
            <Link to={onde.destino.href} className="font-medium text-muted-foreground hover:text-foreground">
              {onde.destino.title}
            </Link>
          ) : (
            <span aria-current="page" className="font-semibold text-foreground">{onde.destino.title}</span>
          )}
        </li>
      </ol>
    </nav>
  );
};

interface LayoutProps {
  children: React.ReactNode;
}

export const Layout: React.FC<LayoutProps> = ({ children }) => {
  const [isNavigationCollapsed, setRecolhido] = useState(lerRecolhido);
  const setIsNavigationCollapsed = (valor: boolean) => {
    setRecolhido(valor);
    try {
      window.localStorage.setItem(CHAVE_RECOLHIDO, valor ? "1" : "0");
    } catch {
      /* sem armazenamento: vale só para esta visita */
    }
  };
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
      {/* `overflow-x-clip` e não `overflow-hidden`: os dois cortam o
          transbordo lateral, mas só o segundo vira contêiner de rolagem — e
          aí o cabeçalho `sticky` deixava de grudar no topo da janela. */}
      <main className="flex min-w-0 flex-1 flex-col overflow-x-clip">
        {isMobile ? (
          /* Mobile: sino no cabeçalho, entre a marca e a busca. */
          <header className="sticky top-0 z-[30] flex h-14 items-center border-b border-border bg-card px-4">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setIsMobileMenuOpen(true)}
              className="h-10 w-10 p-0 touch-target"
              aria-label="Abrir menu"
            >
              <Icone icon={ICONES.abrirMenu} />
            </Button>
            <div className="ml-3 flex items-center gap-2 flex-1 min-w-0">
              <img
                src="/volc-logo-baixa.png"
                alt="VOLC O.S."
                className="h-7 object-contain max-w-[140px] dark:hidden"
              />
              <img
                src="/volc-logo-light.png"
                alt="VOLC O.S."
                className="hidden h-7 object-contain max-w-[140px] dark:block"
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
              <Icone icon={ICONES.buscar} />
            </Button>
          </header>
        ) : (
          /* Desktop: barra de comando. Antes eram 56px vazios com dois ícones
             no canto; agora carrega o contexto (onde estou), a busca que já
             existia só no menu, e quem está logado. O sino continua no canto
             superior direito, onde o operador procura notificações. */
          <header className="sticky top-0 z-[30] flex h-14 shrink-0 items-center gap-4 border-b border-border bg-card px-6">
            <div className="min-w-0 flex-1">
              <Trilha />
            </div>
            <button
              type="button"
              onClick={() => openCommandPalette()}
              className="nav-search hidden h-9 w-72 items-center gap-2 rounded-md border border-border bg-background/60 px-3 text-sm text-muted-foreground hover:text-foreground lg:flex"
            >
              <Icone icon={ICONES.buscar} tamanho="sm" />
              <span className="flex-1 text-left">Buscar ou ir para…</span>
              <kbd className="rounded border border-border bg-card px-1.5 py-0.5 text-[10px] leading-none text-muted-foreground">⌘K</kbd>
            </button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => openCommandPalette()}
              className="h-9 w-9 p-0 lg:hidden"
              aria-label="Buscar"
            >
              <Icone icon={ICONES.buscar} tamanho="sm" />
            </Button>
            <div className="flex items-center gap-1.5">
              <SeletorDeTema />
              <SinoDeAlertas
                className="h-9 w-9 border border-border bg-card"
                side="bottom"
                align="end"
              />
              <span aria-hidden className="mx-1 h-6 w-px bg-border" />
              <MenuDoUsuario />
            </div>
          </header>
        )}

        <div id="conteudo-principal" tabIndex={-1} className="min-h-0 flex-1 overflow-auto">
          <div className={isMobile ? "pb-4" : ""}>
            {children}
          </div>
        </div>
      </main>
      {/* Bia (P09-T04): só com VITE_BIA_ENABLED e papel ADMIN; some no logout. */}
      {isBiaEnabled() ? (
        <React.Suspense fallback={null}>
          <BiaNoLayout />
        </React.Suspense>
      ) : null}
    </div>
  );
};
