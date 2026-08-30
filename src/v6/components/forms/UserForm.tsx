/**
 * v6 RBAC — UserForm
 *
 * Formulário de criação ou edição de usuário básico (sem
 * memberships e sem comissões — esses são tratados em formulários
 * dedicados ou no OnboardingWizard).
 *
 * Modos:
 *   - mode="create": exige password, retorna CreateUserInput
 *   - mode="edit":   esconde password, exige id, retorna UpdateUserInput
 *
 * O componente é "presentational" — chama `onSubmit` com os dados
 * validados; quem usa decide o que fazer (chamar mutation hook,
 * fechar modal, mostrar toast, etc).
 */
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
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
  userCreateSchema,
  userEditSchema,
  type UserCreateValues,
  type UserEditValues,
} from '@/v6/forms/schemas';

type CreateProps = {
  mode: 'create';
  defaultValues?: Partial<UserCreateValues>;
  onSubmit: (values: UserCreateValues) => Promise<void> | void;
  onCancel?: () => void;
  isSubmitting?: boolean;
  submitLabel?: string;
};

type EditProps = {
  mode: 'edit';
  defaultValues: UserEditValues;
  onSubmit: (values: UserEditValues) => Promise<void> | void;
  onCancel?: () => void;
  isSubmitting?: boolean;
  submitLabel?: string;
};

export type UserFormProps = CreateProps | EditProps;

export function UserForm(props: UserFormProps) {
  if (props.mode === 'create') {
    return <UserCreateForm {...props} />;
  }
  return <UserEditForm {...props} />;
}

function UserCreateForm({
  defaultValues,
  onSubmit,
  onCancel,
  isSubmitting,
  submitLabel = 'Criar usuário',
}: CreateProps) {
  const form = useForm<UserCreateValues>({
    resolver: zodResolver(userCreateSchema),
    defaultValues: {
      name: defaultValues?.name ?? '',
      email: defaultValues?.email ?? '',
      password: defaultValues?.password ?? '',
      role: defaultValues?.role ?? 'OPERATOR',
    },
  });

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
          name="name"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Nome completo</FormLabel>
              <FormControl>
                <Input placeholder="Maria Silva" autoComplete="off" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="email"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Email</FormLabel>
              <FormControl>
                <Input
                  type="email"
                  placeholder="maria@exemplo.com"
                  autoComplete="off"
                  {...field}
                />
              </FormControl>
              <FormDescription>
                Será o login do usuário. Não pode ser duplicado.
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="password"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Senha temporária</FormLabel>
              <FormControl>
                <Input type="text" autoComplete="new-password" {...field} />
              </FormControl>
              <FormDescription>
                Mínimo 8 caracteres. O usuário será obrigado a trocar no
                primeiro login (`needs_password_change=true`).
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="role"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Role global</FormLabel>
              <Select onValueChange={field.onChange} value={field.value}>
                <FormControl>
                  <SelectTrigger>
                    <SelectValue placeholder="Selecione" />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  <SelectItem value="OPERATOR">
                    OPERATOR — usuário comum, vê apenas suas campanhas
                  </SelectItem>
                  <SelectItem value="ADMIN">
                    ADMIN — gerencia o sistema inteiro
                  </SelectItem>
                </SelectContent>
              </Select>
              <FormDescription>
                Esse é o role global legado. Roles funcionais por campanha
                (OWNER, OPERATOR, REVIEWER, VIEWER) são definidos
                separadamente em "Memberships".
              </FormDescription>
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

function UserEditForm({
  defaultValues,
  onSubmit,
  onCancel,
  isSubmitting,
  submitLabel = 'Salvar alterações',
}: EditProps) {
  const form = useForm<UserEditValues>({
    resolver: zodResolver(userEditSchema),
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
        <FormField
          control={form.control}
          name="name"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Nome completo</FormLabel>
              <FormControl>
                <Input {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="email"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Email</FormLabel>
              <FormControl>
                <Input type="email" {...field} />
              </FormControl>
              <FormDescription>
                Atenção: alterar o email NÃO atualiza o email no Supabase Auth.
                Isso é uma limitação herdada do legado.
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="role"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Role global</FormLabel>
              <Select onValueChange={field.onChange} value={field.value}>
                <FormControl>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  <SelectItem value="OPERATOR">OPERATOR</SelectItem>
                  <SelectItem value="ADMIN">ADMIN</SelectItem>
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
