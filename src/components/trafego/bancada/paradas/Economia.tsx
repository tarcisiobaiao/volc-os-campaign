/**
 * Parada 5 — Economia. Quanto isto pode gastar por dia.
 *
 * Vem depois de Termos porque é a régua do leilão que dimensiona a aposta: o
 * CPC dos termos é o que diz se dez reais compram trinta cliques ou três.
 *
 * ## ⚠️ Possibilidade de gasto servido, e NÃO teto garantido
 *
 * O Google pode servir até aproximadamente 2× o orçamento diário médio em
 * determinados dias, compensando dentro do mês. Chamar esse número de "teto"
 * seria uma promessa que a plataforma não faz: ela promete a média mensal, não
 * o dia. Um operador que lê "teto de R$ 20,00" e vê R$ 20,00 gastos num dia
 * acha que bateu no limite; um que lê "pode servir até" sabe que aquilo era o
 * previsto.
 *
 * A ressalva mensal viaja colada, e o frescor NÃO se associa a esta aritmética:
 * ela é uma regra da plataforma sobre um número que o operador acabou de
 * digitar, não uma medição com idade.
 *
 * ## ⚠️ `cost_micros` aparece como "custo servido"
 *
 * Nunca como "gasto" ou "investimento": o que a métrica conta é o que a
 * plataforma serviu e cobrou, e a diferença importa quando há crédito, ajuste
 * ou tráfego inválido devolvido depois.
 */
import React from 'react';

import { BlocoDeEvidencia, LinhaDeFato } from '../BlocoDeEvidencia';
import { ChipDeEstado } from '../ChipDeEstado';
import { MesaDeLance } from '../../MesaDeLance';
import {
  ORDEM_DOS_PORTOES, ROTULO_DO_PORTAO, EXIGENCIA_DO_PORTAO,
  type PlanoVigenteResposta,
} from '@/lib/trafego/portoes';
import { GLIFO_DO_ESTADO, TOM_DO_ESTADO } from './portoesVisual';
import type { Cockpit, EstrategiaDeLance } from '@/types/trafego';

/** A moeda em que a régua do canário trabalha nesta primeira versão. */
export const MOEDA_DA_REGUA = 'BRL';

const brl = (n: number) => `R$ ${n.toFixed(2).replace('.', ',')}`;

export const ParadaEconomia: React.FC<{
  cockpit: Cockpit;
  plano: PlanoVigenteResposta | null;
  planoIndisponivel: string | null;
  orcamento: number | null;
  lance: number | null;
  estrategia: EstrategiaDeLance;
  // Os controles continuam no componente que já os conhece.
  orcamentoBruto: string;
  onOrcamento: (v: string) => void;
  lanceBruto: string;
  onLance: (v: string) => void;
  onEstrategia: (e: EstrategiaDeLance) => void;
  graduacao: number;
  onGraduacao: (g: number) => void;
}> = ({
  cockpit, plano, planoIndisponivel, orcamento, lance, estrategia,
  orcamentoBruto, onOrcamento, lanceBruto, onLance, onEstrategia, graduacao, onGraduacao,
}) => {
  const conta = cockpit.conta;
  const moedaDaConta = conta?.moeda ?? null;
  // A régua do canário é BRL. Quando a conta declara OUTRA moeda, isso é dito —
  // não convertido em silêncio, porque não há taxa declarada em lugar nenhum.
  const moedaDivergente = Boolean(moedaDaConta && moedaDaConta !== MOEDA_DA_REGUA);

  return (
    <div className="space-y-4">
      <BlocoDeEvidencia titulo="A conta que vai gastar" tom={conta?.vinculada ? 'bom' : 'ruim'}>
        <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
          <LinhaDeFato
            rotulo="conta de anúncio"
            valor={conta?.customer_id ? <span className="tabular">{conta.customer_id}</span> : null}
            fonte="o projeto"
            ausencia={conta?.motivo ?? 'o projeto não tem conta vinculada'}
          />
          <LinhaDeFato rotulo="nome da conta" valor={conta?.nome ?? null} fonte="a conta" />
          <LinhaDeFato
            rotulo="moeda da conta"
            valor={moedaDaConta}
            fonte="a conta"
            ausencia={conta?.detalhes_indisponiveis ?? 'não lida'}
          />
          {/* ⚠️ O fuso decide A QUE HORA o dia do orçamento vira. Nenhum dos dois
              aparecia na tela anterior, e os dois mudam o payload. */}
          <LinhaDeFato
            rotulo="fuso da conta"
            valor={conta?.fuso ?? null}
            fonte="a conta"
            ausencia={conta?.detalhes_indisponiveis ?? 'não lido'}
          />
          <LinhaDeFato
            rotulo="meta de conversão"
            valor={conta?.meta_conversao?.primaria?.nome ?? null}
            fonte="a conta"
            ausencia="a conta não tem ação primária resolvida"
          />
          <LinhaDeFato
            rotulo="auto-tagging"
            valor={conta?.auto_tagging == null ? null : (conta.auto_tagging ? 'ligado' : 'desligado')}
            fonte="a conta"
            ausencia="não lido"
          />
        </dl>

        {moedaDivergente && (
          <p className="mt-3 max-w-[70ch] text-sm leading-6 text-warning text-pretty">
            A conta declara <strong className="text-foreground">{moedaDaConta}</strong> e esta
            primeira versão operacional trabalha em <strong className="text-foreground">BRL</strong>.
            Os limites abaixo são comparados em BRL, sem conversão — não existe taxa
            declarada neste sistema para converter.
          </p>
        )}
      </BlocoDeEvidencia>

      {/* Os controles: orçamento, lance, estratégia e graduação. */}
      <MesaDeLance
        cockpit={cockpit}
        estrategia={estrategia}
        onEstrategia={onEstrategia}
        lance={lanceBruto}
        onLance={onLance}
        budget={orcamentoBruto}
        onBudget={onOrcamento}
        graduacao={graduacao}
        onGraduacao={onGraduacao}
      />

      <BlocoDeEvidencia titulo="A consequência do orçamento" tom="atencao">
        <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
          <LinhaDeFato
            rotulo="orçamento diário"
            valor={orcamento == null ? null : <span className="tabular">{brl(orcamento)}</span>}
            fonte="você, agora"
            ausencia="você ainda não declarou"
          />
          <LinhaDeFato
            rotulo="possibilidade de gasto servido no dia"
            valor={orcamento == null ? null : <span className="tabular">até {brl(orcamento * 2)}</span>}
            fonte="regra do Google: até 2× o orçamento diário médio"
          />
          <LinhaDeFato
            rotulo="lance inicial"
            valor={lance == null ? null : <span className="tabular">{brl(lance)}</span>}
            fonte="você, agora"
            ausencia="você ainda não declarou"
          />
          <LinhaDeFato
            rotulo="estratégia"
            valor={estrategia}
            fonte="você, agora"
          />
        </dl>
        {/* ⚠️ A RESSALVA MENSAL, SEMPRE COLADA AO NÚMERO. Sem ela, "até 2×" lê
            como teto garantido — e teto é exatamente o que a plataforma NÃO
            promete no dia. */}
        <p className="mt-3 max-w-[70ch] text-sm leading-6 text-foreground text-pretty">
          O Google pode servir até aproximadamente o dobro do orçamento diário médio em
          determinados dias e compensar nos outros: o compromisso dele é com a média do
          mês, não com o dia. Isto é uma <strong>possibilidade de gasto servido</strong>,
          não um teto garantido.
        </p>
      </BlocoDeEvidencia>

      <BlocoDeEvidencia titulo="Os sete portões de mensuração">
        {planoIndisponivel ? (
          <p className="max-w-[70ch] text-sm leading-6 text-muted-foreground text-pretty">
            {planoIndisponivel}
          </p>
        ) : !plano ? (
          <p className="max-w-[70ch] text-sm leading-6 text-muted-foreground text-pretty">
            Lendo o plano gravado desta conta…
          </p>
        ) : (
          <>
            <ul className="grid gap-3 sm:grid-cols-2">
              {ORDEM_DOS_PORTOES.map((p) => {
                const estado = plano.portoes[p];
                return (
                  <li key={p} className="rounded-md border border-border/60 bg-muted/20 p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-medium text-foreground">{ROTULO_DO_PORTAO[p]}</span>
                      <ChipDeEstado
                        glifo={GLIFO_DO_ESTADO[estado]}
                        palavra={estado.toLowerCase().replace('_', ' ')}
                        descricao={EXIGENCIA_DO_PORTAO[p]}
                        tom={TOM_DO_ESTADO[estado]}
                      />
                    </div>
                    {estado !== 'PRONTO' && (
                      <p className="mt-1.5 max-w-[70ch] text-sm leading-6 text-muted-foreground text-pretty">
                        {EXIGENCIA_DO_PORTAO[p]}
                      </p>
                    )}
                  </li>
                );
              })}
            </ul>
            {/* ⚠️ Estes portões NÃO barram a criação pausada — eles barram a
                ATIVAÇÃO, que não existe nesta tela. Dizê-lo evita que o operador
                trate um portão fechado como impedimento de criar. */}
            <p className="mt-3 max-w-[70ch] text-sm leading-6 text-muted-foreground text-pretty">
              Nenhum destes portões impede criar a campanha pausada. Eles respondem se ela
              poderia ser ativada e se o lance poderia aprender — duas decisões que não
              acontecem aqui.
            </p>
            {plano.bloqueadores.length > 0 && (
              <ul className="mt-3 space-y-1.5 text-sm leading-6 text-muted-foreground">
                {plano.bloqueadores.map((b) => <li key={b}>{b}</li>)}
              </ul>
            )}
          </>
        )}
      </BlocoDeEvidencia>
    </div>
  );
};
