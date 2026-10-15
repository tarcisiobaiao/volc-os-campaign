import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import {
  AUSENTE,
  ESTADO_DE_PROPOSTA,
  avaliarDelta,
  formatarNumero,
  geometriaDaSparkline,
  nivelDeFrescor,
} from "@/lib/instrumento";
import { CURVA, DURACAO, atrasoEscalonado } from "@/lib/movimento";

const nbsp = (s: string) => s.replace(/ /g, " ");

describe("formatarNumero", () => {
  it("ausência vira travessão, nunca zero", () => {
    expect(formatarNumero(null, { tipo: "inteiro" })).toBe(AUSENTE);
    expect(formatarNumero(undefined, { tipo: "moeda", moeda: "BRL" })).toBe(AUSENTE);
    expect(formatarNumero(Number.NaN, { tipo: "razao" })).toBe(AUSENTE);
  });

  it("zero medido continua sendo zero", () => {
    expect(formatarNumero(0, { tipo: "inteiro" })).toBe("0");
  });

  it("formata em pt-BR", () => {
    expect(nbsp(formatarNumero(554.75, { tipo: "moeda", moeda: "BRL" }))).toBe("R$ 554,75");
    expect(formatarNumero(0.125, { tipo: "percentual" })).toBe("12,5%");
    expect(formatarNumero(0.0735, { tipo: "razao", casas: 3 })).toBe("0,074×");
    expect(formatarNumero(12840, { tipo: "inteiro" })).toBe("12.840");
  });
});

describe("avaliarDelta", () => {
  it("o sentido decide o tom: custo que sobe é ruim", () => {
    expect(avaliarDelta(120, 100, "menor-melhor")).toEqual({ direcao: "sobe", fracao: 0.2, tom: "ruim" });
    expect(avaliarDelta(120, 100, "maior-melhor").tom).toBe("bom");
    expect(avaliarDelta(80, 100, "maior-melhor").tom).toBe("ruim");
  });

  it("neutro nunca pinta", () => {
    expect(avaliarDelta(120, 100, "neutro").tom).toBe("neutro");
  });

  it("base zero tem direção mas não percentual", () => {
    expect(avaliarDelta(10, 0, "maior-melhor")).toEqual({ direcao: "sobe", fracao: null, tom: "bom" });
  });

  it("sem base ou sem atual, a direção é desconhecida", () => {
    expect(avaliarDelta(10, null, "maior-melhor").direcao).toBe("desconhecida");
    expect(avaliarDelta(null, 10, "maior-melhor").direcao).toBe("desconhecida");
  });

  it("base negativa usa o módulo", () => {
    expect(avaliarDelta(-50, -100, "maior-melhor").fracao).toBe(0.5);
  });
});

describe("nivelDeFrescor", () => {
  const agora = new Date("2026-10-15T17:00:00Z");
  const ha = (min: number) => new Date(agora.getTime() - min * 60_000);

  it("nunca lido não é fresco", () => {
    expect(nivelDeFrescor(null, agora).nivel).toBe("nunca");
    expect(nivelDeFrescor("isto não é data", agora).nivel).toBe("nunca");
  });

  it("limites padrão: 60 min envelhece, 24 h vence", () => {
    expect(nivelDeFrescor(ha(5), agora).nivel).toBe("fresco");
    expect(nivelDeFrescor(ha(61), agora).nivel).toBe("envelhecido");
    expect(nivelDeFrescor(ha(24 * 60), agora).nivel).toBe("vencido");
  });

  it("data no futuro não degrada para fresco, salvo a tolerância de relógio", () => {
    expect(nivelDeFrescor(new Date(agora.getTime() + 3600_000), agora).nivel).toBe("futuro");
    expect(nivelDeFrescor(new Date(agora.getTime() + 60_000), agora).nivel).toBe("fresco");
  });

  it("aceita limites por fonte", () => {
    expect(nivelDeFrescor(ha(90), agora, { envelhecidoMin: 120, vencidoMin: 240 }).nivel).toBe("fresco");
  });
});

describe("geometriaDaSparkline", () => {
  it("null quebra a linha em trechos, sem interpolar", () => {
    const g = geometriaDaSparkline([1, 2, null, 3, 4], 100, 20);
    expect(g.trechos).toHaveLength(2);
    expect(g.lacunas).toBe(1);
    expect(g.final).not.toBeNull();
  });

  it("ponto isolado entre lacunas vira marca, não some", () => {
    const g = geometriaDaSparkline([null, 5, null], 100, 20);
    expect(g.trechos).toHaveLength(0);
    expect(g.isolados).toHaveLength(1);
  });

  it("série toda ausente não desenha nada (não desenha zero)", () => {
    const g = geometriaDaSparkline([null, null], 100, 20);
    expect(g).toEqual({ trechos: [], isolados: [], final: null, lacunas: 2 });
  });

  it("série constante fica no meio, não no chão", () => {
    const g = geometriaDaSparkline([3, 3, 3], 100, 20);
    expect(g.trechos[0]).toContain(",10");
  });
});

describe("estados de proposta", () => {
  it("todo estado tem glifo, palavra e descrição", () => {
    for (const item of Object.values(ESTADO_DE_PROPOSTA)) {
      expect(item.glifo.length).toBeGreaterThan(0);
      expect(item.palavra.length).toBeGreaterThan(0);
      expect(item.descricao.length).toBeGreaterThan(0);
    }
  });

  it("sombra declara que não foi executada", () => {
    expect(ESTADO_DE_PROPOSTA.sombra.palavra).toMatch(/não executada/);
  });
});

describe("movimento espelha o CSS", () => {
  const css = readFileSync(resolve(__dirname, "../../../index.css"), "utf-8");
  const varDe = (nome: string) => css.match(new RegExp(`--${nome}:\\s*([^;]+);`))?.[1].trim();

  it("durações batem com as vars", () => {
    expect(varDe("motion-press")).toBe(`${DURACAO.press * 1000}ms`);
    expect(varDe("motion-menu")).toBe(`${DURACAO.menu * 1000}ms`);
    expect(varDe("motion-sheet")).toBe(`${DURACAO.sheet * 1000}ms`);
    expect(varDe("motion-dado")).toBe(`${Math.round(DURACAO.dado * 1000)}ms`);
  });

  it("curvas batem com as vars", () => {
    expect(varDe("ease-enter")).toBe(`cubic-bezier(${CURVA.enter.join(", ")})`);
    expect(varDe("ease-move")).toBe(`cubic-bezier(${CURVA.move.join(", ")})`);
    expect(varDe("ease-dado")).toBe(`cubic-bezier(${CURVA.dado.join(", ")})`);
  });

  it("stagger tem teto", () => {
    expect(atrasoEscalonado(0)).toBe(0);
    expect(atrasoEscalonado(100)).toBeCloseTo(0.18);
  });

  it("V3 não removeu nenhum token V2 de cor", () => {
    for (const t of ["--background", "--card", "--primary", "--verified", "--success", "--warning", "--destructive", "--info", "--demo"]) {
      expect(css).toContain(`${t}:`);
    }
  });
});
