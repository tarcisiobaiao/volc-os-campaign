import { useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/contexts/AuthContext";
import { useToast } from "@/hooks/use-toast";
import { useNavigate } from "react-router-dom";
import { supabase } from "@/lib/supabase";
import { Lock, Eye, EyeOff, CheckCircle2, AlertCircle, Shield } from "lucide-react";
import { useIsMobile } from "@/hooks/useIsMobile";
import { useAtmosferaDeMarca } from '@/hooks/useAtmosferaDeMarca';

export default function ChangePassword() {
  // Superfície de identidade: aqui a aurora VOLC pertence (DESIGN.md §Colors).
  useAtmosferaDeMarca();
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const { userProfile, clearUnauthorizedUser } = useAuth();
  const { toast } = useToast();
  const navigate = useNavigate();
  const isMobile = useIsMobile();

  const validatePassword = (password: string): { valid: boolean; message: string } => {
    if (password.length < 8) {
      return { valid: false, message: "A senha deve ter no mínimo 8 caracteres" };
    }
    if (!/[A-Z]/.test(password)) {
      return { valid: false, message: "A senha deve conter pelo menos uma letra maiúscula" };
    }
    if (!/[a-z]/.test(password)) {
      return { valid: false, message: "A senha deve conter pelo menos uma letra minúscula" };
    }
    if (!/[0-9]/.test(password)) {
      return { valid: false, message: "A senha deve conter pelo menos um número" };
    }
    return { valid: true, message: "" };
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    // Validações
    if (!newPassword || !confirmPassword) {
      toast({
        title: "Campos obrigatórios",
        description: "Preencha todos os campos",
        variant: "destructive"
      });
      return;
    }

    if (newPassword !== confirmPassword) {
      toast({
        title: "Senhas não coincidem",
        description: "A nova senha e a confirmação devem ser iguais",
        variant: "destructive"
      });
      return;
    }

    const validation = validatePassword(newPassword);
    if (!validation.valid) {
      toast({
        title: "Senha inválida",
        description: validation.message,
        variant: "destructive"
      });
      return;
    }

    try {
      setIsLoading(true);

      // Atualizar senha no Supabase Auth (usuário já está autenticado)
      const { error: updateError } = await supabase.auth.updateUser({
        password: newPassword
      });

      if (updateError) {
        throw updateError;
      }

      // Atualizar flag needs_password_change na tabela users
      if (userProfile?.id) {
        const { error: dbError } = await supabase
          .from('users')
          .update({ needs_password_change: false })
          .eq('id', userProfile.id);

        if (dbError) {
          console.error("Erro ao atualizar flag:", dbError);
        }
      }

      toast({
        title: "Senha alterada com sucesso!",
        description: "Redirecionando para o sistema...",
      });

      // Limpar qualquer aviso de usuário não autorizado
      clearUnauthorizedUser();

      // Pequeno delay para garantir que o DB foi atualizado
      await new Promise(resolve => setTimeout(resolve, 500));

      // Redirecionar para a página inicial do usuário baseado no role
      if (userProfile?.role === 'OPERATOR') {
        window.location.href = "/dashboard/projects";
      } else {
        window.location.href = "/";
      }

    } catch (error: any) {
      console.error("Erro ao alterar senha:", error);
      toast({
        title: "Erro ao alterar senha",
        description: error.message || "Tente novamente",
        variant: "destructive"
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className={`relative min-h-[100dvh] overflow-hidden flex items-center justify-center ${isMobile ? 'p-4' : 'p-4'} bg-background text-foreground`}>
      {/* Glow aurora atmosférico atrás do cartão */}
      <div
        className="pointer-events-none absolute left-1/2 top-24 -translate-x-1/2 h-64 w-64 rounded-full bg-gradient-aurora opacity-20 blur-3xl"
        aria-hidden
      />

      <div className={`relative z-[2] w-full ${isMobile ? 'max-w-full' : 'max-w-md'}`}>
        <div className="text-center mb-6">
          <div className="reveal" style={{ ["--i" as any]: 1 }}>
            <div className={`inline-flex items-center justify-center ${isMobile ? 'w-12 h-12' : 'w-16 h-16'} rounded-2xl bg-gradient-aurora shadow-glow mb-4`}>
              <Shield className={`${isMobile ? 'h-6 w-6' : 'h-8 w-8'} text-white`} />
            </div>
          </div>
          <div className="kicker mb-2 reveal" style={{ ["--i" as any]: 2 }}>VOLC O.S. // Acesso seguro</div>
          <h1 className={`font-display font-bold tracking-tight ${isMobile ? 'text-xl' : 'text-2xl'} mb-2 reveal`} style={{ ["--i" as any]: 3 }}>
            Primeiro <span className="text-aurora">Acesso</span>
          </h1>
          <p className={`text-muted-foreground reveal ${isMobile ? 'text-sm' : ''}`} style={{ ["--i" as any]: 4 }}>
            Por segurança, você precisa alterar sua senha provisória
          </p>
          <div className="mx-auto mt-4 aurora-rule w-16 reveal" style={{ ["--i" as any]: 5 }} />
        </div>

        <Card className="shadow-elevated relative overflow-hidden reveal" style={{ ["--i" as any]: 6 }}>
          <span className="hairline-aurora absolute inset-x-0 top-0" />
          <CardHeader>
            <CardTitle className="font-display tracking-tight">Alterar Senha</CardTitle>
            <CardDescription>
              Crie uma senha forte e segura para sua conta
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              {/* Nova Senha */}
              <div className="space-y-2">
                <Label htmlFor="new-password">
                  Nova Senha <span className="text-destructive">*</span>
                </Label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    id="new-password"
                    type={showNewPassword ? "text" : "password"}
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    className={`pl-10 pr-10 ${isMobile ? 'h-12 touch-target' : ''}`}
                    placeholder="Mínimo 8 caracteres"
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShowNewPassword(!showNewPassword)}
                    className={`absolute right-3 top-1/2 transform -translate-y-1/2 text-muted-foreground hover:text-foreground ${isMobile ? 'touch-target' : ''}`}
                  >
                    {showNewPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>

              {/* Confirmar Senha */}
              <div className="space-y-2">
                <Label htmlFor="confirm-password">
                  Confirmar Nova Senha <span className="text-destructive">*</span>
                </Label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    id="confirm-password"
                    type={showConfirmPassword ? "text" : "password"}
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    className={`pl-10 pr-10 ${isMobile ? 'h-12 touch-target' : ''}`}
                    placeholder="Digite a senha novamente"
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                    className={`absolute right-3 top-1/2 transform -translate-y-1/2 text-muted-foreground hover:text-foreground ${isMobile ? 'touch-target' : ''}`}
                  >
                    {showConfirmPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>

              {/* Requisitos de Senha */}
              <div className="bg-muted/50 border border-border rounded-lg p-4 space-y-2">
                <p className="kicker mb-2">Requisitos da senha</p>
                <div className="space-y-1 text-xs text-muted-foreground">
                  <div className="flex items-center gap-2">
                    {newPassword.length >= 8 ? (
                      <CheckCircle2 className="h-3 w-3 text-success" />
                    ) : (
                      <AlertCircle className="h-3 w-3 text-muted-foreground" />
                    )}
                    <span>Mínimo 8 caracteres</span>
                  </div>
                  <div className="flex items-center gap-2">
                    {/[A-Z]/.test(newPassword) ? (
                      <CheckCircle2 className="h-3 w-3 text-success" />
                    ) : (
                      <AlertCircle className="h-3 w-3 text-muted-foreground" />
                    )}
                    <span>Pelo menos uma letra maiúscula</span>
                  </div>
                  <div className="flex items-center gap-2">
                    {/[a-z]/.test(newPassword) ? (
                      <CheckCircle2 className="h-3 w-3 text-success" />
                    ) : (
                      <AlertCircle className="h-3 w-3 text-muted-foreground" />
                    )}
                    <span>Pelo menos uma letra minúscula</span>
                  </div>
                  <div className="flex items-center gap-2">
                    {/[0-9]/.test(newPassword) ? (
                      <CheckCircle2 className="h-3 w-3 text-success" />
                    ) : (
                      <AlertCircle className="h-3 w-3 text-muted-foreground" />
                    )}
                    <span>Pelo menos um número</span>
                  </div>
                </div>
              </div>

              <Button
                type="submit"
                variant="aurora"
                disabled={isLoading}
                className={`w-full text-white font-medium hover-glow ${isMobile ? 'h-12 touch-target' : ''}`}
              >
                {isLoading ? (
                  <div className="flex items-center gap-2">
                    <div className="h-4 w-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                    Alterando senha...
                  </div>
                ) : (
                  <div className="flex items-center gap-2">
                    <Lock className="h-4 w-4" />
                    Confirmar e Continuar
                  </div>
                )}
              </Button>
            </form>
          </CardContent>
        </Card>

        <div className="text-center mt-6 text-sm text-muted-foreground">
          <p>Após alterar sua senha, você terá acesso ao sistema</p>
        </div>
      </div>
    </div>
  );
}

