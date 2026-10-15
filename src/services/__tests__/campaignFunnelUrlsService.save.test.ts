import { beforeEach, describe, expect, it, vi } from 'vitest';

// Banco falso de campaign_funnel_urls com a regra da v19_10 para o operador:
// gravar ou reativar URL fora do domínio do projeto → 42501; desativar sempre pode.
type Linha = { campaign_id: string; url: string; Active: boolean };
let tabela: Linha[] = [];
const chamadas: string[] = [];
const rpc = vi.fn();
const noDominio = (url: string) => url.startsWith('p1.example');
const recusa = { code: '42501', message: 'new row violates row-level security policy' };

function consulta(acao: 'select' | 'update' | 'insert', valores?: Partial<Linha>) {
  const filtros: Array<[keyof Linha, unknown]> = [];
  const q = {
    eq(col: keyof Linha, v: unknown) { filtros.push([col, v]); return q; },
    order() { return q; },
    then(ok: (r: unknown) => unknown, falha?: (e: unknown) => unknown) {
      return Promise.resolve(executar()).then(ok, falha);
    },
  };
  const casa = (l: Linha) => filtros.every(([c, v]) => l[c] === v);
  function executar() {
    chamadas.push(acao);
    if (acao === 'select') return { data: tabela.filter(casa).map(l => ({ ...l })), error: null };
    if (acao === 'insert') {
      const nova = { ...(valores as Linha) };
      if (!noDominio(nova.url)) return { data: null, error: recusa };
      tabela.push(nova);
      return { data: null, error: null };
    }
    const alvo = tabela.filter(casa);
    if (valores?.Active === true && alvo.some(l => !l.Active && !noDominio(l.url))) return { data: null, error: recusa };
    alvo.forEach(l => Object.assign(l, { Active: valores?.Active ?? l.Active }));
    return { data: null, error: null };
  }
  return q;
}

vi.mock('@/lib/supabase', () => ({
  supabase: {
    rpc: (...a: unknown[]) => rpc(...a),
    from: () => ({
      select: () => consulta('select'),
      update: (v: Partial<Linha>) => consulta('update', v),
      insert: (v: Partial<Linha>) => consulta('insert', v),
    }),
  },
}));

import { campaignFunnelUrlsService, limparUrlFunil } from '../campaignFunnelUrlsService';

const C = '123456789';
const entrada = (urls: string[]) => urls.map(url => ({ campaign_id: C, url, Active: true }));
const ativas = () => tabela.filter(l => l.Active).map(l => l.url).sort();

beforeEach(() => {
  rpc.mockReset();
  chamadas.length = 0;
  // cenário do revisor: histórica de subdomínio ativa + uma válida ativa
  tabela = [
    { campaign_id: C, url: 'blog.p1.example/old', Active: true },
    { campaign_id: C, url: 'p1.example/a', Active: true },
    { campaign_id: C, url: 'outro.example/inativa', Active: false },
  ];
});

describe('saveFunnelUrls — uma chamada atômica (RPC volc_salvar_funil)', () => {
  it('manda a lista inteira numa só RPC e não faz nenhuma escrita direta', async () => {
    rpc.mockResolvedValue({ data: [], error: null });
    await campaignFunnelUrlsService.saveFunnelUrls(C, entrada(['blog.p1.example/old', 'p1.example/a', 'p1.example/b']));
    expect(rpc).toHaveBeenCalledWith('volc_salvar_funil', {
      p_campaign_id: C, p_urls: ['blog.p1.example/old', 'p1.example/a', 'p1.example/b'],
    });
    expect(chamadas).toEqual([]);
  });

  it('se o banco recusa, propaga o erro sem desativar nada pelo front (antes: desativava tudo e depois falhava)', async () => {
    rpc.mockResolvedValue({ data: null, error: recusa });
    await expect(campaignFunnelUrlsService.saveFunnelUrls(C, entrada(['outro.example/inativa']))).rejects.toEqual(recusa);
    expect(chamadas).toEqual([]);
    expect(ativas()).toEqual(['blog.p1.example/old', 'p1.example/a']);
  });
});

describe('saveFunnelUrls — banco ainda sem a RPC (só o que mudou, grava antes de desativar)', () => {
  beforeEach(() => rpc.mockResolvedValue({ data: null, error: { code: 'PGRST202', message: 'function not found' } }));

  it('histórica divergente reenviada sem mudança não é tocada; as ativas válidas ficam e a nova entra', async () => {
    await campaignFunnelUrlsService.saveFunnelUrls(C, entrada(['https://www.blog.p1.example/old/', 'p1.example/a', 'p1.example/b']));
    expect(ativas()).toEqual(['blog.p1.example/old', 'p1.example/a', 'p1.example/b']);
    expect(chamadas.filter(c => c === 'update')).toEqual([]);
  });

  it('URL que saiu da lista é desativada, inclusive a histórica divergente', async () => {
    await campaignFunnelUrlsService.saveFunnelUrls(C, entrada(['p1.example/a']));
    expect(ativas()).toEqual(['p1.example/a']);
  });

  it('reativar a divergente falha ANTES de desativar qualquer coisa: as ativas não diminuem', async () => {
    await expect(campaignFunnelUrlsService.saveFunnelUrls(C, entrada(['outro.example/inativa']))).rejects.toEqual(recusa);
    expect(ativas()).toEqual(['blog.p1.example/old', 'p1.example/a']);
  });
});

describe('cenário do revisor — algoritmo antigo (2 requisições) contra o mesmo banco', () => {
  it('desativava tudo, o upsert falhava na divergente e a campanha ficava com ZERO ativas', async () => {
    const { supabase } = await import('@/lib/supabase');
    await supabase.from('campaign_funnel_urls').update({ Active: false }).eq('campaign_id', C);
    const r = await supabase.from('campaign_funnel_urls').insert({ campaign_id: C, url: 'outro.example/inativa', Active: true });
    expect(r.error).toEqual(recusa);
    expect(ativas()).toEqual([]);
  });
});

describe('limparUrlFunil', () => {
  it('espelha public.clean_funnel_url', () => {
    expect(limparUrlFunil('  HTTPS://www.p1.example/x//  ')).toBe('p1.example/x');
    expect(limparUrlFunil('http://WWW.p1.example')).toBe('p1.example');
  });
});
