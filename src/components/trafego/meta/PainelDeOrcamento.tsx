/**
 * A etapa de orçamento: ABO ou CBO, diário ou total (`F04`, `F05`, `F06`).
 *
 * ## O que esta tela precisa impedir
 *
 * Trocar onde a verba mora não é trocar um rótulo: é mudar QUEM decide o gasto.
 * Em ABO cada conjunto tem a verba dele e a Meta distribui dentro do conjunto;
 * em CBO existe uma verba só e a Meta decide quanto vai para cada conjunto. Um
 * seletor que trocasse isso no clique deixaria um plano de R$ 10,00 por
 * conjunto virar R$ 10,00 no total — sem que ninguém tivesse decidido reduzir a
 * verba a um décimo. Por isso a troca é um ato de DOIS tempos: escolher e
 * confirmar, com a consequência escrita antes do segundo clique.
 *
 * ## ⚠️ O campo de valor não pode perder o foco (`A31`)
 *
 * O texto DIGITADO é o estado; o valor interpretado aparece ao lado. Guardar
 * centavos e reescrever o input a cada tecla faria "1" virar "R$ 0,01", o
 * cursor pular para o fim e o segundo dígito cair no lugar errado. `Campo` e
 * `Input` moram no topo do módulo justamente para que a identidade do nó não
 * mude entre renders.
 */
import React from 'react';
import { CircleAlert, Landmark, Layers3 } from 'lucide-react';

import { BlocoDeEvidencia, LinhaDeFato } from '@/components/trafego/bancada';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

import { Campo, GrupoDeEscolha } from './primitivas';
import { fluxoPausadoImplementado } from './capacidadePausada';
import {
  Draft, NivelDeOrcamento, PeriodoDeOrcamento, formatarBrl, ondeAVerbaMoraLocal,
  orcamentosDoPlano, reaisParaMinor,
} from './rascunho';
import type { ModoDeOrcamentoMetaV2, ResumoDoPlanoMetaV2 } from '@/lib/pautadorApi';

const PALAVRA_DO_NIVEL: Record<NivelDeOrcamento, string> = {
  ADSET: 'Em cada conjunto (ABO)',
  CAMPAIGN: 'Na campanha (CBO)',
};

const PALAVRA_DO_PERIODO: Record<PeriodoDeOrcamento, string> = {
  DAILY: 'Diário',
  LIFETIME: 'Total do período',
};

/** A consequência da troca, em linguagem de operador e ANTES do segundo clique. */
function consequencia(
  de: { nivel: NivelDeOrcamento; periodo: PeriodoDeOrcamento },
  para: { nivel: NivelDeOrcamento; periodo: PeriodoDeOrcamento },
  draft: Draft,
): string[] {
  const frases: string[] = [];
  if (de.nivel !== para.nivel) {
    frases.push(para.nivel === 'CAMPAIGN'
      ? 'A verba deixa de ser de cada conjunto e passa a ser UMA SÓ, decidida na '
        + 'campanha. A Meta escolhe quanto vai para cada conjunto; você deixa de '
        + 'escolher. Os valores por conjunto continuam guardados neste rascunho e '
        + 'voltam se você desfizer a troca — mas eles NÃO viajam no corpo enviado.'
      : 'A verba deixa de ser uma só e volta a ser de cada conjunto. Você passa a '
        + 'decidir o valor de cada um, e a verba da campanha deixa de viajar no '
        + 'corpo enviado.');
    frases.push('Os dois níveis nunca viajam juntos: a Meta recusa um plano com '
      + 'verba na campanha e no conjunto ao mesmo tempo (META_BUDGET_DUPLICATED).');
  }
  if (de.periodo !== para.periodo) {
    frases.push(para.periodo === 'LIFETIME'
      ? 'O valor deixa de ser por dia e passa a ser o total do período. O mesmo '
        + 'número escrito continua o mesmo número — o que muda é o que ele '
        + 'significa, e nada é recalculado por conta própria.'
      : 'O valor deixa de ser o total do período e passa a ser por dia. O número '
        + 'escrito não é convertido: quem decide quanto vale por dia é você.');
    if (para.periodo === 'LIFETIME') {
      frases.push('Orçamento total exige data de TÉRMINO em todos os conjuntos; sem '
        + 'ela o plano é recusado com META_SCHEDULE_END_REQUIRED.');
    }
  }
  const atuais = orcamentosDoPlano(draft).filter((item) => item.minor > 0);
  if (atuais.length) {
    frases.push(`Nenhum valor é movido agora: ${atuais
      .map((item) => `${item.rotulo} · ${formatarBrl(item.minor)}`).join(' · ')}.`);
  }
  return frases;
}

export const PainelDeOrcamento: React.FC<{
  draft: Draft;
  /** Modos que a receita escolhida registra, com o nível de prova de cada um. */
  modos: readonly ModoDeOrcamentoMetaV2[];
  /** O resumo do SERVIDOR. Quando existe, é ele quem diz onde a verba mora. */
  resumo: ResumoDoPlanoMetaV2 | null;
  onTrocarModo: (nivel: NivelDeOrcamento, periodo: PeriodoDeOrcamento) => void;
  onValorDaCampanha: (texto: string) => void;
  onValorDoConjunto: (chave: string, texto: string) => void;
  /** Motivo declarado pelo servidor para o compartilhamento entre conjuntos. */
  motivoDoCompartilhamento: string | null;
}> = ({
  draft, modos, resumo, onTrocarModo, onValorDaCampanha, onValorDoConjunto,
  motivoDoCompartilhamento,
}) => {
  const atual = { nivel: draft.nivelDeOrcamento, periodo: draft.periodoDeOrcamento };
  const [pendente, setPendente] = React.useState<{
    nivel: NivelDeOrcamento; periodo: PeriodoDeOrcamento;
  } | null>(null);

  // ⚠️ Uma troca pendente que o rascunho já aplicou (ou que outra edição tornou
  // obsoleta) não pode continuar oferecendo "confirmar": ela descreveria um
  // salto que não existe mais.
  React.useEffect(() => {
    setPendente((atualPendente) => (
      atualPendente
        && atualPendente.nivel === draft.nivelDeOrcamento
        && atualPendente.periodo === draft.periodoDeOrcamento
        ? null : atualPendente));
  }, [draft.nivelDeOrcamento, draft.periodoDeOrcamento]);

  const modoDoPlano = modos.find(
    (item) => item.nivel === atual.nivel && item.periodo === atual.periodo);
  const cbo = atual.nivel === 'CAMPAIGN';
  const diario = atual.periodo === 'DAILY';
  const rotuloDoValor = diario ? 'Orçamento diário em reais' : 'Orçamento total em reais';

  const pedir = (proximo: { nivel: NivelDeOrcamento; periodo: PeriodoDeOrcamento }) => {
    if (proximo.nivel === atual.nivel && proximo.periodo === atual.periodo) return;
    setPendente(proximo);
  };

  const ajudaDoValor = (texto: string) => {
    const minor = reaisParaMinor(texto);
    return minor > 0
      ? `A bancada entendeu ${formatarBrl(minor)}${diario ? ' por dia' : ' no período'}.`
      : 'Informe um valor maior que zero. Use vírgula ou ponto para os centavos.';
  };

  return (
    <>
      <div className="space-y-3">
        <p className="kicker text-primary">Onde a verba mora</p>
        <GrupoDeEscolha<NivelDeOrcamento>
          rotuloAcessivel="Onde a verba mora"
          valor={atual.nivel}
          onEscolher={(nivel) => pedir({ nivel, periodo: atual.periodo })}
          opcoes={[
            {
              id: 'ADSET', nome: PALAVRA_DO_NIVEL.ADSET,
              detalhe: 'você decide o valor de cada conjunto',
            },
            {
              id: 'CAMPAIGN', nome: PALAVRA_DO_NIVEL.CAMPAIGN,
              detalhe: 'a Meta distribui uma verba só entre os conjuntos',
            },
          ]}
        />
        <p className="kicker text-primary">Ritmo da verba</p>
        <GrupoDeEscolha<PeriodoDeOrcamento>
          rotuloAcessivel="Ritmo da verba"
          valor={atual.periodo}
          onEscolher={(periodo) => pedir({ nivel: atual.nivel, periodo })}
          opcoes={[
            { id: 'DAILY', nome: PALAVRA_DO_PERIODO.DAILY, detalhe: 'o valor é por dia' },
            {
              id: 'LIFETIME', nome: PALAVRA_DO_PERIODO.LIFETIME,
              detalhe: 'o valor é o total; exige data de término',
            },
          ]}
        />
      </div>

      {/* ⚠️ O SEGUNDO TEMPO DA TROCA. Nada mudou ainda: o rascunho só muda no
          clique de confirmar, e é por isso que a consequência cabe aqui. */}
      {pendente && (
        <div
          className="space-y-3 rounded-lg border border-warning/40 bg-warning/10 p-4"
          role="group"
          aria-label="Confirmar a troca do modo de orçamento"
        >
          <div className="flex items-start gap-3">
            <CircleAlert className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden />
            <div className="min-w-0 space-y-2">
              <p className="text-sm font-semibold text-foreground">
                Trocar de {PALAVRA_DO_NIVEL[atual.nivel]} · {PALAVRA_DO_PERIODO[atual.periodo]}
                {' '}para {PALAVRA_DO_NIVEL[pendente.nivel]} · {PALAVRA_DO_PERIODO[pendente.periodo]}?
              </p>
              {consequencia(atual, pendente, draft).map((frase) => (
                <p key={frase} className="max-w-[74ch] text-sm leading-relaxed text-pretty text-muted-foreground">
                  {frase}
                </p>
              ))}
            </div>
          </div>
          <div className="flex flex-wrap gap-3">
            <Button
              type="button"
              onClick={() => { onTrocarModo(pendente.nivel, pendente.periodo); setPendente(null); }}
            >
              Confirmar a troca
            </Button>
            <Button type="button" variant="outline" onClick={() => setPendente(null)}>
              Manter como está
            </Button>
          </div>
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        {diario && (cbo || draft.conjuntos.length === 1) && <div role="group" className="flex flex-wrap gap-2 md:col-span-2" aria-label="Valores sugeridos">
          {[10, 25, 50, 100].map(valor => <Button key={valor} type="button" variant="outline" size="sm"
            onClick={() => cbo ? onValorDaCampanha(`${valor},00`) : onValorDoConjunto(draft.conjuntos[0].key, `${valor},00`)}>
            R$ {valor}/dia
          </Button>)}
        </div>}
        {cbo ? (
          <Campo
            id="meta-budget"
            rotulo={rotuloDoValor}
            ajuda={ajudaDoValor(draft.budgetBrl)}
            largo
          >
            <Input
              id="meta-budget"
              inputMode="decimal"
              value={draft.budgetBrl}
              onChange={(e) => onValorDaCampanha(e.target.value)}
            />
          </Campo>
        ) : (
          draft.conjuntos.map((conjunto) => (
            <Campo
              key={conjunto.key}
              id={`meta-budget-${conjunto.key}`}
              rotulo={draft.conjuntos.length > 1
                ? `${rotuloDoValor} · ${conjunto.nome || 'conjunto sem nome'}`
                : rotuloDoValor}
              ajuda={ajudaDoValor(conjunto.orcamentoBrl)}
              largo={draft.conjuntos.length === 1}
            >
              <Input
                id={`meta-budget-${conjunto.key}`}
                inputMode="decimal"
                value={conjunto.orcamentoBrl}
                onChange={(e) => onValorDoConjunto(conjunto.key, e.target.value)}
              />
            </Campo>
          ))
        )}

        {/* ⚠️ Não é mais uma escolha. Em 05/09/2026 a validação real na Meta
            recusou o compartilhamento ligado com o código 100/4005 — ele
            exige estratégia de lance no Campaign. O contrato V2 recusa `true`
            com nome próprio em vez de convertê-lo em silêncio, e o corpo
            enviado carrega o booleano explícito como `false`. */}
        <details className="text-sm md:col-span-2"><summary className="cursor-pointer py-2 text-muted-foreground">Compartilhamento de orçamento</summary>
          <strong className="block text-sm text-foreground">
            Compartilhamento entre conjuntos: desativado
          </strong>
          <p className="mt-1 max-w-[72ch] text-sm leading-relaxed text-pretty text-muted-foreground">
            O compartilhamento entre conjuntos fica desativado nesta configuração. O orçamento de campanha (CBO) continua disponível como uma escolha independente.
          </p>
        </details>
      </div>

      <details className="text-sm"><summary className="cursor-pointer py-2 text-muted-foreground">Conferir distribuição e configuração</summary>
      <BlocoDeEvidencia titulo="Como a verba é aplicada" tom={resumo ? 'verificado' : 'info'}>
        {/* ⚠️ A frase vem do SERVIDOR quando existe compilação. Recalculá-la
            aqui seria a tela afirmando sobre o corpo enviado uma coisa que o
            corpo enviado não confirmou (`F37`/`A33`). */}
        <LinhaDeFato
          rotulo="Onde a verba mora"
          valor={resumo ? resumo.orcamento.onde_a_verba_mora : ondeAVerbaMoraLocal(draft)}
          fonte={resumo ? 'o resumo do backend' : 'você, agora · ainda não conferido no backend'}
        />
        <LinhaDeFato
          rotulo="Ritmo"
          valor={resumo
            ? (resumo.orcamento.periodo === 'DAILY' ? 'Diário' : 'Total do período')
            : PALAVRA_DO_PERIODO[atual.periodo]}
          fonte={resumo ? 'o resumo do backend' : 'você, agora'}
        />
        <LinhaDeFato
          rotulo="Modo registrado na receita"
          valor={resumo ? resumo.orcamento.modo : (modoDoPlano?.id ?? null)}
          fonte={resumo ? 'o resumo do backend' : 'o catálogo de receitas'}
          ausencia="catálogo de receitas ainda não lido"
        />
        <LinhaDeFato
          rotulo="Prova deste modo"
          valor={resumo ? resumo.orcamento.prova : (modoDoPlano?.prova ?? null)}
          fonte="o registro de receitas do backend"
          ausencia="não lida"
        />
        <LinhaDeFato
          rotulo="Compartilhamento entre conjuntos"
          valor="Desativado"
          fonte="a Meta, na validação real"
        />
        <LinhaDeFato
          rotulo="Lance"
          valor="Maior volume dentro da verba, sem teto de lance"
          fonte="a receita provada"
        />
        {orcamentosDoPlano(draft).map((item) => (
          <LinhaDeFato
            key={item.rotulo}
            rotulo={`Valor enviado · ${item.rotulo}`}
            valor={item.minor > 0 ? `${item.minor} centavos` : null}
            fonte="o compilador"
            ausencia="ainda não informado"
          />
        ))}
      </BlocoDeEvidencia></details>

      {modoDoPlano && !fluxoPausadoImplementado(modoDoPlano) && (
        <div className="flex items-start gap-3 rounded-lg border border-border/70 bg-muted/30 p-4">
          {cbo
            ? <Landmark className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
            : <Layers3 className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />}
          <p className="max-w-[74ch] text-sm leading-relaxed text-pretty text-muted-foreground">
            <strong className="text-foreground">
              Confira a disponibilidade deste modo de orçamento.
            </strong>{' '}
            O catálogo não confirmou o fluxo de criação pausada para esta opção.
            Você pode preparar e validar o plano; a autorização de envio é conferida separadamente no servidor.
          </p>
        </div>
      )}
    </>
  );
};
