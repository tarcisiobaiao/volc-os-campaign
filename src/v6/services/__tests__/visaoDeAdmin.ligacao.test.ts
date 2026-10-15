import { beforeEach, describe, expect, it, vi } from 'vitest';

// Prova que o aviso de "ADMIN sem papel no banco" está LIGADO nos serviços que
// listam usuários: com public.users devolvendo só a linha de um ADMIN (o que a
// RLS da v8_03 faz quando app_auth não o reconhece) e volc_current_admin=false,
// cada serviço tem de rejeitar em vez de devolver uma lista incompleta.
// Tirar a chamada de qualquer um deles derruba o caso correspondente.

const estado = {
  users: [] as Array<Record<string, unknown>>,
  contagemAdmins: 0,
  alvo: null as Record<string, unknown> | null,
  rpc: { data: false as unknown, error: null as unknown },
};

function construtor(tabela: string) {
  let head = false;
  const b: Record<string, unknown> = {};
  const resultado = () => {
    if (tabela === 'users' && head) return { data: null, count: estado.contagemAdmins, error: null };
    if (tabela === 'users') return { data: estado.users, count: estado.users.length, error: null };
    return { data: [], count: 0, error: null };
  };
  for (const m of ['eq', 'order', 'in', 'is', 'gte', 'lte', 'not', 'filter']) b[m] = () => b;
  b.select = (_c?: string, opts?: { head?: boolean }) => { head = Boolean(opts?.head); return b; };
  b.range = async () => resultado();
  b.maybeSingle = async () => ({ data: tabela === 'users' ? estado.alvo : null, error: null });
  b.single = b.maybeSingle;
  b.then = (ok: (v: unknown) => unknown, erro?: (e: unknown) => unknown) => Promise.resolve(resultado()).then(ok, erro);
  return b;
}

vi.mock('@/lib/supabase', () => ({
  supabase: {
    from: (t: string) => construtor(t),
    rpc: async (nome: string) => (nome === 'volc_current_admin' ? estado.rpc : { data: null, error: null }),
  },
}));

import { lookupsService } from '@/v6/services/lookupsService';
import { memberPayoutsService } from '@/v6/services/memberPayoutsService';
import { campaignMembersService } from '@/v6/services/campaignMembersService';
import { campaignCommissionsService } from '@/v6/services/campaignCommissionsService';
import { v6OperationsService } from '@/v6/services/v6OperationsService';
import {
  MENSAGEM_ADMIN_SEM_PAPEL,
  MENSAGEM_PAPEL_INDETERMINADO,
} from '@/v6/services/visaoDeAdmin';

const SO_O_ADMIN = [{ id: 'u-admin', name: 'Admin', email: 'a@example.invalid', role: 'ADMIN', commission_percentage: 0 }];
const TODOS = [...SO_O_ADMIN, { id: 'u-op', name: 'Op', email: 'o@example.invalid', role: 'OPERATOR', commission_percentage: 0 }];

const servicos: Array<[string, () => Promise<unknown>]> = [
  ['lookupsService.listUsers', () => lookupsService.listUsers()],
  ['memberPayoutsService.fetchUsersMap', () => memberPayoutsService.fetchUsersMap()],
  ['campaignMembersService.listWithUserData', () => campaignMembersService.listWithUserData()],
  ['campaignCommissionsService.listWithUserData', () => campaignCommissionsService.listWithUserData()],
];

describe('aviso de admin sem papel ligado nos serviços', () => {
  beforeEach(() => {
    estado.users = SO_O_ADMIN;
    estado.contagemAdmins = 1;
    estado.alvo = { id: 'u-outro-admin', role: 'ADMIN' };
    estado.rpc = { data: false, error: null };
  });

  it.each(servicos)('%s rejeita quando só vem a linha de um ADMIN sem papel', async (_n, chamar) => {
    await expect(chamar()).rejects.toThrow(MENSAGEM_ADMIN_SEM_PAPEL);
  });

  it.each(servicos)('%s rejeita quando a confirmação do papel falha', async (_n, chamar) => {
    estado.rpc = { data: null, error: { message: 'função ausente' } };
    await expect(chamar()).rejects.toThrow(MENSAGEM_PAPEL_INDETERMINADO);
  });

  it.each(servicos)('%s segue normal com a lista completa', async (_n, chamar) => {
    estado.users = TODOS;
    await expect(chamar()).resolves.toBeDefined();
  });

  it('v6OperationsService.deleteUser não diz "último administrador" quando a contagem é só o que a RLS deixou ver', async () => {
    await expect(v6OperationsService.deleteUser('u-outro-admin', 'u-admin')).rejects.toThrow(MENSAGEM_ADMIN_SEM_PAPEL);
  });

  it('v6OperationsService.deleteUser mantém "último administrador" quando o banco confirma o papel', async () => {
    estado.rpc = { data: true, error: null };
    await expect(v6OperationsService.deleteUser('u-outro-admin', 'u-admin')).rejects.toThrow(/último administrador/);
  });
});
