// @vitest-environment jsdom
/**
 * A escada de lançamento.
 *
 * ⚠️ ESTE É O ÚNICO LUGAR ONDE O CAMINHO DE ESCRITA É EXERCITADO.
 *
 * `volc_ads/subir.py` nunca rodou com a trava aberta — por instrução, desde o
 * início. Com dublê dá para provar o que a TELA faz em cada desfecho: que ela
 * não chama `/subir` com a trava fechada, que ela exige motivo, e que ela sabe
 * ler o preparo que vem dentro do 409. O que nenhum teste aqui prova é o que a
 * API do Google faz — isso só o primeiro disparo real dirá.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';

import type { EstadoDaTrava, PedidoDeProvaSearch } from '@/types/trafego';

// Tudo que a fábrica de `vi.mock` usa precisa nascer aqui: a chamada sobe para
// o topo do arquivo, e um `const`/`class` comum ainda não existe quando ela roda.
const { provarCampanha, subirCampanha, ErroFalso } = vi.hoisted(() => ({
  provarCampanha: vi.fn(),
  subirCampanha: vi.fn(),
  ErroFalso: class extends Error {
    status: number;
    corpo?: unknown;
    constructor(msg: string, status: number, corpo?: unknown) {
      super(msg);
      this.status = status;
      this.corpo = corpo;
    }
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
  opportunity_id: 73, run_id: 6, customer_id: '5478096539',
  login_customer_id: '6016739364', grupos: [{ tipo: 'ACESSO', keywords: ['banco pan telefone'] }],
  budget_diario: 10, cpc_inicial: 0.12, match_type: 'PHRASE',
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
  budget_diario: 10, cpc_inicial: 0.12, ativacao_incluida: false,
} as const;

const FECHADA: EstadoDaTrava = {
  escrita_permitida: false, destravado_no_codigo: false, env_presente: false,
  motivo: '', explicacao: 'A trava é de dois fatores, de propósito.',
};
const ABERTA: EstadoDaTrava = { ...FECHADA, escrita_permitida: true, env_presente: true };

const APROVADO = {
  preparo: {
    aprovado: true, n_operacoes: 72, recusa_local: { ok: true, achados: [] },
    falha_validacao: null, selo: { impressao: 'ab12cd', n_operacoes: 72 },
  },
  avisos: [], grupos: [], autorizacao: AUTORIZACAO,
};

const REPROVADO = {
  preparo: {
    aprovado: false, n_operacoes: 72,
    recusa_local: { ok: false, achados: [{ campo: 'headline[3]', motivo: 'passa de 30 caracteres' }] },
    falha_validacao: null, selo: null,
  },
  avisos: [], grupos: [], autorizacao: AUTORIZACAO,
};

const renderizar = (trava: EstadoDaTrava) =>
  render(<Lancamento pedido={PEDIDO} trava={trava} titulo="Cartão para Negativado"
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

describe('Lancamento', () => {
  it('roda a prova ao abrir e mostra os dois juízes', async () => {
    provarCampanha.mockResolvedValue(APROVADO);
    renderizar(FECHADA);
    await waitFor(() => expect(screen.getByText('72 operações · nada foi criado')).toBeTruthy());
    expect(screen.getByText('forma')).toBeTruthy();
    expect(screen.getByText('google')).toBeTruthy();
    expect(provarCampanha).toHaveBeenCalledTimes(1);
  });

  it('com a trava fechada NÃO chama /subir, e diz por quê', async () => {
    provarCampanha.mockResolvedValue(APROVADO);
    renderizar(FECHADA);
    await waitFor(() =>
      expect(screen.getByText(/A trava de escrita está fechada/)).toBeTruthy());
    expect(screen.getByText('trava de escrita fechada')).toBeTruthy();
    expect(subirCampanha).not.toHaveBeenCalled();
  });

  it('prova reprovada para a escada e nomeia o achado', async () => {
    provarCampanha.mockResolvedValue(REPROVADO);
    renderizar(ABERTA);
    await waitFor(() => expect(screen.getByText('Nada foi enviado.')).toBeTruthy());
    expect(screen.getByText('headline[3]')).toBeTruthy();
    expect(screen.getByText(/passa de 30 caracteres/)).toBeTruthy();
    expect(subirCampanha).not.toHaveBeenCalled();
  });

  it('com a trava aberta exige motivo de 10+ caracteres e escreve com ele', async () => {
    provarCampanha.mockResolvedValue(APROVADO);
    subirCampanha.mockResolvedValue({
      recibo: { nome_campanha: 'FORGE · Cartão', customer_id: '8017851692',
                n_operacoes: 72, request_id: 'req-1', criados: [] },
    });
    renderizar(ABERTA);

    const campo = await screen.findByDisplayValue(/lançamento de "Cartão para Negativado"/);
    const botao = screen.getByRole('button', { name: 'Criar campanha pausada' });
    expect((botao as HTMLButtonElement).disabled).toBe(true);

    // `subir()` recusa motivo com menos de 10 caracteres — o botão tem de
    // recusar antes, senão o operador só descobre depois da chamada.
    fireEvent.change(campo, { target: { value: 'curto' } });
    expect((screen.getByRole('button', { name: 'Criar campanha pausada' }) as HTMLButtonElement).disabled).toBe(true);

    fireEvent.change(campo, { target: { value: 'canário na conta da casa' } });
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: 'Criar campanha pausada' }));

    await waitFor(() => expect(screen.getByText('A campanha existe, e está pausada.')).toBeTruthy());
    expect(subirCampanha).toHaveBeenCalledWith(
      expect.objectContaining({
        motivo: 'canário na conta da casa',
        plano_impressao: 'f'.repeat(64),
        confirmar_criacao_pausada: true,
      }));
  });

  it('dinheiro ausente NÃO vira R$ 0,00 no cartão que o humano autoriza', async () => {
    // ⚠️ O DEFEITO: `Number(prova?.autorizacao.budget_diario ?? 0).toFixed(2)`.
    //
    // Este retângulo fica imediatamente acima do checkbox de confirmação — é o
    // último texto que a pessoa lê antes de autorizar gasto. Com o campo
    // ausente, o `?? 0` escrevia "orçamento R$ 0.00 / dia", e um orçamento zero
    // é uma afirmação: ela diz que a campanha não vai gastar. O que houve foi o
    // servidor não ter mandado o número.
    const semDinheiro = {
      ...APROVADO,
      autorizacao: { ...AUTORIZACAO, budget_diario: null, cpc_inicial: null },
    };
    provarCampanha.mockResolvedValue(semDinheiro);
    renderizar(ABERTA);

    await screen.findByRole('checkbox');
    expect(screen.queryByText(/R\$ 0\.00/)).toBeNull();
    expect(screen.getByText(/orçamento R\$ —/)).toBeTruthy();
  });

  it('lê o preparo que vem DENTRO do 409 de /subir, sem repetir a prova', async () => {
    provarCampanha.mockResolvedValue(APROVADO);
    subirCampanha.mockRejectedValue(new ErroFalso(
      'O payload não passou na prova — nada foi enviado.', 409,
      { mensagem: 'O payload não passou na prova — nada foi enviado.',
        preparo: REPROVADO.preparo }));

    renderizar(ABERTA);
    const campo = await screen.findByDisplayValue(/lançamento de/);
    fireEvent.change(campo, { target: { value: 'motivo suficientemente longo' } });
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: 'Criar campanha pausada' }));

    await waitFor(() => expect(screen.getByText('headline[3]')).toBeTruthy());
    // A prova rodou UMA vez. Antes, o 409 mandava "rode /provar" — e /provar é
    // a chamada mais lenta do fluxo.
    expect(provarCampanha).toHaveBeenCalledTimes(1);
  });

  it('bloqueia uma prova aprovada que não pertence à conta-laboratório', async () => {
    provarCampanha.mockResolvedValue({
      ...APROVADO,
      autorizacao: { ...AUTORIZACAO, alvo_canario: false, elegivel: false,
        motivo_elegibilidade: 'esta janela cria somente em Portal Mundo Mais' },
    });
    renderizar(ABERTA);
    await waitFor(() =>
      expect(screen.getAllByText(/fora da janela do canário/).length).toBeGreaterThan(0));
    expect(screen.getAllByText(/Portal Mundo Mais/).length).toBeGreaterThan(0);
    expect(subirCampanha).not.toHaveBeenCalled();
  });

  it('queda sem resposta vira indeterminado e nunca oferece reenvio', async () => {
    provarCampanha.mockResolvedValue(APROVADO);
    subirCampanha.mockRejectedValue(new ErroFalso('conexão caiu', 0));
    renderizar(ABERTA);
    const campo = await screen.findByDisplayValue(/lançamento de/);
    fireEvent.change(campo, { target: { value: 'canário manual com recibo' } });
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: 'Criar campanha pausada' }));

    await waitFor(() => expect(screen.getByText('A resposta se perdeu. Não reenvie.')).toBeTruthy());
    expect(screen.queryByRole('button', { name: 'Criar campanha pausada' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Voltar e ajustar' })).toBeNull();
  });

  it('uma recusa RESPONDIDA mostra o que corrigir, e não some com o recibo', async () => {
    // ⚠️ Este caminho não existia antes de 31/08/2026: a rota não lia
    // `recibo.estado`, e uma recusa do Google chegava como 200 dizendo "a
    // campanha existe, e está pausada". Agora chega 502 estruturado, e a tela
    // precisa mostrar o código do erro e o recibo — sem eles, "corrija e
    // reenvie" é um conselho que ninguém consegue seguir.
    provarCampanha.mockResolvedValue(APROVADO);
    subirCampanha.mockRejectedValue(new ErroFalso('recusado', 502, {
      estado: 'recusado',
      mensagem: 'headline excede 30 caracteres',
      erro_codigo: 'AdError.HEADLINE_TOO_LONG',
      request_id: 'req-9', recibo_id: 'recibo-1', item_id: 'item-1',
      reenvio_permitido: true,
    }));
    renderizar(ABERTA);
    const campo = await screen.findByDisplayValue(/lançamento de/);
    fireEvent.change(campo, { target: { value: 'canário manual com recibo' } });
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: 'Criar campanha pausada' }));

    await waitFor(() =>
      expect(screen.getByText('O Google recusou. Nada foi criado.')).toBeTruthy());
    expect(screen.getByText('AdError.HEADLINE_TOO_LONG')).toBeTruthy();
    expect(screen.getByText('recibo-1')).toBeTruthy();
    expect(screen.getByText('item-1')).toBeTruthy();
    // Recusa É reentrável — houve resposta e nada ficou em trânsito. A volta ao
    // formulário tem de existir, ao contrário do caminho indeterminado.
    expect(screen.queryByRole('button', { name: 'Voltar e ajustar' })).not.toBeNull();
  });

  it('não confunde recusa com indeterminação: a saída de cada uma é oposta', async () => {
    provarCampanha.mockResolvedValue(APROVADO);
    subirCampanha.mockRejectedValue(new ErroFalso('sem resposta', 504, {
      estado: 'indeterminado', mensagem: 'a chamada não teve resposta',
      recibo_id: 'recibo-2', item_id: 'item-2', reenvio_permitido: false,
    }));
    renderizar(ABERTA);
    const campo = await screen.findByDisplayValue(/lançamento de/);
    fireEvent.change(campo, { target: { value: 'canário manual com recibo' } });
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: 'Criar campanha pausada' }));

    await waitFor(() =>
      expect(screen.getByText('A resposta se perdeu. Não reenvie.')).toBeTruthy());
    expect(screen.queryByText('O Google recusou. Nada foi criado.')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Voltar e ajustar' })).toBeNull();
  });

  it('o recibo diz QUANDO a campanha foi criada, e não só o nome', async () => {
    provarCampanha.mockResolvedValue(APROVADO);
    subirCampanha.mockResolvedValue({
      recibo: {
        nome_campanha: 'FORGE · Cartão', customer_id: '8017851692',
        n_operacoes: 72, request_id: 'req-1', criados: [],
        carimbo: '20260831_180000',
      },
    });
    renderizar(ABERTA);
    const campo = await screen.findByDisplayValue(/lançamento de/);
    fireEvent.change(campo, { target: { value: 'canário manual com recibo' } });
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: 'Criar campanha pausada' }));

    await waitFor(() =>
      expect(screen.getByText('A campanha existe, e está pausada.')).toBeTruthy());
    expect(screen.getByText('quando')).toBeTruthy();
    expect(screen.getByText('20260831_180000')).toBeTruthy();
  });

  it('o laranja da marca só acende com recurso persistido', async () => {
    provarCampanha.mockResolvedValue(APROVADO);
    const { container } = renderizar(FECHADA);
    await waitFor(() => expect(screen.getByText('trava de escrita fechada')).toBeTruthy());
    // Aprovar é preflight; existir é outra coisa. `data-estado` é o que a CSS lê
    // para acender `.ignicao-fogo`.
    expect(container.querySelector('.ignicao')?.getAttribute('data-estado')).toBe('travada');
  });
});
