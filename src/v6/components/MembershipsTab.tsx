/**
 * v6 RBAC — MembershipsTab
 *
 * Wrapper de página em torno do MembersTable + ações de criação,
 * edição (alterar role) e remoção. Reutiliza o componente MembersTable
 * com props opcionais `onEdit`/`onRemove`.
 */
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Plus } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { useAuth } from '@/contexts/AuthContext';
import { MembersTable } from '@/v6/components/MembersTable';
import { MembershipForm } from '@/v6/components/forms/MembershipForm';
import { ConfirmDialog } from '@/v6/components/ConfirmDialog';
import { useCampaignMembers } from '@/v6/hooks/useCampaignMembers';
import { useCampaignRoles } from '@/v6/hooks/useCampaignRoles';
import {
  useV6Users,
  useV6CampaignsWithContext,
  useV6Projects,
} from '@/v6/hooks/useV6Lookups';
import {
  useCreateMembership,
  useUpdateMembership,
  useRemoveMembership,
} from '@/v6/hooks/useV6Mutations';
import type { CampaignMemberEnriched } from '@/v6/types/v6';

interface MembershipsTabProps {
  onMutated?: () => void;
}

export function MembershipsTab({ onMutated }: MembershipsTabProps) {
  const { toast } = useToast();
  const { userProfile } = useAuth();

  const membersHook = useCampaignMembers();
  const rolesHook = useCampaignRoles();
  const usersHook = useV6Users();
  const projectsHook = useV6Projects();
  const campaignsHook = useV6CampaignsWithContext();

  const createMembership = useCreateMembership();
  const updateMembership = useUpdateMembership();
  const removeMembership = useRemoveMembership();

  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<CampaignMemberEnriched | null>(null);
  const [removingTarget, setRemovingTarget] = useState<CampaignMemberEnriched | null>(null);

  const refreshAll = () => {
    membersHook.refetch();
    onMutated?.();
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="mr-2 h-4 w-4" /> Novo link
        </Button>
      </div>

      <MembersTable
        members={membersHook.members}
        isLoading={membersHook.isLoading}
        error={membersHook.error}
        onEdit={(m) => setEditing(m)}
        onRemove={(m) => setRemovingTarget(m)}
      />

      {/* Modal: criar membership */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Novo membership</DialogTitle>
            <DialogDescription>
              Cria vínculos de acesso entre um usuário e uma ou mais
              campanhas de uma só vez. Comissão é configurada
              separadamente na aba "Comissões".
            </DialogDescription>
          </DialogHeader>
          <MembershipForm
            mode="create"
            users={usersHook.data}
            projects={projectsHook.data}
            campaigns={campaignsHook.data}
            roles={rolesHook.selectable}
            isSubmitting={createMembership.isLoading}
            onCancel={() => setCreateOpen(false)}
            onSubmit={async (values) => {
              // Criação em lote: itera sobre as campanhas selecionadas.
              // Pula silenciosamente as que já possuem vínculo com esse
              // usuário (o multi-selector já bloqueia, mas aqui é um
              // segundo guard contra race conditions).
              const existingPairs = new Set(
                membersHook.members
                  .filter((m) => m.user_id === values.user_id)
                  .map((m) => m.campaign_id)
              );
              const targets = values.campaign_ids.filter(
                (id) => !existingPairs.has(id)
              );

              if (targets.length === 0) {
                toast({
                  title: 'Nada a criar',
                  description:
                    'O usuário já está vinculado a todas as campanhas selecionadas.',
                });
                return;
              }

              const results = await Promise.allSettled(
                targets.map((campaign_id) =>
                  createMembership.mutate({
                    user_id: values.user_id,
                    campaign_id,
                    role_id: values.role_id,
                    created_by: userProfile?.id ?? null,
                  })
                )
              );

              const okCount = results.filter(
                (r) => r.status === 'fulfilled'
              ).length;
              const failCount = results.length - okCount;

              if (failCount === 0) {
                toast({
                  title:
                    okCount === 1
                      ? 'Membership criado'
                      : `${okCount} memberships criados`,
                  description: 'Vínculos adicionados com sucesso.',
                });
                setCreateOpen(false);
              } else if (okCount === 0) {
                const firstErr = results.find(
                  (r): r is PromiseRejectedResult => r.status === 'rejected'
                );
                toast({
                  title: 'Erro ao criar memberships',
                  description:
                    firstErr?.reason instanceof Error
                      ? firstErr.reason.message
                      : 'Falha ao criar vínculos.',
                  variant: 'destructive',
                });
              } else {
                toast({
                  title: `${okCount} criados, ${failCount} falharam`,
                  description:
                    'Alguns vínculos não puderam ser criados. Verifique e tente novamente.',
                  variant: 'destructive',
                });
                setCreateOpen(false);
              }

              refreshAll();
            }}
          />
        </DialogContent>
      </Dialog>

      {/* Modal: editar role do membership */}
      <Dialog open={editing !== null} onOpenChange={(open) => !open && setEditing(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Alterar role funcional</DialogTitle>
            <DialogDescription>
              Você só pode mudar o role. Para mudar o usuário ou a campanha,
              remova este membership e crie um novo.
            </DialogDescription>
          </DialogHeader>
          {editing && (
            <MembershipForm
              mode="edit"
              roles={rolesHook.selectable}
              context={{
                user_label:
                  editing.user?.name || editing.user?.email || editing.user_id,
                campaign_label:
                  editing.campaign?.campaign_name || editing.campaign_id,
              }}
              defaultValues={{ role_id: editing.role_id }}
              isSubmitting={updateMembership.isLoading}
              onCancel={() => setEditing(null)}
              onSubmit={async (values) => {
                try {
                  await updateMembership.mutate({
                    id: editing.id,
                    role_id: values.role_id,
                  });
                  toast({
                    title: 'Role atualizado',
                    description: 'Role funcional do membership foi alterado.',
                  });
                  setEditing(null);
                  refreshAll();
                } catch (err) {
                  toast({
                    title: 'Erro ao atualizar role',
                    description:
                      err instanceof Error ? err.message : 'erro desconhecido',
                    variant: 'destructive',
                  });
                }
              }}
            />
          )}
        </DialogContent>
      </Dialog>

      {/* Confirmação: remover membership */}
      <ConfirmDialog
        open={removingTarget !== null}
        onOpenChange={(open) => !open && setRemovingTarget(null)}
        title="Remover membership?"
        description={
          removingTarget && (
            <div className="space-y-2">
              <p>
                Vai remover o vínculo de{' '}
                <strong>
                  {removingTarget.user?.name || removingTarget.user?.email}
                </strong>{' '}
                com a campanha{' '}
                <strong>
                  {removingTarget.campaign?.campaign_name ||
                    removingTarget.campaign_id}
                </strong>
                .
              </p>
              <p className="text-xs">
                <strong>Atenção:</strong> isso remove tanto de{' '}
                <code>campaign_members</code> quanto de{' '}
                <code>user_campaigns</code> (legado), <strong>se</strong> esse
                par usuário/campanha não tiver mais nenhum outro role no v6.
                Comissões já configuradas <strong>não</strong> são afetadas.
              </p>
            </div>
          )
        }
        confirmLabel="Remover"
        variant="destructive"
        isLoading={removeMembership.isLoading}
        onConfirm={async () => {
          if (!removingTarget) return;
          try {
            await removeMembership.mutate({
              id: removingTarget.id,
              user_id: removingTarget.user_id,
              campaign_id: removingTarget.campaign_id,
            });
            toast({
              title: 'Membership removido',
              description: 'Vínculo apagado com sucesso.',
            });
            setRemovingTarget(null);
            refreshAll();
          } catch (err) {
            toast({
              title: 'Erro ao remover membership',
              description:
                err instanceof Error ? err.message : 'erro desconhecido',
              variant: 'destructive',
            });
          }
        }}
      />
    </div>
  );
}
