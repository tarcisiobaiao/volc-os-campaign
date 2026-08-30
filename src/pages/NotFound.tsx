import { useLocation } from "react-router-dom";
import { useEffect } from "react";
import { Button } from "@/components/ui/button";
import { ArrowLeft } from "lucide-react";
import { useAtmosferaDeMarca } from '@/hooks/useAtmosferaDeMarca';

const NotFound = () => {
  // Superfície de identidade: aqui a aurora VOLC pertence (DESIGN.md §Colors).
  useAtmosferaDeMarca();
  const location = useLocation();

  useEffect(() => {
    console.error(
      "404 Error: User attempted to access non-existent route:",
      location.pathname
    );
  }, [location.pathname]);

  return (
    <div className="relative min-h-[100dvh] overflow-hidden flex items-center justify-center bg-background text-foreground px-5 py-12">
      {/* Glow aurora atmosférico atrás do conteúdo */}
      <div
        className="pointer-events-none absolute left-1/2 top-1/3 h-px w-16 -translate-x-1/2 bg-gradient-aurora"
        aria-hidden
      />

      {/* Moldura-instrumento */}
      <div className="pointer-events-none absolute inset-4 md:inset-6 z-[1]" aria-hidden>
        <div className="absolute top-0 inset-x-0 h-px bg-border/60" />
        <div className="absolute bottom-0 inset-x-0 h-px bg-border/60" />
        <div className="absolute inset-y-0 left-0 w-px bg-border/60" />
        <div className="absolute inset-y-0 right-0 w-px bg-border/60" />
        <span className="crosshair absolute top-0 left-0" />
        <span className="crosshair absolute top-0 right-0" />
        <span className="crosshair absolute bottom-0 left-0 hidden sm:block" />
        <span className="crosshair absolute bottom-0 right-0 hidden sm:block" />
        <span className="kicker absolute top-1.5 right-6 tabular hidden sm:block">
          SIGNAL LOST // VOLC O.S.
        </span>
      </div>

      <div className="relative z-[2] w-full max-w-md text-center">
        <div
          className="kicker mb-4 flex items-center justify-center gap-2 reveal"
          style={{ ["--i" as any]: 1 }}
        >
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-destructive animate-pulse" />
          ERR 404 // Rota não encontrada
        </div>

        <h1
          className="font-display font-bold tracking-tight leading-none tabular reveal text-[5.5rem] md:text-[8rem]"
          style={{ ["--i" as any]: 2 }}
        >
          <span className="text-foreground">404</span>
        </h1>

        <div
          className="mx-auto mt-4 aurora-rule w-16 reveal"
          style={{ ["--i" as any]: 3 }}
        />

        <p
          className="mt-6 text-lg md:text-xl font-medium reveal"
          style={{ ["--i" as any]: 4 }}
        >
          Esta página saiu de órbita
        </p>
        <p
          className="mt-2 text-sm text-muted-foreground reveal"
          style={{ ["--i" as any]: 5 }}
        >
          O endereço que você tentou acessar não existe ou foi movido.
        </p>

        <div
          className="mt-8 flex items-center justify-center reveal"
          style={{ ["--i" as any]: 6 }}
        >
          <Button
            asChild
            variant="aurora"
            className="h-12 px-6 text-white font-medium hover-glow touch-target"
          >
            <a href="/">
              <ArrowLeft className="h-4 w-4 mr-2" />
              Voltar ao início
            </a>
          </Button>
        </div>
      </div>
    </div>
  );
};

export default NotFound;
