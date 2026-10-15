import { useAuth } from "@/contexts/AuthContext";
import { Navigate, useLocation } from "react-router-dom";
import { Skeleton } from "@/components/ui/skeleton";

interface ProtectedRouteProps {
  children: React.ReactNode;
}

export const ProtectedRoute = ({ children }: ProtectedRouteProps) => {
  const { user, userProfile, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    // Esqueleto do shell, não um giro solto no meio da tela (PRODUCT.md §10):
    // quem espera a sessão já vê onde o menu, o cabeçalho e o trabalho vão
    // estar. Nada aqui afirma dado.
    return (
      <div className="flex min-h-screen bg-background" role="status" aria-live="polite">
        <span className="sr-only">Verificando sua sessão</span>
        <div aria-hidden className="hidden w-[248px] shrink-0 flex-col gap-3 border-r border-sidebar-border bg-sidebar p-4 md:flex">
          <Skeleton className="h-8 w-28" />
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-7 w-full" />
          ))}
        </div>
        <div aria-hidden className="flex flex-1 flex-col">
          <div className="h-14 border-b border-border bg-card" />
          <div className="space-y-4 p-6">
            <Skeleton className="h-9 w-64" />
            <Skeleton className="h-32 w-full max-w-5xl" />
            <Skeleton className="h-48 w-full max-w-5xl" />
          </div>
        </div>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  // Se precisa trocar senha e não está na página de troca de senha, redirecionar
  if (userProfile?.needs_password_change && location.pathname !== '/change-password') {
    return <Navigate to="/change-password" replace />;
  }

  // Se já trocou a senha e está tentando acessar a página de troca, redirecionar para dashboard
  if (!userProfile?.needs_password_change && location.pathname === '/change-password') {
    // Operador vai para campanhas, Admin vai para home
    const redirectTo = userProfile?.role === 'OPERATOR' ? '/settings/campaigns' : '/';
    return <Navigate to={redirectTo} replace />;
  }

  // OPERATOR só acessa suas páginas permitidas (exceto change-password que é para todos)
  if (userProfile?.role === 'OPERATOR' && location.pathname !== '/change-password') {
    const allowedPaths = [
      '/dashboard/campaign/', // Permite acessar campanhas específicas
      '/settings/campaigns'   // Página principal de campanhas
    ];

    const isAllowed = allowedPaths.some(path => location.pathname.startsWith(path));

    if (!isAllowed) {
      console.log('🔀 Operador tentou acessar rota não permitida, redirecionando para campanhas:', location.pathname);
      return <Navigate to="/settings/campaigns" replace />;
    }
  }

  return <>{children}</>;
};