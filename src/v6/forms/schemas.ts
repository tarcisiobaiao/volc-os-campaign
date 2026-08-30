/**
 * v6 RBAC — schemas de validação (Etapa 3.C operacional)
 *
 * Zod + react-hook-form. Padrão idêntico ao já usado em outras
 * features do projeto que dependem de @hookform/resolvers + zod.
 */
import { z } from 'zod';

// ----------------------------------------------------------------
// Usuário
// ----------------------------------------------------------------

export const userCreateSchema = z.object({
  name: z
    .string()
    .trim()
    .min(2, 'Nome deve ter ao menos 2 caracteres')
    .max(120, 'Nome muito longo'),
  email: z
    .string()
    .trim()
    .toLowerCase()
    .email('Email inválido'),
  password: z
    .string()
    .min(8, 'Senha deve ter ao menos 8 caracteres')
    .max(128, 'Senha muito longa'),
  role: z.enum(['ADMIN', 'OPERATOR'], {
    required_error: 'Selecione um role global',
  }),
});

export type UserCreateValues = z.infer<typeof userCreateSchema>;

export const userEditSchema = z.object({
  name: z
    .string()
    .trim()
    .min(2, 'Nome deve ter ao menos 2 caracteres')
    .max(120, 'Nome muito longo'),
  email: z
    .string()
    .trim()
    .toLowerCase()
    .email('Email inválido'),
  role: z.enum(['ADMIN', 'OPERATOR']),
});

export type UserEditValues = z.infer<typeof userEditSchema>;

// ----------------------------------------------------------------
// Membership (vínculo de acesso por campanha)
// ----------------------------------------------------------------

export const membershipCreateSchema = z.object({
  user_id: z.string().uuid('Selecione um usuário'),
  // Suporte a criação em lote: aceita 1..N campanhas de uma vez.
  // O wrapper no MembershipsTab itera e cria um membership por campanha.
  campaign_ids: z
    .array(z.string().min(1))
    .min(1, 'Selecione pelo menos uma campanha'),
  role_id: z.coerce
    .number({ invalid_type_error: 'Selecione um role' })
    .int()
    .positive('Selecione um role'),
});

export type MembershipCreateValues = z.infer<typeof membershipCreateSchema>;

export const membershipEditSchema = z.object({
  role_id: z.coerce
    .number({ invalid_type_error: 'Selecione um role' })
    .int()
    .positive('Selecione um role'),
});

export type MembershipEditValues = z.infer<typeof membershipEditSchema>;

// ----------------------------------------------------------------
// Comissão (regra financeira versionada)
// ----------------------------------------------------------------

const isoDate = z
  .string()
  .regex(/^\d{4}-\d{2}-\d{2}$/, 'Data deve estar no formato AAAA-MM-DD');

export const commissionCreateSchema = z.object({
  user_id: z.string().uuid('Selecione um usuário'),
  campaign_id: z.string().min(1, 'Selecione uma campanha'),
  percentage: z.coerce
    .number({ invalid_type_error: 'Percentual inválido' })
    .min(0, 'Percentual não pode ser negativo')
    .max(100, 'Percentual não pode passar de 100'),
  valid_from: isoDate,
  notes: z
    .string()
    .max(500, 'Observação muito longa')
    .optional()
    .or(z.literal('')),
});

export type CommissionCreateValues = z.infer<typeof commissionCreateSchema>;

export const commissionEndSchema = z.object({
  valid_to: isoDate,
});

export type CommissionEndValues = z.infer<typeof commissionEndSchema>;
