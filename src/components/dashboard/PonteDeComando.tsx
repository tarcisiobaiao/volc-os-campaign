import React from "react";
import { format } from "date-fns";
import { ptBR } from "date-fns/locale";
import { ChevronDown, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { EstadoOperacional } from "@/components/sistema/EstadoOperacional";
import { Frescor } from "@/components/sistema/Frescor";
import { Metrica } from "@/components/sistema/Metrica";
import { FaixaDeMetricas, PainelInstrumento } from "@/components/sistema/PainelInstrumento";
import type { FormatoDeNumero } from "@/lib/instrumento";

/**
 * Ponte de comando — o primeiro bloco depois do login.
 *
 * Substitui a grade de seis cartões idênticos (proibida pelo design.md) por
 * UMA faixa de instrumento: o lucro líquido como métrica dominante e quatro
 * métricas de faixa ao lado, cada uma com frescor e variação só quando
 * medida. Componente de apresentação: quem calcula lucro, ROI e impostos
 * continua sendo a página, com as mesmas funções de antes.
 */

const BRL: FormatoDeNumero = { tipo: "moeda", moeda: "BRL" };

export type PeriodoDaPonte = "today" | "yesterday" | "custom";

export interface ValoresDaPonte {
  lucroLiquido: number | null;
  investimento: number | null;
  receitaLiquida: number | null;
  /** Receita ÷ investimento (razão). `null` quando não há gasto. */
  roas: number | null;
  /** Lucro líquido ÷ investimento, em FRAÇÃO (0,216 = 21,6%). */
  roiFinal: number | null;
  /** Variações do período em PONTOS PERCENTUAIS, como o serviço devolve. */
  variacao?: { lucro?: number; investimento?: number; receita?: number; roi?: number };
}

interface Props {
  nome?: string | null;
  periodo: PeriodoDaPonte;
  dataSelecionada?: string;
  /** O seletor de período existente da página, renderizado como está. */
  seletorDePeriodo: React.ReactNode;
  valores: ValoresDaPonte;
  carregando: boolean;
  /** A leitura falhou: os números do serviço são preenchimento, não medição. */
  falhou: boolean;
  lidoEm?: string | null;
  rodape?: React.ReactNode;
  onRecarregar: () => void;
  onPedirAtualizacao: (alvo: "google-ads" | "gam") => void;
  pedidoEmCurso: boolean;
  resultadoDoPedido?: "success" | "error" | "idle" | "loading";
}

function saudacao(agora: Date): string {
  const h = agora.getHours();
  if (h < 5) return "Boa noite";
  if (h < 12) return "Bom dia";
  if (h < 18) return "Boa tarde";
  return "Boa noite";
}

/**
 * A variação vem do serviço em pontos percentuais. `Metrica` compara contra
 * uma BASE absoluta; a base é reconstruída da própria variação. Variação
 * ausente, não-finita ou zero não vira delta: zero aqui também é o valor de
 * "a comparação não rodou", e o contrato ainda não distingue os dois.
 */
function deltaDe(atual: number | null, pct: number | undefined, rotuloBase: string, sentido: "maior-melhor" | "menor-melhor" | "neutro") {
  if (atual == null || pct == null || !Number.isFinite(pct) || pct === 0 || pct <= -100) return undefined;
  return { base: atual / (1 + pct / 100), sentido, rotuloBase };
}

export function PonteDeComando({
  nome,
  periodo,
  dataSelecionada,
  seletorDePeriodo,
  valores,
  carregando,
  falhou,
  lidoEm,
  rodape,
  onRecarregar,
  onPedirAtualizacao,
  pedidoEmCurso,
  resultadoDoPedido,
}: Props) {
  const agora = new Date();
  const primeiroNome = (nome ?? "").trim().split(/\s+/)[0];
  const rotuloDoPeriodo =
    periodo === "today"
      ? "Hoje"
      : periodo === "yesterday"
        ? "Ontem"
        : dataSelecionada
          ? format(new Date(dataSelecionada + "T12:00:00"), "dd 'de' MMMM", { locale: ptBR })
          : "Data escolhida";
  const base = "vs período anterior";
  const verdade = "real" as const;

  return (
    <section aria-labelledby="ponte-titulo" className="space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <p className="kicker mb-2">Portfólio · {format(agora, "EEEE, d 'de' MMMM", { locale: ptBR })}</p>
          <h1 id="ponte-titulo" className="font-display text-[1.75rem] font-bold leading-[1.1] tracking-tight text-foreground md:text-4xl">
            {primeiroNome ? `${saudacao(agora)}, ${primeiroNome}` : "Dashboard Geral"}
          </h1>
          <div className="aurora-rule mt-3 w-16" aria-hidden />
          <p className="mt-3 max-w-[70ch] text-sm text-muted-foreground">
            O resultado de todos os projetos e campanhas, com a hora de cada leitura.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {seletorDePeriodo}
          {/* Antes eram três botões — dois deles com o gradiente primário —
              disputando o cabeçalho. Recarregar a leitura e PEDIR uma coleta
              nova são atos diferentes: o primeiro só lê, o segundo dispara um
              fluxo no servidor. Ficam num menu, e o nome de cada item diz qual
              é qual. */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="secondary" className="gap-2" disabled={pedidoEmCurso}>
                <RefreshCw className={pedidoEmCurso ? "h-4 w-4 animate-spin motion-reduce:animate-none" : "h-4 w-4"} aria-hidden />
                Atualizar dados
                <ChevronDown className="h-4 w-4 opacity-70" aria-hidden />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-72">
              <DropdownMenuItem onSelect={onRecarregar} className="flex-col items-start gap-0.5">
                <span className="font-medium">Recarregar esta leitura</span>
                <span className="text-xs text-muted-foreground">Lê de novo o que já está no banco.</span>
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuLabel className="kicker">Pedir coleta nova ao servidor</DropdownMenuLabel>
              <DropdownMenuItem onSelect={() => onPedirAtualizacao("google-ads")}>Coletar Google Ads</DropdownMenuItem>
              <DropdownMenuItem onSelect={() => onPedirAtualizacao("gam")}>Coletar Ad Manager (GAM)</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <span role="status" aria-live="polite" className="text-xs text-muted-foreground">
            {resultadoDoPedido === "success" ? "Coleta pedida. Os números mudam quando ela terminar." : null}
            {resultadoDoPedido === "error" ? <span className="text-destructive">O pedido de coleta falhou.</span> : null}
          </span>
        </div>
      </header>

      <PainelInstrumento
        titulo={`Resultado · ${rotuloDoPeriodo}`}
        lateral={lidoEm !== undefined && !falhou ? <Frescor lidoEm={lidoEm} fonte="banco VOLC" /> : null}
      >
        {falhou && !carregando ? (
          <EstadoOperacional
            tom="erro"
            titulo="A leitura do resultado falhou"
            explicacao="Receita ou investimento não voltaram do banco. Nenhum número é mostrado para não confundir falha com zero."
            acao={{ rotulo: "Tentar ler de novo", onClick: onRecarregar }}
          />
        ) : (
          // No telefone, o lucro ocupa a linha inteira e as quatro métricas de
          // faixa vão em duas colunas: cinco blocos empilhados empurravam o
          // ROI para a terceira tela de rolagem.
          <FaixaDeMetricas className="grid-cols-2 gap-x-4 [&>*:first-child]:col-span-2 lg:[&>*:first-child]:col-span-1">
            <Metrica
              tamanho="hero"
              rotulo="Lucro líquido"
              valor={valores.lucroLiquido}
              formato={BRL}
              verdade={verdade}
              carregando={carregando}
              delta={deltaDe(valores.lucroLiquido, valores.variacao?.lucro, base, "maior-melhor")}
            />
            <Metrica
              rotulo="Investimento"
              valor={valores.investimento}
              formato={BRL}
              verdade={verdade}
              carregando={carregando}
              delta={deltaDe(valores.investimento, valores.variacao?.investimento, base, "neutro")}
            />
            <Metrica
              rotulo="Receita líquida"
              valor={valores.receitaLiquida}
              formato={BRL}
              verdade={verdade}
              carregando={carregando}
              delta={deltaDe(valores.receitaLiquida, valores.variacao?.receita, base, "maior-melhor")}
            />
            <Metrica
              rotulo="ROAS"
              valor={valores.roas}
              formato={{ tipo: "razao" }}
              verdade={verdade}
              carregando={carregando}
            />
            <Metrica
              rotulo="ROI final"
              valor={valores.roiFinal}
              formato={{ tipo: "percentual" }}
              verdade={verdade}
              carregando={carregando}
            />
          </FaixaDeMetricas>
        )}
        {/* Com a leitura falha, a contagem de campanhas também é preenchimento. */}
        {rodape && !falhou ? <div className="mt-4 border-t border-border/70 pt-3 text-xs text-muted-foreground">{rodape}</div> : null}
      </PainelInstrumento>
    </section>
  );
}
