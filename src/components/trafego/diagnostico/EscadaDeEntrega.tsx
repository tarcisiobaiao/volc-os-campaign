/**
 * A escada de entrega — a superfície que explica por que uma campanha não entrega.
 *
 * ## Por que é uma escada, e não um painel de indicadores
 *
 * Uma campanha que não entrega falha em exatamente um degrau, e o degrau de
 * baixo torna os de cima irrelevantes. Uma grade de cartões com nove medições
 * lado a lado dá nove candidatos com o mesmo peso visual — e o operador escolhe
 * o mais familiar, que costuma ser lance ou verba, quando a causa era cobrança
 * da conta. A ordem causal é a informação principal desta tela, então ela é a
 * própria estrutura: uma lista ordenada, de baixo para cima.
 *
 * ## Leitura suspensa
 *
 * Quando um degrau não pôde ser apurado, os degraus acima dele continuam na
 * tela — e sob um rótulo que diz que aquilo é leitura suspensa. Escondê-los
 * perderia informação; exibi-los como conclusão afirmaria o que não se provou.
 *
 * ⚠️ Zero chamada ao Google Ads. Este componente recebe um `DiagnosticoDeEntrega`
 * já apurado e não faz busca, não escreve e não conhece credencial.
 */
import React from 'react';
import { ChevronRight, Copy } from 'lucide-react';

import { cn } from '@/lib/utils';
import { Chip } from '@/components/trafego/inventario/Selos';
import { AUSENTE, idade, lidoHa } from '@/components/trafego/inventario/formato';
import { degrausConfiaveis, vereditoDaEscada } from '@/lib/diagnostico/escada';
import type { DegrauDeEntrega, DiagnosticoDeEntrega } from '@/types/diagnostico';

import { eixoLegivel, estadoLegivel, fraseDoVeredito, origemLegivel } from './vocabulario';

export interface EscadaDeEntregaProps {
  diagnostico: DiagnosticoDeEntrega;
  /** Aberto por padrão. Usado pelo teste e pelo link direto para um degrau. */
  eixoAberto?: string | null;
}

export const EscadaDeEntrega: React.FC<EscadaDeEntregaProps> = ({
  diagnostico,
  eixoAberto = null,
}) => {
  const veredito = vereditoDaEscada(diagnostico.degraus);
  const { confiaveis, suspensos } = degrausConfiaveis(diagnostico.degraus, veredito);
  const frase = fraseDoVeredito(veredito);
  const [aberto, setAberto] = React.useState<string | null>(eixoAberto);

  return (
    <section aria-labelledby="escada-titulo" className="max-w-[78ch]">
      <p className="kicker">diagnóstico de entrega</p>
      <h2
        id="escada-titulo"
        className="mt-1 font-display text-lg font-semibold tracking-tight md:text-xl"
      >
        {frase.titulo}
      </h2>
      <p className="mt-1.5 text-[13px] leading-relaxed text-muted-foreground">
        {frase.descricao}
      </p>

      <p className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
        <span>{lidoHa(diagnostico.leitura?.idade_s ?? null)}</span>
        <span aria-hidden>·</span>
        {/* ⚠️ A preposição depende da janela, e o `replace` cego produzia
            "métricas dos janela não declarada", "métricas dos hoje" e
            "métricas dos este mês". A janela é texto vindo do servidor: ou ela
            começa com "últimos N", e aí "dos N" lê bem, ou ela é outra coisa e
            a frase precisa mudar de forma. */}
        <span>
          {/^últimos /.test(diagnostico.janela)
            ? `métricas dos ${diagnostico.janela.replace(/^últimos /, '')}`
            : `métricas: ${diagnostico.janela}`}
        </span>
        <span aria-hidden>·</span>
        <span>
          {diagnostico.moeda ? `moeda ${diagnostico.moeda}` : 'moeda não declarada'}
        </span>
        {diagnostico.parcial && (
          <>
            <span aria-hidden>·</span>
            <span>leitura parcial</span>
          </>
        )}
      </p>

      <ol className="mt-5 border-t border-border" role="list">
        {confiaveis.map((d, i) => (
          <Degrau
            key={d.eixo}
            degrau={d}
            posicao={i + 1}
            suspenso={false}
            aberto={aberto === d.eixo}
            aoAlternar={() => setAberto(aberto === d.eixo ? null : d.eixo)}
            moeda={diagnostico.moeda}
          />
        ))}
      </ol>

      {suspensos.length > 0 && (
        <>
          <p
            className="mt-6 border-t border-dashed border-border pt-3 text-[11px] leading-relaxed text-muted-foreground"
            role="note"
          >
            A leitura para aqui. Os degraus abaixo foram consultados, e enquanto o
            degrau acima não for resolvido eles não sustentam conclusão — inclusive
            os que vieram sem impedimento.
          </p>
          <ol className="mt-3 border-t border-border" role="list">
            {suspensos.map((d, i) => (
              <Degrau
                key={d.eixo}
                degrau={d}
                posicao={confiaveis.length + i + 1}
                suspenso
                aberto={aberto === d.eixo}
                aoAlternar={() => setAberto(aberto === d.eixo ? null : d.eixo)}
                moeda={diagnostico.moeda}
              />
            ))}
          </ol>
        </>
      )}
    </section>
  );
};

// ── um degrau ───────────────────────────────────────────────────────────────

const Degrau: React.FC<{
  degrau: DegrauDeEntrega;
  posicao: number;
  suspenso: boolean;
  aberto: boolean;
  aoAlternar: () => void;
  moeda: string | null;
}> = ({ degrau, posicao, suspenso, aberto, aoAlternar }) => {
  const eixo = eixoLegivel(degrau.eixo);
  const estado = estadoLegivel(degrau.estado);
  const idDoPainel = `degrau-${degrau.eixo}`;
  const Glifo = eixo.glifo;

  return (
    <li className={cn('border-b border-border', suspenso && 'opacity-75')}>
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
        <span className="tabular mt-0.5 w-4 shrink-0 text-[11px] text-muted-foreground">
          {posicao}
        </span>
        <Glifo className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="font-display text-[13px] font-semibold">{eixo.rotulo}</span>
            <Chip
              glifo={estado.glifo}
              palavra={estado.palavra}
              descricao={estado.descricao}
              tom={estado.tom}
            />
          </span>
          <span className="mt-1 block text-[12px] leading-relaxed text-muted-foreground">
            {degrau.frase}
          </span>
          {degrau.impedimento && (
            <span className="mt-1 block text-[12px] leading-relaxed text-muted-foreground">
              motivo da falha de leitura: {degrau.impedimento}
            </span>
          )}
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
        <div id={idDoPainel} className="pb-4 pl-8 pr-1">
          <p className="text-[12px] leading-relaxed text-muted-foreground">
            {eixo.pergunta}
          </p>

          {degrau.motivo_da_conta.length > 0 && (
            <div className="mt-3">
              <p className="kicker text-muted-foreground">o que o Google diz</p>
              <ul className="mt-1 list-disc space-y-0.5 pl-4 text-[12px] leading-relaxed">
                {degrau.motivo_da_conta.map((m) => (
                  <li key={m}>{m}</li>
                ))}
              </ul>
            </div>
          )}

          <Evidencias degrau={degrau} />
        </div>
      )}
    </li>
  );
};

// ── as evidências de um degrau ──────────────────────────────────────────────

const Evidencias: React.FC<{ degrau: DegrauDeEntrega }> = ({ degrau }) => {
  const [copiado, setCopiado] = React.useState(false);
  const [falhouAoCopiar, setFalhouAoCopiar] = React.useState(false);

  if (degrau.evidencias.length === 0) {
    return (
      <p className="mt-3 text-[12px] leading-relaxed text-muted-foreground">
        Nenhuma medida chegou para este degrau. A conclusão acima vem da ausência
        da leitura, não de um valor lido.
      </p>
    );
  }

  const paraCopiar = [
    `degrau: ${degrau.eixo} — ${degrau.estado}`,
    ...degrau.evidencias.map(
      (e) =>
        `${e.campo} = ${e.valor ?? 'sem valor'}` +
        (e.janela ? ` (${e.janela})` : '') +
        (e.leitura ? ` [lido ${idade(e.leitura.idade_s)}]` : ' [sem data de leitura]'),
    ),
  ].join('\n');

  return (
    <div className="mt-3">
      <p className="kicker text-muted-foreground">evidência</p>
      <dl className="mt-1 grid gap-x-4 gap-y-1.5 text-[12px] sm:grid-cols-[minmax(0,1fr)_auto]">
        {degrau.evidencias.map((e) => {
          const origem = origemLegivel(e.origem);
          return (
            <React.Fragment key={`${e.campo}-${e.rotulo}`}>
              <dt className="min-w-0 text-muted-foreground">
                {e.rotulo}
                <span className="sr-only"> ({origem.palavra}: {origem.descricao})</span>
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
                {e.janela && (
                  <span className="ml-1.5 text-[10px] font-normal text-muted-foreground">
                    {e.janela}
                  </span>
                )}
              </dd>
            </React.Fragment>
          );
        })}
      </dl>

      <button
        type="button"
        onClick={() => {
          // ⚠️ Só anuncia depois de a cópia acontecer. O `setCopiado(true)`
          // incondicional dizia "evidência copiada" em origem não segura (onde
          // `navigator.clipboard` é undefined) e quando a promessa rejeitava —
          // e este é justamente o texto que o operador cola ao pedir ajuda.
          // Anunciar sucesso falso aqui custa a conversa inteira depois.
          const area = navigator.clipboard;
          if (!area?.writeText) {
            setFalhouAoCopiar(true);
            window.setTimeout(() => setFalhouAoCopiar(false), 4000);
            return;
          }
          area.writeText(paraCopiar).then(
            () => {
              setCopiado(true);
              window.setTimeout(() => setCopiado(false), 2000);
            },
            () => {
              setFalhouAoCopiar(true);
              window.setTimeout(() => setFalhouAoCopiar(false), 4000);
            },
          );
        }}
        className={cn(
          'mt-3 inline-flex min-h-11 items-center gap-1.5 rounded-md border border-border px-2.5',
          'text-[11px] text-muted-foreground transition-colors duration-150 md:min-h-8',
          'hover:bg-muted/60 hover:text-foreground',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1',
        )}
      >
        <Copy className="h-3 w-3" aria-hidden />
        {falhouAoCopiar
          ? 'não deu para copiar — selecione o texto acima'
          : copiado
            ? 'evidência copiada'
            : 'copiar evidência'}
      </button>
    </div>
  );
};

export default EscadaDeEntrega;
