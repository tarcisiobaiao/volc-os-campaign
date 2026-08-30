/**
 * Como a campanha NASCE — a escolha que a gestão inteira vai herdar.
 *
 * ## O defeito que esta mesa conserta
 *
 * O engine criava toda campanha em `maximize_conversions`, e o cockpit era
 * honesto sobre isso: o painel de lançamento avisava, em letra miúda, que "o
 * cockpit não escolhe a meta". Só que a casa não opera assim. A doutrina —
 * medida no flow `GOOGLE ADS - New Campaigns Validation`, nó `Code1` — é
 * nascer em CPC manual e graduar para lance automático em 30 conversões.
 *
 * Nascer errado não é um detalhe de configuração: o motor de gestão lê o que o
 * nascimento definiu. Uma campanha que nasce em `maximize_conversions` sem
 * histórico entrega o lance a um modelo que ainda não tem o que aprender, e
 * todo ajuste posterior corrige um alvo que não deveria existir.
 *
 * ## Uma escolha, não uma lista de campos
 *
 * O operador escolhe COMO a campanha nasce. Match type, teto e estrutura
 * DECORREM — e a tela mostra o que decorreu, na hora, para que ele nunca
 * descubra depois. É a diferença entre um formulário e uma decisão.
 *
 * ## A graduação aparece no dia zero
 *
 * Ela não é configuração futura: é contrato que a campanha carrega desde o
 * lançamento. Esta tela apenas REGISTRA a regra — quem a executa é o motor de
 * gestão, lendo o que o nascimento declarou. Dizer isso aqui evita a leitura
 * errada de que o lançamento vai ficar vigiando a conta.
 */
import React from 'react';
import { AlertTriangle, ArrowRight, Gauge, Info, Target } from 'lucide-react';

import { cn } from '@/lib/utils';
import { DECORRE_DA_ESTRATEGIA } from '@/types/trafego';
import type { Cockpit, EstrategiaDeLance } from '@/types/trafego';

interface Props {
  cockpit: Cockpit;
  estrategia: EstrategiaDeLance;
  onEstrategia: (e: EstrategiaDeLance) => void;
  lance: string;
  onLance: (v: string) => void;
  budget: string;
  onBudget: (v: string) => void;
  graduacao: number;
  onGraduacao: (n: number) => void;
}

/** Teto de CPC da casa, medido no flow `New Campaigns Validation` (`Code1`):
 *  `MAX_CPC_BRL: 0.50`. Não bloqueia — avisa. Quem manda é o operador. */
const TETO_CPC_BRL = 0.5;
/** `GRADUATION_BUDGET_FLOOR: 30.00` no mesmo nó: a verba mínima que a campanha
 *  recebe AO GRADUAR. Abaixo disso, a graduação chega e não tem o que gastar. */
const PISO_VERBA_GRADUACAO = 30;

export const MesaDeLance: React.FC<Props> = ({
  cockpit, estrategia, onEstrategia,
  lance, onLance, budget, onBudget, graduacao, onGraduacao,
}) => {
  const conta = cockpit.conta;
  const meta = conta?.meta_conversao?.primaria ?? null;
  const semMeta = !!conta?.vinculada && !!conta?.meta_conversao && !meta;
  const moeda = conta?.moeda ? `${conta.moeda} ` : 'R$ ';

  const lanceNum = Number(lance.replace(',', '.')) || 0;
  const budgetNum = Number(budget.replace(',', '.')) || 0;
  const decorre = DECORRE_DA_ESTRATEGIA[estrategia];

  const acimaDoTeto = lanceNum > TETO_CPC_BRL;
  const verbaAbaixoDoPiso = graduacao > 0 && budgetNum > 0 && budgetNum < PISO_VERBA_GRADUACAO;

  return (
    <div className="space-y-5">
      {/* ── a escolha ─────────────────────────────────────────────────────── */}
      <fieldset>
        <legend className="kicker mb-3">como esta campanha nasce</legend>
        <div className="grid gap-3 sm:grid-cols-2">
          <Nascimento
            escolhida={estrategia === 'MANUAL_CPC'}
            onClick={() => onEstrategia('MANUAL_CPC')}
            titulo="CPC manual"
            resumo="você controla o clique"
            detalhe="O lance é seu. Nenhum modelo decide por você enquanto não houver histórico para ele aprender."
            recomendado
          />
          <Nascimento
            escolhida={estrategia === 'MAXIMIZE_CONVERSIONS'}
            onClick={() => onEstrategia('MAXIMIZE_CONVERSIONS')}
            titulo="Maximizar conversões"
            resumo="o Google controla o leilão"
            detalhe="Precisa de histórico de conversão na conta. Sem ele, o modelo gasta aprendendo o que você já sabe."
          />
        </div>

        {/* O que a escolha CAUSA, dito na hora. O operador nunca descobre
            depois que o match type foi decidido por ele. */}
        <p className="mt-3 flex items-start gap-2 text-[11px] leading-relaxed text-muted-foreground">
          <ArrowRight className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
          <span>
            decorre daqui: <span className="font-mono text-foreground">{decorre.match_type}</span>
            {' · '}1 conjunto{' · '}<span className="text-foreground">{decorre.explica}</span>
          </span>
        </p>
      </fieldset>

      {/* ── os números ────────────────────────────────────────────────────── */}
      <div className="grid gap-4 sm:grid-cols-3">
        <Numero
          rotulo={estrategia === 'MANUAL_CPC' ? 'lance por clique' : 'CPA alvo'}
          prefixo={moeda}
          valor={lance}
          onChange={onLance}
          nota={acimaDoTeto
            ? `acima do teto da casa (${moeda}${TETO_CPC_BRL.toFixed(2).replace('.', ',')})`
            : undefined}
          alerta={acimaDoTeto}
        />
        <Numero
          rotulo="orçamento por dia"
          prefixo={moeda}
          valor={budget}
          onChange={onBudget}
          nota={conta?.fuso ? `o dia vira em ${conta.fuso}` : undefined}
        />
        <div>
          <span className="kicker">meta de conversão</span>
          <div className="mt-1 text-sm">
            {meta ? (
              <>
                <span className="flex items-center gap-1.5">
                  <Target className="h-3 w-3 shrink-0" aria-hidden />
                  {meta.nome}
                </span>
                <span className="block text-[11px] text-muted-foreground">
                  {meta.categoria.toLowerCase()} · da conta
                </span>
              </>
            ) : semMeta ? (
              <span className="text-destructive">sem meta primária</span>
            ) : (
              <span className="text-muted-foreground">não medido</span>
            )}
          </div>
        </div>
      </div>

      {semMeta && (
        <Aviso tom="ruim">{cockpit.conta?.meta_conversao?.por_que}</Aviso>
      )}

      {/* ── a graduação ───────────────────────────────────────────────────── */}
      <div className="rounded-md border border-border p-4">
        <div className="mb-3 flex items-center gap-2">
          <Gauge className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
          <span className="kicker">graduação</span>
        </div>

        {estrategia === 'MAXIMIZE_CONVERSIONS' ? (
          <p className="text-[11px] leading-relaxed text-muted-foreground">
            A campanha já nasce em lance automático — não há para onde graduar.
          </p>
        ) : (
          <>
            <label className="flex flex-wrap items-center gap-2 text-sm">
              <span className="text-muted-foreground">trocar de estratégia em</span>
              <input
                type="number" min={0} step={5} value={graduacao}
                onChange={(e) => onGraduacao(Math.max(0, Number(e.target.value) || 0))}
                className="tabular w-20 rounded-md border border-input bg-background px-2 py-1
                           text-sm focus-visible:outline-none focus-visible:ring-2
                           focus-visible:ring-ring"
                aria-label="conversões para graduar"
              />
              <span className="text-muted-foreground">conversões</span>
              {graduacao === 0 && (
                <span className="text-[11px] text-muted-foreground">— desligada</span>
              )}
            </label>

            {graduacao > 0 && (
              <ul className="mt-3 space-y-1 border-l-2 border-border pl-3 text-[11px]
                             leading-relaxed text-muted-foreground">
                <li>estratégia → <span className="text-foreground">Maximizar conversões</span></li>
                <li>lance → <span className="text-foreground">o CPA real do dia anterior</span></li>
                <li>
                  verba → <span className="text-foreground">
                    o dobro, com piso de {moeda}{PISO_VERBA_GRADUACAO.toFixed(2).replace('.', ',')}
                  </span>
                </li>
                <li>match type → <span className="text-foreground">broad liberado</span></li>
              </ul>
            )}

            {/* ⚠️ Desde 17/08/2026 o Smart Bidding converge para a meta em
                campanhas limitadas por orçamento, em vez de frequentemente
                entregar abaixo dela. Arbitragem é limitada por orçamento por
                definição. Sem este aviso, a linha "lance = CPA real de ontem"
                lê como teto de segurança — e ela virou autorização de gasto.
                Ver docs/SMART-BIDDING-2026-08-17.md.

                Só faz sentido com a graduação LIGADA: sem ela não há meta
                futura sobre a qual avisar, e o aviso vira ruído. */}
            {graduacao > 0 && (
            <p className="mt-3 flex items-start gap-2 rounded-md border
                          border-warning/40 bg-warning/[0.06] p-2.5 text-[11px]
                          leading-relaxed text-foreground">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" aria-hidden />
              <span>
                Desde <b>17/08/2026</b>, o Google faz a campanha{' '}
                <b>convergir para a meta</b> em vez de entregar abaixo dela. Em
                campanha limitada por orçamento — que é o nosso caso sempre — a
                meta da graduação é <b>o que será gasto</b>, não um teto. Por
                isso ela sai do CPA real, e não de um número arredondado para
                cima.
              </span>
            </p>
            )}

            {/* Sem isto, a tela sugere que o lançamento vai vigiar a conta. */}
            <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">
              A regra é <b>registrada agora</b> e viaja com a campanha. Quem a
              executa é o motor de gestão — este lançamento não fica vigiando a
              conta.
            </p>
          </>
        )}

        {verbaAbaixoDoPiso && (
          <Aviso tom="nota">
            No dia da graduação a verba sobe para o piso de {moeda}
            {PISO_VERBA_GRADUACAO.toFixed(2).replace('.', ',')} — mais que o
            dobro do que você está definindo agora.
          </Aviso>
        )}
      </div>
    </div>
  );
};

/** Um nascimento possível. Cartão inteiro clicável: o alvo de toque é o cartão,
 *  não o rádio de 16px. */
const Nascimento: React.FC<{
  escolhida: boolean; onClick: () => void;
  titulo: string; resumo: string; detalhe: string; recomendado?: boolean;
}> = ({ escolhida, onClick, titulo, resumo, detalhe, recomendado }) => (
  <button
    type="button" onClick={onClick} aria-pressed={escolhida}
    className={cn(
      'rounded-md border p-4 text-left transition-colors',
      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
      escolhida
        ? 'border-foreground/40 bg-foreground/[0.04]'
        : 'border-border hover:border-foreground/25',
    )}
  >
    <span className="flex items-center gap-2">
      <span
        aria-hidden
        className={cn('h-3 w-3 shrink-0 rounded-full border',
                      escolhida ? 'border-foreground bg-foreground' : 'border-muted-foreground')}
      />
      <span className="text-sm font-medium">{titulo}</span>
      {recomendado && <span className="kicker">como a casa opera</span>}
    </span>
    <span className="mt-1 block text-[11px] text-muted-foreground">{resumo}</span>
    <span className="mt-2 block text-[11px] leading-relaxed text-muted-foreground">{detalhe}</span>
  </button>
);

const Numero: React.FC<{
  rotulo: string; prefixo: string; valor: string;
  onChange: (v: string) => void; nota?: string; alerta?: boolean;
}> = ({ rotulo, prefixo, valor, onChange, nota, alerta }) => (
  <label className="block">
    <span className="kicker">{rotulo}</span>
    <span className="mt-1 flex items-center gap-1 rounded-md border border-input
                     bg-background px-2 py-1.5 focus-within:ring-2 focus-within:ring-ring">
      <span className="text-[11px] text-muted-foreground">{prefixo}</span>
      <input
        inputMode="decimal" value={valor}
        onChange={(e) => onChange(e.target.value)}
        className="tabular w-full bg-transparent text-sm focus-visible:outline-none"
      />
    </span>
    {nota && (
      <span className={cn('mt-1 block text-[11px]',
                          alerta ? 'text-warning' : 'text-muted-foreground')}>
        {nota}
      </span>
    )}
  </label>
);

const Aviso: React.FC<{ tom: 'ruim' | 'nota'; children: React.ReactNode }> =
  ({ tom, children }) => (
  <div className={cn('mt-3 flex items-start gap-2 rounded-md border p-3 text-[11px] leading-relaxed',
                     tom === 'ruim'
                       ? 'border-destructive/40 bg-destructive/[0.05] text-foreground'
                       : 'border-border text-muted-foreground')}>
    {tom === 'ruim'
      ? <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-destructive" aria-hidden />
      : <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />}
    <span className="min-w-0">{children}</span>
  </div>
);
