// @vitest-environment jsdom

/**
 * O painel de prontidão renderizado — e o que ele se recusa a dizer.
 *
 * A prova central: **um estado nunca chega ao usuário só pela cor**. Cada
 * asserção aqui procura TEXTO. Se alguém trocar o rótulo por um ponto colorido,
 * estes testes caem — que é o ponto, porque este painel decide se alguém
 * publica.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as React from "react";

import { ProntidaoVisual } from "../ProntidaoVisual";
import type { ProntidaoVisualPayload } from "../prontidao";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

function payload(over: Partial<ProntidaoVisualPayload> = {}): ProntidaoVisualPayload {
  return {
    ativo_id: "asset:facebook-page:piloto",
    destino: { ativo_id: "asset:facebook-page:piloto" },
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

describe("estados da tela", () => {
  it("carregando anuncia o que está apurando", () => {
    render(<ProntidaoVisual carregando indisponivel={false} prontidao={null} />);
    expect(screen.getByRole("status").textContent).toContain("Apurando a prontidão");
  });

  it("indisponível não vira 'não está pronto'", () => {
    render(<ProntidaoVisual carregando={false} indisponivel prontidao={null}
      mensagemDeErro="O Cofre não respondeu." />);
    const status = screen.getByRole("status");
    expect(status.textContent).toContain("Prontidão indisponível");
    expect(status.textContent).toContain("significa que não sabemos");
    expect(status.textContent).not.toContain("Aprovado");
    expect(screen.getByText("O Cofre não respondeu.")).toBeTruthy();
  });

  it("vazio diz que a página não existe, sem inventar uma", () => {
    render(<ProntidaoVisual carregando={false} indisponivel={false}
      prontidao={payload({ pagina: { presente: false, motivo: "sem página" } })} />);
    expect(screen.getByRole("status").textContent).toContain("Página real não cadastrada");
    expect(screen.getByText("não cadastrada")).toBeTruthy();
  });

  it("pronto para peça deixa claro que ainda não publica", () => {
    render(<ProntidaoVisual carregando={false} indisponivel={false}
      prontidao={payload({
        perfil_de_navegador: { presente: false, rotulo: null, ativo_id: null },
        pronto_para_publicar: false, pronto_para_qa: false,
        bloqueios: [{ codigo: "perfil_ausente", mensagem: "nenhum perfil relacionado", onde: "cofre" }],
        proxima_acao: "Inventarie o perfil AdsPower (P03-T07).",
      })} />);
    expect(screen.getByRole("status").textContent).toContain("Pronto para receber peça");
    expect(screen.getByRole("status").textContent).toContain("NÃO está pronto para publicar");
    expect(screen.getByText("nenhum perfil relacionado", { exact: false })).toBeTruthy();
    // A próxima ação é montada por dois nós ("Próxima ação: " + o texto), então
    // a asserção olha o texto da região inteira em vez de um nó só.
    const regiao = screen.getByRole("region", { name: /Prontidão e prova visual/ });
    expect(regiao.textContent).toContain("Inventarie o perfil AdsPower (P03-T07).");
  });

  it("indeterminado é anunciado como indeterminado, nunca como aprovado", () => {
    render(<ProntidaoVisual carregando={false} indisponivel={false}
      prontidao={payload({
        qa_visual: {
          estado: "indeterminado",
          motivo: "falha técnica do executor (timeout): a página não foi avaliada",
          job: {}, veredito: "indeterminate", artefato: null,
        },
        proxima_acao: "A prova visual não conseguiu concluir. Isso NÃO reprova a página.",
      })} />);
    const status = screen.getByRole("status");
    expect(status.textContent).toContain("QA visual indeterminado");
    expect(status.textContent).toContain("NÃO reprova a página");
    expect(status.textContent).not.toContain("Aprovado");
    expect(screen.getByText(/não foi avaliada/)).toBeTruthy();
  });

  it("capturado aguardando revisão não é aprovado", () => {
    render(<ProntidaoVisual carregando={false} indisponivel={false}
      prontidao={payload({
        qa_visual: {
          estado: "em_execucao", motivo: "aguardando revisão humana",
          job: {}, veredito: "eligible_for_human_review", artefato: null,
        },
      })} />);
    const status = screen.getByRole("status");
    expect(status.textContent).toContain("QA visual em andamento");
    expect(status.textContent).toContain("Capturado não é aprovado");
  });

  it("aprovado diz que foi uma pessoa que aprovou", () => {
    render(<ProntidaoVisual carregando={false} indisponivel={false}
      prontidao={payload({
        qa_visual: {
          estado: "aprovado", motivo: "revisado por tarcisio",
          job: {}, veredito: "approved",
          artefato: {
            referencia: "vpartifact://PERFIL_PILOTO_01/rcp_1/captura.png",
            sha256: "b".repeat(64), bytes: 48000, mime: "image/png",
            criado_em: "2026-09-02T12:00:00+00:00",
          },
        },
      })} />);
    const status = screen.getByRole("status");
    expect(status.textContent).toContain("Aprovado por revisão humana");
    expect(status.textContent).toContain("Nenhuma avaliação automática produz este estado");
  });
});

describe("contenção", () => {
  it("mostra o artefato por hash, nunca a imagem nem caminho de disco", () => {
    const { container } = render(<ProntidaoVisual carregando={false} indisponivel={false}
      prontidao={payload({
        qa_visual: {
          estado: "aprovado", motivo: "ok", job: {}, veredito: "approved",
          artefato: {
            referencia: "vpartifact://PERFIL_PILOTO_01/rcp_1/captura.png",
            sha256: "c".repeat(64), bytes: 48000, mime: "image/png",
            criado_em: "2026-09-02T12:00:00+00:00",
          },
        },
      })} />);
    expect(screen.getByText(`sha256 ${"c".repeat(12)}…`)).toBeTruthy();
    // Nenhuma tag de imagem: os bytes ficam no host isolado.
    expect(container.querySelector("img")).toBeNull();
    expect(container.innerHTML).not.toContain("vpartifact://");
    expect(container.innerHTML).not.toContain("/home/");
    expect(container.innerHTML).not.toContain("/Users/");
    expect(container.innerHTML).not.toContain("base64");
  });

  it("não renderiza op:// nem localizador vindos de um payload malformado", () => {
    const contaminado = payload() as unknown as Record<string, unknown>;
    contaminado.qa_visual = {
      estado: "nao_executado", motivo: "nenhuma prova visual foi executada ainda.",
      job: null, veredito: null, artefato: null,
    };
    const { container } = render(<ProntidaoVisual carregando={false} indisponivel={false}
      prontidao={contaminado as unknown as ProntidaoVisualPayload} />);
    expect(container.innerHTML).not.toContain("op://");
    expect(container.innerHTML).not.toContain("localizador");
  });

  it("sem captura, diz que não há captura — em vez de deixar em branco", () => {
    render(<ProntidaoVisual carregando={false} indisponivel={false} prontidao={payload()} />);
    expect(screen.getByText("Nenhuma captura registrada.")).toBeTruthy();
  });
});

describe("acessibilidade", () => {
  it("o bloco de estado é status com aria-live polite", () => {
    render(<ProntidaoVisual carregando={false} indisponivel={false} prontidao={payload()} />);
    expect(screen.getByRole("status").getAttribute("aria-live")).toBe("polite");
  });

  it("a seção tem nome acessível", () => {
    render(<ProntidaoVisual carregando={false} indisponivel={false} prontidao={payload()} />);
    expect(screen.getByRole("region", { name: /Prontidão e prova visual/ })).toBeTruthy();
  });

  it("todo estado chega por texto, não só por cor", () => {
    // O `dl` traz rótulo E valor textual para cada elo da cadeia.
    render(<ProntidaoVisual carregando={false} indisponivel={false}
      prontidao={payload({
        broker: { estado: "nao_configurado", motivo: "sem endereço" },
        pronto_para_qa: false,
        bloqueios: [{ codigo: "broker_indisponivel", mensagem: "broker não configurado", onde: "broker" }],
      })} />);
    expect(screen.getByText("Broker")).toBeTruthy();
    expect(screen.getByText("indisponível")).toBeTruthy();
    expect(screen.getByText("Pronto para publicar")).toBeTruthy();
    expect(screen.getByText("Bloqueios (1)")).toBeTruthy();
  });

  it("o botão de tentar de novo é focável e tem anel de foco visível", () => {
    const tentar = vi.fn();
    render(<ProntidaoVisual carregando={false} indisponivel prontidao={null}
      aoTentarDeNovo={tentar} />);
    const botao = screen.getByRole("button", { name: "Tentar de novo" });
    expect(botao.className).toContain("focus-visible:ring-2");
    botao.click();
    expect(tentar).toHaveBeenCalledOnce();
  });
});
