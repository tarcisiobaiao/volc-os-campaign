/**
 * v6 RBAC — CommissionForm
 *
 * Cria nova vigência. Cascade Projeto → Campanha. Encerrar é fluxo
 * separado (modal de confirmação). Editar percentual NÃO existe por
 * design — para mudar a taxa, encerre e crie nova vigência.
 */
import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Loader2 } from 'lucide-react';
import {
  commissionCreateSchema,
  type CommissionCreateValues,
} from '@/v6/forms/schemas';
import type {
  CampaignWithContext,
  ProjectLite,
  UserLite,
} from '@/v6/types/v6';
import { CampaignSelector } from '@/v6/components/forms/CampaignSelector';
import { ProjectSelector } from '@/v6/components/forms/ProjectSelector';

interface CommissionFormProps {
  users: UserLite[];
  projects: ProjectLite[];
  campaigns: CampaignWithContext[];
  defaultValues?: Partial<CommissionCreateValues>;
  onSubmit: (values: CommissionCreateValues) => Promise<void> | void;
  onCancel?: () => void;
  isSubmitting?: boolean;
  submitLabel?: string;
}

const todayIso = (): string => new Date().toISOString().slice(0, 10);

export function CommissionForm({
  users,
  projects,
  campaigns,
  defaultValues,
  onSubmit,
  onCancel,
  isSubmitting,
  submitLabel = 'Criar comissão',
}: CommissionFormProps) {
  const form = useForm<CommissionCreateValues>({
    resolver: zodResolver(commissionCreateSchema),
    defaultValues: {
      user_id: defaultValues?.user_id ?? '',
      campaign_id: defaultValues?.campaign_id ?? '',
      percentage: defaultValues?.percentage ?? 15,
      valid_from: defaultValues?.valid_from ?? todayIso(),
      notes: defaultValues?.notes ?? '',
    },
  });

  const [projectId, setProjectId] = useState<number | null>(null);

  useEffect(() => {
    form.setValue('campaign_id', '');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit(async (values) => {
          await onSubmit(values);
        })}
        className="space-y-4"
      >
        <FormField
          control={form.control}
          name="user_id"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Usuário</FormLabel>
              <Select onValueChange={field.onChange} value={field.value}>
                <FormControl>
                  <SelectTrigger>
                    <SelectValue placeholder="Selecione" />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  {users.map((u) => (
                    <SelectItem key={u.id} value={u.id}>
                      {u.name || '(sem nome)'} — {u.email}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FormMessage />
            </FormItem>
          )}
        />

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormItem>
            <FormLabel>Projeto</FormLabel>
            <ProjectSelector
              projects={projects}
              value={projectId}
              onChange={setProjectId}
            />
          </FormItem>

          <FormField
            control={form.control}
            name="campaign_id"
            render={({ field }) => {
              const selectedUserId = form.watch('user_id');
              return (
                <FormItem>
                  <FormLabel>Campanha</FormLabel>
                  <FormControl>
                    <CampaignSelector
                      campaigns={campaigns}
                      value={field.value}
                      onChange={field.onChange}
                      projectId={projectId}
                      placeholder={
                        projectId == null
                          ? 'Selecione um projeto antes'
                          : 'Selecione uma campanha'
                      }
                      highlightUserId={selectedUserId || undefined}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              );
            }}
          />
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormField
            control={form.control}
            name="percentage"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Percentual</FormLabel>
                <FormControl>
                  <div className="relative">
                    <Input
                      type="number"
                      step="0.0001"
                      min={0}
                      max={100}
                      {...field}
                    />
                    <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">
                      %
                    </span>
                  </div>
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="valid_from"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Início da vigência</FormLabel>
                <FormControl>
                  <Input type="date" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>

        <FormField
          control={form.control}
          name="notes"
          render={({ field }) => (
            <FormItem>
              <FormLabel>
                Observações <span className="text-muted-foreground">(opcional)</span>
              </FormLabel>
              <FormControl>
                <Textarea rows={2} {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <div className="flex items-center justify-end gap-2 pt-2">
          {onCancel && (
            <Button type="button" variant="outline" onClick={onCancel} disabled={isSubmitting}>
              Cancelar
            </Button>
          )}
          <Button type="submit" disabled={isSubmitting}>
            {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {submitLabel}
          </Button>
        </div>
      </form>
    </Form>
  );
}
