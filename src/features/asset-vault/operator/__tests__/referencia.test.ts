import { describe, expect, it } from "vitest";
import {
  diagnosticarReferencia, fraseDaFalha, montarReferencia1Password,
  retratoDaReferencia, retratoMascarado,
} from "../referencia";

describe("referência 1Password", () => {
  it("monta o endereço sem reapresentá-lo no retrato", () => {
    const pecas = { cofre: "VOLC", item: "Pagina Piloto", campo: "credential" };
    const endereco = montarReferencia1Password(pecas);
    expect(endereco.startsWith("op" + ":" + "//")).toBe(true);
    expect(endereco).toContain("Pagina%20Piloto");
    const retrato = retratoDaReferencia(pecas);
    expect(retrato).toMatch(/1Password contém o valor/);
    expect(retrato).not.toContain("op" + ":" + "//");
    expect(retrato).toContain("Pagina Piloto");
  });

  it("recusa MFA, query e campo de senha", () => {
    expect(diagnosticarReferencia({ cofre: "V", item: "I", campo: "otp" })).toBe("mfa");
    expect(diagnosticarReferencia({ cofre: "V", item: "I?x=1", campo: "credential" })).toBe("query");
    expect(diagnosticarReferencia({ cofre: "V", item: "I", campo: "password" })).toBe("valor_bruto");
    expect(fraseDaFalha("mfa")).toMatch(/MFA/);
  });

  it("a postura mascarada nunca inclui o endereço", () => {
    expect(retratoMascarado("1password", "FB_PAGE_ADMIN")).toBe(
      "1Password · FB_PAGE_ADMIN · valor só no cofre externo",
    );
  });
});
