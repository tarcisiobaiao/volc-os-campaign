/**
 * v6 RBAC — useV6Mutations
 *
 * Hooks de mutação para o admin v6 operacional. Padrão consistente
 * com o resto do projeto: useState + useCallback, sem React Query.
 *
 * Cada hook expõe:
 *   - mutate(input)   → Promise<resultado | null>
 *   - isLoading       → boolean
 *   - error           → Error | null
 *   - reset()         → limpa estado
 *
 * Convenções:
 *   - mutate **re-throws** o erro depois de armazená-lo, permitindo
 *     que o componente reaja com try/catch (toast, fechar modal, etc).
 *   - Os hooks não disparam refetch automático; o componente que
 *     consome decide quando recarregar (geralmente via prop
 *     `onSuccess` ou refetch direto dos hooks de leitura).
 */
import { useCallback, useState } from 'react';
import { v6OperationsService } from '@/v6/services/v6OperationsService';
import { campaignMembersService } from '@/v6/services/campaignMembersService';
import { campaignCommissionsService } from '@/v6/services/campaignCommissionsService';
import type {
  CreateUserInput,
  UpdateUserInput,
  CreateMembershipInput,
  UpdateMembershipInput,
  RemoveMembershipInput,
  CreateCommissionInput,
  EndCommissionInput,
  OnboardingInput,
} from '@/v6/types/v6';

interface MutationState<TOutput> {
  isLoading: boolean;
  error: Error | null;
  data: TOutput | null;
}

const initialState = <TOutput,>(): MutationState<TOutput> => ({
  isLoading: false,
  error: null,
  data: null,
});

function useMutationCore<TInput, TOutput>(
  fn: (input: TInput) => Promise<TOutput>
) {
  const [state, setState] = useState<MutationState<TOutput>>(initialState);

  const mutate = useCallback(
    async (input: TInput): Promise<TOutput> => {
      setState({ isLoading: true, error: null, data: null });
      try {
        const result = await fn(input);
        setState({ isLoading: false, error: null, data: result });
        return result;
      } catch (err) {
        const e = err instanceof Error ? err : new Error(String(err));
        setState({ isLoading: false, error: e, data: null });
        throw e;
      }
    },
    [fn]
  );

  const reset = useCallback(() => setState(initialState()), []);

  return {
    mutate,
    isLoading: state.isLoading,
    error: state.error,
    data: state.data,
    reset,
  };
}

// ----------------------------------------------------------------
// Usuário
// ----------------------------------------------------------------

export const useCreateUser = () =>
  useMutationCore<CreateUserInput, Awaited<ReturnType<typeof v6OperationsService.createUser>>>(
    (input) => v6OperationsService.createUser(input)
  );

export const useUpdateUser = () =>
  useMutationCore<UpdateUserInput, Awaited<ReturnType<typeof v6OperationsService.updateUser>>>(
    (input) => v6OperationsService.updateUser(input)
  );

/**
 * Exclusão de usuário. Requer o id do admin logado para a regra
 * "não excluir a si mesmo". Use `canDeleteUser` antes de abrir o
 * diálogo de confirmação para dar feedback claro ao admin.
 */
export const useDeleteUser = (currentAdminId: string | null) =>
  useMutationCore<string, void>((userId) =>
    v6OperationsService.deleteUser(userId, currentAdminId)
  );

// ----------------------------------------------------------------
// Onboarding unificado
// ----------------------------------------------------------------

export const useOnboardUser = (actorId?: string | null) =>
  useMutationCore<OnboardingInput, Awaited<ReturnType<typeof v6OperationsService.onboardUser>>>(
    (input) => v6OperationsService.onboardUser(input, actorId)
  );

// ----------------------------------------------------------------
// Memberships
// ----------------------------------------------------------------

export const useCreateMembership = () =>
  useMutationCore<CreateMembershipInput, Awaited<ReturnType<typeof campaignMembersService.addMember>>>(
    (input) => campaignMembersService.addMember(input)
  );

export const useUpdateMembership = () =>
  useMutationCore<UpdateMembershipInput, Awaited<ReturnType<typeof campaignMembersService.updateMemberRole>>>(
    (input) => campaignMembersService.updateMemberRole(input)
  );

export const useRemoveMembership = () =>
  useMutationCore<RemoveMembershipInput, void>(
    (input) => campaignMembersService.removeMember(input)
  );

// ----------------------------------------------------------------
// Comissões
// ----------------------------------------------------------------

export const useCreateCommission = () =>
  useMutationCore<CreateCommissionInput, Awaited<ReturnType<typeof campaignCommissionsService.createCommission>>>(
    (input) => campaignCommissionsService.createCommission(input)
  );

export const useEndCommission = () =>
  useMutationCore<EndCommissionInput, Awaited<ReturnType<typeof campaignCommissionsService.endCommission>>>(
    (input) => campaignCommissionsService.endCommission(input)
  );
