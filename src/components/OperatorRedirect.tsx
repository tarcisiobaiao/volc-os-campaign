import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';

interface OperatorRedirectProps {
  children: React.ReactNode;
}

/**
 * Componente que redireciona operadores da home para a página de campanhas
 * Apenas admins podem acessar o dashboard geral
 */
export function OperatorRedirect({ children }: OperatorRedirectProps) {
  const { userProfile } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    // Se for operador, redirecionar para campanhas
    if (userProfile?.role === 'OPERATOR') {
      console.log('🔀 Operador detectado, redirecionando para campanhas...');
      navigate('/settings/campaigns', { replace: true });
    }
  }, [userProfile, navigate]);

  // Se for admin, renderizar normalmente
  if (userProfile?.role === 'ADMIN') {
    return <>{children}</>;
  }

  // Enquanto carrega ou está redirecionando, não mostrar nada
  return null;
}
