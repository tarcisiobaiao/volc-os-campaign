import { describe, expect, it } from "vitest";
import {
  RASCUNHO_VAZIO, hitsDeReferenciaNoTexto, hidratarRascunhoPersistivel,
  serializarRascunhoPersistivel,
} from "../rascunho";

function esquema() {
  return "op" + ":" + "//";
}

describe("rascunho persistível do onboarding", () => {
  it("serializa metadados e recusa pecas, localizador e esquema", () => {
    const json = serializarRascunhoPersistivel({
      ...RASCUNHO_VAZIO,
      passo: 5,
      kind: "website",
      credencial: {
        provider: "1password",
        nome_logico: "FB_PAGE_ADMIN",
        owner_nome: "Tarcisio",
        finalidade: "Acesso administrativo",
        pular: false,
      },
    });
    const lido = JSON.parse(json) as { credencial: Record<string, unknown> };
    expect(Object.keys(lido.credencial).sort()).toEqual([
      "finalidade", "nome_logico", "owner_nome", "provider", "pular",
    ]);
    expect(lido.credencial.nome_logico).toBe("FB_PAGE_ADMIN");
    expect(hitsDeReferenciaNoTexto(json)).toEqual([]);
    expect(json.includes(esquema())).toBe(false);
    expect(json).not.toMatch(/"cofre"/);
    expect(json).not.toMatch(/"item"/);
    expect(json).not.toMatch(/"campo"/);
    expect(json).not.toMatch(/"localizador"/);
  });

  it("hidrata rascunho legado sem reter pecas nem localizador", () => {
    const lido = hidratarRascunhoPersistivel({
      passo: 7,
      kind: "website",
      credencial: {
        cofre: "CofreLegado",
        item: "ItemLegado",
        campo: "credential",
        localizador: `${esquema()}CofreLegado/ItemLegado/credential`,
        nome_logico: "FB_PAGE_ADMIN",
        owner_nome: "Tarcisio",
        finalidade: "Acesso administrativo",
        pular: false,
      },
    });
    expect(lido.credencial).toEqual({
      provider: "1password",
      nome_logico: "FB_PAGE_ADMIN",
      owner_nome: "Tarcisio",
      finalidade: "Acesso administrativo",
      pular: false,
    });
    const json = serializarRascunhoPersistivel(lido);
    expect(hitsDeReferenciaNoTexto(json)).toEqual([]);
    expect(json).not.toContain("CofreLegado");
    expect(json).not.toContain("ItemLegado");
    expect(json.includes(esquema())).toBe(false);
  });
});
