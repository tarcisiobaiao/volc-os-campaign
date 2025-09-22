import React, { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Eye,
  EyeOff,
  Mail,
  Lock,
  TrendingUp,
  DollarSign,
  BarChart3,
  Zap,
  ArrowRight,
  CheckCircle,
  AlertCircle
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useToast } from "@/hooks/use-toast";
import { useNavigate } from "react-router-dom";

// Componente de animação de partículas
const ParticleBackground = () => (
  <div className="absolute inset-0 overflow-hidden pointer-events-none">
    <div className="absolute top-1/4 left-1/4 w-2 h-2 bg-primary/20 rounded-full animate-float"></div>
    <div className="absolute top-1/3 right-1/3 w-1 h-1 bg-purple-500/30 rounded-full animate-float" style={{ animationDelay: '1s' }}></div>
    <div className="absolute bottom-1/4 left-1/3 w-1.5 h-1.5 bg-blue-500/20 rounded-full animate-float" style={{ animationDelay: '2s' }}></div>
    <div className="absolute top-1/2 right-1/4 w-1 h-1 bg-green-500/30 rounded-full animate-float" style={{ animationDelay: '0.5s' }}></div>
    <div className="absolute bottom-1/3 left-1/4 w-2 h-2 bg-yellow-500/20 rounded-full animate-float" style={{ animationDelay: '1.5s' }}></div>
  </div>
);

// Componente de estatísticas animadas
const AnimatedStats = () => (
  <div className="hidden lg:flex flex-col space-y-6 text-white/80">
    <div className="space-y-4">
      <div className="flex items-center gap-3 p-4 rounded-lg bg-white/5 backdrop-blur-sm border border-white/10">
        <div className="p-2 rounded-lg bg-gradient-to-r from-green-500 to-emerald-500">
          <TrendingUp className="h-5 w-5 text-white" />
        </div>
        <div>
          <div className="text-lg font-bold">+2.5M</div>
          <div className="text-sm text-white/60">Impressões</div>
        </div>
      </div>
      
      <div className="flex items-center gap-3 p-4 rounded-lg bg-white/5 backdrop-blur-sm border border-white/10">
        <div className="p-2 rounded-lg bg-gradient-to-r from-blue-500 to-indigo-500">
          <DollarSign className="h-5 w-5 text-white" />
        </div>
        <div>
          <div className="text-lg font-bold">+$450K</div>
          <div className="text-sm text-white/60">Receita</div>
        </div>
      </div>
      
      <div className="flex items-center gap-3 p-4 rounded-lg bg-white/5 backdrop-blur-sm border border-white/10">
        <div className="p-2 rounded-lg bg-gradient-to-r from-purple-500 to-pink-500">
          <BarChart3 className="h-5 w-5 text-white" />
        </div>
        <div>
          <div className="text-lg font-bold">+85%</div>
          <div className="text-sm text-white/60">ROAS</div>
        </div>
      </div>
    </div>
  </div>
);

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);

  const { signIn, signInWithGoogle, unauthorizedUser, clearUnauthorizedUser } = useAuth();
  const { toast } = useToast();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);

    try {
      await signIn(email, password);
      setIsSuccess(true);

      toast({
        title: "Login realizado com sucesso!",
        description: "Bem-vindo ao Campaign Manager",
      });

      setTimeout(() => {
        navigate("/");
      }, 1000);
    } catch (error) {
      toast({
        title: "Erro no login",
        description: "Verifique suas credenciais e tente novamente.",
        variant: "destructive",
      });
    } finally {
      setIsLoading(false);
      setIsSuccess(false);
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
    <div className="min-h-screen flex">
      {/* Lado Esquerdo - Background com Gradiente */}
      <div className="hidden lg:flex lg:w-1/2 relative bg-gradient-to-br from-primary via-purple-600 to-blue-600 overflow-hidden">
        <ParticleBackground />

        {/* Overlay com padrão */}
        <div className="absolute inset-0 bg-black/20"></div>

        {/* Conteúdo do lado esquerdo */}
        <div className="relative z-10 flex flex-col justify-center px-12 text-white">
          <div className="mb-8">
            <div className="flex items-center gap-3 mb-6">
              <div className="h-12 w-12 bg-white/20 rounded-xl flex items-center justify-center backdrop-blur-sm">
                <Zap className="h-6 w-6 text-white" />
              </div>
              <div>
                <h1 className="text-3xl font-bold bg-gradient-to-r from-white to-white/80 bg-clip-text text-transparent">
                  Campaign Manager
                </h1>
                <p className="text-white/80">Arbitragem & Monetização</p>
              </div>
            </div>

            <h2 className="text-4xl font-bold mb-4">
              Maximize seus{" "}
              <span className="bg-gradient-to-r from-yellow-400 to-orange-400 bg-clip-text text-transparent">
                lucros
              </span>
            </h2>

            <p className="text-xl text-white/80 mb-8">
              Plataforma completa para arbitragem de tráfego e otimização de campanhas de marketing digital.
            </p>
          </div>

          <AnimatedStats />
        </div>
      </div>

      {/* Lado Direito - Formulário de Login */}
      <div className="flex-1 flex items-center justify-center p-8 bg-gradient-to-br from-background to-muted/30">
        <div className="w-full max-w-md">
          {/* Logo para mobile */}
          <div className="lg:hidden text-center mb-8">
            <div className="flex items-center justify-center gap-3 mb-4">
              <div className="h-12 w-12 bg-gradient-to-r from-primary to-purple-600 rounded-xl flex items-center justify-center">
                <Zap className="h-6 w-6 text-white" />
              </div>
              <div>
                <h1 className="text-2xl font-bold">Campaign Manager</h1>
                <p className="text-muted-foreground">Arbitragem & Monetização</p>
              </div>
            </div>
          </div>

          {/* Erro de autorização */}
          {unauthorizedUser && (
            <Card className="mb-6 shadow-lg border-red-200 bg-red-50/90 backdrop-blur-sm">
              <CardContent className="p-4">
                <div className="flex items-start gap-3">
                  <div className="p-2 rounded-full bg-red-100">
                    <AlertCircle className="h-5 w-5 text-red-600" />
                  </div>
                  <div className="flex-1">
                    <h3 className="font-medium text-red-800 mb-1">
                      Acesso não autorizado
                    </h3>
                    <p className="text-sm text-red-700 mb-3">
                      O email <strong>{unauthorizedUser}</strong> não está cadastrado no sistema.
                    </p>
                    <p className="text-xs text-red-600 mb-3">
                      Entre em contato com o administrador para solicitar acesso.
                    </p>
                    <Button
                      onClick={clearUnauthorizedUser}
                      variant="outline"
                      size="sm"
                      className="text-red-700 border-red-300 hover:bg-red-100"
                    >
                      Entendi
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          <Card className="shadow-2xl border-0 bg-white/80 backdrop-blur-sm">
            <CardHeader className="text-center pb-6">
              <CardTitle className="text-2xl font-bold bg-gradient-to-r from-primary to-purple-600 bg-clip-text text-transparent">
                Bem-vindo de volta
              </CardTitle>
              <p className="text-muted-foreground">
                Acesse sua conta para continuar
              </p>
            </CardHeader>

            <CardContent className="space-y-6">
              <form onSubmit={handleSubmit} className="space-y-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium text-foreground">
                    Email
                  </label>
                  <div className="relative">
                    <Mail className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                      type="email"
                      placeholder="seu@email.com"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className="pl-10 h-12 border-muted-foreground/20 focus:border-primary"
                      required
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <label className="text-sm font-medium text-foreground">
                    Senha
                  </label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                      type={showPassword ? "text" : "password"}
                      placeholder="••••••••"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      className="pl-10 pr-10 h-12 border-muted-foreground/20 focus:border-primary"
                      required
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-3 top-1/2 transform -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                    >
                      {showPassword ? (
                        <EyeOff className="h-4 w-4" />
                      ) : (
                        <Eye className="h-4 w-4" />
                      )}
                    </button>
                  </div>
                </div>

                <div className="flex items-center justify-between text-sm">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input type="checkbox" className="rounded border-muted-foreground/20" />
                    <span className="text-muted-foreground">Lembrar de mim</span>
                  </label>
                  <a href="#" className="text-primary hover:underline">
                    Esqueceu a senha?
                  </a>
                </div>

                <Button
                  type="submit"
                  disabled={isLoading}
                  className="w-full h-12 bg-gradient-to-r from-primary to-purple-600 hover:from-primary/90 hover:to-purple-600/90 text-white font-medium transition-all duration-200 transform hover:scale-[1.02] disabled:scale-100"
                >
                  {isLoading ? (
                    <div className="flex items-center gap-2">
                      <div className="h-4 w-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                      Entrando...
                    </div>
                  ) : isSuccess ? (
                    <div className="flex items-center gap-2">
                      <CheckCircle className="h-4 w-4" />
                      Sucesso!
                    </div>
                  ) : (
                    <div className="flex items-center gap-2">
                      Entrar
                      <ArrowRight className="h-4 w-4" />
                    </div>
                  )}
                </Button>
              </form>

              <div className="relative">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-muted-foreground/20"></div>
                </div>
                <div className="relative flex justify-center text-xs uppercase">
                  <span className="bg-white px-2 text-muted-foreground">Ou continue com</span>
                </div>
              </div>

              <Button
                variant="outline"
                className="w-full h-12 hover:bg-muted/50"
                onClick={handleGoogleSignIn}
                disabled={isLoading}
              >
                <svg className="h-5 w-5 mr-2" viewBox="0 0 24 24">
                  <path
                    fill="#4285F4"
                    d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                  />
                  <path
                    fill="#34A853"
                    d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                  />
                  <path
                    fill="#FBBC05"
                    d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"
                  />
                  <path
                    fill="#EA4335"
                    d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                  />
                </svg>
                {isLoading ? "Conectando..." : "Continuar com Google"}
              </Button>

              <div className="text-center text-sm text-muted-foreground">
                Não tem uma conta?{" "}
                <a href="#" className="text-primary hover:underline font-medium">
                  Criar conta
                </a>
              </div>
            </CardContent>
          </Card>


          {/* Footer */}
          <div className="mt-8 text-center text-sm text-muted-foreground">
            <p>© 2024 Campaign Manager. Todos os direitos reservados.</p>
          </div>
        </div>
      </div>
    </div>
  );
}