// @vitest-environment jsdom

/**
 * O Cofre de Ativos contra a API — e contra a tentação de mentir quando ela cai.
 *
 * A prova central deste arquivo não é que a tela mostra o inventário: é que ela
 * NÃO mostra a fixture quando a API falha. Até 01/09/2026 `fixtures.ts` era a
 * única fonte, e uma tela que sempre mostra os mesmos oito ativos não distingue
 * "o Cofre está vazio" de "o Cofre não respondeu" — porque nunca esteve vazio
 * nem deixou de responder. Se alguém reintroduzir a fixture como fallback "para
 * a tela não ficar feia", os testes de indisponibilidade caem.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import * as React from "react";

vi.mock("@/lib/supabase", () => ({ supabase: { auth: { getSession: async () => ({ data: { session: { access_token: "t" } } }) } } }));
vi.mock("@/hooks/use-toast", () => ({ useToast: () => ({ toast: vi.fn() }) }));

import * as cofre from "../cofreApi";
import { AssetVaultContent } from "../AssetVaultContent";
import { INITIAL_ASSETS } from "../fixtures";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

const GAVETAS: cofre.GavetaDoCofre[] = [
  { cluster: "social_presence", rotulo: "Presenças sociais", descricao: "Perfis e páginas.", ordem: 1, total: 1 },
  { cluster: "paid_media", rotulo: "Mídia paga", descricao: "Contas que compram mídia.", ordem: 2, total: 0 },
  { cluster: "web_properties", rotulo: "Sites e domínios", descricao: "Domínios e sites.", ordem: 3, total: 0 },
  { cluster: "communities", rotulo: "Comunidades e mensagens", descricao: "WhatsApp e Telegram.", ordem: 4, total: 0 },
  { cluster: "creative_production", rotulo: "Produção criativa", descricao: "Engines criativos.", ordem: 5, total: 1 },
  { cluster: "automation", rotulo: "Automações e integrações", descricao: "Workflows.", ordem: 6, total: 0 },
  { cluster: "infrastructure", rotulo: "Infraestrutura e dados", descricao: "Bancos e servidores.", ordem: 7, total: 0 },
];

const PAGINA: cofre.AtivoDaLista = {
  ativo_id: "asset:facebook-page:piloto", nome: "Página monetizada do piloto",
  kind: "facebook_page", tipo_rotulo: "Página do Facebook", cluster: "social_presence",
  plataforma: "Meta", estado: "declared", criticidade: "high",
  resumo: "Página declarada pelo dono, sem identidade técnica conferida.",
  dono_nome: "Tarcisio", dono_custodia: "declared", tags: ["piloto"],
  proxima_acao: "Conferir ID da página e Business Portfolio.", revisao_atual: 1,
  relacoes: [{ tipo: "produces_for", destino: "cap:organic-content", rotulo: "Operação de conteúdo orgânico", estado: "declared" }],
  credencial_registrada: false, verificacao_estado: "unverified",
};

const ENGINE: cofre.AtivoDaLista = {
  ativo_id: "asset:engine:motor-video-volc", nome: "Motor de Vídeo VOLC",
  kind: "creative_engine", tipo_rotulo: "Engine criativo", cluster: "creative_production",
  plataforma: "VOLC", estado: "ready", criticidade: "medium",
  resumo: "Engine de vídeo catalogado, com runtime fora do VOLC O.S.",
  dono_nome: "VOLC", dono_custodia: "verified", tags: ["video"],
  proxima_acao: "Criar adapter e fila no VOLC O.S.", revisao_atual: 1,
  relacoes: [], credencial_registrada: true, verificacao_estado: "verified",
  verificado_em: "2026-08-26T12:00:00Z",
};

const DETALHE: cofre.DetalheDoAtivo = {
  ...PAGINA, gaveta_rotulo: "Presenças sociais", localizacao_rotulo: null,
  capacidades: ["Publicação orgânica"], criado_em: "2026-09-01T10:00:00Z",
  atualizado_em: "2026-09-01T10:00:00Z", engine: null,
  credencial: [], verificacao: [], historico: [
    { revisao: 1, operacao: "cadastro", motivo: "cadastro pela tela", autor_email: "admin@volc", ocorrido_em: "2026-09-01T10:00:00Z" },
  ],
};

/**
 * A prontidão do inspetor, na forma que o backend produz.
 *
 * ⚠️ Ela é mockada em `comInventario` de propósito. Sem isso, cada teste que
 * abre o inspetor faria a consulta real cair no estado "não configurado" — o
 * que não quebraria nada hoje, mas transformaria a saída de todos eles num
 * painel de erro, e a próxima pessoa leria isso como defeito da tela.
 */
const PRONTIDAO: cofre.ProntidaoDoAtivo = {
  ativo_id: PAGINA.ativo_id,
  perguntas: {
    pagina_de_destino: { valor: "sim", motivo: "Página monetizada do piloto (facebook_page)", procedencia: "registro" },
    dono: { valor: "sim", motivo: "Tarcisio — custodia declarada, nao conferida", procedencia: "registro" },
    ativos_relacionados: { valor: "sim", motivo: "1 relacao(oes) declarada(s)", procedencia: "registro" },
    perfil_de_navegador: { valor: "nao", motivo: "nenhuma aresta authenticates_through declarada", procedencia: "registro" },
    onde_esta_a_credencial: { valor: "nao", motivo: "nenhuma referencia de acesso registrada", procedencia: "registro" },
    referencia_resolvivel: { valor: "nao", motivo: "nao ha referencia para resolver", procedencia: "registro" },
    perfil_disponivel: { valor: "nao", motivo: "nao ha perfil relacionado para consultar", procedencia: "registro" },
    peca_roteavel: { valor: "nao", motivo: "nenhuma referencia de acesso registrada", procedencia: "registro" },
  },
  retrato: {
    estado: "declared", criticidade: "high", dono_nome: "Tarcisio", dono_custodia: "declared",
    finalidade: "Conferir ID da página e Business Portfolio.", revisao_atual: 1,
    atualizado_em: "2026-09-01T10:00:00Z", ultima_revisao_em: null,
    ultima_revisao_resultado: null, aposentado_em: null,
  },
  producao_possivel: [],
  componentes_seguintes: {
    porta_de_publicacao: { tarefa: "P12-T09", estado: "todo" },
    broker_de_acesso: { tarefa: "P03-T11", implementacao: "local_verified", operacao_real: "live_read_not_proven" },
  },
  pronto_para_receber_peca: true,
  pronto_para_operar_acesso: false,
  pronto_para_publicar: false,
  bloqueios: ["nao existe porta de publicacao no VOLC (P12-T09): nenhuma peca aprovada tem por onde sair"],
  bloqueios_por_portao: {
    recebimento: [],
    acesso: ["nenhum perfil de navegador relacionado"],
    publicacao: ["nao existe porta de publicacao no VOLC (P12-T09): nenhuma peca aprovada tem por onde sair"],
  },
  publica: false,
};

function mount(entrada = "/settings/cofre-ativos") {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(
    <QueryClientProvider client={cliente}>
      <MemoryRouter initialEntries={[entrada]}><AssetVaultContent /></MemoryRouter>
    </QueryClientProvider>,
  );
}

function comInventario(ativos: cofre.AtivoDaLista[], gavetas = GAVETAS) {
  vi.spyOn(cofre, "cofreConfigurado").mockReturnValue(true);
  vi.spyOn(cofre, "inventario").mockResolvedValue({ gavetas, ativos });
  vi.spyOn(cofre, "detalhe").mockResolvedValue(DETALHE);
  vi.spyOn(cofre, "prontidao").mockResolvedValue(PRONTIDAO);
  vi.spyOn(cofre, "prontidaoVisual").mockResolvedValue({
    ativo_id: PAGINA.ativo_id,
    destino: {},
    pagina: { presente: true, motivo: "" },
    referencia_de_credencial: {
      presente: false, verificada: false, provider: null, nome_logico: null,
      verificacao_estado: null, verificado_em: null,
    },
    perfil_de_navegador: { presente: false, rotulo: null, ativo_id: null },
    broker: { estado: "nao_configurado", motivo: "" },
    qa_visual: { estado: "nao_persistido", motivo: "", job: null, veredito: null, artefato: null },
    pronto_para_receber_peca: true,
    pronto_para_publicar: false,
    pronto_para_qa: false,
    bloqueios: [],
    bloqueios_do_cofre: [],
    proxima_acao: "Registrar referência de acesso.",
  } as cofre.ProntidaoVisualPayload);
}

describe("Cofre de Ativos — os estados que não são dado", () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.spyOn(cofre, "cofreConfigurado").mockReturnValue(true);
  });

  it("mostra carregamento enquanto não sabe", () => {
    vi.spyOn(cofre, "inventario").mockImplementation(() => new Promise(() => { /* nunca resolve */ }));
    mount();
    expect(screen.getByRole("status", { name: /carregando o inventário/i })).toBeTruthy();
  });

  it("indisponibilidade NÃO vira inventário vazio, e NÃO cai para a fixture", async () => {
    vi.spyOn(cofre, "inventario").mockRejectedValue(
      new cofre.ErroDoCofre("Não foi possível falar com o Cofre agora.", "cofre_indisponivel", 503));
    mount();
    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy());
    expect(screen.getByRole("heading", { name: /o cofre não respondeu/i })).toBeTruthy();
    expect(screen.getByText(/vazio e indisponível são fatos diferentes/i)).toBeTruthy();
    // A prova de que a fixture não é fallback: nenhum nome dela aparece.
    for (const ativo of INITIAL_ASSETS) {
      expect(screen.queryByText(ativo.name)).toBeNull();
    }
  });

  it("403 fala de papel, não de sessão", async () => {
    vi.spyOn(cofre, "inventario").mockRejectedValue(
      new cofre.ErroDoCofre("O Cofre é exclusivo para administradores.", "sem_permissao", 403));
    mount();
    await waitFor(() => expect(screen.getByRole("heading", { name: /acesso restrito/i })).toBeTruthy());
    expect(screen.getByText(/o papel é que não permite/i)).toBeTruthy();
  });

  it("401 manda entrar de novo, que é outra ação", async () => {
    vi.spyOn(cofre, "inventario").mockRejectedValue(
      new cofre.ErroDoCofre("Sua sessão expirou.", "sessao_expirada", 401));
    mount();
    await waitFor(() => expect(screen.getByRole("heading", { name: /sua sessão expirou/i })).toBeTruthy());
  });

  it("ambiente sem VITE_PAUTADOR_API_URL é configuração, não ausência de dado", async () => {
    vi.spyOn(cofre, "cofreConfigurado").mockReturnValue(false);
    const espiao = vi.spyOn(cofre, "inventario");
    mount();
    expect(screen.getByRole("heading", { name: /não está configurado/i })).toBeTruthy();
    expect(espiao).not.toHaveBeenCalled();
  });

  it("vazio de verdade mostra a ESTRUTURA, não uma página em branco", async () => {
    comInventario([], GAVETAS.map((g) => ({ ...g, total: 0 })));
    mount();
    await waitFor(() => expect(screen.getByText(/o cofre está vazio/i)).toBeTruthy());
    // As sete gavetas continuam visíveis com contagem zero.
    expect(screen.getByRole("button", { name: /Presenças sociais 0/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Infraestrutura e dados 0/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /cadastrar o primeiro ativo/i })).toBeTruthy();
    expect(screen.getByText("Sem amostra")).toBeTruthy();
    expect(screen.getAllByText("sem amostra").length).toBeGreaterThan(0);
  });
});

describe("Cofre de Ativos — inventário real", () => {
  beforeEach(() => { sessionStorage.clear(); comInventario([PAGINA, ENGINE]); });

  it("abre por gavetas, com a contagem que veio do servidor", async () => {
    mount();
    await waitFor(() => expect(screen.getByRole("heading", { name: "Cofre de Ativos" })).toBeTruthy());
    expect(screen.getByRole("button", { name: /Presenças sociais 1/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Mídia paga 0/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Produção criativa 1/ })).toBeTruthy();
    expect(screen.getByText("Zero segredo neste contrato")).toBeTruthy();
  });

  it("filtra uma gaveta vazia sem inventar ativo", async () => {
    mount();
    await waitFor(() => expect(screen.getByRole("button", { name: /Mídia paga 0/ })).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: /Mídia paga 0/ }));
    expect(screen.getByText(/nenhum ativo neste recorte/i)).toBeTruthy();
    expect(screen.getByText(/o inventário não foi alterado/i)).toBeTruthy();
  });

  it("busca e abre o detalhe pelo endpoint, não por dado local", async () => {
    mount();
    await waitFor(() => expect(screen.getByPlaceholderText(/buscar ativo/i)).toBeTruthy());
    fireEvent.change(screen.getByPlaceholderText(/buscar ativo/i), { target: { value: "Motor" } });
    expect(screen.getByText("1 de 2")).toBeTruthy();
    // A busca filtra a LISTA. O inspetor continua no ativo selecionado, e isso
    // é o certo: filtrar não é desselecionar, e limpar o detalhe a cada tecla
    // faria a pessoa perder o que estava lendo.
    const lista = screen.getByRole("region", { name: /ativos encontrados/i });
    expect(within(lista).queryByText("Página monetizada do piloto")).toBeNull();
    expect(within(lista).getByText("Motor de Vídeo VOLC")).toBeTruthy();
    expect(cofre.detalhe).toHaveBeenCalled();
  });

  it("as quatro lentes existem e cada uma muda a tela", async () => {
    mount();
    await waitFor(() => expect(screen.getByRole("button", { name: /^Inventário$/ })).toBeTruthy());

    fireEvent.click(screen.getByRole("button", { name: /^Revisões$/ }));
    await waitFor(() => expect(screen.getByRole("heading", { name: /o que o inventário está devendo/i })).toBeTruthy());
    expect(screen.getByText(/nenhuma referência de acesso registrada/i)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /^Relações$/ }));
    await waitFor(() => expect(screen.getByRole("heading", { name: /relações declaradas/i })).toBeTruthy());
    // A aresta aparece na lente E no inspetor do ativo selecionado — as duas
    // são legítimas, então a asserção é escopada à lente.
    const lente = screen.getByRole("region", { name: /relações declaradas/i });
    expect(within(lente).getByText("Operação de conteúdo orgânico")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /^Contrato$/ }));
    await waitFor(() => expect(screen.getByRole("heading", { name: /o que um ativo precisa provar/i })).toBeTruthy());
    expect(screen.getByRole("heading", { name: /tipos organizados por gaveta/i })).toBeTruthy();
    expect(screen.getByText("Business Portfolio Meta")).toBeTruthy();
  });

  it("a postura de acesso aparece sem segredo e sem endereço", async () => {
    vi.spyOn(cofre, "detalhe").mockResolvedValue({
      ...DETALHE,
      credencial: [{
        referencia_id: 1, provider: "1password", nome_logico: "FB_PAGE_ADMIN",
        finalidade: "Acesso administrativo à página do piloto", owner_nome: "Tarcisio",
        estado: "referenced", verificacao_estado: "unverified", referencia_registrada: true,
      }],
    });
    const { container } = mount();
    await waitFor(() => expect(screen.getByText("FB_PAGE_ADMIN")).toBeTruthy());
    expect(screen.getByText(/acesso administrativo à página do piloto/i)).toBeTruthy();
    // A tela precisa DIZER que o endereço não é exibido — e não exibi-lo.
    expect(screen.getByText(/não é exibido nem devolvido por esta tela/i)).toBeTruthy();
    expect(container.textContent).not.toContain("op://");
  });
});

describe("Cofre de Ativos — a fronteira do segredo na tela", () => {
  beforeEach(() => { sessionStorage.clear(); comInventario([PAGINA]); });

  it("o formulário de referência manda o localizador e não o mostra de volta", async () => {
    const enviar = vi.spyOn(cofre, "referenciarCredencial")
      .mockResolvedValue({ operacao: "cofre.referenciar_credencial", ativo_id: PAGINA.ativo_id, idempotente: false });
    const { container } = mount();
    await waitFor(() => expect(screen.getByRole("button", { name: /registrar referência de acesso/i })).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: /registrar referência de acesso/i }));

    fireEvent.change(screen.getByPlaceholderText("FB_PAGE_ADMIN"), { target: { value: "FB_PAGE_ADMIN" } });
    fireEvent.change(screen.getByPlaceholderText("VOLC"), { target: { value: "VOLC" } });
    fireEvent.change(screen.getByPlaceholderText("Pagina do piloto"), { target: { value: "Pagina Piloto" } });
    fireEvent.change(screen.getByPlaceholderText("credential"), { target: { value: "credential" } });
    const campos = container.querySelectorAll("form input");
    fireEvent.change(campos[campos.length - 2], { target: { value: "Tarcisio" } });
    fireEvent.change(campos[campos.length - 1], { target: { value: "Acesso administrativo à página" } });
    fireEvent.submit(container.querySelector("form")!);

    await waitFor(() => expect(enviar).toHaveBeenCalled());
    const corpo = enviar.mock.calls[0][1] as Record<string, unknown>;
    expect(corpo.localizador).toBe("op://VOLC/Pagina%20Piloto/credential");
    expect(String(corpo.chave_idempotencia).length).toBeGreaterThanOrEqual(8);
  });

  it("a chave de idempotência é DERIVADA do ato, não sorteada", () => {
    const a = cofre.chaveDoAto("cadastro", "asset:x:y");
    const b = cofre.chaveDoAto("cadastro", "asset:x:y");
    const c = cofre.chaveDoAto("cadastro", "asset:outro:z");
    // Sorteá-la faria o segundo clique de quem achou que o primeiro não pegou
    // valer como operação nova.
    expect(a).toBe(b);
    expect(a).not.toBe(c);
    expect(a).toMatch(/^[A-Za-z0-9._:-]{8,120}$/);
  });

  it("o formulário de cadastro deriva a gaveta do tipo, sem oferecer a contradição", async () => {
    const enviar = vi.spyOn(cofre, "cadastrarAtivo")
      .mockResolvedValue({ operacao: "cofre.cadastrar_ativo", ativo_id: "asset:website:novo", revisao: 1, idempotente: false });
    const { container } = mount();
    await waitFor(() => expect(screen.getByRole("button", { name: /cadastrar ativo/i })).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: /cadastrar ativo/i }));
    const selects = container.querySelectorAll("form select");
    fireEvent.change(selects[0], { target: { value: "website" } });
    await waitFor(() => expect(screen.getByText(/Gaveta: Sites e domínios/)).toBeTruthy());
    expect(enviar).not.toHaveBeenCalled();
  });
  it("aposentar pede consequência explícita antes de mutar", async () => {
    const enviar = vi.spyOn(cofre, "aposentar")
      .mockResolvedValue({ operacao: "cofre.aposentar", ativo_id: PAGINA.ativo_id, revisao: 2, idempotente: false });
    mount();
    await waitFor(() => expect(screen.getByRole("button", { name: /^Aposentar$/ })).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: /^Aposentar$/ }));
    expect(enviar).not.toHaveBeenCalled();
    expect(screen.getByText(/permanece no inventário/i)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /confirmar aposentadoria/i }));
    await waitFor(() => expect(enviar).toHaveBeenCalled());
  });

  it("a revisão manda só o que MUDOU, e a chave distingue revisões diferentes", async () => {
    const enviar = vi.spyOn(cofre, "revisarAtivo")
      .mockResolvedValue({ operacao: "cofre.revisar_ativo", ativo_id: PAGINA.ativo_id, revisao: 2, idempotente: false });
    const { container } = mount();
    await waitFor(() => expect(screen.getByRole("button", { name: /revisar ativo/i })).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: /revisar ativo/i }));

    // Sem mudança nenhuma, o botão fica desabilitado: mandar um patch vazio
    // criaria uma revisão que não revisa nada.
    await waitFor(() => expect(screen.getByText(/nenhum campo foi alterado/i)).toBeTruthy());
    const botao = screen.getByRole("button", { name: /registrar revisão/i }) as HTMLButtonElement;
    expect(botao.disabled).toBe(true);

    const formulario = container.querySelectorAll("form")[0];
    const entradas = formulario.querySelectorAll("input");
    fireEvent.change(entradas[0], { target: { value: "Página do piloto (renomeada)" } });
    fireEvent.change(entradas[entradas.length - 1], { target: { value: "nome corrigido pelo dono" } });
    await waitFor(() => expect(screen.getByText(/1 campo\(s\) alterado\(s\): nome/i)).toBeTruthy());
    fireEvent.submit(formulario);

    await waitFor(() => expect(enviar).toHaveBeenCalled());
    const corpo = enviar.mock.calls[0][1] as { mudancas: Record<string, unknown>; chave_idempotencia: string };
    // SÓ o campo tocado. Um put disfarçado de patch é como uma edição de nome
    // zera a custódia comprovada.
    expect(Object.keys(corpo.mudancas)).toEqual(["nome"]);
    expect(corpo.mudancas.nome).toBe("Página do piloto (renomeada)");
    // A chave inclui os campos mudados: duas revisões distintas no mesmo minuto
    // não podem compartilhar recibo.
    expect(corpo.chave_idempotencia).not.toBe(cofre.chaveDoAto("revisao", PAGINA.ativo_id, "resumo"));
  });

  it("A5: a chave de idempotência não depende do relógio", () => {
    // ACHADO A5 da revisão adversarial. A versão anterior misturava uma janela
    // de 60s: com Date.now() em 59999 e 60000 a MESMA ação produzia duas chaves,
    // e o mesmo payload entrava duas vezes no banco. Um retry que cruza a
    // fronteira do minuto deixava de ser retry — e é justamente quando o retry
    // humano acontece.
    const corpo = { alvo: "ativo", resultado: "verified", metodo: "conferência" };
    const antes = cofre.chaveDoAto("verificacao", "asset:x:y", corpo);
    // Substituição deliberada do relógio: a prova é que ele NÃO importa mais.
    const real = Date.now;
    try {
      Date.now = () => 59_999;
      const a = cofre.chaveDoAto("verificacao", "asset:x:y", corpo);
      Date.now = () => 60_000;
      const b = cofre.chaveDoAto("verificacao", "asset:x:y", corpo);
      expect(a).toBe(b);
      expect(a).toBe(antes);
    } finally {
      Date.now = real;
    }
  });

  it("A5: conteúdo diferente produz chave diferente, e a ordem das chaves não conta", () => {
    const a = cofre.chaveDoAto("verificacao", "asset:x:y", { alvo: "ativo", resultado: "verified" });
    const b = cofre.chaveDoAto("verificacao", "asset:x:y", { resultado: "verified", alvo: "ativo" });
    const c = cofre.chaveDoAto("verificacao", "asset:x:y", { alvo: "ativo", resultado: "failed" });
    expect(a).toBe(b);
    expect(a).not.toBe(c);
    expect(a).toMatch(/^[A-Za-z0-9._:-]{8,120}$/);
  });
});
