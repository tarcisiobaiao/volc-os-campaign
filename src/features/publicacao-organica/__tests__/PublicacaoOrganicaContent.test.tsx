// @vitest-environment jsdom

/**
 * A tela da publicação orgânica contra a API — e contra as três tentações.
 *
 *   1. **Mentir quando a API cai.** Não existe fixture neste módulo, e estes
 *      testes provam que a tela distingue vazio de indisponível, de sem
 *      permissão e de sem sessão. Se alguém acrescentar um retrato plausível
 *      "para a tela não ficar feia", o teste de indisponibilidade cai.
 *   2. **Pintar de verde o que ninguém confirmou.** A varredura percorre todos
 *      os estados no DOM real e falha se um selo com `data-incerto="true"`
 *      carregar token de sucesso — inclusive quando o próprio backend se
 *      contradiz.
 *   3. **Publicar por engano.** Agendar exige confirmação; publicar agora exige
 *      outra, mais forte, com o texto do que vai acontecer e uma caixa marcada
 *      à mão. O campo `confirmo_publicacao_imediata` só existe no corpo quando
 *      a caixa foi marcada.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as React from 'react';

vi.mock('@/lib/supabase', () => ({
  supabase: { auth: { getSession: async () => ({ data: { session: { access_token: 't' } } }) } },
}));
vi.mock('@/hooks/use-toast', () => ({ useToast: () => ({ toast: vi.fn() }) }));

import * as api from '../publicacaoOrganicaApi';
import { PublicacaoOrganicaContent } from '../PublicacaoOrganicaContent';
import {
  ESTADOS, TOKENS_DE_SUCESSO,
  type DestinoOrganico, type JobOrganico, type LeituraDoEstado,
} from '../contract';

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

// ─────────────────────────────────────────────────────────────────────────────
// Fixtures de RESPOSTA — o que a API devolveria. Nunca fallback de tela.
// ─────────────────────────────────────────────────────────────────────────────

const LEITURA: Record<string, LeituraDoEstado> = {
  rascunho: { rotulo: 'Rascunho local', tom: 'neutro', proxima_acao: 'Revise e libere para despacho.', incerto: false, terminal: false },
  pronto: { rotulo: 'Pronto para despachar', tom: 'neutro', proxima_acao: 'Aguardando o despachante assumir.', incerto: false, terminal: false },
  em_voo: { rotulo: 'Em voo', tom: 'aguardando', proxima_acao: 'O pedido foi enviado e a resposta ainda não chegou. Não reenvie.', incerto: true, terminal: false },
  rascunho_externo: { rotulo: 'Rascunho criado no destino', tom: 'aguardando', proxima_acao: 'Reconcilie para confirmar.', incerto: false, terminal: false },
  agendado: { rotulo: 'Agendado no destino', tom: 'aguardando', proxima_acao: 'Aguardando o horário.', incerto: false, terminal: false },
  publicacao_solicitada: { rotulo: 'Publicação solicitada', tom: 'atencao', proxima_acao: 'Reconcilie antes de considerar publicado.', incerto: true, terminal: false },
  publicado: { rotulo: 'Publicado (sem prova fechada)', tom: 'atencao', proxima_acao: 'Reconcilie para trazer URL e horário.', incerto: false, terminal: false },
  reconciliado: { rotulo: 'Publicado e conferido', tom: 'sucesso', proxima_acao: 'Nada a fazer. A URL e o horário estão registrados.', incerto: false, terminal: true },
  falha: { rotulo: 'Falhou', tom: 'falha', proxima_acao: 'Leia o erro e crie um job novo — este não é rearmado.', incerto: false, terminal: false },
  indeterminado: { rotulo: 'Indeterminado', tom: 'atencao', proxima_acao: 'Não sabemos se publicou. Reconcilie antes de tentar de novo.', incerto: true, terminal: false },
  cancelado: { rotulo: 'Cancelado', tom: 'neutro', proxima_acao: 'Nada a fazer.', incerto: false, terminal: true },
};

const DESTINO_APTO: DestinoOrganico = {
  destino_id: 'dest-apto', ativo_id: 'asset:instagram:piloto', nome: 'Perfil do piloto',
  plataforma: 'instagram', identidade_logica: '@volc.piloto', provedor: 'postiz',
  apto: true, motivo: null, timezone_padrao: 'America/Sao_Paulo', estado: 'ativo',
};

const DESTINO_INAPTO: DestinoOrganico = {
  destino_id: 'dest-inapto', ativo_id: 'asset:threads:piloto', nome: 'Threads do piloto',
  plataforma: 'threads', identidade_logica: '@volc.threads', provedor: 'multipost',
  apto: false, motivo: 'sem adapter oficial para Threads neste provedor',
  timezone_padrao: 'America/Sao_Paulo', estado: 'ativo',
};

function job(estado: string, extra: Partial<JobOrganico> = {}): JobOrganico {
  return {
    job_id: `job-${estado}`,
    estado,
    modo: 'schedule',
    horario_local: '2026-09-10 09:30:00',
    timezone: 'America/Sao_Paulo',
    instante_utc: '2026-09-10T12:30:00+00:00',
    tentativas: 0,
    ultimo_erro: null,
    adapter: 'postiz',
    destino: { destino_id: 'dest-apto', plataforma: 'instagram', identidade_logica: '@volc.piloto' },
    peca: { id: '7f3c2b10-4a5d-4e2f-9a11-8c7b6d5e4f30', versao: 3, content_hash: 'sha256:a1b2c3d4e5f60718293a' },
    aprovacao: {
      id: 'apr-1', ator_id: '9c1d2e3f-0000-4444-8888-aabbccddeeff',
      finalidade: 'publicacao_organica', decidido_em: '2026-09-01T10:00:00+00:00', revogada_em: null,
    },
    recibo: null,
    criado_em: '2026-09-01T10:05:00+00:00',
    atualizado_em: '2026-09-01T10:05:00+00:00',
    leitura: LEITURA[estado] ?? {
      rotulo: `Estado nao reconhecido (${estado})`, tom: 'atencao',
      proxima_acao: 'Não trate como publicado.', incerto: false, terminal: false,
    },
    ...extra,
  };
}

/**
 * ⚠️ A FIXTURE HOSTIL — sem ela a varredura do DOM é vácua onde importa.
 *
 * DEFEITO MEDIDO (revisão de 02/09/2026): a varredura filtrava por
 * `data-incerto === 'true' && temTokenDeSucesso(className)`, mas a fixture
 * nunca combinava `incerto: true` com `tom: 'sucesso'`. O array filtrado saía
 * vazio COM ou SEM o veto — o teste passava por não ter o que olhar, e a
 * mutação que trocasse `classeDoTom(job)` por `CLASSE_DO_TOM[job.leitura.tom]`
 * passava junto.
 *
 * Estes três jobs são a hipótese hostil de verdade:
 *   1. o backend se contradiz — em trânsito E verde;
 *   2. o mesmo, num estado que ainda não é publicação;
 *   3. backend ANTIGO — manda `tom: 'sucesso'` e nem envia `incerto`, que é
 *      exatamente o caso em que o piso `ESTADOS_INCERTOS` tem de responder.
 */
const JOBS_HOSTIS: JobOrganico[] = [
  job('em_voo', {
    job_id: 'hostil-em-voo',
    leitura: { rotulo: 'Publicado', tom: 'sucesso', proxima_acao: 'Nada a fazer.', incerto: true, terminal: true },
  }),
  job('publicacao_solicitada', {
    job_id: 'hostil-solicitada',
    leitura: { rotulo: 'Publicado', tom: 'sucesso', proxima_acao: 'Nada a fazer.', incerto: true, terminal: false },
  }),
  job('indeterminado', {
    job_id: 'hostil-sem-campo',
    // Sem `incerto` e sem `terminal`: é assim que um backend anterior à v14_01
    // responderia, e o contrato tolera essa forma em tempo de execução.
    leitura: { rotulo: 'Publicado', tom: 'sucesso', proxima_acao: 'Nada a fazer.' } as unknown as LeituraDoEstado,
  }),
];

function montar() {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(
    <QueryClientProvider client={cliente}>
      <PublicacaoOrganicaContent />
    </QueryClientProvider>,
  );
}

/** O caminho feliz de fundo: destinos e prontidão respondem, jobs varia. */
function comAmbienteBase(destinos: DestinoOrganico[] = [DESTINO_APTO, DESTINO_INAPTO]) {
  vi.spyOn(api, 'publicacaoConfigurada').mockReturnValue(true);
  vi.spyOn(api, 'listarDestinos').mockResolvedValue({ destinos });
  vi.spyOn(api, 'prontidao').mockResolvedValue({
    pronto: true, fonte: 'proxy:/integrations', detalhe: 'control plane respondeu', canais_visiveis: 2,
  });
}

function temTokenDeSucesso(classe: string): boolean {
  return TOKENS_DE_SUCESSO.some((token) => classe.includes(token));
}

// ─────────────────────────────────────────────────────────────────────────────

describe('os estados que não são dado', () => {
  beforeEach(() => { comAmbienteBase(); });

  it('carregando: diz que ainda não sabe, e não mostra fila nenhuma', () => {
    vi.spyOn(api, 'listarJobs').mockImplementation(() => new Promise(() => { /* nunca resolve */ }));
    montar();
    expect(screen.getByRole('status', { name: /carregando as publicações/i })).toBeTruthy();
  });

  it('vazio é um FATO, e a tela diz que é diferente de falha', async () => {
    vi.spyOn(api, 'listarJobs').mockResolvedValue({ jobs: [] });
    montar();
    await waitFor(() => expect(screen.getByRole('heading', { name: /nenhuma publicação registrada/i })).toBeTruthy());
    expect(screen.getByText(/quando a api não responde, esta tela mostra outra coisa/i)).toBeTruthy();
  });

  it('indisponível (503) NÃO vira fila vazia', async () => {
    vi.spyOn(api, 'listarJobs').mockRejectedValue(
      new api.ErroDaPublicacao('Não foi possível falar com a publicação agora.', 'publicacao_indisponivel', 503));
    montar();
    await waitFor(() => expect(screen.getByRole('heading', { name: /a publicação não respondeu/i })).toBeTruthy());
    expect(screen.getByText(/vazio e indisponível são fatos diferentes/i)).toBeTruthy();
    expect(screen.queryByRole('heading', { name: /nenhuma publicação registrada/i })).toBeNull();
  });

  it('bloqueado (403) fala de papel, não de sessão', async () => {
    vi.spyOn(api, 'listarJobs').mockRejectedValue(
      new api.ErroDaPublicacao('A publicação orgânica é exclusiva para administradores.', 'sem_permissao', 403));
    montar();
    await waitFor(() => expect(screen.getByRole('heading', { name: /acesso restrito/i })).toBeTruthy());
    expect(screen.getByText(/o papel é que não permite/i)).toBeTruthy();
  });

  it('sem sessão (401) manda entrar de novo, que é outra ação', async () => {
    vi.spyOn(api, 'listarJobs').mockRejectedValue(
      new api.ErroDaPublicacao('Sua sessão expirou.', 'sessao_expirada', 401));
    montar();
    await waitFor(() => expect(screen.getByRole('heading', { name: /sua sessão expirou/i })).toBeTruthy());
  });

  /**
   * ⚠️ O RAMO QUE FALTAVA. A decisão mais citada desta entrega — "a faixa NUNCA
   * fica verde, nem quando `pronto: true`, porque a fonte é um proxy
   * `/integrations` e não um health check" — não tinha teste: o único que
   * existia usava `pronto: false`, que já é warning por outro motivo. O ramo
   * verdadeiro nunca era asseverado, e trocar a classe do ramo `pronto` por
   * `text-success` passava com a suíte inteira verde.
   */
  it('COM control plane pronto a faixa AINDA não fica verde — a fonte é um proxy', async () => {
    vi.spyOn(api, 'listarJobs').mockResolvedValue({ jobs: [] });
    vi.spyOn(api, 'prontidao').mockResolvedValue({
      pronto: true, fonte: 'proxy:/integrations',
      detalhe: 'control plane respondeu', canais_visiveis: 2,
    });
    montar();
    const faixa = await screen.findByText(/isto é um proxy de saúde, não um health check oficial/i);
    const container = faixa.closest('[data-prontidao]') as HTMLElement;

    // O ramo é mesmo o de sucesso da sonda — sem isto o teste poderia estar
    // olhando o warning e passando por engano.
    expect(container.getAttribute('data-prontidao')).toBe('pronta');
    expect(container.textContent).toContain('proxy:/integrations');
    expect(container.textContent).toContain('2 canal(is) visível(is).');

    // E mesmo assim: nenhum token de "deu certo" na faixa.
    expect(temTokenDeSucesso(container.className)).toBe(false);
  });

  it('sem control plane, a faixa de prontidão nunca fica verde e avisa o efeito', async () => {
    vi.spyOn(api, 'listarJobs').mockResolvedValue({ jobs: [] });
    vi.spyOn(api, 'prontidao').mockResolvedValue({
      pronto: false, fonte: 'sem-adaptador', detalhe: 'nenhum control plane configurado neste ambiente',
    });
    montar();
    const faixa = await screen.findByText(/nada pode ser despachado agora/i);
    const container = faixa.closest('[data-prontidao]') as HTMLElement;
    expect(container.getAttribute('data-prontidao')).toBe('indisponivel');
    expect(temTokenDeSucesso(container.className)).toBe(false);
  });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('CONTRAPROVA M — no DOM, com todos os estados', () => {
  beforeEach(() => { comAmbienteBase(); });

  it('nenhum selo de estado incerto carrega token de sucesso', async () => {
    vi.spyOn(api, 'listarJobs').mockResolvedValue({
      jobs: [...ESTADOS.map((e) => job(e)), ...JOBS_HOSTIS],
    });
    montar();
    await waitFor(() => expect(document.querySelectorAll('[data-estado]').length).toBeGreaterThan(0));

    const selos = Array.from(document.querySelectorAll<HTMLElement>('[data-estado]'));
    // A varredura só vale se ela viu todos os estados. Sem esta linha, um
    // filtro acidental na lista faria o teste passar vendo dois cartões.
    const vistos = new Set(selos.map((s) => s.getAttribute('data-estado')));
    for (const estado of ESTADOS) expect(vistos.has(estado), `faltou ${estado}`).toBe(true);

    // ⚠️ A GUARDA CONTRA VACUIDADE. O filtro abaixo só prova alguma coisa se
    // existir no DOM pelo menos um selo em que o servidor PEDIU verde e a tela
    // concluiu incerteza. Sem esta linha, o teste passa mesmo com o veto
    // removido — foi assim que a contraprova nasceu satisfeita por vacuidade.
    const contraditorios = selos.filter((s) =>
      s.getAttribute('data-incerto') === 'true' && s.getAttribute('data-tom-servidor') === 'sucesso');
    expect(contraditorios.length, 'a fixture precisa conter o caso hostil').toBeGreaterThanOrEqual(3);

    const verdesIndevidos = selos
      .filter((s) => s.getAttribute('data-incerto') === 'true' && temTokenDeSucesso(s.className))
      .map((s) => s.getAttribute('data-estado'));
    expect(verdesIndevidos).toEqual([]);
  });

  it('`data-incerto` publica a incerteza EFETIVA, não o eco do backend', async () => {
    // O job `hostil-sem-campo` não traz `leitura.incerto`. Antes, o atributo
    // ecoava o valor cru e saía `false` — e a varredura acima, que filtra por
    // ele, deixava de olhar justamente a linha protegida pelo piso do contrato.
    vi.spyOn(api, 'listarJobs').mockResolvedValue({ jobs: JOBS_HOSTIS });
    montar();
    await waitFor(() => expect(document.querySelectorAll('[data-estado]').length).toBeGreaterThan(0));

    const semCampo = Array.from(document.querySelectorAll<HTMLElement>('[data-estado="indeterminado"]'));
    expect(semCampo.length).toBeGreaterThan(0);
    for (const selo of semCampo) {
      expect(selo.getAttribute('data-incerto-servidor')).toBe('ausente');
      expect(selo.getAttribute('data-incerto')).toBe('true');
      expect(selo.getAttribute('data-tom-servidor')).toBe('sucesso');
      expect(selo.getAttribute('data-tom')).toBe('atencao');
      expect(temTokenDeSucesso(selo.className)).toBe(false);
    }
  });

  it('só `reconciliado` fica verde — e ele é o único com prova fechada', async () => {
    vi.spyOn(api, 'listarJobs').mockResolvedValue({
      jobs: [...ESTADOS.map((e) => job(e)), ...JOBS_HOSTIS],
    });
    montar();
    await waitFor(() => expect(document.querySelectorAll('[data-estado]').length).toBeGreaterThan(0));
    const verdes = Array.from(document.querySelectorAll<HTMLElement>('[data-estado]'))
      .filter((s) => temTokenDeSucesso(s.className))
      .map((s) => s.getAttribute('data-estado'));
    expect(new Set(verdes)).toEqual(new Set(['reconciliado']));
  });

  it('um estado DESCONHECIDO vindo do backend não vira verde', async () => {
    // O cenário real: o backend ganhou um estado que esta versão da tela não
    // conhece, e por descuido mandou tom `sucesso` junto.
    const doFuturo = job('publicado_e_promovido', {
      leitura: { rotulo: 'Tudo certo', tom: 'sucesso', proxima_acao: 'Nada a fazer.', incerto: false, terminal: true },
    });
    vi.spyOn(api, 'listarJobs').mockResolvedValue({ jobs: [doFuturo] });
    montar();
    const selo = await waitFor(() => {
      const achado = document.querySelector<HTMLElement>('[data-estado="publicado_e_promovido"]');
      expect(achado).toBeTruthy();
      return achado!;
    });
    expect(selo.getAttribute('data-tom')).toBe('atencao');
    expect(temTokenDeSucesso(selo.className)).toBe(false);
  });

  it('um backend que se contradiz (incerto + sucesso) também não ganha o verde', async () => {
    const contraditorio = job('indeterminado', {
      leitura: { rotulo: 'Publicado', tom: 'sucesso', proxima_acao: 'Nada.', incerto: true, terminal: true },
    });
    vi.spyOn(api, 'listarJobs').mockResolvedValue({ jobs: [contraditorio] });
    montar();
    const selo = await waitFor(() => {
      const achado = document.querySelector<HTMLElement>('[data-estado="indeterminado"]');
      expect(achado).toBeTruthy();
      return achado!;
    });
    expect(temTokenDeSucesso(selo.className)).toBe(false);
  });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('a frase inteira do job, sem jargão', () => {
  beforeEach(() => { comAmbienteBase(); });

  it('mostra peça, revisão, quem aprovou e quando, destino, modo e horário com o fuso', async () => {
    vi.spyOn(api, 'listarJobs').mockResolvedValue({ jobs: [job('agendado')] });
    montar();
    const inspetor = await screen.findByRole('region', { name: /@volc\.piloto/i });
    const texto = inspetor.textContent ?? '';

    expect(texto).toContain('versão 3');
    expect(texto).toContain('a1b2c3d4e5f6…');            // content_hash abreviado
    expect(texto).toContain('9c1d2e3f…eeff');            // quem aprovou
    expect(texto).toContain('publicacao_organica');      // a finalidade da aprovação
    expect(texto).toContain('Instagram');                // plataforma legível
    expect(texto).toContain('Agendado');                 // modo
    // ⚠️ O horário aparece COM o fuso declarado, e sem passar por `new Date`.
    expect(texto).toContain('10/09/2026 09:30 (America/Sao_Paulo)');
    // A próxima ação é a do servidor, não uma frase inventada aqui.
    expect(texto).toContain('Aguardando o horário.');
  });

  it('quando há recibo, mostra estado no destino e a URL publicada', async () => {
    const publicado = job('reconciliado', {
      recibo: {
        referencia_externa: 'post-991', estado_externo: 'PUBLISHED',
        url_publicada: 'https://instagram.com/p/abc123',
        publicado_em: '2026-09-10T12:31:00+00:00', observado_em: '2026-09-10T12:35:00+00:00',
      },
    });
    vi.spyOn(api, 'listarJobs').mockResolvedValue({ jobs: [publicado] });
    montar();
    const link = await screen.findByRole('link', { name: /abrir a publicação/i });
    expect(link.getAttribute('href')).toBe('https://instagram.com/p/abc123');
    expect(screen.getByText(/publicado \(declarado pelo destino\)/i)).toBeTruthy();
    expect(screen.getByText('post-991')).toBeTruthy();
  });

  it('um job EM VOO não oferece botão nenhum — esperar é a única coisa certa', async () => {
    vi.spyOn(api, 'listarJobs').mockResolvedValue({ jobs: [job('em_voo')] });
    montar();
    const inspetor = await screen.findByRole('region', { name: /@volc\.piloto/i });
    expect(within(inspetor).queryByRole('button', { name: /despachar|publicar|conferir|cancelar/i })).toBeNull();
    expect(within(inspetor).getByText(/nenhuma ação é segura neste estado/i)).toBeTruthy();
    // Aqui "espere" é verdade: o pedido está em trânsito.
    const rodape = inspetor.querySelector('[data-rodape-sem-acao]') as HTMLElement;
    expect(rodape.getAttribute('data-rodape-sem-acao')).toBe('aguardando_destino');
    expect(rodape.textContent).toMatch(/espere a resposta do destino/i);
  });

  /**
   * ⚠️ AS DUAS ORDENS OPOSTAS. Um job em `falha` não tem botão (`acoesDoJob`
   * devolve `[]`) e não é terminal — `aplicacao._com_leitura` só marca terminal
   * `reconciliado` e `cancelado`. O rodapé, que só sabia decidir entre terminal
   * e "espere", mandava "Espere a resposta do destino antes de decidir." três
   * linhas abaixo do `aria-live` que imprimia a próxima ação do servidor: "Leia
   * o erro e crie um job novo — este não é rearmado." Uma das duas frases estava
   * errada, e a errada era a mais confortável de obedecer.
   */
  it('um job em FALHA não recebe duas ordens opostas na mesma tela', async () => {
    const falhou = job('falha', {
      modo: 'now', horario_local: null, instante_utc: null,
      ultimo_erro: 'o destino recusou o token do canal',
    });
    vi.spyOn(api, 'listarJobs').mockResolvedValue({ jobs: [falhou] });
    montar();
    const inspetor = await screen.findByRole('region', { name: /@volc\.piloto/i });

    // A região viva continua imprimindo a instrução do servidor, sem edição.
    const viva = inspetor.querySelector('[aria-live="polite"]') as HTMLElement;
    expect(viva.textContent).toContain('Leia o erro e crie um job novo — este não é rearmado.');

    // E o rodapé não pode contradizê-la: nem mandar esperar…
    const rodape = inspetor.querySelector('[data-rodape-sem-acao]') as HTMLElement;
    expect(rodape.getAttribute('data-rodape-sem-acao')).toBe('falha');
    expect(rodape.textContent).not.toMatch(/espere a resposta do destino/i);
    // …nem afirmar que não há mais nada a fazer, que é o "nada a conferir" de
    // um estado que ainda exige um ato humano.
    expect(rodape.textContent).not.toMatch(/nada a fazer neste job/i);
    expect(rodape.textContent).toMatch(/não é rearmado por nenhum botão desta tela/i);
    expect(within(inspetor).queryByRole('button', { name: /despachar|publicar|conferir|liberar/i })).toBeNull();
  });

  it('um job TERMINAL diz que acabou, e um estado desconhecido não finge que acabou', async () => {
    // `reconciliado` é terminal de verdade: o rodapé pode dizer que acabou.
    vi.spyOn(api, 'listarJobs').mockResolvedValue({ jobs: [job('reconciliado')] });
    const { unmount } = montar();
    let inspetor = await screen.findByRole('region', { name: /@volc\.piloto/i });
    expect((inspetor.querySelector('[data-rodape-sem-acao]') as HTMLElement)
      .getAttribute('data-rodape-sem-acao')).toBe('terminal');
    unmount();

    // ⚠️ Já um estado que este contrato não conhece, com `terminal: true`,
    // NÃO pode virar "Nada a fazer neste job": é o verde proibido em texto.
    const doFuturo = job('publicado_e_promovido', {
      leitura: { rotulo: 'Tudo certo', tom: 'atencao', proxima_acao: 'Confira no painel.', incerto: false, terminal: true },
    });
    vi.spyOn(api, 'listarJobs').mockResolvedValue({ jobs: [doFuturo] });
    montar();
    inspetor = await screen.findByRole('region', { name: /@volc\.piloto/i });
    const rodape = inspetor.querySelector('[data-rodape-sem-acao]') as HTMLElement;
    expect(rodape.getAttribute('data-rodape-sem-acao')).toBe('sem_acao_nesta_tela');
    expect(rodape.textContent).not.toMatch(/nada a fazer neste job/i);
    expect(rodape.textContent).toMatch(/siga a próxima ação descrita acima/i);
  });

  it('aprovação revogada bloqueia liberar, e diz por quê', async () => {
    const revogado = job('rascunho', {
      modo: 'draft', horario_local: null, instante_utc: null,
      aprovacao: {
        id: 'apr-1', ator_id: '9c1d2e3f-0000-4444-8888-aabbccddeeff', finalidade: 'publicacao_organica',
        decidido_em: '2026-09-01T10:00:00+00:00', revogada_em: '2026-09-02T08:00:00+00:00',
      },
    });
    vi.spyOn(api, 'listarJobs').mockResolvedValue({ jobs: [revogado] });
    montar();
    const botao = await screen.findByRole('button', { name: /liberar para despacho/i });
    expect(botao.hasAttribute('disabled')).toBe(true);
    expect(screen.getByText(/a aprovação deste job foi revogada/i)).toBeTruthy();
  });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('destino inapto', () => {
  beforeEach(() => {
    comAmbienteBase();
    vi.spyOn(api, 'listarJobs').mockResolvedValue({ jobs: [] });
  });

  it('aparece na lista, desabilitado, COM o motivo — nunca filtrado para fora', async () => {
    montar();
    const linha = await waitFor(() => {
      const achado = document.querySelector<HTMLElement>('[data-destino="dest-inapto"]');
      expect(achado).toBeTruthy();
      return achado!;
    });
    expect(linha.getAttribute('data-apto')).toBe('false');
    expect(linha.textContent).toContain('sem adapter oficial para Threads neste provedor');

    // E a opção do seletor está desabilitada, com o motivo no próprio rótulo.
    const seletor = screen.getByLabelText(/^destino$/i) as HTMLSelectElement;
    const opcao = Array.from(seletor.options).find((o) => o.value === 'dest-inapto')!;
    expect(opcao.disabled).toBe(true);
    expect(opcao.textContent).toContain('sem adapter oficial');
  });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('confirmação humana — agendar e publicar agora são atos diferentes', () => {
  beforeEach(() => {
    comAmbienteBase();
    vi.spyOn(api, 'listarJobs').mockResolvedValue({ jobs: [] });
  });

  async function preencher(modo: 'schedule' | 'now') {
    montar();
    await screen.findByLabelText(/^destino$/i);
    fireEvent.change(screen.getByLabelText(/peça aprovada/i), { target: { value: 'peca-1' } });
    fireEvent.change(screen.getByLabelText(/aprovação \(identificador\)/i), { target: { value: 'apr-1' } });
    fireEvent.change(screen.getByLabelText(/^destino$/i), { target: { value: 'dest-apto' } });
    fireEvent.change(screen.getByLabelText(/texto que vai ao ar/i), { target: { value: 'olá mundo' } });
    fireEvent.click(screen.getByRole('button', { name: modo === 'now' ? 'Publicar agora' : 'Agendado' }));
    if (modo === 'schedule') {
      fireEvent.change(await screen.findByLabelText(/horário local/i), { target: { value: '2026-09-10 09:30' } });
    }
  }

  it('agendar abre uma confirmação, e nada é criado antes do sim', async () => {
    const criar = vi.spyOn(api, 'criarJob').mockResolvedValue({ job_id: 'novo', estado: 'rascunho' });
    await preencher('schedule');
    fireEvent.click(screen.getByRole('button', { name: /revisar antes de agendar/i }));

    const dialogo = await screen.findByRole('dialog', { name: /confirmar agendamento/i });
    expect(criar).not.toHaveBeenCalled();
    // A confirmação diz O QUE vai acontecer, com canal e horário.
    expect(dialogo.textContent).toContain('@volc.piloto');
    expect(dialogo.textContent).toContain('10/09/2026 09:30 (America/Sao_Paulo)');

    fireEvent.click(within(dialogo).getByRole('button', { name: /^agendar$/i }));
    await waitFor(() => expect(criar).toHaveBeenCalledTimes(1));
    const enviado = criar.mock.calls[0][0];
    expect(enviado.modo).toBe('schedule');
    expect(enviado.horario_local).toBe('2026-09-10 09:30');
    // ⚠️ Agendar nunca carrega consentimento de publicação imediata.
    expect(enviado.confirmo_publicacao_imediata).toBe(false);
  });

  it('publicar agora exige uma confirmação SEPARADA, mais forte, e uma caixa marcada', async () => {
    const criar = vi.spyOn(api, 'criarJob').mockResolvedValue({ job_id: 'novo', estado: 'rascunho' });
    await preencher('now');
    fireEvent.click(screen.getByRole('button', { name: /revisar antes de publicar agora/i }));

    const dialogo = await screen.findByRole('dialog', { name: /publicar agora, para o público/i });
    // O texto do que vai acontecer, não um "tem certeza?".
    expect(dialogo.textContent).toContain('Publica imediatamente');
    expect(dialogo.textContent).toContain('não há desfazer que devolva quem já viu');

    const confirmar = within(dialogo).getByRole('button', { name: /sim, publicar agora/i });
    expect(confirmar.hasAttribute('disabled')).toBe(true);
    fireEvent.click(confirmar);
    expect(criar).not.toHaveBeenCalled();

    const caixa = within(dialogo).getByLabelText(/confirmo a publicação imediata/i) as HTMLInputElement;
    expect(caixa.checked).toBe(false); // ⚠️ nunca marcada por padrão
    fireEvent.click(caixa);
    expect(confirmar.hasAttribute('disabled')).toBe(false);

    fireEvent.click(confirmar);
    await waitFor(() => expect(criar).toHaveBeenCalledTimes(1));
    expect(criar.mock.calls[0][0].confirmo_publicacao_imediata).toBe(true);
  });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('o corpo que sai para a API', () => {
  it('`confirmo_publicacao_imediata` só existe no corpo quando o humano marcou', () => {
    const base = {
      peca_id: 'p', peca_versao: 1, autorizacao_id: 'a', destino_id: 'd',
      timezone: 'America/Sao_Paulo', texto: 'oi',
    };
    // Marcado e em `now`: o campo existe, e é `true`.
    expect(api.corpoDoPedido({ ...base, modo: 'now', confirmo_publicacao_imediata: true }))
      .toHaveProperty('confirmo_publicacao_imediata', true);
    // Não marcado: o campo não existe. Não é `false` — é ausente.
    expect(api.corpoDoPedido({ ...base, modo: 'now', confirmo_publicacao_imediata: false }))
      .not.toHaveProperty('confirmo_publicacao_imediata');
    // ⚠️ Marcado FORA do `now`: o campo continua ausente. O backend recusaria a
    // combinação (`consentimento_sem_now`), e um estado esquecido no formulário
    // não pode virar consentimento herdado.
    expect(api.corpoDoPedido({ ...base, modo: 'draft', confirmo_publicacao_imediata: true }))
      .not.toHaveProperty('confirmo_publicacao_imediata');
    expect(api.corpoDoPedido({ ...base, modo: 'schedule', horario_local: '2026-09-10 09:30', confirmo_publicacao_imediata: true }))
      .not.toHaveProperty('confirmo_publicacao_imediata');
  });

  it('`horario_local` só existe em `schedule`', () => {
    const base = {
      peca_id: 'p', peca_versao: 1, autorizacao_id: 'a', destino_id: 'd',
      timezone: 'America/Sao_Paulo', texto: 'oi', horario_local: '2026-09-10 09:30',
    };
    expect(api.corpoDoPedido({ ...base, modo: 'schedule' }))
      .toHaveProperty('horario_local', '2026-09-10 09:30');
    expect(api.corpoDoPedido({ ...base, modo: 'draft' })).not.toHaveProperty('horario_local');
    expect(api.corpoDoPedido({ ...base, modo: 'now' })).not.toHaveProperty('horario_local');
  });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('a revisão exata — versão e horário são recusados ANTES do sim', () => {
  beforeEach(() => {
    comAmbienteBase();
    vi.spyOn(api, 'listarJobs').mockResolvedValue({ jobs: [] });
  });

  /** Preenche o mínimo válido e devolve o formulário, para submeter à mão. */
  async function formularioPreenchido(): Promise<HTMLElement> {
    montar();
    await screen.findByLabelText(/^destino$/i);
    fireEvent.change(screen.getByLabelText(/peça aprovada/i), { target: { value: 'peca-1' } });
    fireEvent.change(screen.getByLabelText(/aprovação \(identificador\)/i), { target: { value: 'apr-1' } });
    fireEvent.change(screen.getByLabelText(/^destino$/i), { target: { value: 'dest-apto' } });
    fireEvent.change(screen.getByLabelText(/texto que vai ao ar/i), { target: { value: 'olá mundo' } });
    return screen.getByRole('form', { name: /nova publicação orgânica/i });
  }

  /**
   * ⚠️ O defeito medido: `paraPedido` fazia `Math.max(1, parseInt(v, 10) || 1)`
   * e `peca_versao` não estava nos bloqueadores. Com o campo vazio, o diálogo
   * mostrava "versão " e o corpo saía com `peca_versao: 1` — outra revisão,
   * carimbada com a aprovação que cobria a revisão certa.
   */
  it('versão vazia BLOQUEIA o envio em vez de virar 1 em silêncio', async () => {
    const criar = vi.spyOn(api, 'criarJob').mockResolvedValue({ job_id: 'novo', estado: 'rascunho' });
    const formulario = await formularioPreenchido();
    fireEvent.change(screen.getByLabelText(/versão da peça/i), { target: { value: '' } });

    expect(screen.getByText(/informe a versão da peça/i)).toBeTruthy();
    const enviar = screen.getByRole('button', { name: /criar rascunho/i });
    expect(enviar.hasAttribute('disabled')).toBe(true);

    // E o guarda não é só o `disabled`: submeter o formulário à mão (Enter num
    // campo, um teste de automação) também não cria nada.
    fireEvent.submit(formulario);
    await waitFor(() => expect(criar).not.toHaveBeenCalled());
  });

  it('versão 0 e versão fracionária são recusadas — a aprovação cobre um inteiro', async () => {
    const criar = vi.spyOn(api, 'criarJob').mockResolvedValue({ job_id: 'novo', estado: 'rascunho' });
    const formulario = await formularioPreenchido();
    for (const valor of ['0', '2.5']) {
      fireEvent.change(screen.getByLabelText(/versão da peça/i), { target: { value: valor } });
      expect(screen.getByText(/informe a versão da peça/i), valor).toBeTruthy();
      fireEvent.submit(formulario);
    }
    await waitFor(() => expect(criar).not.toHaveBeenCalled());

    // Com um inteiro válido, o mesmo formulário envia — e envia o que foi digitado.
    fireEvent.change(screen.getByLabelText(/versão da peça/i), { target: { value: '7' } });
    expect(screen.queryByText(/informe a versão da peça/i)).toBeNull();
    fireEvent.submit(formulario);
    await waitFor(() => expect(criar).toHaveBeenCalledTimes(1));
    expect(criar.mock.calls[0][0].peca_versao).toBe(7);
  });

  /**
   * ⚠️ O horário era conferido só por "está vazio?". "amanhã cedo" abria o
   * diálogo, aparecia nele no lugar do horário e colhia o "sim" humano — o 400
   * `horario_invalido` só chegava DEPOIS do consentimento dado.
   */
  it('horário mal formado bloqueia ANTES da confirmação, e nenhum diálogo abre', async () => {
    const criar = vi.spyOn(api, 'criarJob').mockResolvedValue({ job_id: 'novo', estado: 'rascunho' });
    const formulario = await formularioPreenchido();
    fireEvent.click(screen.getByRole('button', { name: 'Agendado' }));
    fireEvent.change(await screen.findByLabelText(/horário local/i), { target: { value: 'amanhã cedo' } });

    expect(screen.getByText(/o horário local precisa ser AAAA-MM-DD HH:MM/i)).toBeTruthy();
    expect(screen.getByRole('button', { name: /revisar antes de agendar/i }).hasAttribute('disabled')).toBe(true);
    fireEvent.submit(formulario);
    expect(screen.queryByRole('dialog')).toBeNull();
    await waitFor(() => expect(criar).not.toHaveBeenCalled());
  });

  it('data que não existe no calendário também não chega à confirmação', async () => {
    const formulario = await formularioPreenchido();
    fireEvent.click(screen.getByRole('button', { name: 'Agendado' }));
    fireEvent.change(await screen.findByLabelText(/horário local/i), { target: { value: '2026-02-30 10:00' } });
    expect(screen.getByText(/precisa existir no calendário/i)).toBeTruthy();
    fireEvent.submit(formulario);
    expect(screen.queryByRole('dialog')).toBeNull();

    // E a forma correta passa: o bloqueio é do horário impossível, não do campo.
    fireEvent.change(screen.getByLabelText(/horário local/i), { target: { value: '2026-09-10 09:30' } });
    expect(screen.queryByText(/precisa existir no calendário/i)).toBeNull();
    fireEvent.submit(formulario);
    expect(await screen.findByRole('dialog', { name: /confirmar agendamento/i })).toBeTruthy();
  });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('paraPedido — nada é normalizado em silêncio', () => {
  const rascunho = {
    peca_id: ' peca-1 ', peca_versao: '3', autorizacao_id: ' apr-1 ', destino_id: 'dest-apto',
    modo: 'draft' as const, timezone: 'America/Sao_Paulo', horario_local: '', texto: 'olá',
  };

  it('leva a versão que foi digitada, sem piso nem arredondamento', () => {
    expect(api.paraPedido({ ...rascunho, peca_versao: '12' }, false).peca_versao).toBe(12);
    expect(api.paraPedido({ ...rascunho, peca_versao: ' 4 ' }, false).peca_versao).toBe(4);
  });

  it('LEVANTA em vez de escolher uma revisão no lugar do humano', () => {
    // ⚠️ Este é o coração do defeito: `Math.max(1, parseInt('') || 1)` devolvia
    // 1 para todos estes casos, sem que nada na tela dissesse isso.
    for (const valor of ['', '   ', '0', '-2', 'abc', '2.5']) {
      expect(() => api.paraPedido({ ...rascunho, peca_versao: valor }, false), valor)
        .toThrow(/versão da peça inválida/i);
    }
  });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('acessibilidade', () => {
  beforeEach(() => { comAmbienteBase(); });

  it('o estado do job vive numa região viva, com o rótulo e a próxima ação do servidor', async () => {
    vi.spyOn(api, 'listarJobs').mockResolvedValue({ jobs: [job('indeterminado')] });
    montar();
    await screen.findByRole('region', { name: /@volc\.piloto/i });

    const vivas = Array.from(document.querySelectorAll<HTMLElement>('[aria-live="polite"]'));
    const doEstado = vivas.find((v) => (v.textContent ?? '').includes('Indeterminado'));
    expect(doEstado, 'o estado precisa estar numa região aria-live').toBeTruthy();
    expect(doEstado!.getAttribute('role')).toBe('status');
    expect(doEstado!.textContent).toContain('Reconcilie antes de tentar de novo');
  });

  it('cada campo do formulário tem label associada — inclusive o texto que vai ao ar', async () => {
    vi.spyOn(api, 'listarJobs').mockResolvedValue({ jobs: [] });
    montar();
    const area = await screen.findByLabelText(/texto que vai ao ar/i);
    expect(area.tagName).toBe('TEXTAREA');
    expect(area.getAttribute('id')).toBe('texto');
    // A ajuda está associada, não apenas próxima visualmente.
    expect(area.getAttribute('aria-describedby')).toBe('texto-ajuda');
    expect(document.getElementById('texto-ajuda')?.textContent).toMatch(/imagem exige upload/i);
  });

  it('o diálogo de confirmação é navegável por teclado: Escape fecha sem publicar', async () => {
    const criar = vi.spyOn(api, 'criarJob').mockResolvedValue({ job_id: 'novo', estado: 'rascunho' });
    vi.spyOn(api, 'listarJobs').mockResolvedValue({ jobs: [] });
    montar();
    await screen.findByLabelText(/^destino$/i);
    fireEvent.change(screen.getByLabelText(/peça aprovada/i), { target: { value: 'peca-1' } });
    fireEvent.change(screen.getByLabelText(/aprovação \(identificador\)/i), { target: { value: 'apr-1' } });
    fireEvent.change(screen.getByLabelText(/^destino$/i), { target: { value: 'dest-apto' } });
    fireEvent.change(screen.getByLabelText(/texto que vai ao ar/i), { target: { value: 'olá' } });
    fireEvent.click(screen.getByRole('button', { name: 'Publicar agora' }));
    fireEvent.click(screen.getByRole('button', { name: /revisar antes de publicar agora/i }));

    const dialogo = await screen.findByRole('dialog');
    // O foco entra no painel para que o título e a consequência sejam lidos
    // antes de qualquer botão.
    expect(document.activeElement).toBe(dialogo);

    fireEvent.keyDown(dialogo, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(criar).not.toHaveBeenCalled();
  });

  it('o Tab circula dentro do diálogo em vez de escapar para o formulário atrás', async () => {
    vi.spyOn(api, 'listarJobs').mockResolvedValue({ jobs: [] });
    montar();
    await screen.findByLabelText(/^destino$/i);
    fireEvent.change(screen.getByLabelText(/peça aprovada/i), { target: { value: 'peca-1' } });
    fireEvent.change(screen.getByLabelText(/aprovação \(identificador\)/i), { target: { value: 'apr-1' } });
    fireEvent.change(screen.getByLabelText(/^destino$/i), { target: { value: 'dest-apto' } });
    fireEvent.change(screen.getByLabelText(/texto que vai ao ar/i), { target: { value: 'olá' } });
    fireEvent.click(screen.getByRole('button', { name: 'Publicar agora' }));
    fireEvent.click(screen.getByRole('button', { name: /revisar antes de publicar agora/i }));

    const dialogo = await screen.findByRole('dialog');
    // Mesma definição de "focável" que o componente usa: um botão desabilitado
    // (Confirmar, enquanto a caixa não foi marcada) não entra no ciclo.
    const focaveis = Array.from(
      dialogo.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled])'));
    const ultimo = focaveis[focaveis.length - 1];
    ultimo.focus();
    fireEvent.keyDown(dialogo, { key: 'Tab' });
    expect(document.activeElement).toBe(focaveis[0]);

    focaveis[0].focus();
    fireEvent.keyDown(dialogo, { key: 'Tab', shiftKey: true });
    expect(document.activeElement).toBe(ultimo);
  });
});
