/**
 * v6 RBAC — MembershipForm
 *
 * Cria/edita um vínculo. Cascata: Projeto → Campanha → Role.
 * Microcopy mínima — contexto vive nos selectors.
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
  membershipCreateSchema,
  membershipEditSchema,
  type MembershipCreateValues,
  type MembershipEditValues,
} from '@/v6/forms/schemas';
import type {
  CampaignWithContext,
  CampaignRole,
  ProjectLite,
  UserLite,
} from '@/v6/types/v6';
import { CampaignMultiSelector } from '@/v6/components/forms/CampaignMultiSelector';
import { ProjectSelector } from '@/v6/components/forms/ProjectSelector';

interface CommonProps {
  roles: CampaignRole[];
  isSubmitting?: boolean;
  onCancel?: () => void;
  submitLabel?: string;
}

interface CreateProps extends CommonProps {
  mode: 'create';
  users: UserLite[];
  projects: ProjectLite[];
  campaigns: CampaignWithContext[];
  defaultValues?: Partial<MembershipCreateValues>;
  onSubmit: (values: MembershipCreateValues) => Promise<void> | void;
}

interface EditProps extends CommonProps {
  mode: 'edit';
  context: {
    user_label: string;
    campaign_label: string;
  };
  defaultValues: MembershipEditValues;
  onSubmit: (values: MembershipEditValues) => Promise<void> | void;
}

export type MembershipFormProps = CreateProps | EditProps;

export function MembershipForm(props: MembershipFormProps) {
  if (props.mode === 'create') return <MembershipCreateForm {...props} />;
  return <MembershipEditForm {...props} />;
}

function MembershipCreateForm({
  users,
  projects,
  campaigns,
  roles,
  defaultValues,
  onSubmit,
  onCancel,
  isSubmitting,
  submitLabel = 'Criar memberships',
}: CreateProps) {
  const form = useForm<MembershipCreateValues>({
    resolver: zodResolver(membershipCreateSchema),
    defaultValues: {
      user_id: defaultValues?.user_id ?? '',
      campaign_ids: defaultValues?.campaign_ids ?? [],
      role_id: defaultValues?.role_id ?? (roles[0]?.id ?? 0),
    },
  });

  // Cascade local state — projeto não faz parte do schema (é UI only).
  const [projectId, setProjectId] = useState<number | null>(null);

  // Quando o projeto muda, limpa as campanhas selecionadas (as
  // anteriores podem pertencer a outro projeto).
  useEffect(() => {
    form.setValue('campaign_ids', []);
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
            name="campaign_ids"
            render={({ field }) => {
              const selectedUserId = form.watch('user_id');
              return (
                <FormItem>
                  <FormLabel>Campanhas</FormLabel>
                  <FormControl>
                    <CampaignMultiSelector
                      campaigns={campaigns}
                      value={field.value}
                      onChange={field.onChange}
                      projectId={projectId}
                      placeholder={
                        projectId == null
                          ? 'Selecione um projeto antes'
                          : 'Selecione campanhas'
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

        <FormField
          control={form.control}
          name="role_id"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Role funcional</FormLabel>
              <Select
                onValueChange={(v) => field.onChange(Number(v))}
                value={String(field.value || '')}
              >
                <FormControl>
                  <SelectTrigger>
                    <SelectValue placeholder="Selecione" />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  {roles.map((r) => (
                    <SelectItem key={r.id} value={String(r.id)}>
                      <span className="font-medium">{r.label}</span>
                      <span className="ml-2 text-xs text-muted-foreground">
                        {r.code}
                      </span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
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

function MembershipEditForm({
  context,
  roles,
  defaultValues,
  onSubmit,
  onCancel,
  isSubmitting,
  submitLabel = 'Salvar',
}: EditProps) {
  const form = useForm<MembershipEditValues>({
    resolver: zodResolver(membershipEditSchema),
    defaultValues,
  });

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit(async (values) => {
          await onSubmit(values);
        })}
        className="space-y-4"
      >
        <div className="rounded-md border bg-muted/40 p-3 text-sm">
          <div>
            <span className="text-muted-foreground">Usuário:</span>{' '}
            <strong>{context.user_label}</strong>
          </div>
          <div>
            <span className="text-muted-foreground">Campanha:</span>{' '}
            <strong>{context.campaign_label}</strong>
          </div>
        </div>

        <FormField
          control={form.control}
          name="role_id"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Novo role funcional</FormLabel>
              <Select
                onValueChange={(v) => field.onChange(Number(v))}
                value={String(field.value || '')}
              >
                <FormControl>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  {roles.map((r) => (
                    <SelectItem key={r.id} value={String(r.id)}>
                      <span className="font-medium">{r.label}</span>
                      <span className="ml-2 text-xs text-muted-foreground">
                        {r.code}
                      </span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
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
