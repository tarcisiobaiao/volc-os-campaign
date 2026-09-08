// @vitest-environment jsdom
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { EstadoOperacional } from "../EstadoOperacional";
import { VerdadeDoDado } from "../VerdadeDoDado";

afterEach(cleanup);

describe("EstadoOperacional", () => {
  it("erro usa role alert e explica a recuperação", () => {
    const { getByRole, getByText } = render(
      <EstadoOperacional
        tom="erro"
        titulo="A leitura falhou"
        explicacao="A conta não respondeu."
        acao={{ rotulo: "Tentar ler de novo", onClick: () => undefined }}
      />,
    );
    expect(getByRole("alert")).toBeTruthy();
    expect(getByText("A leitura falhou")).toBeTruthy();
    expect(getByText("Tentar ler de novo")).toBeTruthy();
  });

  it("demo não usa o vocabulário de erro", () => {
    const { queryByRole, getByText } = render(
      <EstadoOperacional tom="demo" titulo="Demonstração" explicacao="Fixture local, não é conta real." />,
    );
    expect(queryByRole("alert")).toBeNull();
    expect(getByText("Demonstração")).toBeTruthy();
  });
});

describe("VerdadeDoDado", () => {
  it("separa real, demo e zero", () => {
    const { getByText, rerender } = render(<VerdadeDoDado verdade="real" />);
    expect(getByText("Dado real")).toBeTruthy();
    rerender(<VerdadeDoDado verdade="demo" />);
    expect(getByText("Demonstração")).toBeTruthy();
    rerender(<VerdadeDoDado verdade="zero" />);
    expect(getByText("Zero medido")).toBeTruthy();
  });
});
