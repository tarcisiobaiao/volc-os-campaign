/**
 * Estágio 3 — o texto que o anúncio vai dizer.
 *
 * ## Por que ele existe agora e não existia antes
 *
 * `volc_ads/copy` estava inteiro e desligado: cascata de retry, contrato de 5
 * classes, 6.651 headlines de corpus para ancorar o tom. A prova reprovava
 * sempre, e o botão de subir nunca acendia — não por causa da trava, por causa
 * disto.
 *
 * ## O contador NÃO é `texto.length`
 *
 * `{KeyWord:Cartão}` são 16 caracteres para o JavaScript e 6 para o Google, que
 * conta a tag DKI pelo FALLBACK. Medido: `Guia de {KeyWord:Cartão}` tem
 * comprimento efetivo 14, não 24. Contar cru reprovaria título válido e — pior —
 * aprovaria título que estoura no leilão. A regra é a mesma de
 * `copy/contrato.comprimento_efetivo`.
 *
 * ## O tempo é mostrado porque ele é longo
 *
 * Medido em 18/08/2026 no card 73: 174,19 s em duas rodadas. Um spinner mudo
 * por três minutos é indistinguível de uma tela travada, e o operador
 * recarrega a página — jogando fora token já pago.
 */
import React, { useEffect, useState } from 'react';
import { AlertTriangle, Check, Loader2, PenLine, RefreshCw, Sparkles } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import { MODELOS_DE_COPY } from '@/types/trafego';
import type { CopyGerada, CopyPersistida, PendenciaDaCopy } from '@/types/trafego';

/** A mesma conta de `copy/contrato.comprimento_efetivo`: a tag DKI vale o
 *  fallback dela, porque é assim que o Google mede. */
const DKI = /\{KeyWord:([^}]*)\}/gi;
export function comprimentoEfetivo(t: string | null | undefined): number {
  // ⚠️ Tolerar vazio não é preguiça: em 19/08/2026 um `undefined` aqui derrubou
  // a página INTEIRA em tela branca. O texto vem de JSON persistido, e JSON
  // persistido muda de forma — a rota de edição gravou `texto` onde a tela lia
  // `title`. Um contador que quebra leva junto tudo o que estava certo.
  return (t ?? '').replace(DKI, (_m, fallback: string) => fallback).length;
}

/** O título do sitelink, nos DOIS vocabulários.
 *
 *  ⚠️ O engine chama `texto`/`descricao1`; a tela nasceu chamando
 *  `title`/`description1`. A rota de edição faz a copy passar pela dataclass do
 *  engine, então o mesmo card pode ter uma forma antes e outra depois de ser
 *  editado. Ler os dois é o que impede a tela de sumir quando isso acontece —
 *  o backend já faz o mesmo em `_copy_do_corpo`. */
export function tituloDoSitelink(s: Record<string, unknown>): string {
  return String(s?.title ?? s?.texto ?? '');
}

/** Os tetos de `copy/contrato.MAX_CHARS`. */
const TETO = {
  headline: 30,
  description: 90,
  sitelinkTitle: 25,
  sitelinkDesc: 35,
  callout: 25,
  snippet: 25,
} as const;

interface Props {
  escrita: CopyPersistida | null;
  /** A seleção de keywords mudou desde que este texto foi escrito. Ele continua
   *  parecendo válido — 15 títulos, fato citado — e só falharia no leilão. */
  desatualizada?: boolean;
  escrevendo: boolean;
  podeEscrever: boolean;
  motivoBloqueio?: string;
  onEscrever: () => void;
  onEditar: (copy: CopyGerada) => void;
  /** O modelo escolhido para a próxima escrita. Existe para COMPARAR: não há
   *  modelo medido para copy nesta operação, e eleger um sem medir seria
   *  inventar benchmark. */
  modelo: string;
  onModelo: (m: string) => void;
}

export const CartaoCopy: React.FC<Props> = ({
  escrita, escrevendo, podeEscrever, motivoBloqueio, desatualizada,
  onEscrever, onEditar, modelo, onModelo,
}) => {
  // ⚠️ A ORDEM DESTES DESVIOS É O CONTRATO DA TELA.
  //
  // `running` com a linha velha demais é PERDIDA, não "escrevendo": a tarefa
  // vive no processo do backend e um reinício a mata. Tratar as duas como a
  // mesma coisa deixaria o cronômetro girando para sempre.
  if (escrita?.status === 'running' && escrita.perdida) {
    return <Perdida onEscrever={onEscrever} />;
  }
  if (escrevendo) return <Escrevendo desde={escrita?.criado_em ?? null} />;
  if (escrita?.status === 'error') {
    return <Falhou erro={escrita.erro} onEscrever={onEscrever} />;
  }
  if (!escrita || !escrita.copy) {
    return <Vazio podeEscrever={podeEscrever} motivo={motivoBloqueio}
                  onEscrever={onEscrever} modelo={modelo} onModelo={onModelo} />;
  }

  const c = escrita.copy;
  const m = escrita.medicao;
  const pend: PendenciaDaCopy[] = escrita.pendentes ?? [];
  // ⚠️ TRÊS grupos, não dois — e o critério é QUEM JULGA.
  //
  // A versão anterior juntava tudo que fosse `forma_reescrever` e afirmava
  // "a prova reprova". Medido em 19/08/2026: a copy com 10 dessas pendências
  // PASSOU na prova e emitiu selo (34 operações). A frase era falsa.
  //
  // O que reprova de fato é o que o GOOGLE recusa — limite de caractere,
  // política. Cota de molde (C8) e ancoragem (C7) são julgamento DA CASA sobre
  // qualidade: valem como recomendação, não como portão. Confundir os dois
  // manda o operador reescrever copy que já pode subir.
  const barra = (c: string) =>
    /chars? >|limite|politica|policy|vazio|duplicata/i.test(c);
  const reescrever = pend.filter((p) => p.classe === 'forma_reescrever');
  // ⚠️ NORMALIZAÇÃO DEFENSIVA — a razão é uma tela branca de 19/08/2026.
  //
  // Este cartão lia `fatosFora.length`, `listas.sitelinks.length` e
  // outros direto. Um único campo ausente no JSON persistido derrubava a PÁGINA
  // INTEIRA, levando junto tudo o que estava correto — a copy, o portão, o
  // lançamento. E o JSON persistido MUDA de forma: a rota de edição faz a copy
  // passar pela dataclass do engine, que usa outro vocabulário.
  //
  // O custo de um array vazio é zero. O custo de `undefined.length` é o produto
  // inteiro sumir da tela.
  const fatosFora = escrita.fatos_descartados ?? [];
  const listas = {
    headlines: c.headlines ?? [],
    descriptions: c.descriptions ?? [],
    sitelinks: c.sitelinks ?? [],
    callouts: c.callouts ?? [],
    // ⚠️ `valores` é o nome do ENGINE; `values` é o que esta tela nasceu
    // lendo. Depois de a copy passar pela rota de edição, o que volta do banco
    // é `valores` — e `c.snippet.values.length` derrubou a página INTEIRA.
    // Ler os dois aqui é o que impede a terceira ocorrência do mesmo defeito.
    snippet: ((c.snippet as unknown as Record<string, unknown>)?.values
           ?? (c.snippet as unknown as Record<string, unknown>)?.valores
           ?? []) as string[],
  };

  const defeitos = reescrever.filter((p) => barra(`${p.codigo} ${p.detalhe}`));
  const qualidade = reescrever.filter((p) => !barra(`${p.codigo} ${p.detalhe}`));
  const contabilidade = pend.filter((p) => p.classe !== 'forma_reescrever');

  return (
    <div className="space-y-5">
      {/* A medição vem primeiro: ela responde "quanto isto custou e quanto
          demorou" antes de o operador ler 15 títulos e esquecer de perguntar. */}
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-muted-foreground">
        <span className="tabular">{escrita.segundos.toFixed(0)}s</span>
        <span className="tabular">
          {escrita.geracoes_conjunto} {escrita.geracoes_conjunto === 1 ? 'rodada' : 'rodadas'}
          {escrita.geracoes_asset > 0 && ` · ${escrita.geracoes_asset} de asset`}
        </span>
        <span className="tabular">
          {(m.tokens_entrada ?? 0).toLocaleString('pt-BR')} in ·{' '}
          {(m.tokens_saida ?? 0).toLocaleString('pt-BR')} out
        </span>
        {/* ⚠️ `custo_usd` nulo NÃO vira "US$ 0,00". O cliente não inventa preço,
            e um zero aqui seria um custo medido que não foi medido. */}
        <span className={cn('tabular', m.custo_usd == null && 'text-warning')}>
          {m.custo_usd != null
            ? `US$ ${m.custo_usd.toFixed(4)}`
            : 'preço não configurado'}
        </span>
        <Button size="sm" variant="ghost" className="ml-auto h-7 gap-1.5 text-xs"
                onClick={onEscrever}>
          <RefreshCw className="h-3 w-3" /> reescrever
        </Button>
      </div>

      {m.custo_usd == null && m.motivo_sem_custo && (
        <p className="text-[11px] leading-relaxed text-muted-foreground">
          {m.motivo_sem_custo}
        </p>
      )}

      {desatualizada && (
        <Nota tom="atencao" titulo="Este texto foi escrito para outra seleção">
          Você mexeu nas keywords depois de escrever. O anúncio continua válido de
          forma — títulos no tamanho, fato citado —, mas está ancorado em termos
          que podem não estar mais marcados. Reescrever custa outra rodada de LLM.
        </Nota>
      )}

      {fatosFora.length > 0 && (
        <Nota tom="atencao"
              titulo={`${fatosFora.length} ${fatosFora.length === 1 ? 'fato do funil ficou de fora' : 'fatos do funil ficaram de fora'}`}>
          A copy foi escrita com {escrita.fatos_usados}{' '}
          {escrita.fatos_usados === 1 ? 'fato' : 'fatos'}. Os outros têm um tipo que a
          seção 2 do <span className="font-mono">PROMPT.md</span> não conhece, e o texto
          não pode ancorar no que ele não sabe classificar.
          <ul className="mt-1.5 space-y-0.5">
            {fatosFora.map((d) => (
              <li key={d} className="tabular text-[11px]">{d}</li>
            ))}
          </ul>
        </Nota>
      )}

      {/* ⚠️ AS DUAS CLASSES NÃO PODEM DIVIDIR A MESMA LISTA.
          A versão anterior juntava tudo, cortava em 6 e dizia "não impedem
          lançar". Medido no card 74: das 10 pendências, as 6 primeiras eram
          contabilidade do modelo e as 4 escondidas pelo corte eram o anúncio
          errado — inclusive uma descrição de 91 caracteres num teto de 90, que
          o Google recusa. A frase tranquilizadora era falsa justamente sobre o
          que ela escondia. */}
      {defeitos.length > 0 && (
        <Nota tom="defeito"
              titulo={`${defeitos.length} ${defeitos.length === 1 ? 'item precisa' : 'itens precisam'} ser reescrito`}>
          Isto o <b>Google</b> recusa: limite de caractere e política. Enquanto
          estiver assim, a prova reprova de verdade.
          <ul className="mt-1.5 space-y-1">
            {defeitos.map((p) => (
              <li key={p.texto} className="text-[11px] leading-relaxed">
                <span className="kicker text-destructive">{p.alvo ?? p.codigo}</span>{' '}
                <span className="text-foreground">{p.detalhe}</span>
              </li>
            ))}
          </ul>
        </Nota>
      )}

      {/* ⚠️ Este grupo NÃO impede subir, e dizer o contrário foi o defeito que
          fez o operador reescrever copy boa. São as cotas de molde (C8) e a
          ancoragem (C7): julgamento DA CASA sobre qualidade, medido em 6.651
          aprovados das contas desta operação.

          E o corpus tem DOMÍNIO: benefício público (FGTS, INSS, Pé de Meia).
          Num nicho de comparação de produto, onde os modelos se chamam
          Point Pro 3 e T3 Smart, a cota de dígito é insatisfazível dizendo a
          verdade — a régua é de outro campeonato. Por isso aqui é conselho. */}
      {/* ⚠️ RECOLHIDO de propósito, e a razão é de proporção.
          Aviso que aparece sempre deixa de ser aviso e vira ruído: o operador
          leu "10 itens" num anúncio que já podia subir e concluiu que o sistema
          estava quebrado. O que grita nesta tela é só o que o Google recusa.
          Conselho fica a um clique — presente, não no caminho. */}
      {qualidade.length > 0 && (
        <details className="mt-3 rounded-md border border-border px-3 py-2">
          <summary className="cursor-pointer text-[11px] text-muted-foreground">
            {qualidade.length} {qualidade.length === 1 ? 'sugestão' : 'sugestões'} de
            qualidade — <b className="text-foreground">não impedem subir</b>
          </summary>
          Régua da casa, medida em 6.651 títulos aprovados <b>de nichos de
          benefício público</b>. Fora desse domínio ela erra: num comparativo de
          produto, o dígito costuma ser parte do nome do modelo, não uma
          alegação. Leia como conselho.
          <ul className="mt-1.5 space-y-1">
            {qualidade.map((p) => (
              <li key={p.texto} className="text-[11px] leading-relaxed">
                <span className="kicker">{p.alvo ?? p.codigo}</span>{' '}
                <span className="text-muted-foreground">{p.detalhe}</span>
              </li>
            ))}
          </ul>
        </details>
      )}

      {contabilidade.length > 0 && (
        <details className="rounded-md border border-border p-3">
          <summary className="cursor-pointer text-xs text-muted-foreground">
            {contabilidade.length} divergência{contabilidade.length === 1 ? '' : 's'} na
            auto-declaração do modelo — não afetam o anúncio
          </summary>
          <p className="mt-2 max-w-[74ch] text-[11px] leading-relaxed text-muted-foreground">
            O modelo declara quantos caracteres e qual mecânica usou em cada
            título, e o contrato confere. Errar essa conta não muda o texto que
            vai ao leilão — mas divergência de MECÂNICA (C6) é sinal de repetição
            de molde, e isso custa CTR.
          </p>
          <ul className="mt-2 space-y-1">
            {contabilidade.map((p) => (
              <li key={p.texto} className="text-[11px] leading-relaxed text-muted-foreground">
                <span className="kicker">{p.alvo ?? p.codigo}</span> {p.detalhe}
              </li>
            ))}
          </ul>
        </details>
      )}

      <Bloco titulo="títulos" n={listas.headlines.length}>
        {listas.headlines.map((h, i) => (
          <LinhaEditavel
            key={i} valor={h} teto={TETO.headline}
            onChange={(v) => onEditar({ ...c, headlines: troca(listas.headlines, i, v) })}
          />
        ))}
      </Bloco>

      <Bloco titulo="descrições" n={listas.descriptions.length}>
        {listas.descriptions.map((d, i) => (
          <LinhaEditavel
            key={i} valor={d} teto={TETO.description}
            onChange={(v) => onEditar({ ...c, descriptions: troca(listas.descriptions, i, v) })}
          />
        ))}
      </Bloco>

      {/* ⚠️ Estes eram de LEITURA, com a justificativa de que "o que muda o
          anúncio é título e descrição".

          Medido em 19/08/2026: depois de o juiz semântico limpar os falsos
          positivos, a copy do card 74 ficou com UM bloqueio — um callout de 26
          caracteres num teto de 25. O único item impublicável era justamente o
          que a tela não deixava consertar, e a alternativa era refazer 167 s de
          cascata para cortar um caractere.

          Editável não é conveniência: é a diferença entre corrigir e refazer. */}
      {listas.sitelinks.length > 0 && (
        <Bloco titulo="sitelinks" n={listas.sitelinks.length}>
          {listas.sitelinks.map((s, i) => (
            <div key={i} className="rounded-md border border-border px-3 py-2">
              <LinhaEditavel
                valor={tituloDoSitelink(s as unknown as Record<string, unknown>)}
                teto={TETO.sitelinkTitle}
                onChange={(v) => onEditar({
                  ...c,
                  // Grava nos DOIS nomes: quem ler qualquer um encontra.
                  sitelinks: listas.sitelinks.map((x, j) => (
                    j === i ? { ...x, title: v, texto: v } as typeof x : x)),
                })}
              />
              {(() => {
                const r = s as unknown as Record<string, unknown>;
                const d1 = String(r.description1 ?? r.descricao1 ?? '');
                const d2 = String(r.description2 ?? r.descricao2 ?? '');
                return (d1 || d2) ? (
                  <p className="mt-0.5 text-[11px] text-muted-foreground">
                    {[d1, d2].filter(Boolean).join(' · ')}
                  </p>
                ) : null;
              })()}
            </div>
          ))}
        </Bloco>
      )}

      {listas.callouts.length > 0 && (
        <Bloco titulo="callouts" n={listas.callouts.length}>
          <div className="space-y-1.5">
            {listas.callouts.map((texto, i) => (
              <LinhaEditavel
                key={i} valor={texto} teto={TETO.callout}
                onChange={(v) => onEditar({ ...c, callouts: troca(listas.callouts, i, v) })}
              />
            ))}
          </div>
        </Bloco>
      )}

      {c.snippet?.header && (
        <Bloco titulo={`snippet · ${c.snippet.header}`} n={listas.snippet.length}>
          <div className="flex flex-wrap gap-2">
            {listas.snippet.map((v) => (
              <span key={v} className="rounded-md border border-border px-2.5 py-1 text-xs">
                {v}
              </span>
            ))}
          </div>
        </Bloco>
      )}
    </div>
  );
};

const troca = (arr: string[], i: number, v: string) =>
  arr.map((x, j) => (j === i ? v : x));

/** O seletor de modelo. Existe para COMPARAR — ver `MODELOS_DE_COPY`.
 *
 *  Nenhum dos três é declarado melhor aqui, e isso é deliberado: não há
 *  medição de copy por modelo nesta operação, e escrever "recomendado" ao lado
 *  de um seria inventar benchmark. Rode o mesmo card em cada um e compare. */
const EscolhaDeModelo: React.FC<{ modelo: string; onModelo: (m: string) => void }> =
  ({ modelo, onModelo }) => (
  <label className="mt-3 inline-flex items-center gap-2 text-[11px] text-muted-foreground">
    <span>modelo</span>
    <select
      value={modelo} onChange={(e) => onModelo(e.target.value)}
      className="rounded-md border border-input bg-background px-2 py-1 text-[11px]
                 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      {MODELOS_DE_COPY.map((m) => (
        <option key={m.id} value={m.id}>
          {m.rotulo}{m.nota ? ` — ${m.nota}` : ''}
        </option>
      ))}
    </select>
  </label>
);

const Vazio: React.FC<{ podeEscrever: boolean; motivo?: string; onEscrever: () => void;
                        modelo: string; onModelo: (m: string) => void }> =
  ({ podeEscrever, motivo, onEscrever, modelo, onModelo }) => (
  <div className="rounded-lg border border-dashed border-border py-10 text-center">
    <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-full bg-primary/10">
      <PenLine className="h-5 w-5 text-primary" />
    </div>
    <p className="mt-3 text-sm font-medium">O anúncio ainda não tem texto</p>
    <p className="mx-auto mt-1 max-w-md text-xs leading-relaxed text-muted-foreground">
      A cascata escreve 15 títulos e 4 descrições ancorados nos fatos do funil, e
      confere cada um contra o contrato antes de devolver.
    </p>
    <Button className="mt-4 gap-2" disabled={!podeEscrever} onClick={onEscrever}>
      <Sparkles className="h-4 w-4" /> Escrever a copy
    </Button>
    <p className="mt-2 text-[11px] text-muted-foreground">
      {motivo ?? 'Leva alguns minutos e consome tokens.'}
    </p>
    <div><EscolhaDeModelo modelo={modelo} onModelo={onModelo} /></div>
  </div>
);

/** O cronômetro é o conteúdo, não enfeite: 174 s medidos é tempo suficiente
 *  para alguém achar que a tela morreu e recarregar.
 *
 *  ⚠️ Ele conta a partir de `criado_em`, do BANCO — não de quando este
 *  componente montou. Quem abre a página no meio de uma escrita precisa ver
 *  "112s", não "0s": um cronômetro que reinicia a cada visita sugere que o
 *  trabalho recomeçou, e o operador clicaria de novo, gastando dobrado. */
const Escrevendo: React.FC<{ desde: string | null }> = ({ desde }) => {
  const inicio = desde ? new Date(desde).getTime() : Date.now();
  const [s, setS] = useState(() => Math.max(0, Math.round((Date.now() - inicio) / 1000)));
  useEffect(() => {
    const t = setInterval(() => setS(Math.max(0, Math.round((Date.now() - inicio) / 1000))), 1000);
    return () => clearInterval(t);
  }, [inicio]);
  return (
    <div className="rounded-lg border border-primary/30 bg-primary/[0.03] py-10 text-center">
      <Loader2 className="mx-auto h-6 w-6 animate-spin text-primary" />
      <p className="mt-3 text-sm font-medium">Escrevendo o anúncio…</p>
      <p className="tabular mt-1 text-2xl font-display font-bold">{s}s</p>
      <p className="mx-auto mt-2 max-w-sm text-[11px] leading-relaxed text-muted-foreground">
        A medida do card 73 foi de 174 s em duas rodadas. Pode sair da página: o
        servidor está escrevendo e o texto fica guardado.
      </p>
    </div>
  );
};

const Bloco: React.FC<{ titulo: string; n: number; children: React.ReactNode }> =
  ({ titulo, n, children }) => (
  <div>
    <div className="mb-2 flex items-baseline gap-2">
      <span className="kicker">{titulo}</span>
      <span className="tabular text-[11px] text-muted-foreground">{n}</span>
    </div>
    <div className="space-y-1.5">{children}</div>
  </div>
);

const LinhaEditavel: React.FC<{ valor: string; teto: number; onChange: (v: string) => void }> =
  ({ valor, teto, onChange }) => {
  const n = comprimentoEfetivo(valor);
  return (
    <div className="flex items-center gap-3">
      <Input
        value={valor}
        onChange={(e) => onChange(e.target.value)}
        aria-label={`texto do anúncio, ${n} de ${teto} caracteres`}
        className={cn('h-9 text-sm', n > teto && 'border-destructive')}
      />
      <Contador n={n} teto={teto} />
    </div>
  );
};

/** Estado por NÚMERO e por cor, nunca só por cor: `--warning` mede 2,38:1 sobre
 *  `--card` no tema claro, abaixo do piso de 4,5:1. O número sempre diz. */
const Contador: React.FC<{ n: number; teto: number }> = ({ n, teto }) => (
  <span className={cn('tabular w-14 shrink-0 text-right text-[11px]',
                      n > teto ? 'font-medium text-destructive'
                        : n > teto - 4 ? 'text-warning' : 'text-muted-foreground')}>
    {n}/{teto}
  </span>
);

const Nota: React.FC<{ tom: 'atencao' | 'defeito' | 'ok'; titulo: string; children: React.ReactNode }> =
  ({ tom, titulo, children }) => (
  <div className={cn('flex items-start gap-2.5 rounded-md border p-3',
                     tom === 'defeito' ? 'border-destructive/40 bg-destructive/[0.05]'
                       : tom === 'atencao' ? 'border-warning/40 bg-warning/[0.06]'
                       : 'border-border')}>
    {tom === 'defeito'
      ? <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-destructive" aria-hidden />
      : tom === 'atencao'
      ? <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" aria-hidden />
      : <Check className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />}
    <div className="min-w-0 text-xs leading-relaxed text-muted-foreground">
      <span className="block font-medium text-foreground">{titulo}</span>
      {children}
    </div>
  </div>
);

export const contarCopy = (c: CopyGerada | null | undefined) =>
  (c?.headlines?.length ?? 0) + (c?.descriptions?.length ?? 0);

/** ⚠️ `running` sem ninguém escrevendo. A tarefa vive dentro do processo do
 *  backend — um reinício a mata e deixa a linha `running` para sempre. Dizer
 *  isso é melhor que um cronômetro eterno: o operador precisa saber que pode
 *  (e deve) mandar de novo. */
const Perdida: React.FC<{ onEscrever: () => void }> = ({ onEscrever }) => (
  <div className="rounded-lg border border-warning/40 bg-warning/[0.06] py-8 text-center">
    <AlertTriangle className="mx-auto h-5 w-5 text-warning" aria-hidden />
    <p className="mt-3 text-sm font-medium">A escrita anterior se perdeu</p>
    <p className="mx-auto mt-1 max-w-md text-xs leading-relaxed text-muted-foreground">
      A tarefa estava rodando dentro do backend e ele reiniciou. O consumo daquela
      tentativa já aconteceu e o texto não chegou a ser gravado.
    </p>
    <Button className="mt-4 gap-2" onClick={onEscrever}>
      <RefreshCw className="h-4 w-4" /> Escrever de novo
    </Button>
  </div>
);

const Falhou: React.FC<{ erro: string | null; onEscrever: () => void }> =
  ({ erro, onEscrever }) => (
  <div className="rounded-lg border border-destructive/40 bg-destructive/[0.05] py-8 text-center">
    <AlertTriangle className="mx-auto h-5 w-5 text-destructive" aria-hidden />
    <p className="mt-3 text-sm font-medium">A escrita falhou</p>
    <p className="mx-auto mt-1 max-w-md text-xs leading-relaxed text-muted-foreground">
      {erro || 'Sem mensagem do servidor.'}
    </p>
    <Button className="mt-4 gap-2" variant="outline" onClick={onEscrever}>
      <RefreshCw className="h-4 w-4" /> Tentar de novo
    </Button>
  </div>
);
