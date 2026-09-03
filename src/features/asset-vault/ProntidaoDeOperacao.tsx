import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, CheckCircle2, CircleAlert, CircleDashed, Waypoints } from "lucide-react";
import { cn } from "@/lib/utils";
import * as cofre from "./cofreApi";
import {
  PERGUNTAS, PERGUNTA_LABEL, VALOR_LABEL, ehProntidao, fraseDoResumo, resumoDeProntidao,
  type ValorDaResposta,
} from "./prontidaoOperacao";

/**
 * O painel que responde "esta página pode receber uma peça aprovada?".
 *
 * ## A fronteira, escrita na tela
 *
 * Ele RESPONDE. Não cria job, não abre navegador, não publica — e não existe
 * botão aqui que o faça. Publicação continua sendo um ato separado e explícito,
 * e o corpo da resposta carrega `publica: false` para que isso seja um fato
 * lido, e não uma promessa de comentário.
 *
 * ## Por que o "não se sabe" tem cara própria
 *
 * Duas das oito perguntas — se a referência resolve agora, e se o perfil está
 * disponível — só são observáveis de dentro do host isolado, pelo broker. Esta
 * tela não alcança aquele host. Desenhar um ✗ ali faria alguém cadastrar um
 * perfil que já existe, ou reautorizar um cofre que nunca esteve trancado.
 */

const TOM: Record<ValorDaResposta, string> = {
  sim: "text-emerald-600 dark:text-emerald-400",
  nao: "text-destructive",
  desconhecido: "text-muted-foreground",
};

const ICONE: Record<ValorDaResposta, typeof CheckCircle2> = {
  sim: CheckCircle2,
  nao: CircleAlert,
  desconhecido: CircleDashed,
};

function Linha({ rotulo, valor, motivo, procedencia }: {
  rotulo: string; valor: ValorDaResposta; motivo: string; procedencia: string;
}) {
  const Icon = ICONE[valor];
  return (
    <li className="flex items-start gap-2.5">
      <Icon aria-hidden="true" className={cn("mt-0.5 h-3.5 w-3.5 shrink-0", TOM[valor])} />
      <div className="min-w-0">
        <p className="text-xs font-medium">
          {rotulo}: <span className={TOM[valor]}>{VALOR_LABEL[valor]}</span>
        </p>
        <p className="text-[11px] leading-4 text-muted-foreground">
          {motivo}
          {/* A procedência é parte da resposta: "pelo registro" e "observado ao
              vivo" não valem a mesma coisa, e a tela não pode achatá-las. */}
          {procedencia === "sonda" ? " · observado ao vivo" : " · pelo registro"}
        </p>
      </div>
    </li>
  );
}

export function ProntidaoDeOperacao({ ativoId }: { ativoId: string }) {
  const consulta = useQuery({
    queryKey: ["cofre", "prontidao", ativoId],
    queryFn: () => cofre.prontidao(ativoId),
    retry: false,
  });

  const cabecalho = (
    <div className="flex items-center gap-2">
      <Waypoints aria-hidden="true" className="h-4 w-4 text-muted-foreground" />
      <h4 className="text-sm font-semibold">Prontidão por portão</h4>
    </div>
  );

  if (consulta.isPending) {
    return (
      <div className="border-b border-border p-5">
        {cabecalho}
        <p className="mt-3 text-xs text-muted-foreground">Conferindo o que falta…</p>
      </div>
    );
  }

  // Falha é falha. Um painel que desenhasse "nada pendente" aqui afirmaria que
  // está tudo em ordem sobre uma resposta que ninguém leu.
  if (consulta.isError || !ehProntidao(consulta.data)) {
    const erro = consulta.error;
    const frase = erro instanceof Error
      ? erro.message
      : "O Cofre respondeu a prontidão em um formato que esta tela não reconhece.";
    return (
      <div className="border-b border-border p-5">
        {cabecalho}
        <p className="mt-3 text-xs leading-5 text-muted-foreground">
          Não foi possível ler a prontidão deste ativo. {frase}
        </p>
        <button
          type="button"
          onClick={() => void consulta.refetch()}
          className="mt-3 rounded-md border border-border bg-background px-3 py-1.5 text-xs font-medium hover:bg-muted"
        >
          Tentar de novo
        </button>
      </div>
    );
  }

  const prontidao = consulta.data;
  const resumo = resumoDeProntidao(prontidao);
  const producao = prontidao.producao_possivel ?? [];

  return (
    <div className="border-b border-border p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        {cabecalho}
        <span className="text-[11px] tabular-nums text-muted-foreground">{fraseDoResumo(resumo)}</span>
      </div>

      <ul className="mt-3 space-y-2.5">
        {PERGUNTAS.map((chave) => (
          <Linha
            key={chave}
            rotulo={PERGUNTA_LABEL[chave]}
            valor={prontidao.perguntas[chave].valor}
            motivo={prontidao.perguntas[chave].motivo}
            procedencia={prontidao.perguntas[chave].procedencia}
          />
        ))}
      </ul>

      <div className="mt-4 grid gap-2 text-[11px] sm:grid-cols-3">
        <span className={cn("rounded-md border px-2 py-1", prontidao.pronto_para_receber_peca ? "text-emerald-600" : "text-destructive")}>
          Receber peça: {prontidao.pronto_para_receber_peca ? "sim" : "não"}
        </span>
        <span className={cn("rounded-md border px-2 py-1", prontidao.pronto_para_operar_acesso ? "text-emerald-600" : "text-destructive")}>
          Operar acesso: {prontidao.pronto_para_operar_acesso ? "sim" : "não"}
        </span>
        <span className={cn("rounded-md border px-2 py-1", prontidao.pronto_para_publicar ? "text-emerald-600" : "text-destructive")}>
          Publicar: {prontidao.pronto_para_publicar ? "sim" : "não"}
        </span>
      </div>

      {prontidao.bloqueios.length ? (
        <div className="mt-4 rounded-md border border-border bg-muted/40 p-3">
          <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">
            O que impede acesso/publicação
          </p>
          <ul className="mt-1.5 space-y-1">
            {prontidao.bloqueios.map((bloqueio) => (
              <li key={bloqueio} className="flex items-start gap-1.5 text-xs leading-5">
                <ArrowRight aria-hidden="true" className="mt-1 h-3 w-3 shrink-0 text-muted-foreground" />
                <span>{bloqueio}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {producao.length ? (
        <p className="mt-3 text-[11px] leading-4 text-muted-foreground">
          Produção possível hoje: {producao.map((e) => e.nome).join(", ")} — capacidade
          declarada nos manifestos, não fila disponível.
        </p>
      ) : null}

      {/* A frase que explica por que não existe um botão "publicar" aqui. */}
      <p className="mt-3 text-[11px] leading-4 text-muted-foreground">
        Esta leitura responde e não executa: ela não cria job, não abre navegador e não
        publica. A publicação continua sendo um ato separado, com aprovação própria.
      </p>
    </div>
  );
}

export default ProntidaoDeOperacao;
