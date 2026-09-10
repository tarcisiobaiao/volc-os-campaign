// @vitest-environment jsdom
import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import MetaCriacaoPage from '@/pages/trafego/MetaCriacaoPage';

Object.defineProperty(window, 'scrollTo', { value: vi.fn(), writable: true });

const { api } = vi.hoisted(() => ({
  api: {
    trackingAutomaticoMeta: vi.fn().mockRejectedValue(new Error('Prévia indisponível neste dublê')),
    estadoMetaLocal: vi.fn(),
    contasMetaLocal: vi.fn(),
    capacidadesCriacaoMeta: vi.fn(),
    ativosCriacaoMeta: vi.fn(),
    previewAtivoMeta: vi.fn(),
    compilarPlanoMeta: vi.fn(),
    validarPlanoMeta: vi.fn(),
  },
}));

vi.mock('@/lib/pautadorApi', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/pautadorApi')>()),
  pautadorApi: api,
}));

vi.mock('@/components/layout/Layout', () => ({
  Layout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const conta = {
  referencia_opaca: 'metaacct_conta_de_prova',
  nome: 'Conta de prova',
  id_mascarado: '••••1426',
  status: '1',
  moeda: 'BRL',
  fuso: 'America/Sao_Paulo',
  prontidao_leitura: 'READY_FOR_READ' as const,
  business: null,
};

const imagem = (sufixo: string) => ({
  referencia_opaca: `metaasset_${sufixo}`,
  nome: `Imagem ${sufixo}`,
  tipo: 'image_asset' as const,
  id_mascarado: null,
  largura: 1080,
  altura: 1080,
  preview_disponivel: false,
});

beforeEach(() => {
  api.estadoMetaLocal.mockReset().mockResolvedValue({
    configurado: true, armazenamento: 'macOS Keychain', api_version: 'v26.0',
  });
  api.contasMetaLocal.mockReset().mockResolvedValue({
    ok: true, api_version: 'v26.0', armazenamento: 'macOS Keychain', contas: [conta],
  });
  api.capacidadesCriacaoMeta.mockReset().mockResolvedValue({
    ok: true, api_version: 'v26.0', validate_only: 'BLOCKED_BY_SERVER_FLAG',
    single_static: 'AVAILABLE', static_batch: 'AVAILABLE_UP_TO_10',
    video_creative: 'BLOCKED_UNTIL_VIDEO_CONTRACT_PROVEN',
    flexible_creative: 'BLOCKED_UNTIL_ASSET_FEED_SPEC_PROVEN',
  });
  api.ativosCriacaoMeta.mockReset().mockResolvedValue({
    ok: true, api_version: 'v26.0', account_ref: conta.referencia_opaca, conta,
    paginas: [{
      referencia_opaca: 'metaobj_pagina', nome: 'Página de prova', tipo: 'page' as const,
      id_mascarado: '••••7788', largura: null, altura: null, preview_disponivel: false,
    }],
    imagens: [imagem('um'), imagem('dois')],
    videos: [],
    receita: 'OUTCOME_TRAFFIC_WEBSITE_LPV_STATIC_PAUSED',
  });
  api.previewAtivoMeta.mockReset().mockRejectedValue(new Error('sem prévia no teste'));
  api.compilarPlanoMeta.mockReset().mockResolvedValue({
    ok: true, efeito_externo: 'NENHUM',
    plano: {
      account_ref: conta.referencia_opaca, destination_url: 'https://focogenial.com/',
      api_version: 'v26.0', plano_sha256: 'a'.repeat(64), estado_ao_nascer: 'PAUSED',
      operacoes: [],
    },
  });
  api.validarPlanoMeta.mockReset();
});

afterEach(cleanup);

describe('jornada guiada e ponte do assistente', () => {
  it('começa vazia, pede destino e limpa o erro quando a resposta muda, sem leitura Meta automática', async () => {
    abrir('');
    expect(screen.getByRole('heading', { name: 'Qual página você quer anunciar?' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Continuar' }));
    expect(screen.getByText('Informe uma URL HTTPS válida, sem UTMs, para continuar.')).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Endereço da página'), { target: { value: 'https://exemplo.com/materia' } });
    expect(screen.queryByText('Informe uma URL HTTPS válida, sem UTMs, para continuar.')).toBeNull();
    fireEvent.change(screen.getByLabelText('Como vamos chamar esta campanha?'), { target: { value: 'Teste local' } });
    fireEvent.click(screen.getByRole('button', { name: 'Continuar' }));
    expect(screen.getByRole('heading', { name: 'Em qual conta vamos trabalhar?' })).toBeTruthy();
    expect(api.contasMetaLocal).not.toHaveBeenCalled();
    expect(api.compilarPlanoMeta).not.toHaveBeenCalled();
  });

  it('aceita seleção apenas do iframe próprio e preserva o projeto ao retornar, sem upload', async () => {
    abrir('criativo');
    fireEvent.click(screen.getByRole('radio', { name: /Criar com o assistente/ }));
    const frame = screen.getByTitle('Assistente Criativo da campanha') as HTMLIFrameElement;
    const data = { type: 'volc:creative-selection', masterRefs: ['master_selecionado'] };
    fireEvent(window, new MessageEvent('message', { origin: 'https://externo.invalid', source: frame.contentWindow, data }));
    fireEvent(window, new MessageEvent('message', { origin: window.location.origin, source: window, data }));
    expect(screen.queryByText(/1 peça\(s\) selecionada\(s\) no Estúdio/)).toBeNull();
    fireEvent(window, new MessageEvent('message', { origin: window.location.origin, source: frame.contentWindow, data }));
    expect(screen.getByText(/1 peça\(s\) selecionada\(s\) no Estúdio/)).toBeTruthy();
    fireEvent(window, new MessageEvent('message', { origin: window.location.origin, source: frame.contentWindow,
      data: { type: 'volc:creative-project', projectRef: 'crproj_projeto_de_teste' } }));
    expect(frame.getAttribute('src')).toBe('/trafego/meta/assistente-criativo?view=briefing');
    fireEvent.click(screen.getByRole('button', { name: 'Revisão' }));
    expect(screen.getByText(/aguardando registro na conta/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Criativos' }));
    expect(screen.getByTitle('Assistente Criativo da campanha').getAttribute('src'))
      .toBe('/trafego/meta/assistente-criativo/crproj_projeto_de_teste?view=assets');
    expect(api.compilarPlanoMeta).not.toHaveBeenCalled();
    expect(api.validarPlanoMeta).not.toHaveBeenCalled();
  });
});

function abrir(etapa: string) {
  const tela = render(
    <MemoryRouter initialEntries={[`/trafego/meta/nova?etapa=${etapa}`]}>
      <MetaCriacaoPage />
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByText('Ver etapas e editar respostas'));
  return tela;
}

async function esperarAtivos() {
  if (!api.contasMetaLocal.mock.calls.length) {
    const anterior = screen.getByRole('button', { current: 'step' });
    fireEvent.click(screen.getByRole('button', { name: /^Conta$/i }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Carregar minhas contas' })).toHaveProperty('disabled', false));
    fireEvent.click(screen.getByRole('button', { name: 'Carregar minhas contas' }));
    await waitFor(() => expect(api.ativosCriacaoMeta).toHaveBeenCalled());
    fireEvent.click(anterior);
  }
  await waitFor(() => expect(api.ativosCriacaoMeta).toHaveBeenCalled());
}

it('abrir a bancada não consulta a Meta sem clique explícito', async () => {
  abrir('base');
  await waitFor(() => expect(screen.getByRole('button', { name: 'Carregar minhas contas' })).toHaveProperty('disabled', false));
  expect(api.contasMetaLocal).not.toHaveBeenCalled();
  expect(api.ativosCriacaoMeta).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Carregar minhas contas' }));
  await waitFor(() => expect(api.contasMetaLocal).toHaveBeenCalledTimes(1));
});

/** Satisfaz as decisões que a bancada exige antes de liberar a conferência.
 *  A confirmação de categoria especial é uma delas, e é deliberada: sem ela o
 *  plano não pode ser compilado. */
function confirmarEnquadramento() {
  fireEvent.click(screen.getByRole('button', { name: /^Resultado$/i }));
  fireEvent.click(screen.getByRole('button', { name: /^Destino$/i }));
  fireEvent.change(screen.getByLabelText('Endereço da página'), { target: { value: 'https://focogenial.com/' } });
  fireEvent.change(screen.getByLabelText('Como vamos chamar esta campanha?'), { target: { value: 'Campanha de prova' } });
  fireEvent.click(screen.getByRole('button', { name: /^Resultado$/i }));
  fireEvent.click(screen.getByRole('checkbox', { name: /não é de crédito, emprego/i }));
}

function confirmarPeca() {
  fireEvent.click(screen.getByRole('button', { name: /^Criativos$/i }));
  fireEvent.click(screen.getByRole('checkbox', { name: /peça é própria ou licenciada/i }));
  fireEvent.click(screen.getByRole('checkbox', { name: /marcas, logos e identidades/i }));
}

/** Vai até a revisão e dispara a conferência do plano no backend. */
async function compilarPelaRevisao() {
  confirmarEnquadramento();
  confirmarPeca();
  fireEvent.click(screen.getByRole('button', { name: /^Revisão/i }));
  fireEvent.click(await screen.findByRole('button', { name: /conferir o plano/i }));
  await waitFor(() => expect(api.compilarPlanoMeta).toHaveBeenCalled());
}

describe('Bancada de criação Meta — contrato do rascunho', () => {
  it('diz quais confirmações faltam sem declarar a URL inválida', async () => {
    abrir('criativo');
    await esperarAtivos();
    confirmarEnquadramento();
    fireEvent.click(screen.getByRole('button', { name: /^Revisão/i }));
    expect(screen.getAllByText(/Confirme os direitos de uso da imagem/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Confirme a revisão de marcas e identidade/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/O anúncio 1 está incompleto/)).toBeNull();
    expect(screen.queryByText(/Informe uma URL de destino HTTPS/)).toBeNull();
    expect(api.compilarPlanoMeta).not.toHaveBeenCalled();
  });

  it('mostra andamento e conclusão da conferência', async () => {
    let concluir!: (value: unknown) => void;
    const resultado = { ok: true, efeito_externo: 'NENHUM', plano: { operacoes: [], plano_sha256: 'a'.repeat(64) } };
    api.compilarPlanoMeta.mockImplementationOnce(() => new Promise(resolve => { concluir = resolve; }));
    abrir('criativo');
    await esperarAtivos();
    await compilarPelaRevisao();
    expect(screen.getByText(/Conferindo o plano no servidor/)).toBeTruthy();
    concluir(resultado);
    expect(await screen.findByText(/Plano conferido. Próximo passo/)).toBeTruthy();
  });
  it('lê orçamento com ponto decimal sem multiplicar a verba por cem', async () => {
    abrir('orcamento');
    await esperarAtivos();
    fireEvent.change(screen.getByLabelText(/orçamento diário/i), {
      target: { value: '10.00' },
    });
    await waitFor(() => expect(screen.getAllByText(/R\$\s*10,00/).length).toBeGreaterThan(0));
    await compilarPelaRevisao();
    expect(api.compilarPlanoMeta.mock.calls[0][0].daily_budget_minor).toBe(1000);
  });

  it('trata milhar pt-BR sem transformar mil reais em dez', async () => {
    abrir('orcamento');
    await esperarAtivos();
    fireEvent.change(screen.getByLabelText(/orçamento diário/i), {
      target: { value: '1.000' },
    });
    await compilarPelaRevisao();
    expect(api.compilarPlanoMeta.mock.calls[0][0].daily_budget_minor).toBe(100000);
  });

  it('envia a recusa explícita de Advantage+ público, nunca a omissão', async () => {
    abrir('publico');
    await esperarAtivos();
    await compilarPelaRevisao();
    expect(api.compilarPlanoMeta.mock.calls[0][0].advantage_audience).toBe(false);
  });

  it('mantém variation_key única ao remover uma linha do meio e adicionar outra', async () => {
    abrir('criativo');
    await esperarAtivos();
    const adicionar = () => screen.getByRole('button', { name: /adicionar anúncio neste conjunto/i });
    fireEvent.click(adicionar());
    fireEvent.click(adicionar());
    await waitFor(() => expect(screen.getAllByTestId('variacao-chave')).toHaveLength(3));
    fireEvent.click(screen.getAllByRole('button', { name: /remover/i })[1]);
    await waitFor(() => expect(screen.getAllByTestId('variacao-chave')).toHaveLength(2));
    fireEvent.click(adicionar());
    await waitFor(() => expect(screen.getAllByTestId('variacao-chave')).toHaveLength(3));
    const chaves = screen.getAllByTestId('variacao-chave').map((no) => no.textContent);
    expect(new Set(chaves).size).toBe(chaves.length);
  });

  it('remover o segundo anúncio volta ao modo individual e compila só o restante', async () => {
    abrir('criativo');
    await esperarAtivos();
    fireEvent.click(screen.getByRole('button', { name: /adicionar anúncio neste conjunto/i }));
    await waitFor(() => expect(screen.getAllByTestId('variacao-chave')).toHaveLength(2));
    fireEvent.click(screen.getAllByRole('button', { name: /^remover$/i })[1]);
    await waitFor(() => expect(screen.getAllByTestId('variacao-chave')).toHaveLength(1));
    await compilarPelaRevisao();
    const enviado = api.compilarPlanoMeta.mock.calls[0][0];
    expect(enviado.variations).toHaveLength(1);
  });

  it('não expõe o nome da variável de ambiente do servidor ao operador', async () => {
    const { container } = abrir('revisao');
    await esperarAtivos();
    expect(container.innerHTML).not.toContain('META_VALIDATE_ONLY_ENABLED');
  });
});

describe('Bancada de criação Meta — correções adversariais', () => {
  it('recusa orçamento negativo em vez de torná-lo positivo', async () => {
    abrir('orcamento');
    await esperarAtivos();
    fireEvent.change(screen.getByLabelText(/orçamento diário/i), {
      target: { value: '-10,00' },
    });
    // Sem verba válida a conferência não pode ser liberada.
    confirmarEnquadramento();
    fireEvent.click(screen.getByRole('button', { name: /^Revisão/i }));
    const botao = await screen.findByRole('button', { name: /conferir o plano/i });
    expect(botao.hasAttribute('disabled')).toBe(true);
    expect(screen.getAllByText(/orçamento diário maior que zero/i).length).toBeGreaterThan(0);
    expect(api.compilarPlanoMeta).not.toHaveBeenCalled();
  });

  it('ir à revisão e voltar não apaga os anúncios montados no conjunto', async () => {
    abrir('criativo');
    await esperarAtivos();
    fireEvent.click(screen.getByRole('button', { name: /adicionar anúncio neste conjunto/i }));
    fireEvent.click(screen.getByRole('button', { name: /adicionar anúncio neste conjunto/i }));
    await waitFor(() => expect(screen.getAllByTestId('variacao-chave')).toHaveLength(3));
    const antes = screen.getAllByTestId('variacao-chave').map(no => no.textContent);
    fireEvent.click(screen.getByRole('button', { name: /^Revisão/i }));
    fireEvent.click(screen.getByRole('button', { name: /^Criativos$/i }));
    expect(screen.getAllByTestId('variacao-chave').map(no => no.textContent)).toEqual(antes);
  });

  it('anuncia a falha da operação a quem usa leitor de tela', async () => {
    api.compilarPlanoMeta.mockRejectedValueOnce(new Error('a Meta recusou o plano'));
    abrir('revisao');
    await esperarAtivos();
    await esperarAtivos();
    confirmarEnquadramento();
    confirmarPeca();
    fireEvent.click(screen.getByRole('button', { name: /^Revisão/i }));
    fireEvent.click(await screen.findByRole('button', { name: /conferir o plano/i }));
    const alerta = await screen.findByRole('alert', { name: 'Erros da operação' });
    await waitFor(() => expect(alerta.textContent).toContain('a Meta recusou o plano'));
  });
});

// ---------------------------------------------------------------------------
// TIMEOUT DO validate_only — a tela precisa separar silêncio de reprovação
// ---------------------------------------------------------------------------
describe('Bancada de criação Meta — timeout não é recusa', () => {
  async function abrirComValidacaoLiberada() {
    api.capacidadesCriacaoMeta.mockResolvedValue({
      ok: true, api_version: 'v26.0', validate_only: 'ENABLED',
      single_static: 'AVAILABLE', static_batch: 'AVAILABLE_UP_TO_10',
      video_creative: 'BLOCKED_UNTIL_VIDEO_CONTRACT_PROVEN',
      flexible_creative: 'BLOCKED_UNTIL_ASSET_FEED_SPEC_PROVEN',
    });
    abrir('revisao');
    await esperarAtivos();
    await compilarPelaRevisao();
  }

  it('explica que a Meta não respondeu e que nada foi criado, em vez de "sem detalhes"', async () => {
    const { PautadorApiError } = await import('@/lib/pautadorApi');
    api.validarPlanoMeta.mockRejectedValueOnce(new PautadorApiError(
      'a Meta nao respondeu a validacao de campaign a tempo; nada foi criado',
      504,
      { codigo: 'META_VALIDATE_TIMEOUT', retry_permitido: true },
    ));
    await abrirComValidacaoLiberada();
    fireEvent.click(screen.getByRole('button', { name: /validar na meta/i }));

    const alerta = await screen.findByRole('alert', { name: 'Erros da operação' });
    await waitFor(() => expect(alerta.textContent).toContain('META_VALIDATE_TIMEOUT'));
    // O ponto do conserto: o operador não pode ler silêncio como reprovação.
    expect(alerta.textContent).toContain('não é uma recusa');
    expect(alerta.textContent).toContain('nada foi criado');
    expect(alerta.textContent).not.toContain('Nenhum detalhe adicional');
    expect(alerta.textContent).not.toContain('A Meta recusou com o código');
  });

  it('continua nomeando a recusa real da Meta com código e subcódigo', async () => {
    const { PautadorApiError } = await import('@/lib/pautadorApi');
    api.validarPlanoMeta.mockRejectedValueOnce(new PautadorApiError(
      'a Meta recusou o plano', 422,
      { codigo: 'META_REMOTE_REJECTED', provedor: { code: 100, error_subcode: 1487079 } },
    ));
    await abrirComValidacaoLiberada();
    fireEvent.click(screen.getByRole('button', { name: /validar na meta/i }));

    const alerta = await screen.findByRole('alert', { name: 'Erros da operação' });
    await waitFor(() => expect(alerta.textContent).toContain('100/1487079'));
    expect(alerta.textContent).not.toContain('não é uma recusa');
  });
});

// ---------------------------------------------------------------------------
// RECUSA REAL 100/4005 — verba compartilhada travada e UM impedimento
// ---------------------------------------------------------------------------
describe('Bancada de criação Meta — recusa real 100/4005', () => {
  it('mostra o compartilhamento como fato travado, sem toggle interativo', async () => {
    abrir('orcamento');
    await esperarAtivos();

    // O interruptor deixou de existir nesta receita.
    expect(screen.queryByRole('checkbox', {
      name: /compartilhe verba entre conjuntos/i,
    })).toBeNull();

    // E o fato aparece travado, com a razão em linguagem de operador.
    expect(screen.getByText(/Compartilhamento entre conjuntos: desativado/i)).toBeTruthy();
    expect(screen.getByText(/fica desativado nesta configuração/i)).toBeTruthy();
    expect(screen.getByText(/CBO.*escolha independente/i))
      .toBeTruthy();
  });

  it('continua enviando o booleano explícito como false, nunca omitindo', async () => {
    abrir('orcamento');
    await esperarAtivos();
    await compilarPelaRevisao();
    const enviado = api.compilarPlanoMeta.mock.calls[0][0];
    expect('is_adset_budget_sharing_enabled' in enviado).toBe(true);
    expect(enviado.is_adset_budget_sharing_enabled).toBe(false);
  });

  it('consolida uma recusa da Meta com três mensagens em UM impedimento', async () => {
    const { PautadorApiError } = await import('@/lib/pautadorApi');
    api.capacidadesCriacaoMeta.mockResolvedValue({
      ok: true, api_version: 'v26.0', validate_only: 'ENABLED',
      single_static: 'AVAILABLE', static_batch: 'AVAILABLE_UP_TO_10',
      video_creative: 'BLOCKED_UNTIL_VIDEO_CONTRACT_PROVEN',
      flexible_creative: 'BLOCKED_UNTIL_ASSET_FEED_SPEC_PROVEN',
      adset_budget_sharing: 'BLOCKED_IN_SINGLE_ADSET_RECIPE',
    });
    // A recusa literal de 05/09/2026: título, mensagem de usuário e message.
    api.validarPlanoMeta.mockRejectedValueOnce(new PautadorApiError(
      'a Meta recusou campaign (código 100/4005): Estratégia de lance ausente '
      + '— Não é possível usar o compartilhamento do orçamento do conjunto de '
      + 'anúncios sem uma estratégia de lance.',
      422,
      {
        codigo: 'META_REMOTE_VALIDATION_FAILED',
        provedor: {
          objeto: 'campaign', code: 100, error_subcode: 4005, type: 'OAuthException',
          messages: [
            'Estratégia de lance ausente',
            'Não é possível usar o compartilhamento do orçamento do conjunto de anúncios sem uma estratégia de lance.',
            'Invalid parameter',
          ],
        },
      },
    ));
    abrir('revisao');
    await esperarAtivos();
    await compilarPelaRevisao();
    fireEvent.click(screen.getByRole('button', { name: /validar na meta/i }));

    const alerta = await screen.findByRole('alert', { name: 'Erros da operação' });
    // ⚠️ O ponto do conserto: três explicações são UM incidente.
    await waitFor(() => expect(alerta.textContent).toContain('1 impedimento'));
    expect(alerta.textContent).not.toContain('impedimentos');
    expect(alerta.querySelectorAll('li').length).toBe(1);

    // Título carrega objeto, código e subcódigo.
    expect(alerta.textContent).toContain('campaign');
    expect(alerta.textContent).toContain('100/4005');
    // Nenhuma explicação se perde.
    expect(alerta.textContent).toContain('Estratégia de lance ausente');
    expect(alerta.textContent).toContain('sem uma estratégia de lance');
    expect(alerta.textContent).toContain('Invalid parameter');
    // E o código que o operador copia continua lá.
    expect(alerta.textContent).toContain('META_REMOTE_VALIDATION_FAILED');
  });
});
