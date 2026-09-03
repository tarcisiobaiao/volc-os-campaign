import { describe, expect, it } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, extname } from "node:path";

const RAIZ = join(__dirname, "..", "..");

function arquivos(dir: string): string[] {
  const out: string[] = [];
  for (const nome of readdirSync(dir)) {
    if (nome === "node_modules" || nome === "__tests__") continue;
    const caminho = join(dir, nome);
    if (statSync(caminho).isDirectory()) out.push(...arquivos(caminho));
    else if ([".ts", ".tsx"].includes(extname(caminho))) out.push(caminho);
  }
  return out;
}

describe("fronteira de segredo na fonte da tela", () => {
  it("não há endereço 1Password contíguo na UI do operador", () => {
    const esquema = "op" + ":" + "//";
    const alvos = arquivos(join(RAIZ, "operator")).concat([
      join(RAIZ, "AssetVaultContent.tsx"),
    ]);
    for (const arquivo of alvos) {
      const texto = readFileSync(arquivo, "utf8");
      expect(texto.includes(esquema), arquivo).toBe(false);
      expect(texto).not.toMatch(/transition:\s*all/);
      expect(texto).not.toContain("transition-all");
    }
  });
});
