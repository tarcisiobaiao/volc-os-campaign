/**
 * /redator/funil/:runId/p/:n — uma página do funil, inteira.
 *
 * ## Por que isto substituiu o painel lateral
 *
 * A primeira versão abria a página num `Sheet` de 672px. O que se faz aqui é
 * JULGAR SE A COPY PRESTA — ler 900 palavras e decidir se vão ao ar — e uma
 * coluna espremida contra a borda direita, com a grade do funil vazando por
 * baixo, é a pior forma possível de ler qualquer coisa.
 *
 * Página inteira, coluna de 68ch, e o resto (imagem, SEO, canais oficiais,
 * prints, slots) numa lateral estreita que acompanha. O texto é o assunto; o
 * resto é o que se confere sem sair dele.
 *
 * ## A paginação é o que faz revisar um funil ser possível
 *
 * Um funil tem 5 a 7 páginas e elas se referenciam. Anterior/próxima com as
 * setas do teclado deixam percorrer o funil na ordem em que o leitor percorre —
 * que é a única forma de perceber que duas páginas repetem o mesmo argumento.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, ArrowRight, Camera, ExternalLink, Lock, PenLine, Upload } from 'lucide-react';

import { Layout } from '@/components/layout/Layout';
import { LpEmSlots, ProsaDaPagina } from '@/components/redator/ProsaDaPagina';
import { PainelDoDestinoPago } from '@/components/landing-policy/PainelDoDestinoPago';
import { pautadorApi } from '@/lib/pautadorApi';
import { leituraDoDestinoPago } from '@/lib/landing-policy/prontidao';
import { cn } from '@/lib/utils';
import { linkDeEdicao } from '@/lib/wordpress';
import type { ProvaVisual } from '@/types/publicacao';
import type { FunilEscrito, PaginaEscrita } from '@/types/redatorPaginas';
import { abrirArtefato, ImagemDoArtefato } from '@/components/redator/ImagemDoArtefato';

function moeda(v: number): string {
  return `US$ ${v.toFixed(4).replace('.', ',')}`;
}

const Lateral: React.FC<{ titulo: string; nota?: string; children: React.ReactNode }> =
  ({ titulo, nota, children }) => (
    <section className="border-t border-border pt-4">
      <div className="mb-2.5 flex items-baseline justify-between gap-2">
        <h3 className="kicker">{titulo}</h3>
        {nota && <span className="tabular text-[11px] text-muted-foreground">{nota}</span>}
      </div>
      {children}
    </section>
  );

const PaginaDoFunilPage: React.FC = () => {
  const { runId, n } = useParams<{ runId: string; n: string }>();
  const navegar = useNavigate();
  const idRun = Number(runId) || 0;
  const numero = Number(n) || 0;

  const [funil, setFunil] = useState<FunilEscrito | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  // Extraída do efeito para poder ser chamada DE NOVO: depois de enviar a
  // página ao WordPress, o painel precisa passar a mostrar o post e os links —
  // e o dado de `publicada` só existe do lado do servidor.
  const recarregar = useCallback(async () => {
    if (!idRun) return;
    try {
      setFunil(await pautadorApi.paginasDoRun(idRun));
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Falhei ao ler o funil.');
    }
  }, [idRun]);

  useEffect(() => { void recarregar(); }, [recarregar]);

  const ordenadas = useMemo(
    () => [...(funil?.paginas ?? [])].sort((a, b) => a.page_number - b.page_number),
    [funil],
  );
  const idx = ordenadas.findIndex((p) => p.page_number === numero);
  const p: PaginaEscrita | undefined = ordenadas[idx];

  // ⚠️ A PRONTIDÃO DE DESTINO PAGO DESTA PÁGINA, LIDA DO SERVIDOR.
  //
  // O recibo viaja dentro do dict de `publicada` — a mesma `paginas_publicadas`
  // que já existe, sob `landing_policy_receipt`. `publicada` é tipada em
  // `types/redatorPaginas.ts` sem esse campo (o tipo é de outro dono), então o
  // portador entra como `unknown` e o adaptador o abre.
  //
  // ⚠️ `exige_ponto_de_campanha: false` porque AQUI a pergunta é outra. Esta
  // tela julga a página antes/depois de publicar, não a elegibilidade de um
  // destino de campanha — exigir o ponto de campanha aqui reprovaria toda
  // página por uma ausência estrutural, e ensinaria o operador a ignorar o
  // painel. Quem exige o ponto de campanha é o cockpit do lançamento.
  const destino = useMemo(
    () => leituraDoDestinoPago(p?.publicada as unknown, {
      status_wp: p?.publicada?.status_wp,
      exige_ponto_de_campanha: false,
    }),
    [p],
  );
  const anterior = idx > 0 ? ordenadas[idx - 1] : null;
  const proxima = idx >= 0 && idx < ordenadas.length - 1 ? ordenadas[idx + 1] : null;

  // Setas do teclado. É o gesto que alguém revisando cinco páginas faz sem
  // pensar — e sem ele a revisão vira ida e volta ao mouse a cada página.
  useEffect(() => {
    const alvo = (e: KeyboardEvent) => {
      const em = document.activeElement?.tagName;
      if (em === 'INPUT' || em === 'TEXTAREA') return;
      if (e.key === 'ArrowLeft' && anterior) navegar(`/redator/funil/${idRun}/p/${anterior.page_number}`);
      if (e.key === 'ArrowRight' && proxima) navegar(`/redator/funil/${idRun}/p/${proxima.page_number}`);
    };
    window.addEventListener('keydown', alvo);
    return () => window.removeEventListener('keydown', alvo);
  }, [anterior, proxima, idRun, navegar]);

  // Sobe ao trocar de página: herdar a rolagem da anterior faria a próxima
  // abrir no meio do texto.
  useEffect(() => { window.scrollTo(0, 0); }, [numero]);

  return (
    <Layout>
      <div className="space-y-6 p-4 md:p-6">
        {/* A barra de navegação do funil. Fica no topo e não no rodapé porque é
            a primeira coisa que se procura ao terminar de ler uma página. */}
        <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-border bg-card px-4 py-3 shadow-card">
          <Link to={`/redator/funil/${idRun}`}
                className="kicker inline-flex items-center gap-1.5 text-muted-foreground transition-[color] duration-150 hover:text-foreground">
            <ArrowLeft className="h-3 w-3" aria-hidden /> o funil
          </Link>

          {!!ordenadas.length && (
            <div className="inline-flex items-center gap-1 rounded-lg border border-border bg-muted p-1">
              {ordenadas.map((o) => (
                <Link key={o.page_number} to={`/redator/funil/${idRun}/p/${o.page_number}`}
                      aria-label={`página ${o.page_number}: ${o.h1 || o.slug}`}
                      aria-current={o.page_number === numero ? 'page' : undefined}
                      className={cn('flex h-7 w-7 items-center justify-center rounded-md text-[11px] tabular',
                        o.page_number === numero
                          ? 'bg-card text-foreground shadow-card'
                          : o.bloqueada
                            ? 'text-destructive hover:bg-card/70'
                            : 'text-muted-foreground hover:bg-card/70')}>
                  {o.page_number}
                </Link>
              ))}
            </div>
          )}

          <div className="flex items-center gap-1">
            <Link to={anterior ? `/redator/funil/${idRun}/p/${anterior.page_number}` : '#'}
                  aria-disabled={!anterior}
                  className={cn('kicker inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 transition-[border-color,opacity] duration-150',
                    anterior ? 'hover:border-foreground/40' : 'pointer-events-none opacity-35')}>
              <ArrowLeft className="h-3 w-3" aria-hidden /> anterior
            </Link>
            <Link to={proxima ? `/redator/funil/${idRun}/p/${proxima.page_number}` : '#'}
                  aria-disabled={!proxima}
                  className={cn('kicker inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 transition-[border-color,opacity] duration-150',
                    proxima ? 'hover:border-foreground/40' : 'pointer-events-none opacity-35')}>
              próxima <ArrowRight className="h-3 w-3" aria-hidden />
            </Link>
          </div>
        </div>

        {erro && <p className="mt-8 max-w-[68ch] text-sm text-destructive">{erro}</p>}
        {!funil && !erro && <p className="mt-8 text-sm text-muted-foreground">Lendo a página…</p>}
        {funil && !p && (
          <p className="mt-8 max-w-[68ch] text-sm leading-relaxed text-muted-foreground">
            Este funil não tem uma página {numero}.{' '}
            <Link to={`/redator/funil/${idRun}`} className="underline underline-offset-4">Voltar ao funil</Link>.
          </p>
        )}

        {p && (
          <article className="mt-8">
            <div className="kicker">
              página {p.page_number} de {ordenadas.length} · {p.papel}
              {p.engajamento && ` · ${p.engajamento}`}
            </div>
            <h1 className="mt-2 max-w-[24ch] font-display text-3xl font-bold leading-[1.15] tracking-tight md:text-4xl">
              {p.h1 || p.slug}
            </h1>
            <div className="mt-3 aurora-rule w-16" />
            <p className="tabular mt-3 break-all text-xs text-muted-foreground">/{p.slug}</p>

            {p.bloqueada && (
              <div className="mt-6 flex max-w-[68ch] items-start gap-3 rounded-lg border border-destructive/40 bg-card p-4 shadow-card">
                <Lock className="mt-0.5 h-4 w-4 shrink-0 text-destructive" aria-hidden />
                <p className="text-xs leading-relaxed text-muted-foreground">
                  Um portão existencial reprovou esta página, então ela não foi
                  construída nem publicada. O que já tinha sido pago continua
                  aqui — é isso que evita pagar de novo pelo mesmo trabalho.
                </p>
              </div>
            )}

            <div className="mt-10 grid gap-x-14 gap-y-10 lg:grid-cols-[minmax(0,68ch)_260px]">
              {/* O TEXTO. É por ele que alguém abriu esta página. */}
              <div className="min-w-0">
                {p.texto.conteudo ? (
                  p.texto.formato === 'lp_json'
                    ? <LpEmSlots bruto={p.texto.conteudo} />
                    : <ProsaDaPagina bruto={p.texto.conteudo} />
                ) : (
                  <p className="text-sm text-muted-foreground">
                    Não foi escrito: a página parou antes da redação.
                  </p>
                )}
              </div>

              {/* O que se confere sem sair do texto. */}
              <aside className="space-y-6 rounded-xl border border-border bg-card p-4 shadow-card lg:sticky lg:top-6 lg:self-start">
                {p.imagem && (
                  <ImagemDoArtefato runId={idRun} arquivo={p.imagem} className="w-full" />
                )}

                <Lateral titulo="custo desta página">
                  <div className="tabular font-display text-xl font-bold">{moeda(p.custo_usd)}</div>
                  <div className="text-[11px] text-muted-foreground">
                    {p.texto.palavras ? `${p.texto.palavras} palavras · ${p.texto.formato}` : 'sem texto'}
                  </div>
                </Lateral>

                {(p.seo.titulo || p.seo.descricao) && (
                  <Lateral titulo="como aparece na busca"
                           nota={`${p.seo.titulo.length}/60 · ${p.seo.descricao.length}/160`}>
                    <div className="rounded-md border border-border bg-muted/50 p-3">
                      <div className="mb-1 truncate text-[11px] text-muted-foreground">
                        {p.meta?.canonical || `/${p.slug}`}
                      </div>
                      <div className={cn('mb-1 text-sm leading-snug text-info',
                                         p.seo.titulo.length > 60 && 'text-destructive')}>
                        {p.seo.titulo || '—'}
                      </div>
                      <p className={cn('text-[11px] leading-relaxed text-muted-foreground',
                                       p.seo.descricao.length > 160 && 'text-destructive')}>
                        {p.seo.descricao || '—'}
                      </p>
                    </div>
                    {p.meta?.robots?.includes('noindex') && (
                      <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">
                        <span className="tabular">{p.meta.robots}</span> — fora do índice
                        de propósito: esta página vive de tráfego comprado.
                      </p>
                    )}
                  </Lateral>
                )}

                {p.links_oficiais.length > 0 && (
                  <Lateral titulo="canais oficiais" nota={`${p.links_oficiais.length}`}>
                    <ul className="space-y-1.5">
                      {p.links_oficiais.map((u) => (
                        <li key={u}>
                          <a href={u} target="_blank" rel="noreferrer"
                             className="inline-flex items-start gap-1.5 break-all text-[11px] underline-offset-4 hover:underline">
                            <ExternalLink className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />{u}
                          </a>
                        </li>
                      ))}
                    </ul>
                  </Lateral>
                )}

                {p.prints.length > 0 && (
                  <Lateral titulo="prints do canal" nota={`${p.prints.length}`}>
                    <div className="space-y-3">
                      {p.prints.map((s) => (
                        <figure key={s.arquivo}>
                          <ImagemDoArtefato runId={idRun} arquivo={s.arquivo}
                                            className="w-full border border-border" />
                          <figcaption className="mt-1 truncate text-[11px] text-muted-foreground"
                                      title={s.url}>{s.url}</figcaption>
                        </figure>
                      ))}
                    </div>
                  </Lateral>
                )}

                {!!p.anuncios?.slots?.length && (
                  <Lateral titulo="slots de anúncio" nota={`${p.anuncios.slots.length}`}>
                    <div className="space-y-1.5">
                      {p.anuncios.slots.map((s) => (
                        <div key={s.slot_id} className="tabular flex items-baseline justify-between gap-2 text-[11px]">
                          <span>{s.slot_id}</span>
                          <span className="text-muted-foreground">{s.placement}</span>
                        </div>
                      ))}
                    </div>
                  </Lateral>
                )}

                {!!p.issues.length && (
                  <Lateral titulo="validadores" nota={`${p.issues.length}`}>
                    <div className="space-y-3">
                      {p.issues.map((i, k) => (
                        <div key={k}>
                          <div className="kicker text-destructive">{i.etapa} · {i.code}</div>
                          <p className="text-[11px] leading-relaxed text-muted-foreground">{i.message}</p>
                        </div>
                      ))}
                    </div>
                  </Lateral>
                )}

                {/* ⚠️ O PAINEL APARECE SEMPRE — inclusive quando não há post.
                    Ele inteiro vivia dentro de `{p.publicada && …}`, então uma
                    página não publicada não dizia NADA sobre WordPress: nem
                    link, nem post, nem uma palavra explicando a ausência.
                    Diante de um funil recuperado em 19/08/2026, o operador não
                    tinha como saber se o run tinha dado certo — a página pronta
                    e parada era visualmente idêntica à que nunca existiu. */}
                {!p.publicada && (
                  <Lateral titulo="no wordpress">
                    <EnviarAoWordPress runRowId={idRun} pagina={p}
                                       aoPublicar={recarregar} />
                  </Lateral>
                )}

                {p.publicada && (
                  <Lateral titulo="no wordpress">
                    <div className="flex flex-col gap-2">
                      <a href={p.publicada.url_wp} target="_blank" rel="noreferrer"
                         className="inline-flex items-center gap-2 rounded-md border border-border px-3 py-2 text-xs transition-[border-color] duration-150 hover:border-foreground/40">
                        <ExternalLink className="h-3.5 w-3.5" aria-hidden />
                        abrir o {p.publicada.status_wp === 'draft' ? 'rascunho' : p.publicada.status_wp}
                      </a>
                      {/* O caminho de volta. Revisar um rascunho é ir e vir entre
                          esta tela e o editor do WP; sem o link, o operador
                          procura o post por título no admin, e o título do WP é
                          a copy CALMA, não o h1 do briefing que ele leu aqui. */}
                      {linkDeEdicao(p.publicada) && (
                        <a href={linkDeEdicao(p.publicada) as string} target="_blank" rel="noreferrer"
                           className="inline-flex items-center gap-2 rounded-md border border-border px-3 py-2 text-xs transition-[border-color] duration-150 hover:border-foreground/40">
                          <PenLine className="h-3.5 w-3.5" aria-hidden />
                          editar no WordPress
                        </a>
                      )}
                    </div>
                    <p className="tabular mt-2 text-[11px] text-muted-foreground">
                      post #{p.publicada.post_id}
                    </p>
                    <ProvaVisualDaPagina runId={idRun} pagina={p} />
                    {p.publicada.status_wp === 'draft' && (
                      <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">
                        Endereço temporário. O definitivo — o que a campanha vai
                        apontar, por igualdade de string exata — só nasce quando
                        a página for publicada de verdade.
                      </p>
                    )}
                  </Lateral>
                )}

                {/* ⚠️ APARECE SEMPRE, publicada ou não — pelo mesmo motivo que o
                    painel do WordPress passou a aparecer sempre. Uma página sem
                    recibo é visualmente idêntica a uma avaliada e aprovada se a
                    seção só existir quando há recibo, e é justamente a primeira
                    que ninguém pode mandar tráfego pago para. */}
                <Lateral titulo="destino pago">
                  <PainelDoDestinoPago leitura={destino} titulo="" compacto />
                </Lateral>
              </aside>
            </div>

            {/* Fim de página: repete a navegação, porque quem terminou de ler
                900 palavras está no fim do documento, não no topo. */}
            {(anterior || proxima) && (
              <div className="mt-16 grid gap-3 border-t border-border pt-6 sm:grid-cols-2">
                {anterior ? (
                  <Link to={`/redator/funil/${idRun}/p/${anterior.page_number}`}
                        className="group rounded-xl border border-border bg-card p-4 shadow-card hover-lift">
                    <div className="kicker mb-1 flex items-center gap-1.5 text-muted-foreground">
                      <ArrowLeft className="h-3 w-3" aria-hidden /> página {anterior.page_number}
                    </div>
                    <div className="font-display text-sm font-bold leading-snug line-clamp-2">
                      {anterior.h1 || anterior.slug}
                    </div>
                  </Link>
                ) : <div />}
                {proxima && (
                  <Link to={`/redator/funil/${idRun}/p/${proxima.page_number}`}
                        className="group rounded-xl border border-border bg-card p-4 text-right shadow-card hover-lift sm:col-start-2">
                    <div className="kicker mb-1 flex items-center justify-end gap-1.5 text-muted-foreground">
                      página {proxima.page_number} <ArrowRight className="h-3 w-3" aria-hidden />
                    </div>
                    <div className="font-display text-sm font-bold leading-snug line-clamp-2">
                      {proxima.h1 || proxima.slug}
                    </div>
                  </Link>
                )}
              </div>
            )}
          </article>
        )}
      </div>
    </Layout>
  );
};

/** A foto da página no ar — inteira, com a rolagem já acionada.
 *
 * ## O que ela pega que nenhum portão pega
 *
 * Os validadores provam FATO (o número tem fonte) e FORMA (o HTML cumpre o
 * contrato). Nenhum deles vê o TEMA montar a página. Bloco que o tema não
 * conhece, imagem que não carregou, acordeão que não abre — nada disso reprova
 * em validador, e é a primeira coisa que o leitor pago enxerga.
 *
 * Na primeira execução real, 18/08/2026, ela achou um defeito de verdade: a LP
 * renderiza `0.57 %` (ponto decimal e espaço antes do símbolo) onde pt-BR pede
 * `0,57%`. Nenhum teste desta casa pegaria isso.
 */
const ProvaVisualDaPagina: React.FC<{ runId: number; pagina: PaginaEscrita }> =
  ({ runId, pagina }) => {
  const [prova, setProva] = useState<ProvaVisual | null>(null);
  const [tirando, setTirando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  // ⚠️ A rota de artefatos manda `max-age=86400` — correto para imagem do
  // motor, que nunca é reescrita. A prova visual É sobrescrita a cada clique,
  // então sem esta versão o operador clicaria em "tirar print" e aprovaria a
  // página olhando a foto de ontem.
  const [versao, setVersao] = useState(0);

  const tirar = async () => {
    setTirando(true);
    setErro(null);
    try {
      setProva(await pautadorApi.tirarProvaVisual(runId, pagina.page_number));
      setVersao(Date.now());
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Não consegui tirar o print.');
    } finally {
      setTirando(false);
    }
  };

  return (
    <div className="mt-3">
      <button type="button" onClick={tirar} disabled={tirando}
              className="inline-flex w-full items-center justify-center gap-2 rounded-md border border-border px-3 py-2
                         text-xs transition-[border-color,opacity] duration-150 hover:border-foreground/40 disabled:opacity-50">
        <Camera className={cn('h-3.5 w-3.5', tirando && 'animate-spin')} aria-hidden />
        {tirando ? 'fotografando a página…' : 'tirar print da página'}
      </button>

      {tirando && (
        <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">
          O navegador rola a página inteira antes de fotografar, para acionar o
          lazy-load. Leva ~20 s.
        </p>
      )}

      {erro && <p className="mt-2 text-[11px] text-destructive">{erro}</p>}

      {prova && !tirando && (
        <div className="mt-3 space-y-2">
          <p className={cn('text-[11px] leading-relaxed',
                           prova.parece_erro ? 'text-destructive' : 'text-muted-foreground')}>
            {prova.resumo}
          </p>
          <p className="tabular text-[11px] text-muted-foreground">
            HTTP {prova.status_http ?? '—'} · {Math.round(prova.bytes / 1024)} kB
          </p>
          <button
            type="button"
            onClick={() => { void abrirArtefato(runId, prova.arquivo, versao); }}
            className="block w-full overflow-hidden rounded-md border border-border text-left transition-[border-color] duration-150 hover:border-foreground/40"
          >
            <ImagemDoArtefato
              runId={runId}
              arquivo={prova.arquivo}
              versao={versao}
              alt={`página ${pagina.page_number} publicada, capturada inteira`}
              className="w-full"
            />
          </button>
          <p className="text-[11px] text-muted-foreground">
            Clique para abrir em tamanho real.
          </p>
        </div>
      )}
    </div>
  );
};

export default PaginaDoFunilPage;

/**
 * O GATILHO QUE FECHA O FUNIL.
 *
 * ## Por que ele precisou existir
 *
 * O motor publicava tudo ou nada: `--publish` no disparo, e ponto. Uma página
 * que caísse num portão e fosse consertada depois não tinha caminho nenhum de
 * volta ao WordPress — nem pela tela, nem pela API. Só terminal.
 *
 * Medido em 19/08/2026, run 9: p2, p3 e p4 ficaram escritas, aprovadas nos
 * portões e paradas no disco. O funil tinha duas páginas no ar e três órfãs — e
 * funil pela metade não é meio funil: os links internos apontam para páginas que
 * não existem, e a sessão comprada morre no primeiro salto.
 *
 * ## Por que ele confirma antes
 *
 * Isto ESCREVE num site de verdade, e o WordPress não recusa duplicata: ele
 * aceita, dá outro `post_id` e acrescenta `-2` ao slug. A atribuição de receita
 * casa `url_wp` com `campaign_funnel_urls` por igualdade de string exata — um
 * post a mais aponta a campanha para o lugar errado, em silêncio. O servidor
 * barra a duplicata de qualquer jeito; a confirmação existe porque o clique é
 * a autorização, e autorização acidental não é autorização.
 */
const EnviarAoWordPress: React.FC<{
  runRowId: number;
  pagina: PaginaEscrita;
  aoPublicar: () => void | Promise<void>;
}> = ({ runRowId, pagina, aoPublicar }) => {
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  if (pagina.bloqueada) {
    return (
      <p className="text-xs leading-relaxed text-muted-foreground">
        Esta página foi barrada por um portão do motor e não chegou a ser
        enviada ao WordPress. Os validadores acima dizem o motivo — enviar por
        aqui contornaria o portão, então o botão não aparece.
      </p>
    );
  }

  const enviar = async () => {
    if (!window.confirm(
      `Enviar a página ${pagina.page_number} ("${pagina.h1 || pagina.slug}") `
      + 'ao WordPress?\n\nEla sobe como RASCUNHO — quem publica de verdade é '
      + 'você, no WP.')) return;
    setEnviando(true);
    setErro(null);
    try {
      const r = await pautadorApi.publicarPagina(runRowId, pagina.page_number);
      if (!r.ok) { setErro(r.erro || 'O motor rodou e a página não foi publicada.'); return; }
      await aoPublicar();
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Falhei ao enviar ao WordPress.');
    } finally {
      setEnviando(false);
    }
  };

  return (
    <div>
      <p className="text-xs leading-relaxed text-muted-foreground">
        Esta página foi escrita e passou pelos portões, mas ainda não foi
        enviada ao WordPress.
      </p>
      <button type="button" onClick={() => void enviar()} disabled={enviando}
              className={cn('mt-3 inline-flex w-full items-center justify-center gap-2 rounded-md border px-3 py-2 text-xs transition-[opacity,border-color] duration-150',
                enviando
                  ? 'border-border text-muted-foreground'
                  : 'border-primary bg-primary text-primary-foreground hover:opacity-90')}>
        <Upload className={cn('h-3.5 w-3.5', enviando && 'animate-spin')} aria-hidden />
        {enviando ? 'enviando ao WordPress…' : 'enviar ao WordPress'}
      </button>
      {enviando && (
        <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">
          O motor está subindo o artigo. Se a página ainda não tiver widget, ele
          é gerado agora — leva mais uns segundos.
        </p>
      )}
      {erro && (
        <p className="mt-2 text-[11px] leading-relaxed text-destructive">{erro}</p>
      )}
      <p className="mt-3 text-[11px] leading-relaxed text-muted-foreground">
        Sobe como <b>rascunho</b>. O endereço definitivo — o que a campanha vai
        apontar, por igualdade de string exata — só nasce quando você publicar
        de verdade no WordPress.
      </p>
    </div>
  );
};
