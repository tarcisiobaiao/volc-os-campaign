import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import {
  ASSET_CLUSTERS,
  ASSET_KINDS,
  DigitalAssetListSchema,
  KIND_CLUSTER,
  assertPublicAssetContract,
} from "../contract";
import { INITIAL_ASSETS } from "../fixtures";

describe("contrato público do Cofre de Ativos", () => {
  it("aceita o retrato editorial inteiro no schema estrito", () => {
    expect(DigitalAssetListSchema.parse(INITIAL_ASSETS)).toHaveLength(8);
    expect(() => assertPublicAssetContract(INITIAL_ASSETS)).not.toThrow();
  });

  it("mantém tipo e cluster em uma única taxonomia", () => {
    for (const asset of INITIAL_ASSETS) {
      expect(ASSET_CLUSTERS).toContain(asset.cluster);
      expect(KIND_CLUSTER[asset.kind]).toBe(asset.cluster);
    }
  });

  it("recusa material sensível antes de validar o restante do payload", () => {
    const payload = structuredClone(INITIAL_ASSETS[0]) as Record<string, unknown>;
    payload.credential = {
      ...(payload.credential as Record<string, unknown>),
      access_token: "valor-que-nao-pode-chegar-ao-erro",
    };

    let message = "";
    try {
      assertPublicAssetContract(payload);
    } catch (error) {
      message = error instanceof Error ? error.message : String(error);
    }

    expect(message).toContain("Campo proibido no contrato público");
    expect(message).toContain("access_token");
    expect(message).not.toContain("valor-que-nao-pode-chegar-ao-erro");
  });

  it("recusa URL que não seja HTTP ou HTTPS", () => {
    const payload = structuredClone(INITIAL_ASSETS[0]);
    payload.external.publicUrl = "javascript:alert(1)";
    expect(() => assertPublicAssetContract(payload)).toThrow(/HTTP\(S\)/i);
  });

  it("não publica identificadores completos das contas Google conhecidas", () => {
    const googleAccounts = INITIAL_ASSETS.filter((asset) => asset.kind === "google_ads_account");
    expect(googleAccounts).toHaveLength(3);
    for (const asset of googleAccounts) {
      expect(asset.external.displayId).toMatch(/^•••-•••-\d{4}$/);
      expect(asset.external.displayId).not.toMatch(/^\d{10}$/);
    }
  });

  it("o catálogo de tipos é o MESMO da migration v13_01", () => {
    // Três fontes precisam concordar: este contrato público, `dominio.py` do
    // backend e `cofre_tipo` no banco. Divergir em silêncio faz a API aceitar
    // um tipo que a FK do banco recusa — e o operador recebe um erro de
    // integridade referencial onde deveria ter recebido "tipo desconhecido".
    const sql = readFileSync(
      new URL("../../../../supabase/migrations/v13_01_cofre_de_ativos.sql", import.meta.url),
      "utf-8",
    );
    const bloco = sql.slice(sql.indexOf("INSERT INTO public.cofre_tipo"));
    const pares = [...bloco.slice(0, bloco.indexOf(";")).matchAll(/\('([a-z_]+)',\s*'([a-z_]+)'/g)];
    const noSql = new Map(pares.map(([, kind, cluster]) => [kind, cluster]));
    expect(noSql.size).toBe(ASSET_KINDS.length);
    for (const kind of ASSET_KINDS) {
      expect(noSql.get(kind)).toBe(KIND_CLUSTER[kind]);
    }
  });
});
