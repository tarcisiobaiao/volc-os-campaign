/**
 * v6 RBAC — v6OperationsService
 *
 * Orquestrador de fluxos operacionais que cruzam mais de uma
 * tabela ou mesclam v6 + legado.
 *
 * EXCEÇÃO CONTROLADA DE ISOLAMENTO: este arquivo importa o
 * `usersService` legado de `@/services/usersService` para reutilizar
 * a criação/edição/remoção de usuários. Foi explicitamente
 * autorizado pelo usuário ("Se existir uma forma já usada no
 * sistema para criar usuário, reutilize"). Esse é o ÚNICO ponto em
 * `src/v6/` que importa de `@/services/`.
 *
 * Padrão dual-write para memberships: sempre que adicionamos um
 * vínculo no v6 (`campaign_members`), também garantimos a presença
 * em `user_campaigns` (legado). O `campaignMembersService.addMember`
 * já faz esse dual-write internamente.
 */
import { supabase } from '@/lib/supabase';
import { secureApi } from '@/lib/secureApi';
import { usersService } from '@/services/usersService';
import type { User as LegacyUser } from '@/services/usersService';
import { campaignMembersService } from '@/v6/services/campaignMembersService';
import { campaignCommissionsService } from '@/v6/services/campaignCommissionsService';
import type {
  CreateUserInput,
  UpdateUserInput,
  OnboardingInput,
  UserLite,
} from '@/v6/types/v6';

export interface CanDeleteResult {
  canDelete: boolean;
  reason?: string;
  payoutCount?: number;
}

export interface OnboardingResult {
  user: LegacyUser;
  memberships_created: number;
  commissions_created: number;
  warnings: string[];
}

class V6OperationsService {
  /**
   * Cria um usuário via Admin API server-side (`/api/users/create`).
   *
   * Por que NÃO usamos mais `usersService.create`:
   *   O legado faz `supabase.auth.signUp` direto do client. Esse
   *   método troca a sessão do browser pela do usuário recém-criado
   *   — ou seja, derruba o admin logado. O endpoint admin
   *   server-side resolve isso usando service role + Admin API,
   *   sem tocar em nenhuma sessão.
   *
   * Não associa project_ids/campaign_ids legados — isso é
   * responsabilidade do dual-write do v6 quando memberships forem
   * criados depois (campaignMembersService.addMember).
   */
  async createUser(input: CreateUserInput): Promise<LegacyUser> {
    const created = await secureApi.createUser({
      name: input.name,
      email: input.email,
      password: input.password,
      role: input.role,
    });
    // Adapta para o tipo LegacyUser usado pelo restante do fluxo
    return {
      id: created.id,
      name: created.name ?? input.name,
      email: created.email,
      role: created.role,
      commission_percentage: created.commission_percentage ?? 0,
      created_at: created.created_at,
    };
  }

  /**
   * Edita os campos básicos de um usuário (name, email, role).
   * Não toca em project_ids/campaign_ids legados nem em
   * commission_percentage. Memberships e comissões são editados
   * pelos seus próprios CRUDs.
   */
  async updateUser(input: UpdateUserInput): Promise<LegacyUser> {
    return await usersService.update(input.id, {
      name: input.name,
      email: input.email,
      role: input.role,
      // Deixar undefined garante que o usersService NÃO tente
      // recalcular campaign_ids/project_ids legados.
      project_ids: undefined,
      campaign_ids: undefined,
    });
  }

  /**
   * Fluxo unificado: cria usuário + memberships + comissões em
   * sequência. Best-effort com rollback do usuário recém-criado se
   * algo falhar nos passos seguintes (a operação é "atômica do
   * ponto de vista do admin": ou tudo dá certo, ou o usuário não
   * fica criado pela metade).
   *
   * Warnings (não-fatais) são acumulados e devolvidos para que a
   * UI mostre toasts amarelos sem bloquear o fluxo.
   */
  async onboardUser(
    input: OnboardingInput,
    actorId?: string | null
  ): Promise<OnboardingResult> {
    const warnings: string[] = [];

    // 1. Criar usuário
    const user = await this.createUser(input.user);

    let memberships_created = 0;
    let commissions_created = 0;

    try {
      // 2. Memberships (dual-write via addMember)
      for (const m of input.memberships) {
        try {
          await campaignMembersService.addMember({
            user_id: user.id,
            campaign_id: m.campaign_id,
            role_id: m.role_id,
            created_by: actorId ?? null,
          });
          memberships_created += 1;
        } catch (err) {
          // Membership individual falhou: warn mas segue
          warnings.push(
            `Não foi possível criar membership para campanha ${m.campaign_id}: ${
              err instanceof Error ? err.message : 'erro desconhecido'
            }`
          );
        }
      }

      // 3. Comissões
      for (const c of input.commissions) {
        try {
          await campaignCommissionsService.createCommission({
            user_id: user.id,
            campaign_id: c.campaign_id,
            percentage: c.percentage,
            valid_from: c.valid_from,
            notes: c.notes ?? null,
            created_by: actorId ?? null,
          });
          commissions_created += 1;
        } catch (err) {
          warnings.push(
            `Não foi possível criar comissão para campanha ${c.campaign_id}: ${
              err instanceof Error ? err.message : 'erro desconhecido'
            }`
          );
        }
      }

      return { user, memberships_created, commissions_created, warnings };
    } catch (err) {
      // Falha catastrófica nos pós-passos: deletar o usuário recém-criado
      // (o usersService.delete só limpa public.users e tabelas legadas;
      // auth.users não pode ser deletado pelo client — fica como dívida).
      try {
        await usersService.delete(user.id);
      } catch {
        warnings.push(
          'Falha catastrófica e o usuário NÃO pôde ser removido em rollback. Verifique manualmente.'
        );
      }
      throw err;
    }
  }

  // ============================================================
  // DELETE USER — com travas de segurança
  //
  // Regras (defesa em profundidade — checadas na UI antes e
  // re-checadas aqui na hora da ação):
  //
  //   1. Não é possível excluir a própria conta do admin logado
  //   2. Não é possível excluir o último ADMIN (evita lockout)
  //   3. Não é possível excluir usuário com payouts históricos
  //      (preserva histórico financeiro — FK ON DELETE RESTRICT
  //      em daily_campaign_member_payouts força essa regra no
  //      banco também)
  //
  // Cascade automático via FKs quando a regra #3 não bloqueia:
  //   - campaign_members → ON DELETE CASCADE
  //   - campaign_commissions → ON DELETE CASCADE
  //   - user_projects → apagado explicitamente pelo usersService.delete
  //   - user_campaigns → apagado explicitamente pelo usersService.delete
  //
  // Limitação herdada: auth.users NÃO é deletado (sem permissão
  // server-side pelo client). Ficará como "conta órfã" em
  // auth.users, mas sem registro em public.users a pessoa não
  // consegue mais logar no sistema.
  // ============================================================

  /**
   * Pré-verifica se o usuário pode ser excluído, sem executar.
   * Usado pela UI para dar feedback claro antes de abrir o
   * diálogo de confirmação.
   */
  async canDeleteUser(
    userId: string,
    currentAdminId: string | null,
    usersList: UserLite[]
  ): Promise<CanDeleteResult> {
    // Regra 1: não excluir a si mesmo
    if (userId === currentAdminId) {
      return {
        canDelete: false,
        reason: 'Você não pode excluir sua própria conta.',
      };
    }

    const target = usersList.find((u) => u.id === userId);
    if (!target) {
      return { canDelete: false, reason: 'Usuário não encontrado na lista.' };
    }

    // Regra 2: não excluir o último ADMIN
    if (target.role === 'ADMIN') {
      const admins = usersList.filter((u) => u.role === 'ADMIN');
      if (admins.length <= 1) {
        return {
          canDelete: false,
          reason:
            'Não é possível excluir o último administrador do sistema. Promova outro usuário a ADMIN antes.',
        };
      }
    }

    // Regra 3: payouts históricos
    const { count, error } = await supabase
      .from('daily_campaign_member_payouts')
      .select('id', { count: 'exact', head: true })
      .eq('user_id', userId);

    if (error) {
      return {
        canDelete: false,
        reason: `Erro ao verificar histórico financeiro: ${error.message}`,
      };
    }

    const payoutCount = count ?? 0;
    if (payoutCount > 0) {
      return {
        canDelete: false,
        payoutCount,
        reason:
          `Este usuário possui ${payoutCount.toLocaleString('pt-BR')} registros ` +
          'de payout histórico. Para preservar o histórico financeiro, ' +
          'usuários com payouts não podem ser excluídos. ' +
          'Para desativá-lo, encerre as comissões vigentes e remova os memberships.',
      };
    }

    return { canDelete: true };
  }

  /**
   * Executa a exclusão do usuário. Re-verifica as regras de
   * segurança internamente (defesa em profundidade). Lança Error
   * com mensagem amigável em PT-BR se qualquer regra falhar.
   */
  async deleteUser(
    userId: string,
    currentAdminId: string | null
  ): Promise<void> {
    // Regra 1 (defesa)
    if (userId === currentAdminId) {
      throw new Error('Você não pode excluir sua própria conta.');
    }

    // Busca o alvo no banco
    const { data: target, error: targetErr } = await supabase
      .from('users')
      .select('id, role')
      .eq('id', userId)
      .maybeSingle();
    if (targetErr) throw targetErr;
    if (!target) throw new Error('Usuário não encontrado no banco.');

    // Regra 2 (defesa)
    if (target.role === 'ADMIN') {
      const { count: adminCount, error: countErr } = await supabase
        .from('users')
        .select('id', { count: 'exact', head: true })
        .eq('role', 'ADMIN');
      if (countErr) throw countErr;
      if ((adminCount ?? 0) <= 1) {
        throw new Error(
          'Não é possível excluir o último administrador do sistema.'
        );
      }
    }

    // Regra 3 (defesa)
    const { count: payoutCount, error: payoutErr } = await supabase
      .from('daily_campaign_member_payouts')
      .select('id', { count: 'exact', head: true })
      .eq('user_id', userId);
    if (payoutErr) throw payoutErr;
    if ((payoutCount ?? 0) > 0) {
      throw new Error(
        `Usuário possui ${payoutCount} registros de payout histórico. ` +
          'A exclusão foi bloqueada para preservar o histórico financeiro.'
      );
    }

    // OK: delega ao service legado. Ele lida com:
    //   - delete de user_campaigns (legado)
    //   - delete de user_projects (legado)
    //   - delete de public.users
    // As tabelas v6 (campaign_members, campaign_commissions) caem
    // automaticamente via FK ON DELETE CASCADE.
    // auth.users continua existindo como órfão (limitação do client).
    await usersService.delete(userId);
  }
}

export const v6OperationsService = new V6OperationsService();
