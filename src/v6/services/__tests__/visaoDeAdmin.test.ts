import { beforeEach, describe, expect, it, vi } from 'vitest';

const rpc = vi.fn();
vi.mock('@/lib/supabase', () => ({ supabase: { rpc: (...a: unknown[]) => rpc(...a) } }));

import {
  MENSAGEM_ADMIN_SEM_PAPEL,
  MENSAGEM_PAPEL_INDETERMINADO,
  MENSAGEM_SEM_PERFIL,
  garantirContagemDeAdminsConfiavel,
  garantirListaCompletaDeUsuarios,
} from '@/v6/services/visaoDeAdmin';

describe('visão de admin depois da v8_03', () => {
  beforeEach(() => rpc.mockReset());

  it('ADMIN do cadastro sem papel no banco vendo só a própria linha: erro explícito', async () => {
    rpc.mockResolvedValue({ data: false, error: null });
    await expect(garantirListaCompletaDeUsuarios([{ role: 'ADMIN' }])).rejects.toThrow(MENSAGEM_ADMIN_SEM_PAPEL);
    expect(rpc).toHaveBeenCalledWith('volc_current_admin');
  });

  it('ADMIN reconhecido pelo banco com uma linha só (sistema de 1 usuário): segue', async () => {
    rpc.mockResolvedValue({ data: true, error: null });
    await expect(garantirListaCompletaDeUsuarios([{ role: 'ADMIN' }])).resolves.toBeUndefined();
  });

  it('operador vendo só a própria linha é o esperado: não consulta nem lança', async () => {
    await expect(garantirListaCompletaDeUsuarios([{ role: 'OPERATOR' }])).resolves.toBeUndefined();
    expect(rpc).not.toHaveBeenCalled();
  });

  it('lista com várias linhas (antes da v8_03, ou admin reconhecido): não consulta', async () => {
    await expect(garantirListaCompletaDeUsuarios([{ role: 'ADMIN' }, { role: 'OPERATOR' }])).resolves.toBeUndefined();
    expect(rpc).not.toHaveBeenCalled();
  });

  it('contagem de 1 admin sem papel no banco vira erro de papel, não "último administrador"', async () => {
    rpc.mockResolvedValue({ data: false, error: null });
    await expect(garantirContagemDeAdminsConfiavel(1)).rejects.toThrow(MENSAGEM_ADMIN_SEM_PAPEL);
  });

  it('se a confirmação do papel falha, a lista não passa como confiável', async () => {
    rpc.mockResolvedValue({ data: null, error: { message: 'x' } });
    await expect(garantirListaCompletaDeUsuarios([{ role: 'ADMIN' }])).rejects.toThrow(MENSAGEM_PAPEL_INDETERMINADO);
  });

  it('lista vazia de quem o banco não reconhece como ADMIN: erro de perfil', async () => {
    rpc.mockResolvedValue({ data: false, error: null });
    await expect(garantirListaCompletaDeUsuarios([])).rejects.toThrow(MENSAGEM_SEM_PERFIL);
  });
});
