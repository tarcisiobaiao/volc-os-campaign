import React from 'react';
import {
  Check,
  Copy,
  FlaskConical,
  GitCompareArrows,
  LockKeyhole,
  ShieldOff,
} from 'lucide-react';

import { Chip } from '@/components/trafego/inventario/Selos';
import { cn } from '@/lib/utils';
import { SeloDaMedida } from './EstadosDaBancada';
import {
  MARCA_SINTETICA_COM_PROTOTIPO,
  palavraDaCobertura,
  type BancadaVisivel,
  type EvidenciaVisivel,
  type PropostaVisivel,
} from './projection';

function copiar(texto: string): Promise<boolean> {
  const area = navigator.clipboard;
  if (!area?.writeText) return Promise.resolve(false);
  return area.writeText(texto).then(() => true, () => false);
}

const BotaoLocal: React.FC<{
  rotulo: string;
  sucesso?: string;
  aoClicar: () => Promise<boolean> | boolean;
}> = ({ rotulo, sucesso = 'copiado', aoClicar }) => {
  const [estado, setEstado] = React.useState<'idle' | 'ok' | 'falha'>('idle');
  return (
    <button
      type="button"
      aria-live="polite"
      onClick={() => {
        void Promise.resolve(aoClicar()).then((ok) => {
          setEstado(ok ? 'ok' : 'falha');
          window.setTimeout(() => setEstado('idle'), ok ? 2000 : 4000);
        });
      }}
      className={cn(
        'inline-flex min-h-11 items-center gap-1.5 rounded-md px-2.5 text-[12px] font-medium md:min-h-10',
        'bg-transparent text-foreground shadow-[0_0_0_1px_rgba(15,23,42,0.08),0_1px_2px_rgba(15,23,42,0.04)]',
        'transition-[transform,box-shadow,background-color] duration-150 ease-out',
        'hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        'active:scale-[0.96] motion-reduce:transition-none motion-reduce:active:scale-100',
        'dark:shadow-[0_0_0_1px_rgba(255,255,255,0.08)]',
      )}
    >
      {estado === 'ok' ? <Check className="h-3.5 w-3.5" aria-hidden /> : <Copy className="h-3.5 w-3.5" aria-hidden />}
      {estado === 'ok' ? sucesso : estado === 'falha' ? 'não deu para copiar' : rotulo}
    </button>
  );
};

const Dado: React.FC<{ rotulo: string; valor: string; enfatizar?: boolean }> = ({ rotulo, valor, enfatizar }) => (
  <div className="min-w-0">
    <p className="kicker">{rotulo}</p>
    <p className={cn('mt-1 break-words text-[13px] leading-snug', enfatizar ? 'font-medium text-foreground' : 'text-foreground')}>
      {valor}
    </p>
  </div>
);

export const CabecalhoDeVerdade: React.FC<{ bancada: BancadaVisivel }> = ({ bancada }) => (
  <section
    aria-labelledby="verdade-titulo"
    className="rounded-lg bg-card shadow-[var(--di-surface-shadow)]"
  >
    <div className="px-4 py-4 sm:px-5">
      <div className="flex flex-wrap items-center gap-2">
        <Chip
          glifo={bancada.modo === 'shadow_futuro' ? ShieldOff : FlaskConical}
          palavra={bancada.modo === 'shadow_futuro' ? 'shadow futuro' : 'laboratório'}
          descricao={bancada.notaDeModo}
          tom={bancada.modo === 'shadow_futuro' ? 'atencao' : 'info'}
        />
        <p className="text-[11px] font-semibold tracking-[0.08em] text-foreground">
          {bancada.marca}
        </p>
        <span className="inline-flex min-h-8 items-center rounded-sm border border-border px-2 text-[11px] font-semibold uppercase tracking-[0.08em]">
          {bancada.seloSemAcao}
        </span>
      </div>
      <h2 id="verdade-titulo" className="sr-only">Cabeçalho de verdade da fotografia</h2>
      <p className="mt-2 max-w-[70ch] text-pretty text-[12px] leading-relaxed text-muted-foreground">{bancada.notaDeModo}</p>
      <div className="di-truth-meta mt-4">
        <Dado rotulo="fonte" valor={bancada.fonte} />
        <Dado rotulo="campanha" valor={bancada.campanha ?? 'campanha não declarada'} />
        <Dado rotulo="conta" valor={bancada.conta ?? 'conta não declarada'} />
        <Dado rotulo="janela analisada" valor={bancada.janela} />
        <Dado rotulo="momento da leitura" valor={`${bancada.momentoDaLeitura} · ${bancada.idadeDaLeitura}`} />
        <Dado
          rotulo="cobertura"
          valor={`${palavraDaCobertura(bancada.cobertura)} · ${bancada.coberturaRotulo}`}
          enfatizar
        />
        <Dado rotulo="por que esta cobertura" valor={bancada.coberturaMotivo} />
        <Dado rotulo="namespace documentado" valor={`${bancada.namespaceApi} · v25.2 não afirmada`} />
      </div>
    </div>
  </section>
);

export const RespostaExecutiva: React.FC<{ bancada: BancadaVisivel; mudou: boolean }> = ({ bancada, mudou }) => (
  <section aria-labelledby="resposta-executiva" className="pt-8">
    <p className="kicker">o que está acontecendo com esta campanha</p>
    {bancada.insuficienciaAntesDaHipotese && (
      <p className="mt-2 max-w-[70ch] text-[13px] font-medium text-foreground" role="status">
        A evidência ainda não é suficiente para fechar uma causa.
      </p>
    )}
    <h2
      id="resposta-executiva"
      className="di-executiva mt-2 max-w-[22ch] text-balance font-display text-[30px] font-semibold leading-[1.08] tracking-tight md:text-[36px]"
      data-changed={mudou ? 'true' : 'false'}
    >
      {bancada.tituloExecutivo}
    </h2>
    <p className="mt-3 max-w-[68ch] text-pretty text-[15px] leading-relaxed text-foreground/90">
      {bancada.fraseExecutiva}
    </p>
  </section>
);

const LinhaDeEvidencia: React.FC<{ item: EvidenciaVisivel }> = ({ item }) => (
  <div className="grid gap-2 border-t border-border py-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start">
    <div className="min-w-0">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-[13px] font-medium">{item.rotulo}</p>
        <SeloDaMedida estado={item.estado} />
      </div>
      <p className="mt-1 text-pretty text-[13px] leading-relaxed text-muted-foreground">{item.interpretacao}</p>
      {item.ressalva && <p className="mt-1 text-[12px] leading-relaxed text-muted-foreground">{item.ressalva}</p>}
      <p className="mt-1 text-[11px] text-muted-foreground">
        fonte {item.fonte} · {item.janela} · {item.carimbo}
      </p>
    </div>
    <p className="di-medida text-[18px] font-semibold leading-none sm:text-right">{item.valorExibido}</p>
  </div>
);

export const FamiliasDeEvidencia: React.FC<{ bancada: BancadaVisivel }> = ({ bancada }) => (
  <section aria-labelledby="evidencias-titulo" className="pt-10" id="evidencias-da-bancada">
    <p className="kicker">evidências</p>
    <h2 id="evidencias-titulo" className="mt-1 font-display text-[22px] font-semibold tracking-tight">
      O que foi observado, e o que não foi
    </h2>
    <div className="di-familias mt-5">
      {bancada.familias.map((familia) => (
        <section key={familia.id} className="di-familia" aria-labelledby={`familia-${familia.id}`}>
          <h3 id={`familia-${familia.id}`} className="font-display text-[15px] font-semibold">
            {familia.titulo}
          </h3>
          {familia.itens.length === 0 ? (
            <p className="mt-2 text-[13px] leading-relaxed text-muted-foreground">
              Nenhuma evidência desta família veio anexada nesta fotografia.
            </p>
          ) : (
            <div className="mt-1">
              {familia.itens.map((item) => (
                <LinhaDeEvidencia key={item.chave} item={item} />
              ))}
            </div>
          )}
        </section>
      ))}
    </div>
  </section>
);

export const LinhaDeRaciocinio: React.FC<{ bancada: BancadaVisivel }> = ({ bancada }) => (
  <section aria-labelledby="raciocinio-titulo" className="pt-10">
    <p className="kicker">linha de raciocínio</p>
    <h2 id="raciocinio-titulo" className="mt-1 font-display text-[22px] font-semibold tracking-tight">
      Observado, qualificado, diagnosticado, proposto
    </h2>
    <ol className="di-spine mt-5">
      {bancada.estagios.map((estagio) => (
        <li key={estagio.id} className="di-station pr-4">
          <p className="font-display text-[13px] font-semibold">{estagio.titulo}</p>
          <dl className="mt-3 space-y-2 text-[12px] leading-relaxed">
            <div>
              <dt className="text-muted-foreground">entrou</dt>
              <dd className="text-pretty">{estagio.entrou}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">saiu</dt>
              <dd className="text-pretty">{estagio.saiu}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">bloqueou</dt>
              <dd className="text-pretty">{estagio.bloqueou}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">sustenta a passagem</dt>
              <dd className="break-words">{estagio.evidencia}</dd>
            </div>
          </dl>
        </li>
      ))}
    </ol>
    <div className="mt-6 border-t border-border pt-4">
      <h3 id="conflitos-titulo" className="font-display text-[16px] font-semibold">
        {bancada.conflitos.length === 0
          ? 'Nenhum veto venceu a arbitragem'
          : `${bancada.conflitos.length} ${bancada.conflitos.length === 1 ? 'veto venceu' : 'vetos venceram'} a arbitragem`}
      </h3>
      {bancada.conflitos.length === 0 ? (
        <p className="mt-1 text-[13px] text-muted-foreground">Os guardas foram avaliados antes de qualquer proposta.</p>
      ) : (
        <ol className="mt-3">
          {bancada.conflitos.map((conflito) => (
            <li key={conflito.codigo} className="border-t border-border py-3">
              <p className="text-[13px] leading-relaxed">{conflito.motivo}</p>
              <p className="mt-1 text-[11px] text-muted-foreground">{conflito.codigo.replace(/_/g, ' ')}</p>
            </li>
          ))}
        </ol>
      )}
    </div>
  </section>
);

const ColunaDeFatores: React.FC<{ titulo: string; vazio: string; itens: BancadaVisivel['apoiam'] }> = ({
  titulo, vazio, itens,
}) => (
  <div className="min-w-0">
    <h3 className="text-[12px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">{titulo}</h3>
    {itens.length === 0 ? (
      <p className="mt-2 text-[13px] text-muted-foreground">{vazio}</p>
    ) : (
      <ul className="mt-2 space-y-3">
        {itens.map((item) => (
          <li key={`${item.chave}-${item.evidencia}`} className="text-[13px] leading-relaxed">
            <p>{item.frase}</p>
            <p className="mt-0.5 text-[11px] text-muted-foreground">evidência do contrato: {item.evidencia}</p>
          </li>
        ))}
      </ul>
    )}
  </div>
);

export const DiagnosticoDaBancada: React.FC<{ bancada: BancadaVisivel; comparando: boolean; aoComparar: () => void }> = ({
  bancada, comparando, aoComparar,
}) => (
  <section aria-labelledby="diagnostico-titulo-lab" className="pt-10">
    <p className="kicker">diagnóstico</p>
    <h2 id="diagnostico-titulo-lab" className="mt-1 max-w-[28ch] text-balance font-display text-[22px] font-semibold tracking-tight">
      Hipótese principal, não um fato
    </h2>
    <p className="mt-2 font-display text-[18px] font-semibold leading-snug">{bancada.diagnosticoPrincipal}</p>
    <p className="mt-2 max-w-[68ch] text-pretty text-[14px] leading-relaxed text-muted-foreground">
      {bancada.diagnosticoResumo}
    </p>
    <p className="mt-2 text-[12px] text-muted-foreground">Confiança: {bancada.confiancaDoDiagnostico}</p>
    <div className="mt-5 grid gap-6 md:grid-cols-3 md:divide-x md:divide-border">
      <ColunaDeFatores titulo="apoia" itens={bancada.apoiam} vazio="Nenhum fator de apoio veio nesta fotografia." />
      <div className="md:pl-6">
        <ColunaDeFatores titulo="contradiz" itens={bancada.contradizem} vazio="Nenhum fator contrário veio nesta fotografia." />
      </div>
      <div className="md:pl-6">
        <ColunaDeFatores titulo="ainda necessário" itens={bancada.aindaNecessario} vazio="Nenhuma lacuna relevante nesta fotografia." />
      </div>
    </div>
    <div className="mt-5">
      <h3 className="text-[12px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">hipóteses secundárias</h3>
      {bancada.hipotesesSecundarias.length === 0 ? (
        <p className="mt-2 text-[13px] text-muted-foreground">O contrato não enviou hipótese secundária distinta da principal.</p>
      ) : (
        <ul className="mt-2 list-disc space-y-1 pl-4 text-[13px] leading-relaxed">
          {bancada.hipotesesSecundarias.map((item) => <li key={item}>{item}</li>)}
        </ul>
      )}
    </div>
    <button
      type="button"
      onClick={aoComparar}
      aria-expanded={comparando}
      aria-controls="comparacao-diagnostico"
      className={cn(
        'mt-4 inline-flex min-h-11 items-center gap-1.5 rounded-md px-3 text-[12px] font-medium md:min-h-10',
        'shadow-[0_0_0_1px_rgba(15,23,42,0.08)] transition-transform duration-150 ease-out',
        'hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        'active:scale-[0.96] motion-reduce:active:scale-100',
      )}
    >
      <GitCompareArrows className="h-3.5 w-3.5" aria-hidden />
      {comparando ? 'ocultar comparação' : 'comparar diagnóstico'}
    </button>
    {comparando && (
      <div id="comparacao-diagnostico" className="mt-4 grid gap-4 border-t border-border pt-4 text-[13px] md:grid-cols-3">
        <p><span className="block text-[11px] uppercase tracking-[0.08em] text-muted-foreground">hipótese</span>{bancada.diagnosticoPrincipal}</p>
        <p><span className="block text-[11px] uppercase tracking-[0.08em] text-muted-foreground">apoio</span>{bancada.apoiam[0]?.frase ?? 'nenhum'}</p>
        <p><span className="block text-[11px] uppercase tracking-[0.08em] text-muted-foreground">contradição</span>{bancada.contradizem[0]?.frase ?? 'nenhuma'}</p>
      </div>
    )}
  </section>
);

function resumoDaProposta(p: PropostaVisivel): string {
  return [
    `ação: ${p.acao}`,
    `alvo: ${p.alvo}`,
    `antes: ${p.antes}`,
    `depois: ${p.depois}`,
    `efeito: ${p.efeito}`,
    `confiança: ${p.confianca}`,
    `bloqueios: ${p.bloqueios.join('; ') || 'nenhum declarado'}`,
    'estado: proposta, não executada',
  ].join('\n');
}

const CartaoDeProposta: React.FC<{ proposta: PropostaVisivel; aberta: boolean; aoAbrir: () => void }> = ({
  proposta, aberta, aoAbrir,
}) => (
  <article className="border-t border-border py-5">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0 max-w-[70ch]">
        <p className="font-display text-[16px] font-semibold">{proposta.acao}</p>
        <p className="mt-1 text-pretty text-[13px] leading-relaxed text-muted-foreground">{proposta.frase}</p>
        <p className="mt-2 text-[11px] font-semibold uppercase tracking-[0.08em]">proposta, não executada</p>
      </div>
      <p className="text-[12px] text-muted-foreground">confiança: {proposta.confianca}</p>
    </div>
    <dl className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <div><dt className="text-[11px] uppercase tracking-[0.08em] text-muted-foreground">alvo</dt><dd className="mt-1 break-words text-[13px]">{proposta.alvo}</dd></div>
      <div><dt className="text-[11px] uppercase tracking-[0.08em] text-muted-foreground">antes</dt><dd className="di-medida mt-1 text-[13px]">{proposta.antes}</dd></div>
      <div><dt className="text-[11px] uppercase tracking-[0.08em] text-muted-foreground">depois</dt><dd className="di-medida mt-1 text-[13px]">{proposta.depois}</dd></div>
      <div><dt className="text-[11px] uppercase tracking-[0.08em] text-muted-foreground">efeito estimado</dt><dd className="mt-1 text-[13px]">{proposta.efeito}</dd></div>
    </dl>
    <p className="mt-3 text-[12px] text-muted-foreground">amostra: {proposta.amostra}</p>
    <div className="mt-3">
      <p className="text-[11px] uppercase tracking-[0.08em] text-muted-foreground">bloqueios</p>
      {proposta.bloqueios.length === 0 ? (
        <p className="mt-1 text-[13px]">Nenhum bloqueio declarado, e a execução continua inexistente nesta rota.</p>
      ) : (
        <ul className="mt-1 list-disc pl-4 text-[13px] leading-relaxed">
          {proposta.bloqueios.map((b) => <li key={b}>{b}</li>)}
        </ul>
      )}
    </div>
    <p className="mt-3 break-words text-[11px] text-muted-foreground">idempotency key: {proposta.idempotencyKey}</p>
    <div className="mt-4 flex flex-wrap gap-2">
      <BotaoLocal rotulo="copiar ID" aoClicar={() => copiar(proposta.id)} />
      <BotaoLocal rotulo="copiar resumo" aoClicar={() => copiar(resumoDaProposta(proposta))} />
      <button
        type="button"
        onClick={aoAbrir}
        aria-expanded={aberta}
        className={cn(
          'inline-flex min-h-11 items-center rounded-md px-2.5 text-[12px] font-medium md:min-h-10',
          'shadow-[0_0_0_1px_rgba(15,23,42,0.08)] transition-transform duration-150 ease-out',
          'hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
          'active:scale-[0.96] motion-reduce:active:scale-100',
        )}
      >
        {aberta ? 'ocultar evidências' : 'abrir evidências'}
      </button>
    </div>
    {aberta && (
      <div className="mt-4 border-t border-dashed border-border pt-3">
        {proposta.evidencias.length === 0 ? (
          <p className="text-[13px] text-muted-foreground">Esta proposta chegou sem evidência anexada.</p>
        ) : proposta.evidencias.map((item) => <LinhaDeEvidencia key={item.chave} item={item} />)}
      </div>
    )}
  </article>
);

export const PropostasDaBancada: React.FC<{ bancada: BancadaVisivel }> = ({ bancada }) => {
  const [aberta, setAberta] = React.useState<string | null>(null);
  const titulo = bancada.propostas.length === 0
    ? bancada.caixaNaoApurada
      ? 'Não foi possível apurar propostas'
      : 'Nenhuma mudança recomendada'
    : `${bancada.propostas.length} ${bancada.propostas.length === 1 ? 'proposta' : 'propostas'}, não executada${bancada.propostas.length === 1 ? '' : 's'}`;

  return (
    <section aria-labelledby="propostas-titulo-lab" className="pt-10">
      <p className="kicker">propostas</p>
      <h2 id="propostas-titulo-lab" className="mt-1 font-display text-[22px] font-semibold tracking-tight">{titulo}</h2>
      <p className="mt-2 max-w-[68ch] text-[13px] leading-relaxed text-muted-foreground">
        Toda proposta nesta bancada nasce bloqueada. Não há aplicar, aprovar ou executor.
      </p>
      {bancada.propostas.length === 0 ? (
        <p className="mt-4 text-[13px] text-muted-foreground" role="status">
          {bancada.caixaNaoApurada
            ? 'A apuração de propostas não foi concluída. Fila vazia aqui significa que ninguém olhou.'
            : 'A apuração não encontrou mudança que a evidência sustente, ou a proposta tipada não veio neste contrato.'}
        </p>
      ) : (
        <div className="mt-2">
          {bancada.propostas.map((proposta) => (
            <CartaoDeProposta
              key={proposta.id}
              proposta={proposta}
              aberta={aberta === proposta.id}
              aoAbrir={() => setAberta(aberta === proposta.id ? null : proposta.id)}
            />
          ))}
        </div>
      )}
    </section>
  );
};

export const IsolamentoDaBancada: React.FC<{ bancada: BancadaVisivel }> = ({ bancada }) => (
  <aside className="self-start lg:sticky lg:top-4" aria-labelledby="rail-titulo">
    <div className="rounded-lg bg-card px-4 py-4 shadow-[var(--di-surface-shadow)]">
      <div className="flex items-center gap-2 text-destructive">
        <LockKeyhole className="h-4 w-4" aria-hidden />
        <p className="text-[11px] font-semibold uppercase tracking-[0.08em]">decisão bloqueada</p>
      </div>
      <h2 id="rail-titulo" className="mt-2 font-display text-lg font-semibold">Nada sai deste laboratório</h2>
      <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">
        Sem autorização, aplicação, recibo ou executor. A trava de escrita não participa desta rota.
      </p>
      <dl className="mt-4 divide-y divide-border text-[13px]">
        <div className="py-3">
          <dt className="text-muted-foreground">propostas tipadas</dt>
          <dd className="di-medida mt-0.5 font-medium">{bancada.propostas.length}</dd>
        </div>
        <div className="py-3">
          <dt className="text-muted-foreground">mutações executadas</dt>
          <dd className="di-medida mt-0.5 font-medium">{bancada.mutacoesExecutadas}</dd>
        </div>
        <div className="py-3">
          <dt className="text-muted-foreground">recibo</dt>
          <dd className="mt-0.5 font-medium">{bancada.recibo}</dd>
        </div>
        <div className="py-3">
          <dt className="text-muted-foreground">replay dourado</dt>
          <dd className="di-medida mt-0.5 font-medium">{bancada.replay ?? 'pronto para avaliação'}</dd>
        </div>
      </dl>
      {bancada.modo === 'sintetico' && (
        <p className="mt-3 text-[11px] font-semibold tracking-[0.06em] text-muted-foreground">
          {MARCA_SINTETICA_COM_PROTOTIPO}
        </p>
      )}
    </div>
  </aside>
);
