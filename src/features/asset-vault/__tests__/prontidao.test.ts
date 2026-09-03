/**
 * A lógica pura dos dez estados da prontidão.
 *
 * A prova central deste arquivo não é que o cálculo funciona: é que ele NÃO
 * colapsa estados que pedem ações diferentes. `indeterminado` não pode ser
 * verde, `capturado` não pode virar `aprovado`, e "não conferimos" não pode
 * parecer "está errado".
 */
import { describe, expect, it } from "vitest";
import {
  EXPLICACAO_DA_PRONTIDAO, ROTULO_DA_PRONTIDAO, TOM_DA_PRONTIDAO,
  estadoDaProntidao, primeiroBloqueio, rotuloDoArtefato,
  type EstadoDaProntidao, type ProntidaoVisualPayload,
} from "../prontidao";

const TODOS: EstadoDaProntidao[] = [
  "carregando", "vazio", "indisponivel", "bloqueado", "pronto_para_peca",
  "pronto_para_qa", "qa_em_execucao", "corrigir", "indeterminado", "aprovado",
];

function payload(over: Partial<ProntidaoVisualPayload> = {}): ProntidaoVisualPayload {
  return {
    ativo_id: "asset:facebook-page:piloto",
    destino: { ativo_id: "asset:facebook-page:piloto", nome: "Página piloto" },
    pagina: { presente: true, motivo: "" },
    referencia_de_credencial: {
      presente: true, verificada: true, provider: "1password",
      nome_logico: "FB_PAGE_ADMIN", verificacao_estado: "verified",
      verificado_em: "2026-09-01",
    },
    perfil_de_navegador: {
      presente: true, rotulo: "Perfil piloto", ativo_id: "asset:browser-profile:piloto",
    },
    broker: { estado: "configurado", motivo: "" },
    qa_visual: {
      estado: "nao_executado", motivo: "nenhuma prova visual foi executada ainda.",
      job: null, veredito: null, artefato: null,
    },
    pronto_para_receber_peca: true,
    pronto_para_publicar: true,
    pronto_para_qa: true,
    bloqueios: [],
    bloqueios_do_cofre: [],
    proxima_acao: "Peça a prova visual desta superfície.",
    ...over,
  };
}

describe("estadoDaProntidao", () => {
  it("carregando vence tudo", () => {
    expect(estadoDaProntidao({ carregando: true, indisponivel: true, prontidao: payload() }))
      .toBe("carregando");
  });

  it("indisponível é diferente de vazio", () => {
    expect(estadoDaProntidao({ carregando: false, indisponivel: true, prontidao: null }))
      .toBe("indisponivel");
    expect(estadoDaProntidao({ carregando: false, indisponivel: false, prontidao: null }))
      .toBe("indisponivel");
    expect(estadoDaProntidao({
      carregando: false, indisponivel: false,
      prontidao: payload({ pagina: { presente: false, motivo: "sem página" } }),
    })).toBe("vazio");
  });

  it("ativo aposentado bloqueia até receber peça", () => {
    expect(estadoDaProntidao({
      carregando: false, indisponivel: false,
      prontidao: payload({
        pronto_para_receber_peca: false, pronto_para_publicar: false, pronto_para_qa: false,
      }),
    })).toBe("bloqueado");
  });

  it("distingue pronto para peça de pronto para QA", () => {
    expect(estadoDaProntidao({
      carregando: false, indisponivel: false,
      prontidao: payload({
        perfil_de_navegador: { presente: false, rotulo: null, ativo_id: null },
        pronto_para_publicar: false, pronto_para_qa: false,
        bloqueios: [{ codigo: "perfil_ausente", mensagem: "sem perfil", onde: "cofre" }],
      }),
    })).toBe("pronto_para_peca");

    expect(estadoDaProntidao({ carregando: false, indisponivel: false, prontidao: payload() }))
      .toBe("pronto_para_qa");
  });

  it("broker ausente bloqueia o QA sem bloquear a publicação", () => {
    const estado = estadoDaProntidao({
      carregando: false, indisponivel: false,
      prontidao: payload({
        broker: { estado: "nao_configurado", motivo: "sem endereço" },
        pronto_para_qa: false,
        bloqueios: [{ codigo: "broker_indisponivel", mensagem: "sem broker", onde: "broker" }],
      }),
    });
    expect(estado).toBe("bloqueado");
  });

  it.each([
    ["em_execucao", "qa_em_execucao"],
    ["corrigir", "corrigir"],
    ["indeterminado", "indeterminado"],
    ["aprovado", "aprovado"],
  ] as const)("o veredito %s manda no estado da tela", (qa, esperado) => {
    expect(estadoDaProntidao({
      carregando: false, indisponivel: false,
      prontidao: payload({
        qa_visual: { estado: qa, motivo: "…", job: {}, veredito: null, artefato: null },
      }),
    })).toBe(esperado);
  });

  it("nao_persistido e nao_executado não viram veredito", () => {
    for (const qa of ["nao_persistido", "nao_executado"] as const) {
      const estado = estadoDaProntidao({
        carregando: false, indisponivel: false,
        prontidao: payload({
          qa_visual: { estado: qa, motivo: "…", job: null, veredito: null, artefato: null },
        }),
      });
      expect(estado).toBe("pronto_para_qa");
      expect(estado).not.toBe("aprovado");
      expect(estado).not.toBe("corrigir");
    }
  });

  it("QA reprovado vence a cadeia completa", () => {
    // Um ativo com tudo em ordem e QA reprovado NÃO pode aparecer como pronto.
    expect(estadoDaProntidao({
      carregando: false, indisponivel: false,
      prontidao: payload({
        qa_visual: { estado: "corrigir", motivo: "clipping", job: {}, veredito: "needs_correction", artefato: null },
      }),
    })).toBe("corrigir");
  });
});

describe("tom e rótulo", () => {
  it("apenas `aprovado` é verde", () => {
    const verdes = TODOS.filter((e) => TOM_DA_PRONTIDAO[e] === "sucesso");
    expect(verdes).toEqual(["aprovado"]);
  });

  it("indeterminado nunca é sucesso", () => {
    expect(TOM_DA_PRONTIDAO.indeterminado).not.toBe("sucesso");
    expect(TOM_DA_PRONTIDAO.qa_em_execucao).not.toBe("sucesso");
    expect(TOM_DA_PRONTIDAO.pronto_para_qa).not.toBe("sucesso");
  });

  it("todo estado tem rótulo e explicação próprios — sem sinônimo", () => {
    const rotulos = TODOS.map((e) => ROTULO_DA_PRONTIDAO[e]);
    const explicacoes = TODOS.map((e) => EXPLICACAO_DA_PRONTIDAO[e]);
    expect(new Set(rotulos).size).toBe(TODOS.length);
    expect(new Set(explicacoes).size).toBe(TODOS.length);
    for (const texto of [...rotulos, ...explicacoes]) {
      expect(texto.trim().length).toBeGreaterThan(3);
    }
  });
});

describe("artefato", () => {
  it("mostra hash curto e nunca a referência inteira", () => {
    expect(rotuloDoArtefato({
      referencia: "vpartifact://PERFIL_PILOTO_01/rcp_1/captura.png",
      sha256: "a".repeat(64), bytes: 4, mime: "image/png", criado_em: "2026-09-02",
    })).toBe(`sha256 ${"a".repeat(12)}…`);
    expect(rotuloDoArtefato(null)).toBeNull();
  });
});

describe("bloqueios", () => {
  it("o primeiro bloqueio é o que a tela destaca", () => {
    const p = payload({
      bloqueios: [
        { codigo: "perfil_ausente", mensagem: "sem perfil", onde: "cofre" },
        { codigo: "broker_indisponivel", mensagem: "sem broker", onde: "broker" },
      ],
    });
    expect(primeiroBloqueio(p)?.codigo).toBe("perfil_ausente");
    expect(primeiroBloqueio(null)).toBeNull();
  });
});
