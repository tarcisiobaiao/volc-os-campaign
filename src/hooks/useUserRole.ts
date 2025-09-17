import { useAuth } from '@/contexts/AuthContext';

export type UserRole = 'ADMIN' | 'OPERATOR' | 'VIEWER' | null;

export function useUserRole() {
  const { userProfile } = useAuth();

  const isAdmin = (): boolean => {
    return userProfile?.role === 'ADMIN';
  };

  const isOperator = (): boolean => {
    return userProfile?.role === 'OPERATOR';
  };

  const isViewer = (): boolean => {
    return userProfile?.role === 'VIEWER';
  };

  const canManageCategories = (): boolean => {
    // Only admins can create/delete categories
    return isAdmin();
  };

  const canEditCosts = (): boolean => {
    // Admins and operators can edit costs
    return isAdmin() || isOperator();
  };

  const canViewCosts = (): boolean => {
    // All users can view costs
    return userProfile?.role !== null;
  };

  return {
    role: userProfile?.role as UserRole,
    isAdmin,
    isOperator,
    isViewer,
    canManageCategories,
    canEditCosts,
    canViewCosts
  };
}

