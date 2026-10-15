/**
 * Bancada de design V3 "Instrumento" — os primitivos REAIS em todos os estados.
 *
 * Mesmo contrato da `BancadaVisual` de Tráfego: só existe em desenvolvimento
 * (rota e `import()` sob `import.meta.env.DEV`), e a prova de bundle procura o
 * marcador abaixo no build de produção.
 *
 * Todos os números daqui são FIXTURE inventada. Nenhum vem de conta, banco ou
 * recibo. A faixa "Antes" monta o componente de produção `KpiCards` com os
 * mesmos fatos da faixa "Depois", para comparar o padrão, não o dado.
 *
 * Endereço: `/qa/design`
 */
import React from "react";

import { KpiCards } from "@/components/incubator/dashboard/KpiCards";
import { CabecalhoDePagina } from "@/components/sistema/CabecalhoDePagina";
import { Delta } from "@/components/sistema/Delta";
import { EstadoOperacional } from "@/components/sistema/EstadoOperacional";
import { Frescor } from "@/components/sistema/Frescor";
import { Metrica } from "@/components/sistema/Metrica";
import { FaixaDeMetricas, PainelInstrumento } from "@/components/sistema/PainelInstrumento";
import { RecomendacaoSombra } from "@/components/sistema/RecomendacaoSombra";
import { SeloDeProposta } from "@/components/sistema/SeloDeProposta";
import { Sparkline } from "@/components/sistema/Sparkline";
import type { Verdade } from "@/components/sistema/VerdadeDoDado";
import { Button } from "@/components/ui/button";
import { ESTADO_DE_PROPOSTA, formatarNumero, type EstadoDeProposta } from "@/lib/instrumento";

export const MARCADOR_DA_BANCADA_DE_DESIGN = "volc-bancada-de-design-somente-dev";

/** Relógio fixo: a bancada precisa sair igual em toda captura. */
const AGORA = new Date("2026-10-15T17:00:00Z");
const ha = (min: number) => new Date(AGORA.getTime() - min * 60_000);

const BRL = { tipo: "moeda", moeda: "BRL" } as const;

const CUSTO_14D = [38.2, 41.5, 40.1, 44.8, null, null, 47.3, 45.9, 49.2, 52.6, 50.4, 55.1, 53.8, 58.4];
const RECEITA_14D = [9.1, 8.4, 10.2, 7.9, null, null, 6.8, 7.5, 6.1, 5.9, 6.6, 5.2, 5.8, 4.9];
const ROAS_14D = [0.24, 0.2, 0.25, 0.18, null, null, 0.14, 0.16, 0.12, 0.11, 0.13, 0.09, 0.11, 0.08];

function Secao({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3">
      <h2 className="font-display text-base font-semibold text-foreground">{titulo}</h2>
      {children}
    </section>
  );
}

function AlternarTema() {
  const [escuro, setEscuro] = React.useState(() => document.documentElement.classList.contains("dark"));
  const trocar = (proximo: boolean) => {
    document.documentElement.setAttribute("data-theme-switching", "");
    document.documentElement.classList.toggle("dark", proximo);
    setEscuro(proximo);
    requestAnimationFrame(() => document.documentElement.removeAttribute("data-theme-switching"));
  };
  return (
    <div className="flex gap-2" role="group" aria-label="Tema da bancada">
      <Button variant={escuro ? "outline" : "secondary"} size="sm" aria-pressed={!escuro} onClick={() => trocar(false)}>
        Claro
      </Button>
      <Button variant={escuro ? "secondary" : "outline"} size="sm" aria-pressed={escuro} onClick={() => trocar(true)}>
        Escuro
      </Button>
    </div>
  );
}

const VERDADES: Array<{ verdade: Verdade; valor: number | null; rotulo: string }> = [
  { verdade: "real", valor: 1284, rotulo: "Real" },
  { verdade: "zero", valor: 0, rotulo: "Zero medido" },
  { verdade: "demo", valor: 9120, rotulo: "Demonstração" },
  { verdade: "parcial", valor: 640, rotulo: "Parcial" },
  { verdade: "real", valor: null, rotulo: "Real sem valor" },
  { verdade: "erro", valor: 1284, rotulo: "Erro" },
  { verdade: "bloqueado", valor: null, rotulo: "Bloqueado" },
  { verdade: "indisponivel", valor: null, rotulo: "Indisponível" },
];

const LINHAS = [
  { nome: "Search · institucional", custo: 58.4, receita: 4.9, roas: 0.08, serie: ROAS_14D, lido: ha(12) },
  { nome: "Search · genéricas", custo: 31.75, receita: 12.4, roas: 0.39, serie: [0.31, 0.33, 0.35, 0.36, 0.38, 0.37, 0.39], lido: ha(12) },
  { nome: "Demand Gen · teste", custo: null, receita: null, roas: null, serie: [null, null, null], lido: null },
  { nome: "PMax · catálogo", custo: 12.1, receita: 0, roas: 0, serie: [0, 0, 0, 0, 0], lido: ha(190) },
];

export default function BancadaDeDesign() {
  const [custo, setCusto] = React.useState(58.4);

  return (
    <main className="page-workspace mx-auto max-w-[1400px] space-y-10" data-marcador={MARCADOR_DA_BANCADA_DE_DESIGN}>
      <CabecalhoDePagina
        kicker="Bancada de design — só em desenvolvimento"
        titulo={
          <>
            Instrumento <span className="text-aurora">V3</span>
          </>
        }
        proposito="Os primitivos de métrica, frescor, variação, tendência e hipótese em todos os estados, nos dois temas."
        acao={<AlternarTema />}
      />

      <EstadoOperacional
        tom="demo"
        titulo="Todos os números desta bancada são fixture"
        explicacao="Valores inventados para conferir o desenho. Nenhum vem de conta, banco ou recibo."
      />

      <Secao titulo="Antes · grade de cartões V2 (componente de produção KpiCards)">
        <KpiCards total={42} generating={3} submitted={7} approved={28} rejected={4} />
      </Secao>

      <Secao titulo="Depois · faixa de instrumento V3">
        <PainelInstrumento
          titulo="Economia da carteira · últimos 14 dias"
          lateral={<Frescor lidoEm={ha(12)} agora={AGORA} fonte="Google Ads" />}
        >
          <FaixaDeMetricas>
            <Metrica
              tamanho="hero"
              rotulo="Custo"
              valor={custo}
              formato={BRL}
              verdade="real"
              delta={{ base: 38.2, sentido: "menor-melhor", rotuloBase: "vs. 14 dias atrás" }}
              serie={{ valores: CUSTO_14D, rotulo: "Custo diário, 14 dias", indice: 0 }}
            />
            <Metrica
              rotulo="Receita"
              valor={4.9}
              formato={BRL}
              verdade="parcial"
              detalheDaVerdade="Só JoinAds; GAM sem linhas"
              delta={{ base: 9.1, sentido: "maior-melhor" }}
              serie={{ valores: RECEITA_14D, rotulo: "Receita diária, 14 dias", indice: 1 }}
            />
            <Metrica
              rotulo="ROAS"
              valor={0.08}
              formato={{ tipo: "razao" }}
              verdade="real"
              delta={{ base: 0.24, sentido: "maior-melhor" }}
              serie={{ valores: ROAS_14D, rotulo: "ROAS diário, 14 dias", indice: 2 }}
            />
            <Metrica rotulo="Conversões" valor={null} formato={{ tipo: "inteiro" }} verdade="indisponivel" />
          </FaixaDeMetricas>
        </PainelInstrumento>
        <div className="flex items-center gap-3">
          <Button variant="outline" size="sm" onClick={() => setCusto((c) => Math.round((c + 7.35) * 100) / 100)}>
            Simular nova leitura de custo
          </Button>
          <span className="text-micro text-muted-foreground">O número faz o tick do valor anterior ao novo; nunca parte de zero.</span>
        </div>
      </Secao>

      <Secao titulo="Métrica · estados de verdade">
        <div className="instrumento grid grid-cols-2 gap-6 p-5 md:grid-cols-4">
          {VERDADES.map((v) => (
            <Metrica
              key={v.rotulo}
              tamanho="compacta"
              rotulo={v.rotulo}
              valor={v.valor}
              formato={{ tipo: "inteiro" }}
              verdade={v.verdade}
              lidoEm={v.verdade === "real" || v.verdade === "zero" ? ha(6) : undefined}
              agora={AGORA}
            />
          ))}
          <Metrica tamanho="compacta" rotulo="Carregando" valor={null} formato={{ tipo: "inteiro" }} verdade="real" carregando />
        </div>
      </Secao>

      <div className="grid gap-10 lg:grid-cols-2">
        <Secao titulo="Variação · o sentido decide a cor">
          <ul className="instrumento space-y-2 p-5 text-sm">
            <li className="flex justify-between"><span>Receita sobe (maior é melhor)</span><Delta atual={120} base={100} sentido="maior-melhor" /></li>
            <li className="flex justify-between"><span>Custo sobe (menor é melhor)</span><Delta atual={120} base={100} sentido="menor-melhor" /></li>
            <li className="flex justify-between"><span>Impressões sobem (neutro)</span><Delta atual={120} base={100} sentido="neutro" /></li>
            <li className="flex justify-between"><span>Base zero</span><Delta atual={10} base={0} sentido="maior-melhor" /></li>
            <li className="flex justify-between"><span>Sem base</span><Delta atual={10} base={null} sentido="maior-melhor" /></li>
          </ul>
        </Secao>

        <Secao titulo="Frescor · colado ao número">
          <ul className="instrumento space-y-2 p-5">
            <li><Frescor lidoEm={ha(6)} agora={AGORA} fonte="Google Ads" /></li>
            <li><Frescor lidoEm={ha(190)} agora={AGORA} fonte="JoinAds" /></li>
            <li><Frescor lidoEm={ha(60 * 30)} agora={AGORA} fonte="GAM" /></li>
            <li><Frescor lidoEm={new Date(AGORA.getTime() + 2 * 3600_000)} agora={AGORA} /></li>
            <li><Frescor lidoEm={null} agora={AGORA} fonte="Meta" /></li>
          </ul>
        </Secao>
      </div>

      <Secao titulo="Ciclo fato → recomendação → autorização → ação">
        <div className="flex flex-wrap gap-2">
          {(Object.keys(ESTADO_DE_PROPOSTA) as EstadoDeProposta[]).map((e) => (
            <SeloDeProposta key={e} estado={e} />
          ))}
        </div>
      </Secao>

      <Secao titulo="Recomendação em modo sombra">
        <div className="grid gap-4 lg:grid-cols-2">
          <RecomendacaoSombra
            direcao="pausar"
            titulo="Search · institucional"
            motor="Shadow ROAS v1 · janela madura de 21 dias"
            confianca="media"
            evidencias={[
              { rotulo: "Custo na janela", valor: formatarNumero(812.4, BRL), verdade: "real" },
              { rotulo: "Receita na janela", valor: formatarNumero(61.2, BRL), verdade: "parcial" },
              { rotulo: "ROAS medido", valor: formatarNumero(0.11, { tipo: "razao" }), verdade: "real" },
              { rotulo: "ROAS sob estresse", valor: formatarNumero(0.27, { tipo: "razao" }), verdade: "real", hipotese: true },
            ]}
            consequencia="a campanha deixa de veicular e o custo diário cai a zero até alguém reativar no painel do Google."
            acao={{
              rotulo: "Levar à fila de propostas",
              onClick: () => undefined,
              bloqueio: "Indisponível até o ledger de propostas (v10_03) ser aplicado.",
            }}
          />
          <RecomendacaoSombra
            direcao="escalar"
            titulo="Search · genéricas"
            motor="Shadow ROAS v1 · janela imatura de 5 dias"
            confianca="baixa"
            estado="aguardando"
            evidencias={[
              { rotulo: "ROAS medido", valor: formatarNumero(0.39, { tipo: "razao" }), verdade: "real" },
              { rotulo: "Conversões", valor: null, verdade: "indisponivel" },
            ]}
            consequencia="a verba diária sobe 20% na conta."
          />
        </div>
      </Secao>

      <Secao titulo="Tabela densa">
        <div className="instrumento overflow-hidden p-0">
          <div className="flex items-center justify-between border-b border-border/70 px-4 py-2.5">
            <span className="text-sm font-semibold text-foreground">Campanhas · 4</span>
            <Frescor lidoEm={ha(12)} agora={AGORA} fonte="Google Ads" />
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-denso">
              <thead className="sticky top-0 z-[var(--z-sticky)] bg-muted text-left text-micro uppercase text-muted-foreground">
                <tr className="h-linha-compacta">
                  <th scope="col" className="px-4 font-semibold">Campanha</th>
                  <th scope="col" className="px-4 text-right font-semibold">Custo</th>
                  <th scope="col" className="px-4 text-right font-semibold">Receita</th>
                  <th scope="col" className="px-4 text-right font-semibold">ROAS</th>
                  <th scope="col" className="px-4 font-semibold">Tendência</th>
                </tr>
              </thead>
              <tbody>
                {LINHAS.map((l, i) => (
                  <tr key={l.nome} className={i === 0 ? "h-linha border-t border-border/60 bg-primary/[0.06]" : "h-linha border-t border-border/60"}>
                    <th scope="row" className="px-4 text-left font-medium text-foreground">{l.nome}</th>
                    <td className="numero px-4 text-right">{formatarNumero(l.custo, BRL)}</td>
                    <td className="numero px-4 text-right">{formatarNumero(l.receita, BRL)}</td>
                    <td className="numero px-4 text-right">{formatarNumero(l.roas, { tipo: "razao" })}</td>
                    <td className="px-4">
                      <Sparkline valores={l.serie} rotulo={`ROAS de ${l.nome}`} serie={2} largura={80} altura={20} desenhar={false} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </Secao>
    </main>
  );
}
