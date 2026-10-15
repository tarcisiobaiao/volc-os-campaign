// @vitest-environment jsdom
import { act, cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Delta } from "../Delta";
import { Frescor } from "../Frescor";
import { Metrica } from "../Metrica";
import { NumeroAnimado } from "../NumeroAnimado";
import { RecomendacaoSombra } from "../RecomendacaoSombra";
import { SeloDeProposta } from "../SeloDeProposta";
import { Sparkline } from "../Sparkline";

afterEach(cleanup);

const AGORA = new Date("2026-10-15T17:00:00Z");

describe("Metrica", () => {
  it("valor ausente vira travessão e selo Desconhecido, nunca 0", () => {
    const { container, getByText, queryByText } = render(
      <Metrica rotulo="Conversões" valor={null} formato={{ tipo: "inteiro" }} verdade="real" />,
    );
    expect(container.querySelector("[data-verdade]")?.getAttribute("data-verdade")).toBe("desconhecido");
    expect(getByText("Desconhecido")).toBeTruthy();
    expect(queryByText("0")).toBeNull();
  });

  it("erro esconde o número mesmo quando ele veio", () => {
    const { container } = render(
      <Metrica rotulo="Custo" valor={1284} formato={{ tipo: "inteiro" }} verdade="erro" />,
    );
    expect(container.textContent).not.toContain("1.284");
    expect(container.textContent).toContain("Erro de leitura");
  });

  it("demo mostra o número e o selo, inclusive compacta", () => {
    const { container } = render(
      <Metrica tamanho="compacta" rotulo="Cliques" valor={9120} formato={{ tipo: "inteiro" }} verdade="demo" />,
    );
    expect(container.textContent).toContain("9.120");
    expect(container.textContent).toContain("Demonstração");
  });

  it("real não leva selo; zero medido leva", () => {
    const real = render(<Metrica rotulo="A" valor={3} formato={{ tipo: "inteiro" }} verdade="real" />);
    expect(real.container.textContent).not.toContain("Dado real");
    real.unmount();
    const zero = render(<Metrica rotulo="B" valor={0} formato={{ tipo: "inteiro" }} verdade="zero" />);
    expect(zero.container.textContent).toContain("Zero medido");
  });

  it("carregando não mostra número nem selo", () => {
    const { container } = render(
      <Metrica rotulo="Custo" valor={10} formato={{ tipo: "inteiro" }} verdade="real" carregando />,
    );
    expect(container.querySelector("[aria-busy='true']")).toBeTruthy();
    expect(container.textContent).not.toContain("10");
  });
});

describe("não-finitos são ausência em todo primitivo", () => {
  it.each([Infinity, -Infinity, Number.NaN])("Metrica com %s mostra travessão e Desconhecido", (v) => {
    const { container } = render(<Metrica rotulo="ROAS" valor={v} formato={{ tipo: "razao" }} verdade="real" />);
    expect(container.querySelector("[data-verdade]")?.getAttribute("data-verdade")).toBe("desconhecido");
    expect(container.textContent).not.toContain("∞");
    expect(container.textContent).toContain("—");
  });

  it("NumeroAnimado com Infinity mostra travessão", () => {
    const { container } = render(<NumeroAnimado valor={Infinity} formato={{ tipo: "razao" }} />);
    expect(container.querySelector("[aria-hidden]")?.textContent).toBe("—");
  });
});

describe("NumeroAnimado", () => {
  it("primeira leitura aparece pronta (sem contar de zero)", () => {
    const { container } = render(<NumeroAnimado valor={1500} formato={{ tipo: "inteiro" }} />);
    const visivel = container.querySelector("[aria-hidden]");
    expect(visivel?.textContent).toBe("1.500");
    expect(container.querySelector(".sr-only")?.textContent).toBe("1.500");
  });

  it("leitor de tela recebe o valor final na troca", () => {
    const { container, rerender } = render(<NumeroAnimado valor={10} formato={{ tipo: "inteiro" }} />);
    act(() => rerender(<NumeroAnimado valor={20} formato={{ tipo: "inteiro" }} />));
    expect(container.querySelector(".sr-only")?.textContent).toBe("20");
  });
});

describe("Delta", () => {
  it("custo subindo é desfavorável e diz isso em palavra", () => {
    const { container } = render(<Delta atual={120} base={100} sentido="menor-melhor" />);
    expect(container.querySelector(".text-delta-ruim")).toBeTruthy();
    expect(container.textContent).toContain("desfavorável");
  });

  it("ruído de ponto flutuante não ganha seta nem juízo", () => {
    const { container } = render(<Delta atual={0.1 + 0.2} base={0.3} sentido="maior-melhor" />);
    expect(container.textContent).not.toContain("▲");
    expect(container.textContent).not.toContain("favorável");
    expect(container.textContent).toContain("sem juízo de valor");
  });

  it("infinito não vira variação favorável", () => {
    const { container } = render(<Delta atual={Infinity} base={10} sentido="maior-melhor" />);
    expect(container.textContent).toContain("sem base de comparação");
    expect(container.textContent).not.toContain("∞");
  });

  it("sem base, não inventa variação", () => {
    const { container } = render(<Delta atual={120} base={null} sentido="maior-melhor" />);
    expect(container.textContent).toContain("sem base de comparação");
  });
});

describe("Frescor", () => {
  it("leitura vencida diz em palavra", () => {
    const { container } = render(
      <Frescor lidoEm={new Date(AGORA.getTime() - 2 * 86400_000)} agora={AGORA} fonte="GAM" />,
    );
    expect(container.querySelector("[data-frescor]")?.getAttribute("data-frescor")).toBe("vencido");
    expect(container.textContent).toContain("Vencido para decidir");
    expect(container.textContent).toContain("GAM");
  });

  it("nunca lido não mostra idade", () => {
    const { container } = render(<Frescor lidoEm={null} agora={AGORA} />);
    expect(container.textContent).toContain("Nunca lido");
    expect(container.textContent).not.toContain("lido há");
  });
});

describe("Sparkline", () => {
  it("anuncia as lacunas", () => {
    const { getByRole } = render(<Sparkline valores={[1, null, 2, 3]} rotulo="Custo" />);
    expect(getByRole("img").getAttribute("aria-label")).toBe("Custo, 1 ponto sem leitura");
  });
});

describe("RecomendacaoSombra e SeloDeProposta", () => {
  it("sombra declara que nada foi enviado e a ação bloqueada explica o pré-requisito", () => {
    const { container, getByRole } = render(
      <RecomendacaoSombra
        direcao="pausar"
        titulo="Campanha X"
        motor="Shadow v1"
        evidencias={[{ rotulo: "ROAS", valor: "0,10×", verdade: "real" }]}
        consequencia="a campanha para de veicular."
        acao={{ rotulo: "Levar à fila de propostas", onClick: () => undefined, bloqueio: "Ledger não aplicado." }}
      />,
    );
    expect(container.textContent).toContain("Sombra · não executada");
    expect(container.textContent).toContain("Nada foi enviado à conta.");
    const botao = getByRole("button", { name: "Levar à fila de propostas" }) as HTMLButtonElement;
    expect(botao.disabled).toBe(true);
    expect(botao.getAttribute("aria-describedby")).toBeTruthy();
    expect(container.textContent).not.toMatch(/executar agora/i);
  });

  it("aplicada usa verified (observado), não success", () => {
    const { container } = render(<SeloDeProposta estado="aplicada" />);
    expect(container.innerHTML).toContain("verified");
    expect(container.innerHTML).not.toContain("success");
  });
});
