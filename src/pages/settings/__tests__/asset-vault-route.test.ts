import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

describe("entrada do Cofre de Ativos", () => {
  it("mantém rota protegida e item administrativo no menu", () => {
    const app = readFileSync(resolve(process.cwd(), "src/App.tsx"), "utf8");
    const navigation = readFileSync(resolve(process.cwd(), "src/components/layout/Navigation.tsx"), "utf8");

    expect(app).toContain('path="/settings/cofre-ativos"');
    expect(app).toContain("<ProtectedRoute><AssetVaultPage /></ProtectedRoute>");
    expect(navigation).toContain('title: "Cofre de Ativos"');
    expect(navigation).toContain('href: "/settings/cofre-ativos"');
    expect(navigation).toContain("adminOnly: true");
  });
});
