/**
 * A vertical — a decisão de fato que decide se a campanha pode subir hoje.
 *
 * ## Por que esta tela existe
 *
 * Medido no card 74 em 19/08/2026: a vertical veio `financeiro`, que em BR
 * exige `verificacao_servicos_financeiros`, e o portão do engine reprovou o
 * lançamento. Só que a própria copy do anúncio escreve *"este portal apenas
 * explica as regras"* — e a vertical `informativo` existe exatamente para o
 * site que explica e não presta o serviço.
 *
 * Ou seja: o que bloqueava não era um defeito. Era uma **pergunta factual sobre
 * o negócio** que ninguém tinha feito ao operador — e que a tela não deixava
 * responder, porque a vertical chegava fixa da entidade.
 *
 * ## A regra desta tela: dizer a consequência antes da escolha
 *
 * Não existe opção "certa" aqui, existe a verdadeira. Declarar `informativo`
 * num site que intermedia contratação faz o anúncio ser reprovado DEPOIS que a
 * veiculação começou — pior do que ser barrado antes. Por isso cada opção
 * carrega o que ela custa, e a caixa de certificação avisa que declarar o que
 * não se tem não engana o Google, só adia a reprovação.
 */
import React from 'react';
import { AlertTriangle, ExternalLink, Info, ShieldCheck } from 'lucide-react';

import { cn } from '@/lib/utils';
import type { VerticalDePolitica } from '@/types/trafego';

interface Props {
  verticais: VerticalDePolitica[];
  escolhida: string;
  onEscolher: (id: string) => void;
  /** O que a CONTA comprova ter. Vazio é o padrão seguro. */
  certificacoes: string[];
  onCertificacoes: (c: string[]) => void;
  /** País de segmentação — o portão é por país, não global. */
  pais: string;
  /** O que a entidade dizia, para a divergência ficar visível. */
  sugeridaPelaEntidade?: string | null;
}

export const PortaoDePolitica: React.FC<Props> = ({
  verticais, escolhida, onEscolher, certificacoes, onCertificacoes,
  pais, sugeridaPelaEntidade,
}) => {
  const atual = verticais.find((v) => v.id === escolhida);
  // O portão é por PAÍS: verificar no Brasil não habilita o México.
  const exigeAqui = !!atual?.exige && (atual.paises_exigem || []).includes(pais);
  const declarada = !!atual?.exige && certificacoes.includes(atual.exige);
  const barra = exigeAqui && !declarada && atual?.severidade === 'bloqueio';
  const limita = exigeAqui && !declarada && atual?.severidade === 'limitacao';
  const divergiu = !!sugeridaPelaEntidade && sugeridaPelaEntidade !== escolhida;

  return (
    <section className="card-volc p-5 md:p-6" aria-label="portão de política">
      <div className="mb-4 flex items-baseline gap-3">
        <h2 className="text-[15px] font-medium tracking-tight">o que este portal é</h2>
        <span className="hairline flex-1" />
        <span className="kicker">portão por país · {pais}</span>
      </div>

      <p className="mb-4 max-w-[74ch] text-[11px] leading-relaxed text-muted-foreground">
        O Google exige habilitação por <b>vertical × país</b>. A pergunta não é
        de configuração, é de fato: <b>este portal presta o serviço, ou apenas
        explica como ele funciona?</b>
      </p>

      <div className="grid gap-2">
        {verticais.map((v) => {
          const pedeAqui = !!v.exige && (v.paises_exigem || []).includes(pais);
          const sel = v.id === escolhida;
          return (
            <button
              key={v.id} type="button" onClick={() => onEscolher(v.id)}
              aria-pressed={sel}
              className={cn(
                'rounded-md border p-3 text-left transition-colors',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                sel ? 'border-foreground/40 bg-foreground/[0.04]'
                    : 'border-border hover:border-foreground/25',
              )}
            >
              <span className="flex flex-wrap items-center gap-2">
                <span aria-hidden className={cn(
                  'h-3 w-3 shrink-0 rounded-full border',
                  sel ? 'border-foreground bg-foreground' : 'border-muted-foreground')} />
                <span className="text-sm font-medium">{v.titulo}</span>
                {!pedeAqui && (
                  <span className="kicker text-success">sem portão em {pais}</span>
                )}
                {pedeAqui && (
                  <span className={cn('kicker',
                    v.severidade === 'bloqueio' ? 'text-destructive' : 'text-warning')}>
                    {v.severidade === 'bloqueio' ? 'barra o lançamento' : 'veicula limitado'}
                  </span>
                )}
              </span>
              {v.descricao && (
                <span className="mt-1.5 block max-w-[80ch] text-[11px] leading-relaxed text-muted-foreground">
                  {v.descricao}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* A divergência entre o que a entidade dizia e o que o operador marcou
          fica visível — é ela que vira auditoria depois. */}
      {divergiu && (
        <Nota tom="nota">
          A entidade classificou como{' '}
          <span className="font-mono">{sugeridaPelaEntidade}</span>. Você está
          declarando <span className="font-mono">{escolhida}</span> — a
          divergência fica registrada no pedido.
        </Nota>
      )}

      {exigeAqui && (
        <div className="mt-4 rounded-md border border-border p-3">
          <label className="flex cursor-pointer items-start gap-2.5">
            <input
              type="checkbox" checked={declarada}
              onChange={(e) => onCertificacoes(
                e.target.checked
                  ? [...new Set([...certificacoes, atual!.exige!])]
                  : certificacoes.filter((c) => c !== atual!.exige),
              )}
              className="mt-0.5 h-3.5 w-3.5 shrink-0 accent-foreground"
            />
            <span className="min-w-0 text-[11px] leading-relaxed">
              <b>Esta conta já tem <span className="font-mono">{atual!.exige}</span> em {pais}.</b>
              <span className="mt-1 block text-muted-foreground">
                Marcar sem ter não engana o Google — só troca "barrado antes" por
                "reprovado depois de veicular". A verificação é por país:
                verificar no Brasil não habilita o México.
              </span>
            </span>
          </label>
          {atual?.url && (
            <a href={atual.url} target="_blank" rel="noreferrer"
               className="mt-2 inline-flex items-center gap-1 text-[11px] underline underline-offset-4">
              a política do Google <ExternalLink className="h-3 w-3" aria-hidden />
            </a>
          )}
        </div>
      )}

      {barra && (
        <Nota tom="ruim">
          <b>O lançamento está barrado.</b> A vertical{' '}
          <span className="font-mono">{escolhida}</span> exige{' '}
          <span className="font-mono">{atual!.exige}</span> em {pais}. Ou a
          conta tem a habilitação (marque acima), ou a vertical é outra.
        </Nota>
      )}

      {limita && (
        <Nota tom="nota">
          A campanha sobe, mas o anúncio tende a ficar{' '}
          <span className="font-mono">APPROVED_LIMITED</span> — veicula com
          restrição de alcance até a habilitação sair.
        </Nota>
      )}

      {!exigeAqui && (
        <Nota tom="bom">
          Sem portão de habilitação em {pais}. O que decide agora é a revisão do
          anúncio, e ela acontece mesmo com a campanha pausada.
        </Nota>
      )}
    </section>
  );
};

const Nota: React.FC<{ tom: 'ruim' | 'nota' | 'bom'; children: React.ReactNode }> =
  ({ tom, children }) => (
  <div className={cn(
    'mt-4 flex items-start gap-2 rounded-md border p-3 text-[11px] leading-relaxed',
    tom === 'ruim' ? 'border-destructive/40 bg-destructive/[0.05] text-foreground'
    : tom === 'bom' ? 'border-success/40 bg-success/[0.05] text-foreground'
    : 'border-border text-muted-foreground')}>
    {tom === 'ruim' ? <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-destructive" aria-hidden />
     : tom === 'bom' ? <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-success" aria-hidden />
     : <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />}
    <span className="min-w-0">{children}</span>
  </div>
);
