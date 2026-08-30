import { useAuth } from "@/contexts/AuthContext";
import { Navigate, useLocation } from "react-router-dom";
import { LoadingSpinner } from "@/components/ui/loading-spinner";

interface ProtectedRouteProps {
  children: React.ReactNode;
}

export const ProtectedRoute = ({ children }: ProtectedRouteProps) => {
  const { user, userProfile, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <LoadingSpinner />
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