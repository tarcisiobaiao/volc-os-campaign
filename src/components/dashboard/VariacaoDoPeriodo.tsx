import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * A variação de um KPI contra o período anterior.
 *
 * ---------------------------------------------------------------------------
 * O QUE ESTE COMPONENTE EXISTE PARA IMPEDIR
 * ---------------------------------------------------------------------------
 *
 * Os cinco cartões do Dashboard Geral escreviam isto, um por um:
 *
 *     <ArrowUpRight className="text-green-500" />
 *     <span className="text-green-500">+{summary?.trendsPercentage?.roi || 0}%</span>
 *
 * Três afirmações fixas no código, nenhuma delas medida:
 *
 *   • A SETA APONTA PARA CIMA sempre. Uma queda de 40% era desenhada subindo.
 *   • A COR É VERDE sempre. "Piorou" e "melhorou" tinham a mesma tinta.
 *   • `|| 0` transforma AUSÊNCIA em "+0%". Quando a RPC de comparação falha, o
 *     serviço devolve zero, e a tela dizia "+0%" com seta verde para cima — que
 *     o operador lê como "medi, e está estável, e isso é bom".
 *
 * O `design.md` chama isso pelo nome em duas regras: "Fake KPI heroes; invented
 * zeros; numbers without freshness" e "Do not present a number without
 * freshness or turn absence into zero". O PRODUCT.md põe na lista de
 * anti-referências: "dashboard genérico que exibe métricas sem fonte ou cria
 * sensação de controle fictícia".
 *
 * ---------------------------------------------------------------------------
 * O QUE ESTE COMPONENTE **NÃO** CONSEGUE CONSERTAR
 * ---------------------------------------------------------------------------
 *
 * `supabaseDataService` inicializa `trendsPercentage` com zeros e mantém os
 * zeros quando a RPC `get_period_comparison` falha
 * (`supabaseDataService.ts:1564`). Não existe, no contrato de dados, um valor
 * que signifique "não consegui medir" — `0` carrega ao mesmo tempo "sem
 * variação" e "sem leitura".
 *
 * Distinguir os dois é mudança de CONTRATO DE DADOS, fora do escopo desta
 * frente. Então aqui a apresentação faz o máximo honesto que pode: com `0` ela
 * para de afirmar direção e sinal, e escreve "sem variação no período" em tinta
 * neutra. Deixa de mentir; ainda não sabe a verdade inteira.
 *
 * A proposta para fechar isso está no handoff: `trendsPercentage` passar a
 * aceitar `null` por métrica, e este componente já trata `null` e `undefined`
 * como "não medido" — é só o serviço parar de traduzir falha em zero.
 */
export const VariacaoDoPeriodo: React.FC<{
  valor: number | null | undefined;
  /** O que a comparação usa como base. Aparece ao lado, em tinta secundária. */
  base?: string;
  className?: string;
}> = ({ valor, base, className }) => {
  // `null`/`undefined` = a leitura não aconteceu. Não é zero.
  if (valor === null || valor === undefined || Number.isNaN(valor)) {
    return (
      <span className={cn("flex items-center gap-1 text-xs text-muted-foreground", className)}>
        <Minus className="h-3 w-3" aria-hidden="true" />
        <span>variação não medida</span>
      </span>
    );
  }

  if (valor === 0) {
    return (
      <span className={cn("flex items-center gap-1 text-xs text-muted-foreground", className)}>
        <Minus className="h-3 w-3" aria-hidden="true" />
        <span className="tabular">sem variação{base ? ` ${base}` : ""}</span>
      </span>
    );
  }

  const subiu = valor > 0;
  const Seta = subiu ? ArrowUpRight : ArrowDownRight;

  return (
    <span
      className={cn(
        "flex items-center gap-1 text-xs font-medium",
        subiu ? "text-success" : "text-destructive",
        className
      )}
    >
      {/* A seta é redundante com o sinal de propósito: o PRODUCT.md exige que
          estado nunca dependa só de cor, e "+" / "−" sozinhos são fáceis de
          perder num número pequeno. Glifo, sinal e cor dizem a mesma coisa. */}
      <Seta className="h-3 w-3" aria-hidden="true" />
      <span className="tabular">
        {subiu ? "+" : "−"}
        {Math.abs(valor).toFixed(1)}%
      </span>
      {base && <span className="font-normal text-muted-foreground">{base}</span>}
    </span>
  );
};
