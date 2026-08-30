import React, { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Eye, EyeOff, Mail, Lock, ArrowRight, CheckCircle, AlertCircle } from "lucide-react";
import { ErroDeAutorizacao, useAuth } from "@/contexts/AuthContext";
import { useToast } from "@/hooks/use-toast";
import { useNavigate } from "react-router-dom";
import { useAtmosferaDeMarca } from '@/hooks/useAtmosferaDeMarca';

export default function Login() {
  // Superfície de identidade: aqui a aurora VOLC pertence (DESIGN.md §Colors).
  useAtmosferaDeMarca();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);

  const rootRef = useRef<HTMLDivElement>(null);
  const { signIn, signInWithGoogle, unauthorizedUser, clearUnauthorizedUser, falha, tentarNovamente } = useAuth();
  const { toast } = useToast();
  const navigate = useNavigate();

  // — Paralaxe reativa ao cursor, com inércia de mola. Escreve --mx/--my
  //   direto no ref (nunca setState -> zero re-render). Desligada em touch
  //   e em prefers-reduced-motion. —
  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const coarse = window.matchMedia("(pointer: coarse)").matches;
    if (reduce || coarse) return;

    let tx = 0, ty = 0, cx = 0, cy = 0, raf = 0, running = true;
    const onMove = (e: PointerEvent) => {
      tx = e.clientX / window.innerWidth - 0.5;
      ty = e.clientY / window.innerHeight - 0.5;
    };
    const loop = () => {
      cx += (tx - cx) * 0.12;
      cy += (ty - cy) * 0.12;
      root.style.setProperty("--mx", cx.toFixed(4));
      root.style.setProperty("--my", cy.toFixed(4));
      if (running) raf = requestAnimationFrame(loop);
    };
    window.addEventListener("pointermove", onMove, { passive: true });
    raf = requestAnimationFrame(loop);
    return () => {
      running = false;
      cancelAnimationFrame(raf);
      window.removeEventListener("pointermove", onMove);
    };
  }, []);

  // A luz do horizonte "olha" para o campo em foco.
  const setFocusX = (el: HTMLElement) => {
    const r = el.getBoundingClientRect();
    rootRef.current?.style.setProperty(
      "--focus-x",
      `${(((r.left + r.width / 2) / window.innerWidth) * 100).toFixed(1)}%`
    );
  };
  const resetFocusX = () => rootRef.current?.style.setProperty("--focus-x", "50%");

  // Botão magnético.
  const onBtnMove = (e: React.MouseEvent<HTMLButtonElement>) => {
    const b = e.currentTarget.getBoundingClientRect();
    e.currentTarget.style.setProperty("--bx", `${(((e.clientX - b.left) / b.width - 0.5) * 10).toFixed(1)}px`);
    e.currentTarget.style.setProperty("--by", `${(((e.clientY - b.top) / b.height - 0.5) * 6).toFixed(1)}px`);
  };
  const onBtnLeave = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.currentTarget.style.setProperty("--bx", "0px");
    e.currentTarget.style.setProperty("--by", "0px");
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    try {
      // `signIn` só resolve depois que GET /api/me confirmou o cadastro e o
      // perfil está instalado no contexto. Senha correta NÃO é acesso
      // concedido: antes desta mudança a tela comemorava no instante em que o
      // GoTrue aceitava a senha, e só depois descobria que a autorização
      // tinha falhado — mostrando "Acesso concedido" e, em seguida, "o email
      // não está cadastrado" para a mesma pessoa, na mesma sessão.
      await signIn(email, password);

      // Só aqui a coreografia do "amanhecer" pode começar. isSuccess fica
      // ligado até o navigate desmontar a tela.
      setIsSuccess(true);
      setIsLoading(false);
      toast({ title: "Acesso concedido", description: "Bem-vindo ao VOLC O.S." });
      setTimeout(() => {
        navigate("/");
      }, 1000);
    } catch (error: any) {
      setIsSuccess(false);
      setIsLoading(false);

      // A senha estava certa, mas a autorização não passou. O painel acima do
      // formulário explica o motivo real — repetir num toast só empilharia
      // duas versões da mesma notícia.
      if (error instanceof ErroDeAutorizacao) {
        if (error.falha.tipo !== 'sem_cadastro') {
          toast({
            title: error.falha.podeTentarNovamente ? "Não deu para confirmar seu acesso" : "Acesso negado",
            description: error.falha.mensagem,
            variant: "destructive",
          });
        }
        return;
      }

      const rawMessage = (error?.message || "").toString();
      const normalizedMessage = rawMessage.toLowerCase();
      const isCredentialError =
        normalizedMessage.includes("invalid login credentials") ||
        normalizedMessage.includes("email not confirmed") ||
        normalizedMessage.includes("invalid_credentials");
      toast({
        title: "Erro no login",
        description: isCredentialError
          ? "Email ou senha incorretos. Confira também se o email foi digitado corretamente."
          : rawMessage || "Falha ao autenticar. Tente novamente.",
        variant: "destructive",
      });
    }
  };

  const handleGoogleSignIn = async () => {
    try {
      setIsLoading(true);
      await signInWithGoogle();
    } catch (error: any) {
      toast({
        title: "Erro no login",
        description: error.message || "Erro ao tentar fazer login com Google.",
        variant: "destructive",
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div
      ref={rootRef}
      data-state={isSuccess ? "success" : "idle"}
      data-loading={isLoading ? "true" : "false"}
      className="login-root dark relative min-h-[100dvh] overflow-hidden flex items-center justify-center px-5 py-12 text-foreground"
    >
      {/* Camadas de atmosfera */}
      <div className="login-void" aria-hidden />
      <div className="login-horizon" aria-hidden>
        <div className="login-hz-par" style={{ transform: "translate3d(calc(var(--mx)*8px),calc(var(--my)*6px),0)" }}>
          <div className="login-hz login-hz-1" style={{ animationDuration: "18s" }} />
        </div>
        <div className="login-hz-par" style={{ transform: "translate3d(calc(var(--mx)*16px),calc(var(--my)*10px),0)" }}>
          <div className="login-hz login-hz-2" style={{ animationDuration: "22s" }} />
        </div>
        <div className="login-hz-par" style={{ transform: "translate3d(calc(var(--mx)*24px),calc(var(--my)*14px),0)" }}>
          <div className="login-hz login-hz-3" style={{ animationDuration: "26s" }} />
        </div>
        <div className="login-halo" />
        <div className="login-ignite" />
      </div>

      {/* Moldura-instrumento */}
      <div className="pointer-events-none absolute inset-4 md:inset-6 z-[2]" aria-hidden>
        <div className="login-frame-x absolute top-0 inset-x-0 h-px bg-border/50" />
        <div className="login-frame-x absolute bottom-0 inset-x-0 h-px bg-border/50" />
        <div className="login-frame-y absolute inset-y-0 left-0 w-px bg-border/50" />
        <div className="login-frame-y absolute inset-y-0 right-0 w-px bg-border/50" />
        <span className="crosshair absolute top-0 left-0" />
        <span className="crosshair absolute top-0 right-0" />
        <span className="crosshair absolute bottom-0 left-0 hidden sm:block" />
        <span className="crosshair absolute bottom-0 right-0 hidden sm:block" />
        <span className="kicker absolute top-1.5 right-6 tabular hidden sm:block">47.6°N // ORBITAL ACCESS</span>
      </div>

      {/* Painel de vidro + formulário */}
      <div className="login-panel relative z-[3] w-full max-w-[420px]">

        {falha && (
          <div
            role="alert"
            className="glass rounded-lg border border-destructive/40 bg-destructive/[0.06] p-4 mb-4 animate-fade-in"
          >
            <div className="flex items-start gap-3">
              <AlertCircle className="h-5 w-5 text-destructive shrink-0 mt-0.5" aria-hidden />
              <div className="flex-1 min-w-0">
                {/*
                  O rótulo carrega o status REAL. Antes era a string fixa
                  "ERR 403" — que aparecia igual para 401, 500, 503 e para uma
                  queda de rede, mandando quem fosse investigar procurar uma
                  negação de permissão que nunca tinha acontecido.
                */}
                <div className="kicker text-destructive mb-1">
                  {falha.status > 0 ? `ERR ${falha.status}` : "SEM RESPOSTA"}
                  {falha.codigo ? ` // ${falha.codigo}` : ""}
                </div>

                {falha.tipo === 'sem_cadastro' ? (
                  <>
                    <p className="text-sm text-foreground/80">
                      O email <strong className="text-foreground">{unauthorizedUser}</strong> não está cadastrado.
                    </p>
                    <p className="text-xs text-muted-foreground mt-1 mb-3">
                      Fale com o administrador para solicitar acesso.
                    </p>
                  </>
                ) : (
                  <>
                    <p className="text-sm text-foreground/80">{falha.mensagem}</p>
                    <p className="text-xs text-muted-foreground mt-1 mb-3">
                      {falha.podeTentarNovamente
                        ? "Seu login continua válido — isto é um problema para chegar ao servidor, não com a sua conta."
                        : "Entre novamente para continuar."}
                    </p>
                  </>
                )}

                <div className="flex flex-wrap gap-2">
                  {falha.podeTentarNovamente && (
                    <Button onClick={() => { void tentarNovamente(); }} size="sm">
                      Tentar novamente
                    </Button>
                  )}
                  <Button onClick={clearUnauthorizedUser} variant="outline" size="sm">
                    Entendi
                  </Button>
                </div>
              </div>
            </div>
          </div>
        )}

        <div className="glass rounded-lg p-7 relative overflow-hidden">
          <span className="hairline-aurora absolute inset-x-0 top-0" />

          {/* Logo VOLC — herói da tela: sheen de luz varre a marca + glow que respira */}
          <div className="reveal" style={{ ["--i" as any]: 1 }}>
            <div
              className="login-logo"
              style={{ transform: "translate(calc(var(--mx) * 6px), calc(var(--my) * 4px))" }}
            >
              <img
                src="/volc-logo-light.png"
                alt="VOLC — Exploding Ideas"
                className="h-16 w-auto select-none"
                draggable={false}
              />
              <span
                className="login-logo-sheen"
                style={{ WebkitMaskImage: "url(/volc-logo-light.png)", maskImage: "url(/volc-logo-light.png)" }}
                aria-hidden
              />
            </div>
          </div>

          <p className="text-sm text-muted-foreground mt-5 reveal" style={{ ["--i" as any]: 2 }}>
            Entre para continuar no painel VOLC.
          </p>

          <form onSubmit={handleSubmit} className="mt-6 space-y-4">
            <div className="reveal" style={{ ["--i" as any]: 4 }}>
              <label htmlFor="email" className="kicker mb-1.5 block">Email</label>
              <div className="login-field relative">
                <span className="login-field-glow" />
                <Mail className="login-field-icon absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground transition-colors z-10" />
                <Input
                  id="email"
                  type="email"
                  placeholder="voce@agenciavolc.com.br"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  onFocus={(e) => setFocusX(e.currentTarget)}
                  onBlur={resetFocusX}
                  className="pl-10 h-12 bg-white/[0.04] border-white/10 text-foreground placeholder:text-muted-foreground/70 focus-visible:ring-primary/50 relative"
                  required
                />
              </div>
            </div>

            <div className="reveal" style={{ ["--i" as any]: 5 }}>
              <label htmlFor="password" className="kicker mb-1.5 block">Senha</label>
              <div className="login-field relative">
                <span className="login-field-glow" />
                <Lock className="login-field-icon absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground transition-colors z-10" />
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  onFocus={(e) => setFocusX(e.currentTarget)}
                  onBlur={resetFocusX}
                  className="pl-10 pr-10 h-12 bg-white/[0.04] border-white/10 text-foreground placeholder:text-muted-foreground/70 focus-visible:ring-primary/50 relative"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors z-10"
                  aria-label={showPassword ? "Ocultar senha" : "Mostrar senha"}
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            <div className="flex items-center justify-end reveal" style={{ ["--i" as any]: 6 }}>
              <a
                href="mailto:tarcisio@agenciavolc.com.br?subject=Recuperar%20acesso%20—%20VOLC%20O.S."
                className="text-xs text-muted-foreground hover:text-primary transition-colors"
              >
                Esqueceu a senha?
              </a>
            </div>

            <div className="reveal" style={{ ["--i" as any]: 7 }}>
              <Button
                type="submit"
                variant="aurora"
                disabled={isLoading}
                onMouseMove={onBtnMove}
                onMouseLeave={onBtnLeave}
                className="w-full h-12 text-white font-medium overflow-hidden hover-glow"
              >
                <span className="inline-flex items-center gap-2" style={{ transform: "translate(var(--bx,0),var(--by,0))" }}>
                  {isLoading ? (
                    <>
                      <span className="h-4 w-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                      Entrando…
                    </>
                  ) : isSuccess ? (
                    <>
                      <CheckCircle className="h-4 w-4" />
                      Acesso concedido
                    </>
                  ) : (
                    <>
                      Entrar
                      <ArrowRight className="h-4 w-4" />
                    </>
                  )}
                </span>
              </Button>
            </div>
          </form>

          <div className="relative my-5 reveal" style={{ ["--i" as any]: 8 }}>
            <div className="absolute inset-0 flex items-center"><div className="w-full h-px bg-white/10" /></div>
            <div className="relative flex justify-center"><span className="glass px-3 kicker rounded-full">ou</span></div>
          </div>

          <div className="reveal" style={{ ["--i" as any]: 9 }}>
            <Button
              variant="outline"
              className="w-full h-12 bg-white/[0.03] border-white/10 hover:bg-white/[0.07] hover-glow"
              onClick={handleGoogleSignIn}
              disabled={isLoading}
            >
              <svg className="h-5 w-5 mr-2" viewBox="0 0 24 24" aria-hidden>
                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z" />
                <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
              </svg>
              {isLoading ? "Conectando…" : "Continuar com Google"}
            </Button>
          </div>

          <div className="mt-6 flex items-center justify-center gap-2 reveal" style={{ ["--i" as any]: 10 }}>
            <span className="h-1.5 w-1.5 rounded-full bg-success animate-pulse-glow" />
            <span className="kicker">Acesso por convite</span>
          </div>
        </div>
      </div>

      {/* Whiteout do amanhecer (crossfade para o app claro no sucesso) */}
      <div className="login-whiteout" aria-hidden />
    </div>
  );
}
