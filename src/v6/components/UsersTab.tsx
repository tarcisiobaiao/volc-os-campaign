/**
 * v6 RBAC — UsersTab
 *
 * Lista todos os usuários do sistema. Permite:
 *
 *   - criar novos via OnboardingWizard (3 passos)
 *   - editar dados básicos (nome, email, role global) via UserForm
 *   - **excluir** usuários (com travas de segurança em cascata)
 *
 * Travas de exclusão (enforced tanto na UI quanto no service):
 *   1. Admin não pode excluir a própria conta
 *   2. Não é possível excluir o último ADMIN do sistema
 *   3. Usuário com payouts históricos NÃO pode ser excluído
 *      (preserva histórico financeiro — FK ON DELETE RESTRICT
 *      em daily_campaign_member_payouts)
 *
 * Delete cascateia (via FK) para:
 *   - campaign_members
 *   - campaign_commissions
 *   - user_projects / user_campaigns (via usersService legado)
 *
 * NÃO deleta auth.users (limitação do client do Supabase —
 * precisaria de server-side function). A conta fica órfã em
 * auth mas sem registro em public.users a pessoa não loga mais.
 */
import { useMemo, useState } from 'react';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Pencil,
  Plus,
  Search,
  Trash2,
  Users as UsersIcon,
  AlertCircle,
  Loader2,
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { useAuth } from '@/contexts/AuthContext';
import { useV6Users, useV6CampaignsWithContext, useV6Projects } from '@/v6/hooks/useV6Lookups';
import { useCampaignRoles } from '@/v6/hooks/useCampaignRoles';
import {
  useUpdateUser,
  useOnboardUser,
  useDeleteUser,
} from '@/v6/hooks/useV6Mutations';
import { v6OperationsService } from '@/v6/services/v6OperationsService';
import { OnboardingWizard } from '@/v6/components/OnboardingWizard';
import { UserForm } from '@/v6/components/forms/UserForm';
import { ConfirmDialog } from '@/v6/components/ConfirmDialog';
import type { UserLite } from '@/v6/types/v6';

interface UsersTabProps {
  /** Disparado após mutações para recarregar agregações da página. */
  onMutated?: () => void;
}

export function UsersTab({ onMutated }: UsersTabProps) {
  const { toast } = useToast();
  const { userProfile } = useAuth();
  const currentAdminId = userProfile?.id ?? null;

  const usersHook = useV6Users();
  const projectsHook = useV6Projects();
  const campaignsHook = useV6CampaignsWithContext();
  const rolesHook = useCampaignRoles();

  const onboardUser = useOnboardUser(currentAdminId);
  const updateUser = useUpdateUser();
  const deleteUser = useDeleteUser(currentAdminId);

  const [search, setSearch] = useState('');
  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<UserLite | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<UserLite | null>(null);
  const [checkingDeletion, setCheckingDeletion] = useState(false);

  const filtered = useMemo(() => {
    if (!search.trim()) return usersHook.data;
    const q = search.toLowerCase();
    return usersHook.data.filter(
      (u) =>
        u.email.toLowerCase().includes(q) ||
        u.name?.toLowerCase().includes(q) ||
        u.role.toLowerCase().includes(q)
    );
  }, [usersHook.data, search]);

  const handleCreated = () => {
    setCreateOpen(false);
    usersHook.refetch();
    onMutated?.();
  };

  const handleEdited = () => {
    setEditing(null);
    usersHook.refetch();
    onMutated?.();
  };

  /**
   * Pré-verifica se o usuário pode ser excluído.
   * Se sim: abre o diálogo de confirmação.
   * Se não: mostra toast com o motivo (não abre o diálogo).
   */
  const handleDeleteClick = async (user: UserLite) => {
    setCheckingDeletion(true);
    try {
      const result = await v6OperationsService.canDeleteUser(
        user.id,
        currentAdminId,
        usersHook.data
      );
      if (!result.canDelete) {
        toast({
          title: 'Não é possível excluir',
          description: result.reason || 'Motivo desconhecido.',
          variant: 'destructive',
        });
        return;
      }
      setDeleteTarget(user);
    } catch (err) {
      toast({
        title: 'Erro ao verificar usuário',
        description: err instanceof Error ? err.message : 'erro desconhecido',
        variant: 'destructive',
      });
    } finally {
      setCheckingDeletion(false);
    }
  };

  const handleDeleteConfirm = async () => {
    if (!deleteTarget) return;
    try {
      await deleteUser.mutate(deleteTarget.id);
      toast({
        title: 'Usuário excluído',
        description: `${deleteTarget.email} foi removido do sistema.`,
      });
      setDeleteTarget(null);
      usersHook.refetch();
      onMutated?.();
    } catch (err) {
      toast({
        title: 'Erro ao excluir usuário',
        description: err instanceof Error ? err.message : 'erro desconhecido',
        variant: 'destructive',
      });
    }
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <CardTitle className="flex items-center gap-2 font-display">
              <span className="rounded-md bg-primary/10 p-1.5 text-primary">
                <UsersIcon className="h-4 w-4" />
              </span>
              Usuários do sistema
            </CardTitle>
            <CardDescription>
              Cadastre admins e operadores. Use o onboarding completo para já
              criar memberships e comissões na mesma jornada.
            </CardDescription>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row">
            <div className="relative w-full max-w-xs">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                id="busca-de-usuarios"
                type="search"
                aria-label="Buscar usuário por nome ou email"
                placeholder="Buscar por nome ou email"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-8"
              />
            </div>
            <Button onClick={() => setCreateOpen(true)}>
              <Plus className="mr-2 h-4 w-4" /> Novo usuário
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent>
        {usersHook.isLoading && (
          <div className="flex justify-center py-12">
            <LoadingSpinner />
          </div>
        )}

        {!usersHook.isLoading && usersHook.error && (
          <div className="flex items-center gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
            <AlertCircle className="h-4 w-4" />
            <span>Erro ao carregar usuários: {usersHook.error.message}</span>
          </div>
        )}

        {!usersHook.isLoading && !usersHook.error && filtered.length === 0 && (
          <div className="flex flex-col items-center justify-center gap-3 rounded-md border border-dashed py-12 text-center">
            <span className="rounded-full bg-muted p-3 text-muted-foreground">
              {usersHook.data.length === 0 ? (
                <UsersIcon className="h-5 w-5" />
              ) : (
                <Search className="h-5 w-5" />
              )}
            </span>
            <div className="kicker">
              {usersHook.data.length === 0 ? 'Sem usuários' : 'Sem resultados'}
            </div>
            <p className="max-w-sm text-sm text-muted-foreground">
              {usersHook.data.length === 0
                ? 'Nenhum usuário cadastrado. Crie o primeiro com o botão "Novo usuário".'
                : 'Nenhum usuário corresponde ao filtro.'}
            </p>
          </div>
        )}

        {!usersHook.isLoading && !usersHook.error && filtered.length > 0 && (
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="kicker">Nome</TableHead>
                  <TableHead className="kicker">Email</TableHead>
                  <TableHead className="kicker">Role global</TableHead>
                  <TableHead className="kicker text-right">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((u) => {
                  const isSelf = u.id === currentAdminId;
                  return (
                    <TableRow key={u.id}>
                      <TableCell className="font-medium">
                        {u.name || '(sem nome)'}
                        {isSelf && (
                          <span className="ml-2 text-[10px] text-muted-foreground">
                            (você)
                          </span>
                        )}
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {u.email}
                      </TableCell>
                      <TableCell>
                        <span
                          className={
                            'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ' +
                            (u.role === 'ADMIN'
                              ? 'bg-primary/12 text-primary'
                              : 'bg-muted text-muted-foreground')
                          }
                        >
                          <span
                            className={
                              'h-1.5 w-1.5 rounded-full ' +
                              (u.role === 'ADMIN' ? 'bg-primary' : 'bg-muted-foreground')
                            }
                          />
                          {u.role}
                        </span>
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setEditing(u)}
                          >
                            <Pencil className="mr-1.5 h-3.5 w-3.5" /> Editar
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            disabled={isSelf || checkingDeletion}
                            onClick={() => handleDeleteClick(u)}
                            title={
                              isSelf
                                ? 'Você não pode excluir a própria conta'
                                : 'Excluir usuário'
                            }
                            className={
                              isSelf
                                ? ''
                                : 'text-destructive hover:text-destructive'
                            }
                          >
                            {checkingDeletion ? (
                              <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                              <Trash2 className="h-4 w-4" />
                            )}
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>

      {/* Modal: criar novo usuário (wizard 3 passos) */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-h-[92vh] w-[calc(100vw-1.5rem)] max-w-3xl overflow-y-auto overflow-x-hidden p-4 sm:p-6">
          <DialogHeader>
            <DialogTitle>Novo usuário</DialogTitle>
            <DialogDescription>
              Crie o usuário e já vincule campanhas + comissões em um único
              fluxo.
            </DialogDescription>
          </DialogHeader>
          <OnboardingWizard
            projects={projectsHook.data}
            campaigns={campaignsHook.data}
            roles={rolesHook.selectable}
            isSubmitting={onboardUser.isLoading}
            onCancel={() => setCreateOpen(false)}
            onSubmit={async (input) => {
              try {
                const result = await onboardUser.mutate(input);
                toast({
                  title: 'Usuário criado',
                  description: `${result.user.email} • ${result.memberships_created} membership(s) • ${result.commissions_created} comissão(ões)`,
                });
                if (result.warnings.length > 0) {
                  toast({
                    title: 'Atenção',
                    description: result.warnings.join(' '),
                    variant: 'destructive',
                  });
                }
                handleCreated();
              } catch (err) {
                toast({
                  title: 'Erro ao criar usuário',
                  description:
                    err instanceof Error ? err.message : 'erro desconhecido',
                  variant: 'destructive',
                });
              }
            }}
          />
        </DialogContent>
      </Dialog>

      {/* Modal: editar usuário existente */}
      <Dialog open={editing !== null} onOpenChange={(open) => !open && setEditing(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Editar usuário</DialogTitle>
            <DialogDescription>
              Atualiza nome, email e role global. Memberships e comissões são
              gerenciados em abas separadas.
            </DialogDescription>
          </DialogHeader>
          {editing && (
            <UserForm
              mode="edit"
              defaultValues={{
                name: editing.name || '',
                email: editing.email,
                role: editing.role as 'ADMIN' | 'OPERATOR',
              }}
              isSubmitting={updateUser.isLoading}
              onCancel={() => setEditing(null)}
              onSubmit={async (values) => {
                try {
                  await updateUser.mutate({
                    id: editing.id,
                    ...values,
                  });
                  toast({
                    title: 'Usuário atualizado',
                    description: `${values.email} salvo com sucesso.`,
                  });
                  handleEdited();
                } catch (err) {
                  toast({
                    title: 'Erro ao atualizar usuário',
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

      {/* Confirmação: excluir usuário */}
      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        title="Excluir usuário?"
        description={
          deleteTarget && (
            <div className="space-y-3">
              <p>
                Vai excluir permanentemente{' '}
                <strong>{deleteTarget.name || deleteTarget.email}</strong> (
                {deleteTarget.email}).
              </p>
              <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-xs">
                <p className="mb-1 font-medium text-destructive">
                  Esta ação é irreversível e remove em cascata:
                </p>
                <ul className="ml-4 list-disc space-y-0.5">
                  <li>Memberships do usuário em campanhas</li>
                  <li>Vigências de comissão (passadas e atuais)</li>
                  <li>Acessos legados (user_projects, user_campaigns)</li>
                </ul>
              </div>
              <p className="text-[11px] text-muted-foreground">
                Observação: a entrada em <code>auth.users</code> (Supabase
                Auth) não é removida pelo client — o usuário simplesmente
                deixa de conseguir logar porque não há mais registro em{' '}
                <code>public.users</code>.
              </p>
            </div>
          )
        }
        confirmLabel="Excluir permanentemente"
        variant="destructive"
        isLoading={deleteUser.isLoading}
        onConfirm={handleDeleteConfirm}
      />
    </Card>
  );
}
