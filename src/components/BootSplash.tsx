import { useEffect, useRef, useState } from "react";

/**
 * BootSplash — "Primeira Faísca".
 * Overlay de entrada que toca no carregamento: o V da marca é PINTADO ao vivo,
 * o traço laranja IGNITA (clímax) e uma detonação radial abre o overlay
 * revelando o app montado atrás. Timings determinísticos vêm do CSS
 * (animation-delay); o React só orquestra play -> exit -> remoção e o skip.
 * Toca uma vez por sessão de aba (sessionStorage), respeita prefers-reduced-motion,
 * e é pulável por clique/tecla. Não bloqueia: o app monta atrás desde 0ms.
 */
const KEY = "volc-booted";

export function BootSplash() {
  const reduce =
    typeof window !== "undefined" &&
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

  const [mounted, setMounted] = useState(() => {
    if (typeof window === "undefined") return false;
    try {
      return !window.sessionStorage.getItem(KEY);
    } catch {
      return true;
    }
  });
  const [phase, setPhase] = useState<"play" | "exit">("play");
  const rootRef = useRef<HTMLDivElement>(null);

  // marca a sessão (recargas na mesma aba pulam o splash)
  useEffect(() => {
    try {
      window.sessionStorage.setItem(KEY, "1");
    } catch {
      /* ignore */
    }
  }, []);

  // play -> exit (fim do intro), + skip por clique/tecla
  useEffect(() => {
    if (!mounted) return;
    const toExit = window.setTimeout(() => setPhase("exit"), reduce ? 450 : 1520);
    if (reduce) return () => window.clearTimeout(toExit);
    const skip = () => setPhase("exit");
    window.addEventListener("pointerdown", skip, { once: true });
    window.addEventListener("keydown", skip, { once: true });
    return () => {
      window.clearTimeout(toExit);
      window.removeEventListener("pointerdown", skip);
      window.removeEventListener("keydown", skip);
    };
  }, [mounted, reduce]);

  // remoção segura ao entrar em exit (além do onAnimationEnd)
  useEffect(() => {
    if (phase !== "exit") return;
    const t = window.setTimeout(() => setMounted(false), reduce ? 320 : 720);
    return () => window.clearTimeout(t);
  }, [phase, reduce]);

  if (!mounted) return null;

  return (
    <div
      ref={rootRef}
      className="boot"
      data-phase={phase}
      aria-hidden
      onAnimationEnd={(e) => {
        if (e.animationName === "boot-detonate") setMounted(false);
      }}
    >
      <div className="boot-bloom" />
      <div className="boot-v">
        <div className="boot-v-art" />
        <div className="boot-v-edge" />
        <img className="boot-v-img" src="/volc-v-light.png" alt="" draggable={false} />
        <div className="boot-flash" />
        <div className="boot-spark" />
      </div>
      <div className="boot-ring" />
    </div>
  );
}
