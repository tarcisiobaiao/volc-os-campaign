// @vitest-environment jsdom
/**
 * A prova precisa dizer QUEM reprovou e POR QUÊ — e não pode dar verde a um
 * juiz que não rodou.
 *
 * ⚠️ Os dois defeitos que estes testes trancam foram vistos juntos, na mesma
 * tela, no card 65 em 19/08/2026:
 *
 *     prova    0 operações · nada foi criado
 *       FORMA  reprovou   0 achado(s)
 *       GOOGLE passou     o payload passou
 *
 * As duas linhas mentiam, de formas diferentes.
 *
 * 1. `recusa_local` chega do backend como TEXTO — `volc_ads/subir.py` monta a
 *    string com `Resultado.resumo()` —, então `achados` é SEMPRE vazio. "0
 *    achado(s)" é veredito de reprovação sem uma linha do que consertar. O
 *    motivo real estava em `resumo`: "Exige certificacao_servicos_oficiais
 *    (política 15332527)". A tela não o lia.
 *
 * 2. `falha_validacao` é `null` em DOIS casos opostos: o Google aprovou, ou a
 *    prova parou antes e ele nunca foi chamado. Com ZERO operações não havia
 *    payload para validar — e a tela pintou de verde um juiz que não rodou.
 *    Verde falso no juiz mais caro é pior que vermelho: convida a subir.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';

import type { EstadoDaTrava, PedidoDeProvaSearch } from '@/types/trafego';

const { provarCampanha, subirCampanha, ErroFalso } = vi.hoisted(() => ({
  provarCampanha: vi.fn(),
  subirCampanha: vi.fn(),
  ErroFalso: class extends Error {
    status: number;
    constructor(msg: string, status: number) { super(msg); this.status = status; }
  },
}));

vi.mock('@/lib/pautadorApi', () => ({
  pautadorApi: { provarCampanha, subirCampanha },
  PautadorApiError: ErroFalso,
}));

import { Lancamento } from '../Lancamento';
import { leituraDoDestinoPago } from '@/lib/landing-policy/prontidao';
import { portadorApto } from '@/lib/landing-policy/__tests__/recibos';

const PEDIDO: PedidoDeProvaSearch = {
  opportunity_id: 65, run_id: 9, customer_id: '5478096539',
  login_customer_id: '6016739364',
  grupos: [{ tipo: 'SAQUE', keywords: ['consultar fgts'] }],
  budget_diario: 20, cpc_inicial: 1.0, match_type: 'PHRASE',
};
const FECHADA: EstadoDaTrava = {
  escrita_permitida: false, destravado_no_codigo: false, env_presente: false,
  motivo: '', explicacao: 'A trava é de dois fatores, de propósito.',
};

const AUTORIZACAO = {
  plano_impressao: 'f'.repeat(64), chave_intencao: 'e'.repeat(64),
  carimbo_nome: '20260828_120000',
  alvo_canario: true, elegivel: true,
  motivo_elegibilidade: 'pedido dentro da política estreita do canário',
  politica: {
    customer_id: '5478096539', customer_id_formatado: '547-809-6539',
    customer_label: 'Portal Mundo Mais', login_customer_id: '6016739364',
    canal: 'SEARCH', cria_pausada: true, inclui_ativacao: false,
    orcamento_diario_maximo_brl: '20.00', cpc_maximo_brl: '1.00',
  },
  budget_diario: 20, cpc_inicial: 1, ativacao_incluida: false,
} as const;

/** O desfecho REAL do card 65: `construir()` parou antes de montar operação. */
const REPROVOU_ANTES_DO_GOOGLE = {
  preparo: {
    aprovado: false, n_operacoes: 0, selo: null, falha_validacao: null,
    recusa_local: {
      ok: false, achados: [],
      resumo: '  [erro] conta: Exige certificacao_servicos_oficiais '
            + "(política 15332527) — Nichos RG, CPF, CNH.  →  'governo_documentos@BR'",
    },
  },
  avisos: [], grupos: [], autorizacao: AUTORIZACAO,
};

const APROVADO = {
  preparo: {
    aprovado: true, n_operacoes: 72, recusa_local: { ok: true, achados: [] },
    falha_validacao: null, selo: { impressao: 'ab12cd', n_operacoes: 72 },
  },
  avisos: [], grupos: [], autorizacao: AUTORIZACAO,
};

const renderizar = () =>
  render(<Lancamento pedido={PEDIDO} trava={FECHADA} titulo="FGTS Saque-Aniversário"
                     resumoDaCopy="15 títulos · 4 descrições" destino={DESTINO_APTO}
                     onFechar={() => {}} />);

/** ⚠️ O degrau do destino nasceu nesta sprint e a escada PARA nele quando o
 *  destino não está apto — por isso estes testes, que são sobre a prova e a
 *  escrita, precisam de um destino que passa. O caso do destino reprovado tem
 *  teste próprio em `lib/landing-policy/__tests__/prontidao.test.ts`. */
const DESTINO_APTO = leituraDoDestinoPago(portadorApto(), {
  agora_epoch: 1_756_900_000, status_wp: 'publish',
});

afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe('a prova diz a verdade sobre cada juiz', () => {
  it('recusa sem achados mostra o MOTIVO, não um zero', async () => {
    provarCampanha.mockResolvedValue(REPROVOU_ANTES_DO_GOOGLE);
    const { container } = renderizar();

    await waitFor(() =>
      expect(container.textContent).toContain('certificacao_servicos_oficiais'));
    expect(container.textContent).toContain('15332527');
    expect(container.textContent).not.toContain('0 achado(s)');
  });

  it('google NÃO aparece como aprovado quando não foi chamado', async () => {
    provarCampanha.mockResolvedValue(REPROVOU_ANTES_DO_GOOGLE);
    const { container } = renderizar();

    await waitFor(() => expect(screen.getByText('google')).toBeTruthy());
    expect(container.textContent).toContain('não foi consultado');
    expect(container.textContent).not.toContain('o payload passou');
  });

  it('com payload de verdade, google aprovado continua aprovado', async () => {
    provarCampanha.mockResolvedValue(APROVADO);
    const { container } = renderizar();

    await waitFor(() => expect(container.textContent).toContain('o payload passou'));
    expect(container.textContent).not.toContain('não foi consultado');
  });
});

// ── a autocorreção precisa aparecer, sobretudo quando dá certo ─────────────

const CORRIGIDO_E_APROVADO = {
  preparo: {
    aprovado: true, n_operacoes: 113,
    recusa_local: null, falha_validacao: null,
    selo: { impressao: 'x', n_operacoes: 113 },
    autocorrecao: [
      "✓ NON_FAMILY_SAFE sobre 'como sacar o fgts na caixa': isenção pedida",
      "✂ PERSONAL_LOANS sobre 'saldo bloqueado fgts empréstimo': removida",
      '→ revalidado: passou',
    ],
  },
  avisos: [], grupos: [], autorizacao: AUTORIZACAO,
};

describe('a autocorreção de política é visível', () => {
  it('mostra o que foi removido e o que foi isentado, mesmo com a prova APROVADA', async () => {
    provarCampanha.mockResolvedValue(CORRIGIDO_E_APROVADO);
    const { container } = renderizar();

    await waitFor(() => expect(container.textContent).toContain('NON_FAMILY_SAFE'));
    expect(container.textContent).toContain('isenção pedida');
    expect(container.textContent).toContain('PERSONAL_LOANS');
    expect(container.textContent).toContain('removida');
  });

  it('prova sem autocorreção não inventa aviso nenhum', async () => {
    provarCampanha.mockResolvedValue(APROVADO);
    const { container } = renderizar();

    await waitFor(() => expect(container.textContent).toContain('o payload passou'));
    expect(container.textContent).not.toContain('isenção pedida');
  });
});
