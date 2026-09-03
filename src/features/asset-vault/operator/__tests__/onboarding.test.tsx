// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { extname, join } from "node:path";

vi.mock("@/lib/supabase", () => ({ supabase: { auth: { getSession: async () => ({ data: { session: { access_token: "t" } } }) } } }));
vi.mock("@/hooks/use-toast", () => ({ useToast: () => ({ toast: vi.fn() }) }));

import * as cofre from "../../cofreApi";
import { AssetVaultContent } from "../../AssetVaultContent";
import { montarReferencia1Password } from "../referencia";
import {
  CHAVE_RASCUNHO, textoTemEsquema1Password, varrerArmazenamentoDoBrowser,
} from "../rascunho";

function limparStorages() {
  sessionStorage.clear();
  if (typeof localStorage !== "undefined") localStorage.clear();
}

afterEach(() => { cleanup(); vi.restoreAllMocks(); limparStorages(); });

const GAVETAS: cofre.GavetaDoCofre[] = [
  { cluster: "social_presence", rotulo: "Presenças sociais", descricao: "Perfis.", ordem: 1, total: 0 },
  { cluster: "paid_media", rotulo: "Mídia paga", descricao: "Contas.", ordem: 2, total: 0 },
  { cluster: "web_properties", rotulo: "Sites e domínios", descricao: "Sites.", ordem: 3, total: 0 },
  { cluster: "communities", rotulo: "Comunidades e mensagens", descricao: "Mensagens.", ordem: 4, total: 0 },
  { cluster: "creative_production", rotulo: "Produção criativa", descricao: "Engines.", ordem: 5, total: 0 },
  { cluster: "automation", rotulo: "Automações e integrações", descricao: "Workflows.", ordem: 6, total: 0 },
  { cluster: "infrastructure", rotulo: "Infraestrutura e dados", descricao: "Bancos.", ordem: 7, total: 0 },
];

const COFRE = "CofreOperacionalX";
const ITEM = "ItemOperacionalY";
const CAMPO = "credential";
const NOME_LOGICO = "FB_PAGE_ADMIN";
const FINALIDADE = "Acesso administrativo da pagina piloto";
const RESPONSAVEL = "Tarcisio";

function mount() {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  vi.spyOn(cofre, "cofreConfigurado").mockReturnValue(true);
  vi.spyOn(cofre, "inventario").mockResolvedValue({ gavetas: GAVETAS, ativos: [] });
  return render(
    <QueryClientProvider client={cliente}>
      <MemoryRouter initialEntries={["/settings/cofre-ativos"]}><AssetVaultContent /></MemoryRouter>
    </QueryClientProvider>,
  );
}

async function abrirOnboarding() {
  await waitFor(() => expect(screen.getByRole("button", { name: /^Cadastrar ativo$/ })).toBeTruthy());
  fireEvent.click(screen.getByRole("button", { name: /^Cadastrar ativo$/ }));
  await waitFor(() => expect(screen.getByText("Onboarding progressivo")).toBeTruthy());
}

function continuar() {
  fireEvent.click(screen.getByRole("button", { name: /continuar/i }));
}

async function avancarTodasAsEtapas(container: HTMLElement) {
  await abrirOnboarding();
  const select = container.querySelector("form select") as HTMLSelectElement;
  fireEvent.change(select, { target: { value: "website" } });
  continuar();
  await waitFor(() => expect(screen.getByRole("heading", { name: /identidade e finalidade/i })).toBeTruthy());
  fireEvent.change(screen.getByPlaceholderText("asset:facebook-page:piloto"), { target: { value: "asset:website:piloto" } });
  fireEvent.change(screen.getByLabelText(/^nome/i), { target: { value: "Site piloto" } });
  fireEvent.change(screen.getByPlaceholderText("Meta, Google Ads, WordPress…"), { target: { value: "WordPress" } });
  fireEvent.change(screen.getByLabelText(/resumo/i), { target: { value: "Site oficial do piloto para operacao." } });
  fireEvent.change(screen.getByLabelText(/capacidades/i), { target: { value: "publicar" } });
  fireEvent.change(screen.getByLabelText(/próxima ação/i), { target: { value: "Conferir a referencia no cofre externo." } });
  continuar();
  await waitFor(() => expect(screen.getByRole("heading", { name: /owner e custódia/i })).toBeTruthy());
  fireEvent.change(screen.getByLabelText(/^dono/i), { target: { value: "Operador" } });
  continuar();
  await waitFor(() => expect(screen.getByRole("heading", { name: /^destino$/i })).toBeTruthy());
  continuar();
  await waitFor(() => expect(screen.getByRole("heading", { name: /referência da credencial/i })).toBeTruthy());
  fireEvent.change(screen.getByPlaceholderText("VOLC"), { target: { value: COFRE } });
  fireEvent.change(screen.getByPlaceholderText("Pagina do piloto"), { target: { value: ITEM } });
  fireEvent.change(screen.getByPlaceholderText("credential"), { target: { value: CAMPO } });
  fireEvent.change(screen.getByPlaceholderText("FB_PAGE_ADMIN"), { target: { value: NOME_LOGICO } });
  fireEvent.change(screen.getByLabelText(/^responsável/i), { target: { value: RESPONSAVEL } });
  fireEvent.change(screen.getByLabelText(/^finalidade/i), { target: { value: FINALIDADE } });
  continuar();
  await waitFor(() => expect(screen.getByRole("heading", { name: /^relações$/i })).toBeTruthy());
  continuar();
  await waitFor(() => expect(screen.getByRole("heading", { name: /revisão e confirmação/i })).toBeTruthy());
}

function assertStorageSanitizado() {
  expect(varrerArmazenamentoDoBrowser()).toEqual([]);
  const local = typeof localStorage === "undefined" ? [] : Array.from(
    { length: localStorage.length },
    (_, i) => localStorage.getItem(localStorage.key(i) ?? "") ?? "",
  );
  const dump = [
    sessionStorage.getItem(CHAVE_RASCUNHO) ?? "",
    ...Array.from({ length: sessionStorage.length }, (_, i) => sessionStorage.getItem(sessionStorage.key(i) ?? "") ?? ""),
    ...local,
  ].join("\n");
  expect(textoTemEsquema1Password(dump)).toBe(false);
  expect(dump).not.toContain(COFRE);
  expect(dump).not.toContain(ITEM);
  const cru = sessionStorage.getItem(CHAVE_RASCUNHO);
  if (cru) {
    const lido = JSON.parse(cru) as { credencial?: Record<string, unknown> };
    expect(lido.credencial?.cofre).toBeUndefined();
    expect(lido.credencial?.item).toBeUndefined();
    expect(lido.credencial?.campo).toBeUndefined();
    expect(lido.credencial?.localizador).toBeUndefined();
  }
}

function camposDeReferencia() {
  return {
    cofre: screen.getByPlaceholderText("VOLC") as HTMLInputElement,
    item: screen.getByPlaceholderText("Pagina do piloto") as HTMLInputElement,
    campo: screen.getByPlaceholderText("credential") as HTMLInputElement,
  };
}

describe("onboarding progressivo", () => {
  beforeEach(() => {
    limparStorages();
  });

  it("preserva o tipo ao avançar e deriva a gaveta", async () => {
    const { container } = mount();
    await waitFor(() => expect(screen.getByRole("button", { name: /^Cadastrar ativo$/ })).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: /^Cadastrar ativo$/ }));
    await waitFor(() => expect(screen.getByRole("heading", { name: /tipo de ativo/i })).toBeTruthy());
    const select = container.querySelector("form select") as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "website" } });
    expect(screen.getByText(/Gaveta: Sites e domínios/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /continuar/i }));
    await waitFor(() => expect(screen.getByPlaceholderText("asset:facebook-page:piloto")).toBeTruthy());
    expect(sessionStorage.getItem(CHAVE_RASCUNHO)).toMatch(/"kind":"website"/);
    assertStorageSanitizado();
  });

  it("a etapa de credencial não pede senha e recusa MFA no campo", async () => {
    mount();
    await waitFor(() => expect(screen.getByRole("button", { name: /^Cadastrar ativo$/ })).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: /^Cadastrar ativo$/ }));
    fireEvent.click(screen.getByRole("button", { name: /Referência da credencial/i }));
    await waitFor(() => expect(screen.getByRole("heading", { name: /Referência da credencial/i })).toBeTruthy());
    expect(screen.getAllByText(/1Password contém o valor/i).length).toBeGreaterThan(0);
    expect(document.querySelector('input[type="password"]')).toBeNull();
    expect(screen.queryByPlaceholderText(["op", "VOLC/item/credential"].join(":" + "//"))).toBeNull();
    expect(screen.getByPlaceholderText("credential")).toBeTruthy();
  });

  it("recusa password, token, OTP e MFA no campo da referência", async () => {
    mount();
    await abrirOnboarding();
    fireEvent.click(screen.getByRole("button", { name: /Referência da credencial/i }));
    await waitFor(() => expect(screen.getByPlaceholderText("VOLC")).toBeTruthy());
    fireEvent.change(screen.getByPlaceholderText("VOLC"), { target: { value: "VOLC" } });
    fireEvent.change(screen.getByPlaceholderText("Pagina do piloto"), { target: { value: "PaginaPiloto" } });
    const casos: Array<{ campo: string; trecho: RegExp }> = [
      { campo: "password", trecho: /valor secreto|senha/i },
      { campo: "token", trecho: /valor secreto|senha/i },
      { campo: "otp", trecho: /MFA/i },
      { campo: "mfa", trecho: /MFA/i },
    ];
    for (const caso of casos) {
      fireEvent.change(screen.getByPlaceholderText("credential"), { target: { value: caso.campo } });
      const alertas = screen.getAllByRole("alert").map((nodo) => nodo.textContent ?? "");
      expect(alertas.some((texto) => caso.trecho.test(texto))).toBe(true);
    }
    expect(document.querySelector('input[type="password"]')).toBeNull();
  });

  it("avança todas as etapas sem persistir pecas nem localizador e a revisão não as mostra", async () => {
    const logs: string[] = [];
    for (const metodo of ["log", "info", "warn", "error", "debug"] as const) {
      vi.spyOn(console, metodo).mockImplementation((...args: unknown[]) => {
        logs.push(args.map((valor) => typeof valor === "string" ? valor : JSON.stringify(valor)).join(" "));
      });
    }
    const { container } = mount();
    await avancarTodasAsEtapas(container);
    assertStorageSanitizado();
    expect(sessionStorage.getItem(CHAVE_RASCUNHO)).toMatch(/"nome_logico":"FB_PAGE_ADMIN"/);
    expect(screen.getByText("Provider")).toBeTruthy();
    expect(screen.getByText("Nome lógico")).toBeTruthy();
    expect(screen.getByText(NOME_LOGICO)).toBeTruthy();
    expect(screen.getByText(FINALIDADE)).toBeTruthy();
    expect(screen.getByText(RESPONSAVEL)).toBeTruthy();
    expect(screen.queryByText(COFRE)).toBeNull();
    expect(screen.queryByText(ITEM)).toBeNull();
    expect(textoTemEsquema1Password(document.body.textContent)).toBe(false);
    expect(screen.queryByText(/Cofre «/)).toBeNull();
    const diario = logs.join("\n");
    expect(textoTemEsquema1Password(diario)).toBe(false);
    expect(diario).not.toContain(COFRE);
    expect(diario).not.toContain(ITEM);
  });

  it("fechar e reabrir descarta cofre, item e campo", async () => {
    const { container } = mount();
    await avancarTodasAsEtapas(container);
    fireEvent.click(screen.getByRole("button", { name: "Fechar" }));
    await waitFor(() => expect(screen.queryByRole("heading", { name: /revisão e confirmação/i })).toBeNull());
    assertStorageSanitizado();
    fireEvent.click(screen.getByRole("button", { name: /^Cadastrar ativo$/ }));
    await waitFor(() => expect(screen.getByRole("heading", { name: /revisão e confirmação/i })).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: /Referência da credencial/i }));
    await waitFor(() => expect(screen.getByPlaceholderText("VOLC")).toBeTruthy());
    const campos = camposDeReferencia();
    expect(campos.cofre.value).toBe("");
    expect(campos.item.value).toBe("");
    expect(campos.campo.value).toBe("");
    expect(screen.getByPlaceholderText("FB_PAGE_ADMIN")).toHaveProperty("value", NOME_LOGICO);
  });

  it("remontar a interface descarta as peças da referência", async () => {
    const primeira = mount();
    await avancarTodasAsEtapas(primeira.container);
    primeira.unmount();
    const segunda = mount();
    await abrirOnboarding();
    fireEvent.click(screen.getByRole("button", { name: /Referência da credencial/i }));
    await waitFor(() => expect(screen.getByPlaceholderText("VOLC")).toBeTruthy());
    const campos = camposDeReferencia();
    expect(campos.cofre.value).toBe("");
    expect(campos.item.value).toBe("");
    expect(campos.campo.value).toBe("");
    assertStorageSanitizado();
    segunda.unmount();
  });

  it("concluir envia o localizador só na mutation e limpa o storage", async () => {
    const logs: string[] = [];
    for (const metodo of ["log", "info", "warn", "error", "debug"] as const) {
      vi.spyOn(console, metodo).mockImplementation((...args: unknown[]) => {
        logs.push(args.map((valor) => typeof valor === "string" ? valor : JSON.stringify(valor)).join(" "));
      });
    }
    const cadastrar = vi.spyOn(cofre, "cadastrarAtivo").mockResolvedValue({
      operacao: "cofre.cadastrar_ativo", ativo_id: "asset:website:piloto", revisao: 1, idempotente: false,
    });
    const referenciar = vi.spyOn(cofre, "referenciarCredencial").mockResolvedValue({
      operacao: "cofre.referenciar_credencial", ativo_id: "asset:website:piloto", idempotente: false,
    });
    const { container } = mount();
    await avancarTodasAsEtapas(container);
    fireEvent.submit(container.querySelector("form")!);
    await waitFor(() => expect(referenciar).toHaveBeenCalled());
    expect(cadastrar).toHaveBeenCalled();
    const corpo = referenciar.mock.calls[0][1] as Record<string, unknown>;
    expect(corpo.localizador).toBe(montarReferencia1Password({ cofre: COFRE, item: ITEM, campo: CAMPO }));
    expect(corpo.nome_logico).toBe(NOME_LOGICO);
    expect(sessionStorage.getItem(CHAVE_RASCUNHO)).toBeNull();
    expect(varrerArmazenamentoDoBrowser()).toEqual([]);
    expect(textoTemEsquema1Password(logs.join("\n"))).toBe(false);
    expect(textoTemEsquema1Password(document.body.textContent)).toBe(false);
  });
});

describe("scanner de storage e de artefatos públicos do operador", () => {
  it("a fonte do operador não serializa pecas no sessionStorage", () => {
    const onboarding = readFileSync(join(__dirname, "..", "Onboarding.tsx"), "utf8");
    expect(onboarding).not.toMatch(/sessionStorage\.setItem/);
    expect(onboarding).not.toMatch(/localStorage\.setItem/);
    const rascunho = readFileSync(join(__dirname, "..", "rascunho.ts"), "utf8");
    expect(rascunho).toMatch(/serializarRascunhoPersistivel/);
    expect(textoTemEsquema1Password(rascunho)).toBe(false);
  });

  it("artefatos públicos do ownership não embutem o esquema 1Password", () => {
    const raiz = join(__dirname, "..", "..");
    const alvos: string[] = [];
    const caminhar = (dir: string) => {
      for (const nome of readdirSync(dir)) {
        if (nome === "node_modules" || nome === "__tests__") continue;
        const caminho = join(dir, nome);
        if (statSync(caminho).isDirectory()) caminhar(caminho);
        else if ([".ts", ".tsx", ".md"].includes(extname(caminho))) alvos.push(caminho);
      }
    };
    caminhar(join(raiz, "operator"));
    alvos.push(join(raiz, "AssetVaultContent.tsx"));
    alvos.push(join(raiz, "..", "..", "pages", "settings", "AssetVaultPage.tsx"));
    for (const arquivo of alvos) {
      const texto = readFileSync(arquivo, "utf8");
      expect(textoTemEsquema1Password(texto), arquivo).toBe(false);
    }
  });
});
