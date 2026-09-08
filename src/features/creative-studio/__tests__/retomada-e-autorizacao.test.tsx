// @vitest-environment jsdom
/**
 * Retomada da revisão e autorização do gasto — as duas provas desta rodada.
 *
 *  1. RETOMADA: recarregar a página precisa recuperar as aprovações do
 *     SERVIDOR. Antes elas viviam num `Set` de sessão: o F5 mostrava o lote
 *     inteiro como não revisado, com as decisões gravadas no banco o tempo todo.
 *
 *  2. AUTORIZAÇÃO: o botão que gasta só pode liberar depois de uma confirmação
 *     explícita que nomeia o modelo, a quantidade e o teto — e o pedido precisa
 *     CARREGAR essa confirmação, porque é ela que o servidor reconfere.
 *
 * Nenhum teste aqui chama provider, banco ou API de anúncios: o `fetch` é dublê.
 */
import React from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

Object.defineProperty(window, 'scrollTo', { value: vi.fn(), writable: true });

vi.mock('@/components/layout/Layout', () => ({
  Layout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('@/lib/supabase', () => ({
  supabase: {
    auth: {
      getSession: async () => ({ data: { session: { access_token: 'token-de-teste' } } }),
    },
  },
}));

const PROJECT_REF = `crproj_${'a'.repeat(24)}`;
const RUN_REF = `crrun_${'b'.repeat(24)}`;
const CAMINHO = '/pecas/creative_hook_frio';
const MODELO = 'openai:gpt-image-2';
const SELO = 'selo-de-teste.assinatura';

/** O catalogo que o servidor publica. A tela nao tem lista propria. */
const CAPACIDADES = {
  formatos: [
    { slot: '1x1', rotulo: 'Quadrado', proporcao: '1:1', largura: 1080, altura: 1080,
      descricao: 'Feed quadrado.', destinos_tipicos: [], canvas_nativo: null,
      transformacao_final: null, aceita_fotografia_real: true },
    { slot: '4x5', rotulo: 'Retrato', proporcao: '4:5', largura: 1080, altura: 1350,
      descricao: 'Retrato.', destinos_tipicos: [], canvas_nativo: null,
      transformacao_final: null, aceita_fotografia_real: true },
  ],
  teto_de_renders_por_pedido: 45,
  motor: { modelo: MODELO, qualidade: 'medium', configurado: true,
           publica_preco_por_imagem: true },
  modos_de_composicao: [
    { id: 'sem_foto', rotulo: 'Gerar a arte inteira', descricao: 'x',
      preserva_pixels_da_foto: false },
    { id: 'hibrido', rotulo: 'Compor com a fotografia', descricao: 'x',
      preserva_pixels_da_foto: true },
  ],
};

const PECA = {
  ref: 'creative_hook_frio',
  group_ref: 'group_territorio_1',
  shared_copy_ref: 'copy_grupo_1',
  estado_mental_ref: 'state_momento_1',
  hook: 'Hook que interrompe a rolagem',
  direcao_visual: 'Mesa de estudo com luz natural e material aberto.',
  headline_interna: 'Estude com método',
  complemento_interno: 'Sem depender de sorte',
  cta_visual: 'Comece hoje',
};

const SAIDA = {
  project_ref: PROJECT_REF,
  diagnostico: { resumo: 'Diagnóstico do lote.' },
  jornada: [],
  grupos: [],
  copies_compartilhadas: [],
  pecas: [PECA],
};

const PLANO = {
  conceitos: 1,
  formatos: 1,
  total_de_renders: 1,
  teto: 45,
  custo_estimado_usd: 0.039,
  custo_e_estimado: true,
  custo_tem_estimativa: true,
  modelo_de_imagem: MODELO,
  qualidade_de_imagem: 'medium',
  motor_configurado: true,
  pode_executar: true,
  bloqueios: [],
  selo_do_plano: SELO,
  modo_de_composicao: 'sem_foto',
  anexo_sha256: null,
  briefings: [{ creative_ref: PECA.ref, formato_slot: '1x1',
                texto_na_arte: 'Estude com método',
                direcao_visual: 'Mesa de estudo.' }],
};

/** O detalhe COMO O SERVIDOR passou a devolvê-lo: com as decisões projetadas. */
function detalheComAprovacao(aprovado: boolean) {
  return {
    operacao: {
      project_ref: PROJECT_REF,
      status: 'READY_FOR_REVIEW',
      input: { nome_da_operacao: 'Operação teste' },
      latest_run_ref: RUN_REF,
    },
    runs: [{ run_ref: RUN_REF, status: 'COMPLETED', output: SAIDA, created_at: null }],
    decisoes: aprovado
      ? [
          {
            decision_ref: `crdec_${'c'.repeat(24)}`,
            run_ref: RUN_REF,
            path: CAMINHO,
            decisao: 'APROVADO',
            scope: 'PECA',
            snapshot_sha256: 'f'.repeat(64),
            feedback: null,
            created_at: null,
          },
        ]
      : [],
    aprovacoes_validas: { [RUN_REF]: aprovado ? [CAMINHO] : [] },
  };
}

let chamadas: { url: string; metodo: string; corpo: unknown }[] = [];

function instalarFetch(aprovado: boolean, responderGeracao?: () => Promise<Response>) {
  chamadas = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      const endereco = String(url);
      const metodo = init?.method ?? 'GET';
      chamadas.push({
        url: endereco,
        metodo,
        corpo: init?.body ? JSON.parse(String(init.body)) : null,
      });

      let corpo: unknown = {};
      // O catálogo VEM DO SERVIDOR: um dublê que não o serve deixa a tela sem
      // formato nenhum, e o teste passa a medir o dublê.
      if (endereco.includes('/capacidades')) corpo = CAPACIDADES;
      else if (endereco.includes('/anexos')) corpo = { anexos: [] };
      else if (endereco.includes('/geracoes/plano')) corpo = PLANO;
      else if (endereco.includes('/geracoes') && metodo === 'POST') {
        if (responderGeracao) return responderGeracao();
        corpo = { geracoes: [], total_de_renders: 1, custo_estimado_usd: 0.039 };
      } else if (endereco.includes('/geracoes')) corpo = { geracoes: [] };
      else if (endereco.includes(PROJECT_REF)) corpo = detalheComAprovacao(aprovado);

      return { ok: true, status: 200, json: async () => corpo } as unknown as Response;
    }),
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function NavegacaoDeTeste() {
  const navegar = useNavigate();
  const local = useLocation();
  return <>
    <output data-testid="rota-atual">{local.pathname}{local.search}</output>
    <button onClick={() => navegar(`/trafego/meta/assistente-criativo/crproj_${'d'.repeat(24)}?view=producao`)}>Outra operação de teste</button>
  </>;
}

async function abrirProducao(comNavegacao = false) {
  const { default: AssistenteCriativoPage } = await import(
    '@/pages/trafego/AssistenteCriativoPage'
  );
  return render(
    <MemoryRouter
      initialEntries={[`/trafego/meta/assistente-criativo/${PROJECT_REF}?view=producao`]}
    >
      {comNavegacao && <NavegacaoDeTeste />}
      <Routes>
        <Route
          path="/trafego/meta/assistente-criativo/:projectRef"
          element={<AssistenteCriativoPage />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe('a revisão sobrevive ao reload', () => {
  it('a aprovação vem do servidor, sem nenhum clique nesta sessão', async () => {
    instalarFetch(true);
    await abrirProducao();

    // Montagem limpa: ninguém aprovou nada NESTA sessão. Se a peça aparece
    // como produzível, foi o servidor que disse que ela está aprovada.
    expect(await screen.findByText(PECA.hook)).toBeTruthy();
    expect(screen.queryByText(/Nenhuma peça foi aprovada ainda/i)).toBeNull();

    // E a retomada continua sendo só leitura.
    expect(chamadas.every((c) => c.metodo === 'GET')).toBe(true);
    expect(chamadas.some((c) => c.url.includes('/executar'))).toBe(false);
  });

  it('sem aprovação válida no servidor, a produção diz que não há o que produzir', async () => {
    instalarFetch(false);
    await abrirProducao();

    expect(await screen.findByText(/Nenhuma peça foi aprovada ainda/i)).toBeTruthy();
    expect(screen.queryByText(PECA.hook)).toBeNull();
  });
});

describe('espera da geração', () => {
  async function autorizarEGerar() {
    fireEvent.click(await screen.findByRole('checkbox', { name: /Hook que interrompe/i }));
    fireEvent.click(screen.getByRole('button', { name: /Conferir antes de gerar/i }));
    fireEvent.click(await screen.findByRole('checkbox', { name: /Autorizo produzir/i }));
    const botao = screen.getByRole('button', { name: /Gerar 1 imagem/i });
    fireEvent.click(botao);
    fireEvent.click(botao);
    await screen.findByRole('heading', { name: 'Geração solicitada' });
  }

  function respostaPendente() {
    let resolver!: (resposta: Response) => void;
    let rejeitar!: (erro: Error) => void;
    const resposta = new Promise<Response>((resolve, reject) => {
      resolver = resolve;
      rejeitar = reject;
    });
    return {
      resposta,
      concluir: () => resolver({ ok: true, status: 200, json: async () => ({ geracoes: [], total_de_renders: 1 }) } as Response),
      falhar: () => rejeitar(new Error('Conexão interrompida')),
    };
  }

  it('mostra o pedido autorizado, protege o formulário e preserva o acompanhamento ao trocar de aba', async () => {
    const pendente = respostaPendente();
    instalarFetch(true, () => pendente.resposta);
    await abrirProducao();
    await autorizarEGerar();

    const painel = screen.getByRole('region', { name: 'Geração solicitada' });
    expect(document.activeElement).toBe(painel);
    expect(within(painel).getByRole('status').textContent).toContain('Aguardando resposta');
    expect(within(painel).getByText(MODELO)).toBeTruthy();
    expect(within(painel).getByText('medium')).toBeTruthy();
    expect(within(painel).getByText('1')).toBeTruthy();
    expect(painel.textContent).not.toMatch(/\d+%|\d+ segundos|renderizando|finalizando/i);
    expect(painel.querySelectorAll('[class*="motion-reduce:animate-none"]').length).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: /Conferir antes de gerar/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /Gerar 1 imagem/i })).toBeNull();
    expect(screen.queryByText('Fotografia real')).toBeNull();
    expect(screen.queryByRole('checkbox', { name: /Hook que interrompe/i })).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Criativos' }));
    expect(await screen.findByText('Uma geração desta operação está aguardando resposta.')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Acompanhar geração' }));
    expect(await screen.findByRole('region', { name: 'Geração solicitada' })).toBeTruthy();
    expect(chamadas.filter((c) => c.url.endsWith('/geracoes') && c.metodo === 'POST')).toHaveLength(1);

    await act(async () => pendente.concluir());
    expect(await screen.findByText('Resposta recebida. Confira as imagens e eventuais falhas em Criativos.')).toBeTruthy();
    expect(screen.queryByRole('heading', { name: 'Geração solicitada' })).toBeNull();
  });

  it('uma falha orienta conferir o acervo e exige nova autorização, sem repetir o pedido', async () => {
    const pendente = respostaPendente();
    instalarFetch(true, () => pendente.resposta);
    await abrirProducao();
    await autorizarEGerar();
    await act(async () => pendente.falhar());

    expect((await screen.findByRole('alert')).textContent).toContain('Confira a aba Criativos antes de solicitar outra geração');
    expect(screen.queryByRole('heading', { name: 'Geração solicitada' })).toBeNull();
    expect((screen.getByRole('button', { name: /Gerar 1 imagem/i }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole('checkbox', { name: /Autorizo produzir/i }) as HTMLInputElement).checked).toBe(false);
    expect(chamadas.filter((c) => c.url.endsWith('/geracoes') && c.metodo === 'POST')).toHaveLength(1);
  });

  it('a resposta de uma operação anterior não muda a rota nem o aviso da operação atual', async () => {
    const pendente = respostaPendente();
    instalarFetch(true, () => pendente.resposta);
    await abrirProducao(true);
    await autorizarEGerar();
    fireEvent.click(screen.getByRole('button', { name: 'Outra operação de teste' }));
    await screen.findByText('Ainda não há estratégia concluída para produzir.');
    const rota = screen.getByTestId('rota-atual').textContent;
    const leiturasAntes = chamadas.filter((c) => c.url.endsWith('/geracoes') && c.metodo === 'GET').length;

    await act(async () => pendente.concluir());
    expect(screen.getByTestId('rota-atual').textContent).toBe(rota);
    expect(screen.queryByText(/Resposta recebida/)).toBeNull();
    expect(chamadas.filter((c) => c.url.endsWith('/geracoes') && c.metodo === 'GET')).toHaveLength(leiturasAntes);
  });

  it('mantém o erro visível quando a pessoa acompanha pela aba Criativos', async () => {
    const pendente = respostaPendente();
    instalarFetch(true, () => pendente.resposta);
    await abrirProducao();
    await autorizarEGerar();
    fireEvent.click(screen.getByRole('button', { name: 'Criativos' }));
    await act(async () => pendente.falhar());

    expect((await screen.findByRole('alert')).textContent).toContain('a solicitação pode ter sido recebida');
    expect(screen.queryByText('Uma geração desta operação está aguardando resposta.')).toBeNull();
    expect(chamadas.filter((c) => c.url.endsWith('/geracoes') && c.metodo === 'POST')).toHaveLength(1);
  });
});

describe('gerar exige autorização explícita', () => {
  it('o botão fica travado até a confirmação, e o pedido carrega a autorização', async () => {
    instalarFetch(true);
    await abrirProducao();

    fireEvent.click(await screen.findByRole('checkbox', { name: /Hook que interrompe/i }));
    fireEvent.click(screen.getByRole('button', { name: /Conferir antes de gerar/i }));

    const gerar = await screen.findByRole('button', { name: /Gerar 1 imagem/i });
    // Travado: o plano está na tela, mas ninguém confirmou o gasto.
    expect((gerar as HTMLButtonElement).disabled).toBe(true);
    expect(chamadas.some((c) => c.url.endsWith('/geracoes') && c.metodo === 'POST')).toBe(false);

    // O plano precisa NOMEAR o modelo e dizer que o custo é estimativa. O nome
    // aparece duas vezes de propósito: no resumo do plano e dentro da frase que
    // o operador confirma — quem autoriza precisa ler o modelo na própria
    // autorização, não uma linha acima.
    expect(screen.getAllByText(MODELO).length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(/ESTIMATIVA de tabela de referência/i)).toBeTruthy();

    fireEvent.click(screen.getByRole('checkbox', { name: /Autorizo produzir 1 imagem/i }));
    await waitFor(() => expect((gerar as HTMLButtonElement).disabled).toBe(false));

    fireEvent.click(gerar);
    await waitFor(() =>
      expect(chamadas.some((c) => c.url.endsWith('/geracoes') && c.metodo === 'POST')).toBe(true),
    );

    const pedido = chamadas.find((c) => c.url.endsWith('/geracoes') && c.metodo === 'POST')!
      .corpo as { autorizacao?: Record<string, unknown> };
    expect(pedido.autorizacao).toEqual({
      modelo: MODELO,
      total_de_renders: 1,
      teto_custo_usd: 0.04,
      // ⚠️ O selo é o que amarra o consentimento ao CONTEÚDO do plano. Sem ele,
      // autorizar duas peças e produzir outras duas passava nas conferências de
      // modelo e de total, porque nenhuma delas descreve qual conteúdo.
      selo_do_plano: SELO,
      aceito_sem_estimativa: false,
    });
  });

  it('mudar a seleção depois de confirmar derruba a confirmação', async () => {
    instalarFetch(true);
    await abrirProducao();

    fireEvent.click(await screen.findByRole('checkbox', { name: /Hook que interrompe/i }));
    fireEvent.click(screen.getByRole('button', { name: /Conferir antes de gerar/i }));
    fireEvent.click(await screen.findByRole('checkbox', { name: /Autorizo produzir/i }));

    const gerar = screen.getByRole('button', { name: /Gerar 1 imagem/i });
    await waitFor(() => expect((gerar as HTMLButtonElement).disabled).toBe(false));

    // Tirar um formato muda o total. A confirmação anterior não cobre o novo
    // lote, e o plano conferido deixa de valer junto.
    fireEvent.click(screen.getByRole('button', { name: /Quadrado, 1:1/i }));

    await waitFor(() =>
      expect(screen.queryByRole('button', { name: /Gerar 1 imagem/i })).toBeNull(),
    );
    expect(chamadas.some((c) => c.url.endsWith('/geracoes') && c.metodo === 'POST')).toBe(false);
  });
});
