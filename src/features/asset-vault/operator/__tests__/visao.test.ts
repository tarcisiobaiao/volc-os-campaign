import { describe, expect, it } from "vitest";
import { derivarVisao } from "../visao";
import type { AtivoDaLista } from "../../cofreApi";

function ativo(over: Partial<AtivoDaLista> = {}): AtivoDaLista {
  return {
    ativo_id: "asset:facebook-page:piloto",
    nome: "Página do piloto",
    kind: "facebook_page",
    tipo_rotulo: "Página do Facebook",
    cluster: "social_presence",
    plataforma: "Meta",
    estado: "declared",
    criticidade: "high",
    resumo: "Página declarada.",
    dono_nome: "Tarcisio",
    dono_custodia: "declared",
    tags: [],
    proxima_acao: "Conferir o ID da página.",
    revisao_atual: 1,
    relacoes: [],
    credencial_registrada: false,
    verificacao_estado: "unverified",
    ...over,
  };
}

describe("visão operacional", () => {
  it("vazio real não inventa prontidão nem bloqueio zerado", () => {
    const visao = derivarVisao([]);
    expect(visao.amostra).toBe("vazia");
    expect(visao.total).toBe(0);
    expect(visao.verificados).toBeNull();
    expect(visao.semAcesso).toBeNull();
    expect(visao.bloqueadores).toEqual([]);
    expect(visao.prontidaoDominante.rotulo).toBe("Sem amostra");
    expect(visao.proximoAto.frase).toMatch(/primeiro ativo/i);
  });

  it("conta só o que o inventário trouxe", () => {
    const visao = derivarVisao([
      ativo(),
      ativo({
        ativo_id: "asset:engine:video",
        nome: "Motor",
        estado: "ready",
        credencial_registrada: true,
        verificacao_estado: "verified",
        relacoes: [{ tipo: "produces_for", destino: "cap:x", rotulo: "cap", estado: "declared" }],
        proxima_acao: "Criar adapter.",
      }),
    ]);
    expect(visao.amostra).toBe("presente");
    expect(visao.total).toBe(2);
    expect(visao.verificados).toBe(1);
    expect(visao.semAcesso).toBe(1);
    expect(visao.bloqueadores.some((b) => /sem referência/i.test(b))).toBe(true);
    expect(visao.proximoAto.ativoId).toBe("asset:facebook-page:piloto");
  });

  it("cofre bloqueado não é autorização negada nem verificação falha", () => {
    const visao = derivarVisao([
      ativo({ verificacao_estado: "blocked", credencial_registrada: true }),
    ]);
    expect(visao.cofreBloqueado).toBe(1);
    expect(visao.prontidaoDominante.rotulo).toBe("Cofre externo bloqueado");
    expect(visao.bloqueadores.join(" ")).toMatch(/cofre externo bloqueado/i);
  });

  it("revisão vencida e relação incompleta não viram zero saudável", () => {
    const visao = derivarVisao([
      ativo({
        verificacao_estado: "expired",
        credencial_registrada: true,
        relacoes: [],
      }),
    ]);
    expect(visao.revisoesVencidas).toBe(1);
    expect(visao.relacaoIncompleta).toBe(1);
    expect(visao.prontidaoDominante.rotulo).toBe("Revisão vencida");
    expect(visao.bloqueadores.join(" ")).toMatch(/revisão vencida/i);
    expect(visao.bloqueadores.join(" ")).toMatch(/sem relação/i);
  });
});
