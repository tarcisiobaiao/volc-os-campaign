/**
 * v6 RBAC — CommissionsTab
 *
 * Wrapper em torno do CommissionsTimeline com ações de criação e
 * encerramento de vigência. Não tem "editar percentual" — para mudar
 * a taxa, o admin encerra a atual e cria uma nova (preserva
 * histórico financeiro).
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
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Plus } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { useAuth } from '@/contexts/AuthContext';
import { CommissionsTimeline } from '@/v6/components/CommissionsTimeline';
import { CommissionForm } from '@/v6/components/forms/CommissionForm';
import { ConfirmDialog } from '@/v6/components/ConfirmDialog';
import { useCampaignCommissions } from '@/v6/hooks/useCampaignCommissions';
import {
  useV6Users,
  useV6CampaignsWithContext,
  useV6Projects,
} from '@/v6/hooks/useV6Lookups';
import { useCreateCommission, useEndCommission } from '@/v6/hooks/useV6Mutations';
import type { CampaignCommissionEnriched } from '@/v6/types/v6';

interface CommissionsTabProps {
  onMutated?: () => void;
}

const todayIso = (): string => new Date().toISOString().slice(0, 10);

export function CommissionsTab({ onMutated }: CommissionsTabProps) {
  const { toast } = useToast();
  const { userProfile } = useAuth();

  const commissionsHook = useCampaignCommissions();
  const usersHook = useV6Users();
  const projectsHook = useV6Projects();
  const campaignsHook = useV6CampaignsWithContext();

  const createCommission = useCreateCommission();
  const endCommission = useEndCommission();

  const [createOpen, setCreateOpen] = useState(false);
  const [endingTarget, setEndingTarget] = useState<CampaignCommissionEnriched | null>(null);
  const [endValidTo, setEndValidTo] = useState<string>(todayIso());

  const refreshAll = () => {
    commissionsHook.refetch();
    onMutated?.();
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="mr-2 h-4 w-4" /> Nova comissão
        </Button>
      </div>

      <CommissionsTimeline
        data={commissionsHook.data}
        isLoading={commissionsHook.isLoading}
        error={commissionsHook.error}
        onEnd={(c) => {
          setEndingTarget(c);
          setEndValidTo(todayIso());
        }}
      />

      {/* Modal: criar nova vigência */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Nova vigência de comissão</DialogTitle>
            <DialogDescription>
              Cria uma nova vigência. Se já existir vigência aberta para este
              par usuário/campanha, ela será automaticamente encerrada um dia
              antes da nova começar.
            </DialogDescription>
          </DialogHeader>
          <CommissionForm
            users={usersHook.data}
            projects={projectsHook.data}
            campaigns={campaignsHook.data}
            isSubmitting={createCommission.isLoading}
            onCancel={() => setCreateOpen(false)}
            onSubmit={async (values) => {
              try {
                await createCommission.mutate({
                  user_id: values.user_id,
                  campaign_id: values.campaign_id,
                  percentage: values.percentage,
                  valid_from: values.valid_from,
                  notes: values.notes || null,
                  created_by: userProfile?.id ?? null,
                });
                toast({
                  title: 'Comissão criada',
                  description: `Vigência de ${values.percentage}% a partir de ${values.valid_from}.`,
                });
                setCreateOpen(false);
                refreshAll();
              } catch (err) {
                toast({
                  title: 'Erro ao criar comissão',
                  description:
                    err instanceof Error ? err.message : 'erro desconhecido',
                  variant: 'destructive',
                });
              }
            }}
          />
        </DialogContent>
      </Dialog>

      {/* Confirmação: encerrar vigência */}
      <ConfirmDialog
        open={endingTarget !== null}
        onOpenChange={(open) => !open && setEndingTarget(null)}
        title="Encerrar vigência?"
        description={
          endingTarget && (
            <div className="space-y-3">
              <p>
                Encerra a comissão de{' '}
                <strong>{endingTarget.percentage}%</strong> de{' '}
                <strong>
                  {endingTarget.user?.name || endingTarget.user?.email}
                </strong>{' '}
                na campanha{' '}
                <strong>
                  {endingTarget.campaign?.campaign_name || endingTarget.campaign_id}
                </strong>
                .
              </p>
              <div className="space-y-1">
                <Label htmlFor="end-valid-to">Data de encerramento</Label>
                <Input
                  id="end-valid-to"
                  type="date"
                  value={endValidTo}
                  min={endingTarget.valid_from}
                  onChange={(e) => setEndValidTo(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  Inclusiva. Payouts até esta data continuam válidos; depois
                  dela, não há mais comissão até nova vigência ser criada.
                </p>
              </div>
            </div>
          )
        }
        confirmLabel="Encerrar vigência"
        variant="destructive"
        isLoading={endCommission.isLoading}
        onConfirm={async () => {
          if (!endingTarget) return;
          try {
            await endCommission.mutate({
              id: endingTarget.id,
              valid_to: endValidTo,
            });
            toast({
              title: 'Vigência encerrada',
              description: `valid_to = ${endValidTo}.`,
            });
            setEndingTarget(null);
            refreshAll();
          } catch (err) {
            toast({
              title: 'Erro ao encerrar vigência',
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
