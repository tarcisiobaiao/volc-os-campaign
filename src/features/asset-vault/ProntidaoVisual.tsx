/**
 * O painel de prontidão: o que falta antes de publicar, e o que o QA visual diz.
 *
 * ## Por que ele existe
 *
 * O backend já respondia `GET /ativos/{id}/handoff` desde 01/09/2026, e nenhuma
 * tela o consumia. O resultado prático era que "esta página está pronta para
 * receber peça?" continuava sendo respondido por leitura humana do inventário —
 * e "o QA visual passou?" não era respondido por lugar nenhum.
 *
 * ## Acessibilidade, e por que ela não é enfeite aqui
 *
 * Este painel decide se alguém publica. Um estado transmitido só por cor
 * excluiria quem não distingue as cores da decisão mais consequente da tela.
 * Por isso cada estado sai como **ícone + rótulo textual + frase explicativa**,
 * o bloco é `role="status"` com `aria-live="polite"` (para o leitor de tela
 * anunciar a mudança sem interromper), os bloqueios são lista real e o foco é
 * visível em todo elemento interativo.
 *
 * ## O que ele NÃO faz
 *
 * Não dispara QA, não abre navegador, não mostra o screenshot embutido. O
 * artefato aparece por REFERÊNCIA e hash — os bytes vivem em disco privado no
 * host isolado, e trazê-los para o browser do VOLC seria transportar a captura
 * de uma superfície autenticada para dentro de uma sessão administrativa.
 */
import * as React from "react";
import {
  CheckCircle2, CircleAlert, CircleDashed, Clock3, Fingerprint, ImageOff,
  LockKeyhole, PlugZap, ShieldCheck, TriangleAlert,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  EXPLICACAO_DA_PRONTIDAO, ROTULO_DA_PRONTIDAO, TOM_DA_PRONTIDAO,
  estadoDaProntidao, primeiroBloqueio, rotuloDoArtefato,
  type EstadoDaProntidao, type ProntidaoVisualPayload, type TomDaProntidao,
} from "./prontidao";

const ICONE: Record<EstadoDaProntidao, React.ComponentType<{ className?: string }>> = {
  carregando: CircleDashed,
  vazio: CircleDashed,
  indisponivel: CircleAlert,
  bloqueado: LockKeyhole,
  pronto_para_peca: PlugZap,
  pronto_para_qa: ShieldCheck,
  qa_em_execucao: Clock3,
  corrigir: CircleAlert,
  indeterminado: TriangleAlert,
  aprovado: CheckCircle2,
};

/**
 * Classes por tom. Cada uma traz borda E texto — não só fundo.
 *
 * Um tom que só muda o `background` desaparece em alto contraste e em impressão
 * monocromática; a borda sobrevive aos dois.
 */
const CLASSE_DO_TOM: Record<TomDaProntidao, string> = {
  neutro: "border-border bg-muted/30 text-muted-foreground",
  info: "border-primary/35 bg-primary/10 text-primary",
  atencao: "border-warning/40 bg-warning/10 text-warning-foreground",
  erro: "border-destructive/40 bg-destructive/10 text-destructive",
  sucesso: "border-success/40 bg-success/10 text-success",
};

function Linha({ rotulo, valor, ok }: { rotulo: string; valor: string; ok: boolean | null }) {
  return (
    <div className="flex items-start justify-between gap-3 py-1.5">
      <dt className="text-xs text-muted-foreground">{rotulo}</dt>
      <dd className="flex items-center gap-1.5 text-right text-xs font-medium">
        {/* O símbolo é redundante com o texto de propósito: ele ajuda quem lê
            rápido, e o texto continua sendo a fonte para quem usa leitor de
            tela ou não distingue as cores. */}
        {ok === null ? null : (
          <span aria-hidden="true" className={ok ? "text-success" : "text-muted-foreground"}>
            {ok ? "✓" : "—"}
          </span>
        )}
        <span>{valor}</span>
      </dd>
    </div>
  );
}

export interface ProntidaoVisualProps {
  carregando: boolean;
  indisponivel: boolean;
  prontidao: ProntidaoVisualPayload | null;
  /** Mensagem já sanitizada pelo servidor, quando a leitura falhou. */
  mensagemDeErro?: string;
  aoTentarDeNovo?: () => void;
}

export function ProntidaoVisual({
  carregando, indisponivel, prontidao, mensagemDeErro, aoTentarDeNovo,
}: ProntidaoVisualProps) {
  const estado = estadoDaProntidao({ carregando, indisponivel, prontidao });
  const tom = TOM_DA_PRONTIDAO[estado];
  const Icone = ICONE[estado];
  const bloqueio = primeiroBloqueio(prontidao);
  const artefato = prontidao?.qa_visual.artefato ?? null;
  const hash = rotuloDoArtefato(artefato);

  return (
    <section
      className="rounded-lg border border-border bg-card p-5"
      aria-labelledby="prontidao-visual-titulo"
    >
      <div className="flex items-center gap-2">
        <ShieldCheck aria-hidden="true" className="h-4 w-4 text-muted-foreground" />
        <h4 id="prontidao-visual-titulo" className="text-sm font-semibold">
          Prontidão e prova visual
        </h4>
      </div>

      {/* `role="status"` + `aria-live="polite"`: a mudança de estado é anunciada
          sem interromper quem está lendo outra parte da tela. */}
      <div
        role="status"
        aria-live="polite"
        className={cn("mt-3 rounded-md border px-3 py-2.5", CLASSE_DO_TOM[tom])}
      >
        <p className="flex items-center gap-2 text-sm font-medium">
          <Icone aria-hidden="true" className="h-4 w-4 shrink-0" />
          {ROTULO_DA_PRONTIDAO[estado]}
        </p>
        <p className="mt-1.5 text-xs leading-5 opacity-90">
          {EXPLICACAO_DA_PRONTIDAO[estado]}
        </p>
      </div>

      {estado === "indisponivel" && mensagemDeErro ? (
        <p className="mt-3 text-xs text-muted-foreground">{mensagemDeErro}</p>
      ) : null}

      {estado === "indisponivel" && aoTentarDeNovo ? (
        <button
          type="button"
          onClick={aoTentarDeNovo}
          className="mt-3 inline-flex items-center rounded-md border border-border px-3 py-1.5 text-xs font-medium hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        >
          Tentar de novo
        </button>
      ) : null}

      {prontidao ? (
        <>
          <dl className="mt-4 divide-y divide-border border-y border-border">
            <Linha
              rotulo="Página no Cofre"
              ok={prontidao.pagina.presente}
              valor={prontidao.pagina.presente ? "cadastrada" : "não cadastrada"}
            />
            <Linha
              rotulo="Referência de acesso"
              ok={prontidao.referencia_de_credencial.verificada}
              valor={
                !prontidao.referencia_de_credencial.presente
                  ? "ausente"
                  : prontidao.referencia_de_credencial.verificada
                    ? `${prontidao.referencia_de_credencial.nome_logico ?? "registrada"} · verificada`
                    : `${prontidao.referencia_de_credencial.nome_logico ?? "registrada"} · não verificada`
              }
            />
            <Linha
              rotulo="Perfil AdsPower"
              ok={prontidao.perfil_de_navegador.presente}
              valor={prontidao.perfil_de_navegador.presente
                ? (prontidao.perfil_de_navegador.rotulo ?? "relacionado")
                : "não relacionado"}
            />
            <Linha
              rotulo="Broker"
              ok={prontidao.broker.estado === "configurado"}
              valor={prontidao.broker.estado === "configurado" ? "configurado" : "indisponível"}
            />
            <Linha
              rotulo="Pronto para receber peça"
              ok={prontidao.pronto_para_receber_peca}
              valor={prontidao.pronto_para_receber_peca ? "sim" : "não"}
            />
            <Linha
              rotulo="Pronto para publicar"
              ok={prontidao.pronto_para_publicar}
              valor={prontidao.pronto_para_publicar ? "sim" : "não"}
            />
          </dl>

          <div className="mt-4">
            <h5 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Última prova visual
            </h5>
            <p className="mt-1.5 text-xs leading-5 text-muted-foreground">
              {prontidao.qa_visual.motivo}
            </p>
            {artefato && hash ? (
              <p className="mt-2 flex items-center gap-1.5 text-xs font-medium">
                <Fingerprint aria-hidden="true" className="h-3.5 w-3.5 text-muted-foreground" />
                {/* Hash curto apenas — nunca a imagem, nunca o caminho de disco,
                    nunca a referência privada inteira em atributo/DOM. */}
                <span>{hash}</span>
                <span className="text-muted-foreground">· {artefato.bytes} bytes</span>
              </p>
            ) : (
              <p className="mt-2 flex items-center gap-1.5 text-xs text-muted-foreground">
                <ImageOff aria-hidden="true" className="h-3.5 w-3.5" />
                Nenhuma captura registrada.
              </p>
            )}
          </div>

          {prontidao.bloqueios.length ? (
            <div className="mt-4">
              <h5 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Bloqueios ({prontidao.bloqueios.length})
              </h5>
              <ul className="mt-1.5 space-y-1.5">
                {prontidao.bloqueios.map((b) => (
                  <li key={b.codigo} className="flex items-start gap-2 text-xs leading-5">
                    <LockKeyhole aria-hidden="true" className="mt-0.5 h-3 w-3 shrink-0 text-muted-foreground" />
                    <span>
                      {b.mensagem} <span className="text-muted-foreground">({b.onde})</span>
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          <p className="mt-4 rounded-md border border-border bg-muted/30 px-3 py-2 text-xs leading-5">
            <span className="font-semibold">Próxima ação: </span>
            {prontidao.proxima_acao}
            {bloqueio ? <span className="sr-only"> Código do bloqueio: {bloqueio.codigo}.</span> : null}
          </p>
        </>
      ) : null}
    </section>
  );
}

export default ProntidaoVisual;
