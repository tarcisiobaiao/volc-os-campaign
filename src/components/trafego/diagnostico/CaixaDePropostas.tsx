/**
 * A caixa de propostas — a fila de mudanças recomendadas.
 *
 * Cada linha carrega as quatro coisas sem as quais uma recomendação é palpite:
 * de onde veio a evidência, quanta confiança ela sustenta, de que janela, e
 * sobre que amostra. Uma proposta sem isso é uma opinião com botão.
 *
 * ## As duas ausências que esta tela não achata
 *
 *  - `leitura: null` — a apuração falhou. Não há fila porque não se olhou.
 *  - `propostas: []` — olhou-se, e não há o que propor.
 *
 * A primeira pede nova leitura; a segunda pede nada. Um "nenhuma proposta"
 * genérico produziria a ação errada metade das vezes.
 *
 * ⚠️ Zero chamada ao Google Ads, zero mutação. A submissão para aprovação é um
 * gesto local; a aplicação passa por endereço privilegiado fora do browser.
 */
import React from 'react';
import {
  ChevronRight,
  CircleHelp,
  Inbox,
  SignalHigh,
  SignalLow,
  SignalMedium,
  WifiOff,
} from 'lucide-react';

import { cn } from '@/lib/utils';
import { Chip, type Tom } from '@/components/trafego/inventario/Selos';
import { AUSENTE, idade, lidoHa } from '@/components/trafego/inventario/formato';
import { PropostaDeAcao } from '@/components/trafego/hub/PropostaDeAcao';
import type {
  CaixaDePropostas as CaixaDePropostasContrato,
  ConfiancaDaProposta,
  Proposta,
} from '@/types/diagnostico';

import { eixoLegivel, origemLegivel } from './vocabulario';

type Glifo = React.ComponentType<{ className?: string }>;

/**
 * ⚠️ Confiança é degrau, e o glifo muda junto com a palavra.
 *
 * Três barras cheias, duas, uma: a forma sozinha já ordena. Um operador com
 * deuteranopia lê a mesma ordem que qualquer outro, e o mesmo vale para um
 * print em preto e branco levado a uma reunião.
 */
const CONFIANCA: Record<
  ConfiancaDaProposta,
  { palavra: string; descricao: string; tom: Tom; glifo: Glifo }
> = {
  alta: {
    palavra: 'confiança alta',
    descricao: 'a evidência sustenta esta mudança sozinha, com amostra suficiente',
    tom: 'bom',
    glifo: SignalHigh,
  },
  media: {
    palavra: 'confiança média',
    descricao: 'a evidência aponta para esta mudança e não a fecha — vale conferir antes',
    tom: 'atencao',
    glifo: SignalMedium,
  },
  baixa: {
    palavra: 'confiança baixa',
    descricao: 'a evidência é fraca ou a amostra é pequena; a decisão é inteiramente humana',
    tom: 'atencao',
    glifo: SignalLow,
  },
};

/**
 * ⚠️ Confiança e amostra são dois eixos, e o chip já os confundiu.
 *
 * Uma proposta pode nascer com `confianca: 'alta'` E `amostra.insuficiente:
 * true` — é o caso de `subir-verba`, e não é contradição: a evidência aponta
 * com força para a direção, e a amostra não sustenta o tamanho do passo.
 *
 * O chip fechado dizia, na descrição lida por leitor de tela e no `title`,
 * "a evidência sustenta esta mudança sozinha, **com amostra suficiente**". A
 * ressalva contrária só renderizava com a linha ABERTA. O operador que varre a
 * fila lê "confiança alta", aprova, e nunca vê o desmentido — na proposta que
 * aumenta gasto.
 *
 * Agora a insuficiência rebaixa o tom e reescreve a descrição na linha fechada.
 */
function confiancaLegivel(
  valor: string,
  amostraInsuficiente: boolean,
): {
  palavra: string;
  descricao: string;
  tom: Tom;
  glifo: Glifo;
} {
  const base =
    CONFIANCA[valor as ConfiancaDaProposta] ?? {
      palavra: 'confiança não reconhecida',
      descricao: `o sistema informou "${valor}", que esta versão da tela não conhece`,
      tom: 'atencao' as Tom,
      glifo: CircleHelp,
    };
  if (!amostraInsuficiente) return base;
  return {
    ...base,
    palavra: `${base.palavra}, amostra curta`,
    descricao: `${base.descricao.replace(', com amostra suficiente', '')} — mas a amostra não sustenta esta recomendação sozinha`,
    tom: 'atencao' as Tom,
  };
}

export interface CaixaDePropostasProps {
  caixa: CaixaDePropostasContrato;
  /** Id aberto de saída. O teste e o link direto usam. */
  abertoInicial?: string | null;
  /** Chamado ao submeter uma proposta para aprovação. Nunca escreve na conta. */
  aoSubmeter?: (proposta: Proposta) => void;
}

export const CaixaDePropostas: React.FC<CaixaDePropostasProps> = ({
  caixa,
  abertoInicial = null,
  aoSubmeter,
}) => {
  const [aberto, setAberto] = React.useState<string | null>(abertoInicial);

  return (
    <section aria-labelledby="propostas-titulo" className="max-w-[78ch]">
      <p className="kicker">caixa de propostas</p>
      <h2
        id="propostas-titulo"
        className="mt-1 font-display text-lg font-semibold tracking-tight md:text-xl"
      >
        {caixa.leitura == null
          ? 'Não foi possível apurar propostas'
          : caixa.propostas.length === 0
            ? 'Nenhuma mudança recomendada'
            : `${caixa.propostas.length} ${caixa.propostas.length === 1 ? 'mudança recomendada' : 'mudanças recomendadas'}`}
      </h2>

      {caixa.leitura == null ? (
        <div className="mt-3 flex max-w-[70ch] items-start gap-2" role="status">
          <WifiOff className="mt-0.5 h-4 w-4 shrink-0 text-destructive" aria-hidden />
          <p className="text-[13px] leading-relaxed text-muted-foreground">
            A apuração de propostas não foi concluída. Fila vazia aqui significa que
            ninguém olhou, e não que não haja nada a fazer — nenhuma decisão de
            gasto deve sair desta tela enquanto isto não for lido.
          </p>
        </div>
      ) : caixa.propostas.length === 0 ? (
        <div className="mt-3 flex max-w-[70ch] items-start gap-2" role="status">
          <Inbox className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
          <p className="text-[13px] leading-relaxed text-muted-foreground">
            A apuração foi feita {idade(caixa.leitura.idade_s)} e não encontrou
            mudança que a evidência sustente. Isto é um fato medido, não uma fila
            que não carregou.
          </p>
        </div>
      ) : (
        <>
          <p className="mt-1.5 text-[11px] text-muted-foreground">
            {lidoHa(caixa.leitura.idade_s)}
          </p>
          <ul className="mt-4 border-t border-border" role="list">
            {caixa.propostas.map((p) => (
              <LinhaDeProposta
                key={p.id}
                proposta={p}
                aberto={aberto === p.id}
                aoAlternar={() => setAberto(aberto === p.id ? null : p.id)}
                aoSubmeter={aoSubmeter}
              />
            ))}
          </ul>
        </>
      )}
    </section>
  );
};

const LinhaDeProposta: React.FC<{
  proposta: Proposta;
  aberto: boolean;
  aoAlternar: () => void;
  aoSubmeter?: (p: Proposta) => void;
}> = ({ proposta, aberto, aoAlternar, aoSubmeter }) => {
  const eixo = eixoLegivel(proposta.eixo);
  const confianca = confiancaLegivel(proposta.confianca, proposta.amostra.insuficiente);
  const idDoPainel = `proposta-${proposta.id}`;
  const podeSubmeter = proposta.bloqueio === null && aoSubmeter != null;

  return (
    <li className="border-b border-border">
      <button
        type="button"
        onClick={aoAlternar}
        aria-expanded={aberto}
        aria-controls={idDoPainel}
        className={cn(
          'flex w-full min-h-11 items-start gap-3 px-1 py-3 text-left',
          'transition-colors duration-150 hover:bg-muted/40',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1',
        )}
      >
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="font-display text-[13px] font-semibold">{proposta.titulo}</span>
            <Chip
              glifo={confianca.glifo}
              palavra={confianca.palavra}
              descricao={confianca.descricao}
              tom={confianca.tom}
            />
          </span>
          <span className="mt-1 block text-[12px] leading-relaxed text-muted-foreground">
            {proposta.frase}
          </span>
          <span className="mt-1 block text-[11px] text-muted-foreground">
            veio do degrau {eixo.rotulo.toLowerCase()} · {amostraLegivel(proposta)}
          </span>
        </span>
        <ChevronRight
          className={cn(
            'mt-0.5 h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-150',
            aberto && 'rotate-90',
            'motion-reduce:transition-none',
          )}
          aria-hidden
        />
      </button>

      {aberto && (
        <div id={idDoPainel} className="pb-4 pl-1 pr-1">
          <OrigemDaEvidencia proposta={proposta} />
          {proposta.amostra.insuficiente && (
            <p
              className="mt-2 max-w-[68ch] text-[12px] leading-relaxed text-muted-foreground"
              role="note"
            >
              A amostra não sustenta esta recomendação sozinha. Ela continua na fila
              porque escondê-la seria decidir por quem opera; aprovar com base só
              nela é decisão de quem assina.
            </p>
          )}
          <PropostaDeAcao
            className="mt-3"
            acao={proposta.alvo}
            diff={proposta.diff}
            bloqueio={proposta.bloqueio}
            aprovacao={proposta.aprovacao}
            aoSubmeter={podeSubmeter ? () => aoSubmeter?.(proposta) : undefined}
          />
        </div>
      )}
    </li>
  );
};

function amostraLegivel(p: Proposta): string {
  const { n, unidade, janela } = p.amostra;
  if (n == null) return `amostra não apurada · ${janela}`;
  return `${n} ${unidade} · ${janela}`;
}

const OrigemDaEvidencia: React.FC<{ proposta: Proposta }> = ({ proposta }) => {
  if (proposta.evidencias.length === 0) {
    return (
      <p className="mt-2 text-[12px] leading-relaxed text-muted-foreground">
        Esta proposta chegou sem evidência anexada. Não há o que conferir aqui, e
        isso por si só é motivo para não aprovar.
      </p>
    );
  }
  return (
    <div className="mt-2">
      <p className="kicker text-muted-foreground">de onde vem</p>
      <dl className="mt-1 grid gap-x-4 gap-y-1 text-[12px] sm:grid-cols-[minmax(0,1fr)_auto]">
        {proposta.evidencias.map((e) => {
          const origem = origemLegivel(e.origem);
          return (
            <React.Fragment key={`${e.campo}-${e.rotulo}`}>
              <dt className="min-w-0 text-muted-foreground">
                {e.rotulo}
                <span className="sr-only"> ({origem.descricao})</span>
                <span
                  className="ml-1.5 text-[10px] uppercase tracking-[0.08em] text-muted-foreground/70"
                  title={origem.descricao}
                  aria-hidden
                >
                  {origem.palavra}
                </span>
              </dt>
              <dd className="tabular font-medium sm:text-right">
                {e.valor ?? AUSENTE}
                <span className="ml-1.5 text-[10px] font-normal text-muted-foreground">
                  {e.leitura ? idade(e.leitura.idade_s) : 'sem data de leitura'}
                </span>
              </dd>
            </React.Fragment>
          );
        })}
      </dl>
    </div>
  );
};

export default CaixaDePropostas;
