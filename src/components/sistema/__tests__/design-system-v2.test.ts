import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const css = readFileSync(new URL("../../../index.css", import.meta.url), "utf8");
const design = readFileSync(new URL("../../../../design.md", import.meta.url), "utf8");
const product = readFileSync(new URL("../../../../PRODUCT.md", import.meta.url), "utf8");

describe("Design System V2 tokens", () => {
  it("retira Inter e Space Grotesk da autoridade e do CSS de produto", () => {
    expect(design).toContain("Outfit");
    expect(design).toContain("IBM Plex Sans");
    expect(design).not.toMatch(/display:\s*"Inter"|display:\s*"Space Grotesk"/);
    expect(css).toContain("Outfit");
    expect(css).toContain("IBM Plex Sans");
    expect(css).not.toContain('font-family: "Inter"');
    expect(css).not.toContain('font-family: "Space Grotesk"');
  });

  it("canvas claro deixa de ser quase branco", () => {
    expect(css).toContain("--background: 214 16% 86%");
    expect(css).toContain("--card: 210 33% 97%");
    expect(css).not.toContain("--background: 210 20% 96%");
  });

  it("ação primária é navy VOLC, não teal", () => {
    expect(css).toContain("--primary: 214 88% 34%");
    expect(design).toContain("#0D47A1");
    expect(css).not.toContain("--primary: 189 81% 21%");
  });

  it("sidebar clara é papel off-white acima do canvas mineral", () => {
    expect(css).toContain("--sidebar-background: 210 40% 99%");
    expect(css).toContain("--background: 214 16% 86%");
  });

  it("PRODUCT.md declara o contrato de verdade dos dados", () => {
    expect(product).toContain("Demonstração");
    expect(product).toContain("Ausência não vira zero");
    expect(product).toContain("Bloqueado não vira controle aparentemente disponível");
  });
});
