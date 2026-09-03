/**
 * O contrato de prontidão na tela — e o guarda que impede uma tela otimista.
 *
 * A prova central não é que os rótulos existem: é que uma resposta que a tela
 * não entende NÃO vira uma prontidão vazia. Um `pronto: false` com zero
 * bloqueios seria a pior tela possível — ela afirma que algo impede sem dizer o
 * quê, e quem lê vai procurar o defeito no ativo em vez de na resposta.
 *
 * Testes de lógica pura: rodam no ambiente `node` do vitest, sem DOM.
 */
import { describe, expect, it } from "vitest";

import {
  PERGUNTAS,
  PERGUNTA_LABEL,
  VALOR_LABEL,
  ehProntidao,
  fraseDoResumo,
  resumoDeProntidao,
  type ProntidaoDoAtivo,
  type ValorDaResposta,
} from "../prontidaoOperacao";

function resposta(valor: ValorDaResposta, motivo = "motivo", procedencia: "registro" | "sonda" = "registro") {
  return { valor, motivo, procedencia };
}

function prontidao(sobrescreve: Partial<Record<(typeof PERGUNTAS)[number], ReturnType<typeof resposta>>> = {},
                   extra: Partial<ProntidaoDoAtivo> = {}): ProntidaoDoAtivo {
  const perguntas = Object.fromEntries(
    PERGUNTAS.map((chave) => [chave, sobrescreve[chave] ?? resposta("sim")]),
  ) as ProntidaoDoAtivo["perguntas"];
  return {
    ativo_id: "asset:facebook-page:piloto",
    perguntas,
    retrato: { estado: "declared", dono_nome: "Tarcisio", revisao_atual: 1 },
    producao_possivel: [],
    componentes_seguintes: {
      porta_de_publicacao: { tarefa: "P12-T09", estado: "todo" },
      broker_de_acesso: { tarefa: "P03-T11", implementacao: "local_verified", operacao_real: "live_read_not_proven" },
    },
    pronto_para_receber_peca: true,
    pronto_para_operar_acesso: false,
    pronto_para_publicar: false,
    bloqueios: ["nao existe porta de publicacao no VOLC (P12-T09)"],
    bloqueios_por_portao: {
      recebimento: [],
      acesso: ["perfil relacionado sem leitura ao vivo"],
      publicacao: ["nao existe porta de publicacao no VOLC (P12-T09)"],
    },
    publica: false,
    ...extra,
  };
}

describe("prontidão — o guarda de forma", () => {
  it("aceita a resposta completa", () => {
    expect(ehProntidao(prontidao())).toBe(true);
  });

  it("recusa uma resposta a que falta uma pergunta", () => {
    const torta = prontidao() as unknown as Record<string, Record<string, unknown>>;
    delete torta.perguntas.perfil_disponivel;
    expect(ehProntidao(torta)).toBe(false);
  });

  it("recusa um valor fora do vocabulário de três", () => {
    const torta = prontidao();
    (torta.perguntas.dono as { valor: string }).valor = "talvez";
    expect(ehProntidao(torta)).toBe(false);
  });

  it("recusa bloqueios que não são texto", () => {
    expect(ehProntidao(prontidao({}, { bloqueios: [{ x: 1 }] as unknown as string[] }))).toBe(false);
  });

  it("recusa portoes ausentes em vez de assumir `false`", () => {
    for (const chave of ["pronto_para_receber_peca", "pronto_para_operar_acesso", "pronto_para_publicar"]) {
      const torta = prontidao() as unknown as Record<string, unknown>;
      delete torta[chave];
      expect(ehProntidao(torta)).toBe(false);
    }
  });

  it("recusa lista de bloqueios por portao ausente", () => {
    const torta = prontidao() as unknown as Record<string, unknown>;
    delete torta.bloqueios_por_portao;
    expect(ehProntidao(torta)).toBe(false);
  });

  it.each([null, undefined, "texto", 7, [], {}])("recusa a forma %p", (valor) => {
    expect(ehProntidao(valor)).toBe(false);
  });
});

describe("prontidão — o resumo não arredonda", () => {
  it("conta as oito perguntas por valor", () => {
    const resumo = resumoDeProntidao(prontidao({
      perfil_de_navegador: resposta("nao"),
      perfil_disponivel: resposta("desconhecido"),
    }));
    expect(resumo).toEqual({ sim: 6, nao: 1, desconhecido: 1, total: 8 });
  });

  it("a frase nomeia o bloqueio E a ausência de observação, separadamente", () => {
    const frase = fraseDoResumo({ sim: 6, nao: 1, desconhecido: 1, total: 8 });
    expect(frase).toContain("6 de 8 em ordem");
    expect(frase).toContain("1 bloqueando");
    expect(frase).toContain("1 sem observação");
  });

  it("sem pendência, a frase não inventa uma", () => {
    const frase = fraseDoResumo({ sim: 8, nao: 0, desconhecido: 0, total: 8 });
    expect(frase).toBe("8 de 8 em ordem");
  });
});

describe("prontidão — o vocabulário de três valores", () => {
  it("`não se sabe` é uma frase própria, e não um sinônimo de `não`", () => {
    // Achatar os dois é como o painel aprende a dizer "perfil indisponível"
    // sobre um perfil que ninguém olhou.
    expect(VALOR_LABEL.desconhecido).not.toBe(VALOR_LABEL.nao);
    expect(new Set(Object.values(VALOR_LABEL)).size).toBe(3);
  });

  it("toda pergunta do contrato tem rótulo em português", () => {
    for (const chave of PERGUNTAS) {
      expect(PERGUNTA_LABEL[chave]).toBeTruthy();
    }
    expect(Object.keys(PERGUNTA_LABEL).sort()).toEqual([...PERGUNTAS].sort());
  });
});


describe("prontidão — portões separados", () => {
  it("P12-T09 ausente não torna falso o recebimento de peça", () => {
    const p = prontidao({}, {
      pronto_para_receber_peca: true,
      pronto_para_publicar: false,
      bloqueios_por_portao: {
        recebimento: [],
        acesso: [],
        publicacao: ["nao existe porta de publicacao no VOLC (P12-T09)"],
      },
    });
    expect(ehProntidao(p)).toBe(true);
    expect(p.pronto_para_receber_peca).toBe(true);
    expect(p.pronto_para_publicar).toBe(false);
  });

  it("broker local verificado continua diferente de live-read", () => {
    const p = prontidao();
    expect(p.componentes_seguintes.broker_de_acesso).toMatchObject({
      tarefa: "P03-T11",
      implementacao: "local_verified",
      operacao_real: "live_read_not_proven",
    });
    expect(p.perguntas.perfil_disponivel.valor).toBe("sim");
  });
});
