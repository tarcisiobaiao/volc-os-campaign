// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { AssetVaultContent } from "../AssetVaultContent";

afterEach(cleanup);

function mount(entry = "/settings/cofre-ativos") {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <AssetVaultContent />
    </MemoryRouter>,
  );
}

describe("Cofre de Ativos", () => {
  it("abre por gavetas operacionais e mantém o grafo como lente secundária", () => {
    mount();
    expect(screen.getByRole("heading", { name: "Cofre de Ativos" })).toBeTruthy();
    expect(screen.getByText("Zero segredo neste contrato")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Presenças sociais 1/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Mídia paga 3/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Sites e domínios 0/ })).toBeTruthy();

    const tabs = screen.getByRole("tablist");
    const labels = within(tabs).getAllByRole("tab").map((tab) => tab.textContent?.replace(/\d+$/, ""));
    expect(labels).toEqual(["Inventário", "Revisões", "Relações", "Contrato"]);
  });

  it("filtra uma gaveta sem inventar ativos ausentes", () => {
    mount();
    fireEvent.click(screen.getByRole("button", { name: /Sites e domínios 0/ }));
    expect(screen.getByText("Nenhum ativo neste recorte")).toBeTruthy();
    expect(screen.getByText(/inventário original não foi alterado/i)).toBeTruthy();
  });

  it("busca e abre o detalhe de um ativo real do retrato", () => {
    mount();
    const search = screen.getByPlaceholderText("Buscar ativo, plataforma ou projeto");
    fireEvent.change(search, { target: { value: "ChatPion" } });

    expect(screen.getByText("1 de 8, sem persistência nesta etapa.")).toBeTruthy();
    expect(screen.queryByText("PMUNDO+")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /ChatPion próprio/ }));
    expect(screen.getByRole("heading", { name: "ChatPion próprio" })).toBeTruthy();
    expect(screen.getByText(/inventariar versão, administradores, páginas conectadas/i)).toBeTruthy();
  });

  it("documenta os tipos concretos dentro de cada gaveta", () => {
    mount("/settings/cofre-ativos?visao=contract");
    expect(screen.getByRole("heading", { name: "O que um ativo precisa provar" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Tipos organizados por gaveta" })).toBeTruthy();
    expect(screen.getByText("Perfil do Facebook")).toBeTruthy();
    expect(screen.getByText("Página do Facebook")).toBeTruthy();
    expect(screen.getByText("Business Portfolio Meta")).toBeTruthy();
    expect(screen.getByText("Perfil do Instagram")).toBeTruthy();
    expect(screen.getByText("Site WordPress")).toBeTruthy();
    expect(screen.getByText("Conta do Pinterest")).toBeTruthy();
    expect(screen.getByText("Canal do YouTube")).toBeTruthy();
  });
});
