// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import * as React from "react";

vi.mock("@/lib/supabase", () => ({ supabase: { auth: { getSession: async () => ({ data: { session: { access_token: "t" } } }) } } }));
vi.mock("@/hooks/use-toast", () => ({ useToast: () => ({ toast: vi.fn() }) }));

import * as cofre from "../../cofreApi";
import { AssetVaultContent } from "../../AssetVaultContent";

afterEach(() => { cleanup(); vi.restoreAllMocks(); sessionStorage.clear(); });

const GAVETAS: cofre.GavetaDoCofre[] = [
  { cluster: "social_presence", rotulo: "Presenças sociais", descricao: "Perfis.", ordem: 1, total: 0 },
  { cluster: "paid_media", rotulo: "Mídia paga", descricao: "Contas.", ordem: 2, total: 0 },
  { cluster: "web_properties", rotulo: "Sites e domínios", descricao: "Sites.", ordem: 3, total: 0 },
  { cluster: "communities", rotulo: "Comunidades e mensagens", descricao: "Mensagens.", ordem: 4, total: 0 },
  { cluster: "creative_production", rotulo: "Produção criativa", descricao: "Engines.", ordem: 5, total: 0 },
  { cluster: "automation", rotulo: "Automações e integrações", descricao: "Workflows.", ordem: 6, total: 0 },
  { cluster: "infrastructure", rotulo: "Infraestrutura e dados", descricao: "Bancos.", ordem: 7, total: 0 },
];

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

describe("onboarding progressivo", () => {
  beforeEach(() => sessionStorage.clear());

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
    expect(sessionStorage.getItem("volc.cofre.onboarding.v2")).toMatch(/"kind":"website"/);
  });

  it("a etapa de credencial não pede senha e recusa MFA no campo", async () => {
    mount();
    await waitFor(() => expect(screen.getByRole("button", { name: /^Cadastrar ativo$/ })).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: /^Cadastrar ativo$/ }));
    fireEvent.click(screen.getByRole("button", { name: /Referência da credencial/i }));
    await waitFor(() => expect(screen.getByRole("heading", { name: /Referência da credencial/i })).toBeTruthy());
    expect(screen.getAllByText(/1Password contém o valor/i).length).toBeGreaterThan(0);
    expect(document.querySelector('input[type="password"]')).toBeNull();
    expect(screen.queryByPlaceholderText("op://VOLC/item/credential")).toBeNull();
    expect(screen.getByPlaceholderText("credential")).toBeTruthy();
  });
});
