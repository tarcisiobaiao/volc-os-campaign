// @vitest-environment jsdom
/**
 * A leitura real Meta: os seis estados, a página que se declara página, e a
 * ausência que continua ausência.
 *
 * ⚠️ O QUE ESTES TESTES EXISTEM PARA IMPEDIR.
 *
 * `read_model.py` responde `ok: true` para "o Supabase caiu", "as tabelas não
 * existem" e "esta conta não é da casa". Um cliente que só olhasse `items`
 * transformaria as três em UMA lista vazia — a única leitura que o servidor
 * nunca fez. Cada caso abaixo falha contra essa versão, porque cada um exige
 * que a frase daquele estado esteja na tela.
 */
import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  MetaCampaignReadView,
  MetaCatalogoReal,
  comoNumero,
  dinheiroMeta,
  frescorDaConta,
} from '@/components/trafego/meta/MetaCampaignReadView';

const { api } = vi.hoisted(() => ({
  api: {
    contasMetaReadModel: vi.fn(),
    inventarioMetaReadModel: vi.fn(),
    detalheMetaReadModel: vi.fn(),
    financeiroMeta: vi.fn(),
  },
}));

vi.mock('@/lib/pautadorApi', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/pautadorApi')>()),
  pautadorApi: api,
}));

vi.mock('@/components/layout/Layout', () => ({
  Layout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const CONTA = {
  cofre_ativo_id: 'meta_account_h1',
  conta_ref: 'meta-account:h1',
  id_mascarado: '••••1426',
  nome_observado: 'Conta Foco Genial',
  moeda: 'BRL',
  timezone_name: 'America/Sao_Paulo',
  account_status: '1',
  readiness_state: 'READY_FOR_READ',
  observado_em: '2026-09-07T09:00:00Z',
  ultima_leitura_ok_em: '2026-09-07T09:00:00Z',
};

const contas = (extra: Record<string, unknown> = {}) => ({
  ok: true as const,
  has_snapshot: true,
  estado: 'COM_SNAPSHOT' as const,
  contas: [CONTA],
  ...extra,
});

const pagina = (
  entidade: string,
  items: Array<Record<string, unknown>>,
  extra: Record<string, unknown> = {},
) => ({
  ok: true as const,
  has_snapshot: items.length > 0,
  estado: (items.length > 0 ? 'COM_SNAPSHOT' : 'SEM_SNAPSHOT') as never,
  entidade,
  conta_ref: CONTA.conta_ref,
  moeda: 'BRL',
  fuso: 'America/Sao_Paulo',
  frescor: '2026-09-07T09:00:00Z',
  items,
  completo: true,
  has_more: false,
  proximo_cursor: null,
  motivo: null,
  ...extra,
});

const CAMPANHA = {
  meta_campaign_id: 'c-uuid-1',
  ad_account_ativo_id: 'meta_account_h1',
  entity_ref: 'metaobj_campanha_1',
  id_mascarado: '••••7781',
  nome: 'Encceja · leitura real',
  status: 'ACTIVE',
  effective_status: 'ACTIVE',
  objetivo: 'OUTCOME_TRAFFIC',
  observado_em: '2026-09-07T09:00:00Z',
};

const CONJUNTO = {
  meta_adset_id: 'a-uuid-1',
  meta_campaign_id: 'c-uuid-1',
  entity_ref: 'metaobj_conjunto_1',
  id_mascarado: '••••3312',
  nome: 'Brasil · amplo',
  effective_status: 'CAMPAIGN_PAUSED',
  optimization_goal: 'LANDING_PAGE_VIEWS',
};

const ANUNCIO = {
  meta_ad_id: 'ad-uuid-1',
  meta_adset_id: 'a-uuid-1',
  entity_ref: 'metaobj_anuncio_1',
  id_mascarado: '••••4420',
  nome: 'Certificado · imagem A',
  effective_status: 'ACTIVE',
};

const CRIATIVO = {
  meta_creative_id: 'cr-uuid-1',
  entity_ref: 'metaobj_criativo_1',
  nome:
    'Peça com um nome absurdamente longo que precisa quebrar em vez de estourar a coluna da tabela e forçar rolagem lateral da página inteira',
  object_story_id: 'https://exemplo.com.br/uma/url/muito/longa/que/nao/pode/estourar/o/layout?utm_source=meta',
};

const VINCULO = { meta_ad_id: 'ad-uuid-1', meta_creative_id: 'cr-uuid-1' };

/** O roteador por entidade — cada teste só sobrescreve o que lhe interessa. */
function responderPorEntidade(mapa: Record<string, unknown>) {
  api.inventarioMetaReadModel.mockImplementation((entidade: string) =>
    Promise.resolve(mapa[entidade] ?? pagina(entidade, [])),
  );
}

beforeEach(() => {
  api.financeiroMeta.mockResolvedValue({ ok: true, estado: 'SEM_SNAPSHOT', spend: null, revenue: null, profit_gross: null, retorno_excedente_pct: null, currency: 'BRL', impedimentos: [] });
  api.contasMetaReadModel.mockReset().mockResolvedValue(contas());
  api.detalheMetaReadModel.mockReset().mockResolvedValue({
    ok: true,
    has_snapshot: true,
    estado: 'COM_SNAPSHOT',
    entidade: 'campanhas',
    item: CAMPANHA,
    conta_ref: CONTA.conta_ref,
  });
  api.inventarioMetaReadModel.mockReset();
  responderPorEntidade({
    conjuntos: pagina('conjuntos', [CONJUNTO]),
    anuncios: pagina('anuncios', [ANUNCIO]),
    criativos: pagina('criativos', [CRIATIVO]),
    vinculos: pagina('vinculos', [VINCULO]),
    insights: pagina('insights', []),
  });
});

afterEach(cleanup);

const montar = (referencia = 'metaobj_campanha_1') =>
  render(
    <MemoryRouter>
      <MetaCampaignReadView referencia={referencia} contaRef={CONTA.conta_ref} />
    </MemoryRouter>,
  );

describe('MetaCampaignReadView — a hierarquia real', () => {
  it('liga os quatro cards ao financeiro do servidor e aplica o período', async () => {
    api.financeiroMeta.mockResolvedValue({ estado: 'COM_SNAPSHOT', currency: 'BRL',
      spend: 10, revenue: 25, profit_gross: 15, retorno_excedente_pct: 150,
      periodo_inicio: '2026-09-06', periodo_fim: '2026-09-06', timezone: 'America/Sao_Paulo', impedimentos: [] });
    montar();
    await screen.findByText(dinheiroMeta(25, 'BRL'));
    expect(screen.getByText(dinheiroMeta(10, 'BRL'))).toBeTruthy();
    expect(screen.getByText(dinheiroMeta(15, 'BRL'))).toBeTruthy();
    expect(screen.getByText('150,00%')).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Início do período financeiro'), { target: { value: '2026-09-01' } });
    fireEvent.change(screen.getByLabelText('Fim do período financeiro'), { target: { value: '2026-09-06' } });
    fireEvent.click(screen.getByRole('button', { name: 'Aplicar período' }));
    await waitFor(() => expect(api.financeiroMeta).toHaveBeenLastCalledWith('metaobj_campanha_1', CONTA.conta_ref, '2026-09-01', '2026-09-06'));
  });

  it('remove valores da campanha anterior enquanto a próxima está em leitura', async () => {
    api.financeiroMeta.mockResolvedValueOnce({ currency: 'BRL', spend: 10, revenue: 25, profit_gross: 15, retorno_excedente_pct: 150, impedimentos: [] });
    const tela = montar();
    await screen.findByText(dinheiroMeta(25, 'BRL'));
    api.financeiroMeta.mockReturnValue(new Promise(() => {}));
    tela.rerender(<MemoryRouter><MetaCampaignReadView referencia="metaobj_outra" contaRef={CONTA.conta_ref} /></MemoryRouter>);
    expect(screen.queryByText(dinheiroMeta(25, 'BRL'))).toBeNull();
  });

  it('lê campanha → conjunto → anúncio → peça e nunca importa o cenário fictício', async () => {
    montar();

    expect(await screen.findByText('Encceja · leitura real')).toBeTruthy();
    expect(screen.getByText('Brasil · amplo')).toBeTruthy();
    expect(screen.getByText('Certificado · imagem A')).toBeTruthy();
    expect(screen.getByText(CRIATIVO.nome)).toBeTruthy();
    expect(screen.getByText(CRIATIVO.object_story_id)).toBeTruthy();

    // ⚠️ Nome livre e URL longos NÃO podem estourar a página.
    //
    // A largura mora no contêiner da tabela, não no corpo: uma tabela larga
    // rola dentro da própria caixa. Sem isso, a página inteira ganha rolagem
    // lateral e o cabeçalho de conta sai da tela junto.
    const tabela = screen.getAllByRole('table')[0];
    expect(tabela.parentElement?.className).toContain('overflow-x-auto');
    expect(screen.getByText(CRIATIVO.nome).className).toContain('break-words');
    expect(screen.getByText(CRIATIVO.object_story_id).className).toContain('break-all');

    // Nenhum nome do dicionário demonstrativo pode aparecer numa leitura real.
    expect(screen.queryByText('Guia Encceja · Descoberta')).toBeNull();
    expect(screen.queryByText(/Cenário demonstrativo/i)).toBeNull();

    // O detalhe foi resolvido DENTRO da conta, com a referência recebida.
    expect(api.detalheMetaReadModel).toHaveBeenCalledWith(
      'campanhas',
      'metaobj_campanha_1',
      CONTA.conta_ref,
    );
  });

  it('resolve também o UUID persistido, não só o `metaobj_…` do recibo', async () => {
    montar('c-uuid-1');
    await screen.findByText('Encceja · leitura real');
    expect(api.detalheMetaReadModel).toHaveBeenCalledWith('campanhas', 'c-uuid-1', CONTA.conta_ref);
  });

  it('mostra moeda, fuso e frescor da resposta — e o estado da Meta como palavra', async () => {
    montar();
    await screen.findByText('Encceja · leitura real');

    expect(screen.getByText('BRL')).toBeTruthy();
    expect(screen.getByText('America/Sao_Paulo')).toBeTruthy();
    // `SeloDeFrescor` traduz o carimbo em palavra de operação.
    expect(screen.getAllByText(/leitura (recente|antiga)/i).length).toBeGreaterThan(0);
    // `CAMPAIGN_PAUSED` não existe no vocabulário do Google e precisa sair como
    // palavra da Meta, não como "estado não reconhecido".
    expect(screen.getByText('CAMPAIGN_PAUSED')).toBeTruthy();
  });

  it('métrica não medida aparece como AUSENTE, jamais como zero', async () => {
    montar();
    await screen.findByText('Encceja · leitura real');

    // Os quatro cartões da espinha econômica.
    for (const rotulo of ['Investimento Total', 'Revenue', 'Retorno excedente (%)', 'Lucro Bruto']) {
      expect(screen.getByText(rotulo)).toBeTruthy();
    }
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(4);
    expect(screen.queryByText('R$ 0,00')).toBeNull();
    expect(screen.queryByText('0,0%')).toBeNull();
    // E a tela DIZ por que não sabe, em vez de deixar quatro travessões mudos.
    // A frase carrega o GRÃO: receita é do conjunto, campanha é a soma deles.
    expect(screen.getByText(/GAM pelo conjunto/i)).toBeTruthy();
    // A frase do grão aparece em mais de um lugar de propósito: na explicação
    // do período e na nota do cartão de receita. O operador não deveria ter de
    // rolar a tela para descobrir de onde o número veio.
    expect(screen.getAllByText(/a campanha soma os conjuntos/i).length).toBeGreaterThanOrEqual(2);
  });

  it('a linha de insight sem medida vira travessão, e o gasto medido sai em BRL', async () => {
    responderPorEntidade({
      conjuntos: pagina('conjuntos', [CONJUNTO]),
      anuncios: pagina('anuncios', [ANUNCIO]),
      criativos: pagina('criativos', [CRIATIVO]),
      vinculos: pagina('vinculos', [VINCULO]),
      insights: pagina('insights', [
        {
          meta_insight_daily_id: 'i-1',
          nivel: 'campaign',
          periodo_inicio: '2026-09-01',
          periodo_fim: '2026-09-01',
          currency: 'BRL',
          spend: '684.20',
          impressions: 0,
          reach: null,
          inline_link_clicks: null,
          landing_page_views: null,
          ctr: null,
        },
      ]),
    });
    montar();

    expect(await screen.findByText('R$ 684,20')).toBeTruthy();
    // ⚠️ zero MEDIDO continua zero; `null` é que vira travessão.
    expect(screen.getByText('0')).toBeTruthy();
    expect(screen.getByText(/pertencem à conta/i)).toBeTruthy();
  });
});

describe('MetaCampaignReadView — os estados do servidor, como conteúdo', () => {
  it('SCHEMA_NAO_APLICADO diz que a persistência não está instalada', async () => {
    api.contasMetaReadModel.mockResolvedValue({
      ok: true,
      has_snapshot: false,
      estado: 'SCHEMA_NAO_APLICADO',
      contas: [],
      motivo: 'meta_schema_not_applied',
    });
    montar();
    expect(await screen.findByText(/persistência meta não instalada/i)).toBeTruthy();
    expect(screen.queryByText('Guia Encceja · Descoberta')).toBeNull();
  });

  it('SEM_CONEXAO vira falha nomeada, com código copiável, e não lista vazia', async () => {
    api.contasMetaReadModel.mockResolvedValue({
      ok: true,
      has_snapshot: false,
      estado: 'SEM_CONEXAO',
      contas: [],
      motivo: 'supabase_indisponivel',
    });
    montar();
    expect(await screen.findByText('Não consegui ler o inventário')).toBeTruthy();
    expect(screen.getByText('código da ocorrência')).toBeTruthy();
    expect(screen.getByText(/sem conexão com o registro/i)).toBeTruthy();
  });

  it('NAO_ENCONTRADO_NO_ESCOPO não vira demonstração nem tela em branco', async () => {
    api.detalheMetaReadModel.mockResolvedValue({
      ok: true,
      has_snapshot: false,
      estado: 'NAO_ENCONTRADO_NO_ESCOPO',
      entidade: 'campanhas',
      item: null,
      conta_ref: CONTA.conta_ref,
    });
    montar('campanha-descoberta-01');
    expect(await screen.findByText(/não pertence a esta conta/i)).toBeTruthy();
    // O identificador pedido é EXATAMENTE um id do cenário demonstrativo, e
    // mesmo assim nada de fictício aparece.
    expect(screen.queryByText('Guia Encceja · Descoberta')).toBeNull();
  });

  it('NAO_ENCONTRADO_ESCOPO_PARCIAL não afirma que o objeto não existe', async () => {
    api.detalheMetaReadModel.mockResolvedValue({
      ok: true,
      has_snapshot: false,
      estado: 'NAO_ENCONTRADO_ESCOPO_PARCIAL',
      entidade: 'campanhas',
      item: null,
      conta_ref: CONTA.conta_ref,
    });
    montar();
    expect(await screen.findByText(/a leitura foi parcial/i)).toBeTruthy();
    expect(screen.getByText(/não dá para afirmar que ela não existe aqui/i)).toBeTruthy();
  });

  it('uma falha de rede na leitura das contas é falha, não inventário vazio', async () => {
    api.contasMetaReadModel.mockRejectedValue(
      Object.assign(new Error('boom'), { status: 503 }),
    );
    montar();
    expect(await screen.findByText('Não consegui ler o inventário')).toBeTruthy();
    expect(screen.getByText('O registro de campanhas não respondeu.')).toBeTruthy();
    expect(screen.queryByText('Guia Encceja · Descoberta')).toBeNull();
  });

  it('nenhuma entidade é pedida antes de haver conta resolvida', async () => {
    api.contasMetaReadModel.mockResolvedValue({
      ok: true,
      has_snapshot: true,
      estado: 'COM_SNAPSHOT',
      contas: [CONTA, { ...CONTA, conta_ref: 'meta-account:h2', nome_observado: 'Outra conta' }],
    });
    render(
      <MemoryRouter>
        <MetaCampaignReadView referencia="metaobj_campanha_1" />
      </MemoryRouter>,
    );
    expect(await screen.findByText(/falta escolher a conta/i)).toBeTruthy();
    expect(api.inventarioMetaReadModel).not.toHaveBeenCalled();
    // Com duas contas, a escolha existe — e ela é o único caminho adiante.
    expect(screen.getByRole('button', { name: /Outra conta/ })).toBeTruthy();
  });
});

describe('MetaCampaignReadView — a página que se declara página', () => {
  it('`has_more` oferece a próxima página pelo cursor opaco e apenda o resultado', async () => {
    const primeira = pagina('conjuntos', [CONJUNTO], {
      completo: false,
      has_more: true,
      proximo_cursor: 'CURSOR-1',
    });
    const segunda = pagina('conjuntos', [
      { ...CONJUNTO, meta_adset_id: 'a-uuid-2', entity_ref: 'metaobj_conjunto_2', nome: 'Interesses' },
    ]);
    api.inventarioMetaReadModel.mockImplementation(
      (entidade: string, opcoes: { cursor?: string | null }) => {
        if (entidade !== 'conjuntos') return Promise.resolve(pagina(entidade, []));
        return Promise.resolve(opcoes?.cursor === 'CURSOR-1' ? segunda : primeira);
      },
    );
    montar();

    expect(await screen.findByText('Brasil · amplo')).toBeTruthy();
    expect(screen.getByText(/há mais linhas neste escopo/i)).toBeTruthy();
    // Leitura incompleta é dita como leitura parcial em DOIS lugares — no selo
    // de frescor da conta e no aviso — porque as duas perguntas são diferentes:
    // "posso confiar nesta conta agora?" e "o que faltou?".
    expect(screen.getAllByText(/Leitura parcial/i).length).toBeGreaterThanOrEqual(2);

    fireEvent.click(screen.getByRole('button', { name: 'ler próxima página' }));
    expect(await screen.findByText('Interesses')).toBeTruthy();
    expect(screen.getByText('Brasil · amplo')).toBeTruthy();
    await waitFor(() =>
      expect(api.inventarioMetaReadModel).toHaveBeenCalledWith('conjuntos', {
        contaRef: CONTA.conta_ref,
        cursor: 'CURSOR-1',
      }),
    );
  });

  it('`completo: false` sem próxima página ainda diz que aquilo não é o total', async () => {
    responderPorEntidade({
      conjuntos: pagina('conjuntos', [CONJUNTO], {
        completo: false,
        motivo: 'ESCOPO_PAI_TRUNCADO',
      }),
      anuncios: pagina('anuncios', [ANUNCIO]),
      criativos: pagina('criativos', [CRIATIVO]),
      vinculos: pagina('vinculos', [VINCULO]),
      insights: pagina('insights', []),
    });
    montar();
    expect(await screen.findByText(/passou do teto que o servidor resolve de uma vez/i)).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'ler próxima página' })).toBeNull();
  });
});

describe('MetaCampaignReadView — o que NÃO existe nesta tela', () => {
  it('não há controle de ativar, editar, pausar nem orçamento', async () => {
    montar();
    await screen.findByText('Encceja · leitura real');
    for (const proibido of [/ativar/i, /editar/i, /pausar/i, /orçamento/i, /duplicar/i]) {
      expect(screen.queryByRole('button', { name: proibido })).toBeNull();
    }
  });
});

describe('MetaCatalogoReal', () => {
  it('lista as campanhas reais em TABELA e liga cada uma à sua leitura real', async () => {
    responderPorEntidade({ campanhas: pagina('campanhas', [CAMPANHA]) });
    render(
      <MemoryRouter>
        <MetaCatalogoReal contaRef={CONTA.conta_ref} />
      </MemoryRouter>,
    );

    const link = await screen.findByRole('link', { name: 'Encceja · leitura real' });
    expect(link.getAttribute('href')).toBe(
      '/dashboard/campaign/metaobj_campanha_1?rede=meta&conta=meta-account%3Ah1',
    );
    // A rota de destino NÃO carrega `modo=demo`.
    expect(link.getAttribute('href')).not.toContain('modo=demo');
    expect(screen.getByRole('table')).toBeTruthy();
    expect(screen.getByRole('columnheader', { name: 'Campanha' })).toBeTruthy();
  });

  it('sem snapshot, o catálogo diz "ainda não sincronizado" — e não mostra demonstração', async () => {
    responderPorEntidade({ campanhas: pagina('campanhas', []) });
    render(
      <MemoryRouter>
        <MetaCatalogoReal contaRef={CONTA.conta_ref} />
      </MemoryRouter>,
    );
    expect(await screen.findByText(/ainda não sincronizado/i)).toBeTruthy();
    expect(screen.queryByText('Guia Encceja · Descoberta')).toBeNull();
  });
});

describe('as regras de formato, sem DOM', () => {
  it('`spend` da Meta é moeda, não micros', () => {
    // ⚠️ `dinheiro()` do inventário recebe MICROS porque o Google guarda assim.
    // Se alguém passar o `spend` da Meta direto por lá, R$ 684,20 vira R$ 0,00.
    expect(dinheiroMeta('684.20', 'BRL')).toContain('684,20');
    expect(dinheiroMeta(0, 'BRL')).toContain('0,00');
  });

  it('ausência é travessão em todas as suas formas, e zero sobrevive', () => {
    expect(dinheiroMeta(null, 'BRL')).toBe('—');
    expect(dinheiroMeta('', 'BRL')).toBe('—');
    expect(dinheiroMeta('não é número', 'BRL')).toBe('—');
    expect(comoNumero(0)).toBe(0);
    expect(comoNumero(null)).toBeNull();
  });

  it('moeda não declarada é dita, nunca assumida como real', () => {
    expect(dinheiroMeta('10', null)).toContain('sem moeda declarada');
  });

  it('conta sem carimbo de leitura é `nunca_lido`, jamais `recente`', () => {
    expect(frescorDaConta(null, false).frescor).toBe('nunca_lido');
    expect(frescorDaConta({ ultima_leitura_ok_em: null }, false).frescor).toBe('nunca_lido');
    expect(
      frescorDaConta({ ultima_leitura_ok_em: new Date().toISOString() }, false).frescor,
    ).toBe('recente');
    expect(
      frescorDaConta({ ultima_leitura_ok_em: '2020-01-01T00:00:00Z' }, false).frescor,
    ).toBe('velho');
    // Leitura incompleta não pode ser anunciada como recente.
    expect(
      frescorDaConta({ ultima_leitura_ok_em: new Date().toISOString() }, true).frescor,
    ).toBe('parcial');
  });
});

// ═══════════════════════════════════════════════════════════════════════════
// ESCOPO PEDIDO E DESCONHECIDO ≠ ESCOPO NÃO PEDIDO
// ═══════════════════════════════════════════════════════════════════════════

describe('uma conta que o snapshot não conhece', () => {
  beforeEach(() => {
    api.contasMetaReadModel.mockReset().mockResolvedValue(contas());
    api.inventarioMetaReadModel.mockReset().mockResolvedValue(pagina('campanhas', []));
    api.detalheMetaReadModel.mockReset().mockResolvedValue({
      ok: true, has_snapshot: false, estado: 'NAO_ENCONTRADO_NO_ESCOPO',
      entidade: 'campanhas', item: null, conta_ref: CONTA.conta_ref,
    });
  });

  it('NÃO é silenciosamente trocada pela única conta persistida', async () => {
    // Havia exatamente uma conta persistida e a URL pedia outra. A queda para
    // "a única" mostrava os números da conta A com a URL dizendo outra coisa —
    // o operador leria gasto e resultado da conta errada sem nada discordando.
    render(
      <MemoryRouter>
        <MetaCatalogoReal contaRef="meta-account:conta-que-nao-existe" />
      </MemoryRouter>,
    );
    await waitFor(() => expect(api.contasMetaReadModel).toHaveBeenCalled());

    // Nenhuma leitura escopada pode ter acontecido: não há escopo resolvido.
    expect(api.inventarioMetaReadModel).not.toHaveBeenCalled();
    // O cabeçalho da conta, que só existe quando há escopo resolvido, não pode
    // aparecer: ele é o que faria os números parecerem "desta conta".
    expect(screen.queryByText('conta de anúncios')).toBeNull();
  });

  it('diz que não reconheceu a conta, e oferece a que reconhece', async () => {
    render(
      <MemoryRouter>
        <MetaCatalogoReal contaRef="meta-account:conta-que-nao-existe" />
      </MemoryRouter>,
    );
    // A escolha aparece MESMO com uma conta só: sem ela a tela seria um beco
    // sem saída — diz que não reconheceu e não oferece nenhuma que reconheça.
    await waitFor(() => expect(screen.getByText('conta lida')).toBeTruthy());
    const botoes = screen.getAllByRole('button');
    expect(botoes.some((b) => (b.textContent ?? '').includes(CONTA.id_mascarado!))).toBe(true);
  });

  it('quando NINGUÉM pediu conta, a única continua sendo assumida', async () => {
    render(
      <MemoryRouter>
        <MetaCatalogoReal />
      </MemoryRouter>,
    );
    await waitFor(() => expect(api.inventarioMetaReadModel).toHaveBeenCalled());
    const escopo = api.inventarioMetaReadModel.mock.calls[0][1];
    expect(escopo).toMatchObject({ contaRef: CONTA.conta_ref });
  });
});
