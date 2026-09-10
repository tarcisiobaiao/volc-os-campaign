/**
 * Revisão da estratégia criativa.
 *
 * Direção e peça são decisões independentes. Aprovar nunca dispara geração: o
 * ato pago continua isolado na Produção, depois da conferência de formatos,
 * quantidade e custo.
 *
 * ## O que esta tela deixou de ser
 *
 * Era um dossiê integralmente expandido: cada peça abria com ângulo, momento,
 * texto da arte, direção visual e copy do anúncio ao mesmo tempo, repetindo a
 * mesma frase por grupo. Nada era comparável, porque comparar exige ver dois
 * itens lado a lado e aqui cada um ocupava uma tela.
 *
 * Agora a peça é um CARTÃO com o essencial — gancho, ângulo, momento, uma linha
 * de direção — e o resto vive atrás de "Ver detalhes". Comparar é a tarefa; o
 * detalhe é a exceção.
 *
 * ## Os três defeitos de confiança que ela tinha
 *
 * 1. O erro de aprovar ou refinar era renderizado DENTRO de um `<details>`
 *    fechado. O operador clicava, nada acontecia, e nenhuma mensagem aparecia.
 *    Agora ele mora no topo, fora de qualquer bloco condicional.
 *
 * 2. `pendente` era a AUSÊNCIA de chip, e `rejeitado` não existia visualmente,
 *    embora o contrato tenha `REPROVADO`. Estado que só existe por ausência não
 *    é legível: cada peça agora carrega o seu, com glifo e palavra.
 *
 * 3. Não havia como desfazer uma aprovação. O contrato sempre teve `REPROVADO`
 *    e o servidor sempre aceitou; faltava o botão.
 *
 * ## Aurora
 *
 * `design.md` proíbe nominalmente `text-aurora` e a família de gradientes no
 * Estúdio. Nada aqui usa nenhum deles; a energia visual vem de tipografia e
 * hierarquia, e o estado usa o vocabulário semântico fechado.
 */
import { useMemo, useState } from 'react';
import {
  AlertCircle,
  ArrowRight,
  Check,
  CheckCircle2,
  ChevronDown,
  CircleSlash,
  Clock,
  Lock,
  RefreshCw,
  Undo2,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

import { caminhoDe } from '../api';
import { assistenteIntegrado } from '@/components/trafego/meta/ponteAssistente';
import type {
  EscopoFeedback,
  PecaCriativa,
  PedidoDeDecisao,
  SaidaDoAgente,
} from '../tipos';

export interface PainelDeEstrategiaProps {
  saida: SaidaDoAgente;
  runRef: string;
  aprovados: ReadonlySet<string>;
  ocupado: boolean;
  erro?: string | null;
  /** O nome que o operador deu ao trabalho. Sem ele a tela não diz qual operação é esta. */
  nomeDaOperacao?: string | null;
  onDecidir: (pedido: PedidoDeDecisao) => void;
  onRefinar: (feedback: string, escopo: EscopoFeedback) => void;
  onContinuar?: () => void;
}

const ESCOPOS: { valor: EscopoFeedback; rotulo: string; ajuda: string }[] = [
  { valor: 'PONTUAL', rotulo: 'Só este item', ajuda: 'Vale para o elemento escolhido.' },
  { valor: 'GRUPO', rotulo: 'A direção', ajuda: 'Vale para esta direção estratégica.' },
  { valor: 'PROJETO', rotulo: 'A operação', ajuda: 'Vale para o lote inteiro.' },
];

type Tom = 'neutro' | 'aprovado' | 'proposta' | 'pendente';

function Chip({ tom, children }: { tom: Tom; children: React.ReactNode }) {
  const estilo =
    tom === 'aprovado'
      ? 'bg-success/10 text-success'
      : tom === 'proposta'
        ? 'bg-primary/10 text-primary'
        : tom === 'pendente'
          ? 'bg-warning/10 text-warning'
          : 'bg-muted/60 text-foreground';
  return (
    <span
      className={`inline-flex h-6 items-center gap-1.5 rounded-full px-2.5 text-[11px] font-medium ${estilo}`}
    >
      {children}
    </span>
  );
}

export function PainelDeEstrategia({
  saida,
  runRef,
  aprovados,
  ocupado,
  erro,
  nomeDaOperacao,
  onDecidir,
  onRefinar,
  onContinuar,
}: PainelDeEstrategiaProps) {
  const [feedback, setFeedback] = useState('');
  const [escopo, setEscopo] = useState<EscopoFeedback>('PONTUAL');
  const [abertas, setAbertas] = useState<ReadonlySet<string>>(new Set());

  const pecasPorGrupo = useMemo(() => {
    const mapa = new Map<string, PecaCriativa[]>();
    for (const peca of saida.pecas) {
      const lista = mapa.get(peca.group_ref) ?? [];
      lista.push(peca);
      mapa.set(peca.group_ref, lista);
    }
    return mapa;
  }, [saida.pecas]);
  const copyPorRef = useMemo(
    () => new Map(saida.copies_compartilhadas.map((copy) => [copy.ref, copy])),
    [saida.copies_compartilhadas],
  );
  const estadoPorRef = useMemo(
    () => new Map(saida.jornada.map((estado) => [estado.ref, estado])),
    [saida.jornada],
  );

  const totalDePecas = saida.pecas.length;
  const totalAprovado = saida.pecas.filter((peca) =>
    aprovados.has(caminhoDe('pecas', peca.ref)),
  ).length;
  const haPecaAprovada = totalAprovado > 0;

  function decidir(
    colecao: string,
    ref: string,
    decisao: 'APROVADO' | 'REPROVADO',
    escopoDaDecisao: EscopoFeedback,
  ) {
    onDecidir({
      run_ref: runRef,
      decisao,
      escopo: escopoDaDecisao,
      caminho: caminhoDe(colecao, ref),
    });
  }

  function alternar(ref: string) {
    setAbertas((atual) => {
      const proxima = new Set(atual);
      if (proxima.has(ref)) proxima.delete(ref);
      else proxima.add(ref);
      return proxima;
    });
  }

  return (
    <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_18rem]">
      <main className="min-w-0 space-y-5">
        {/* ⚠️ O erro mora AQUI e não dentro do bloco de refinamento: ele
            aparecia dentro de um `<details>` fechado, e uma falha ao aprovar
            era literalmente invisível. */}
        {erro && (
          <p
            role="alert"
            className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive"
          >
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            {erro}
          </p>
        )}

        <section className="studio-surface">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="kicker">
                {nomeDaOperacao ? nomeDaOperacao : 'Leitura do briefing'}
              </p>
              <h2 className="mt-1 font-display text-xl font-semibold">Diagnóstico criativo</h2>
            </div>
            <Chip tom="proposta">Proposta do Assistente</Chip>
          </div>
          <dl className="mt-5 grid gap-5 md:grid-cols-3">
            <div>
              <dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Oferta real
              </dt>
              <dd className="mt-1 text-sm leading-relaxed text-foreground">
                {saida.diagnostico.oferta_real}
              </dd>
            </div>
            <div>
              <dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Promessa segura
              </dt>
              <dd className="mt-1 text-sm leading-relaxed text-foreground">
                {saida.diagnostico.promessa_maxima}
              </dd>
            </div>
            <div>
              <dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Tensão central
              </dt>
              <dd className="mt-1 text-sm leading-relaxed text-foreground">
                {saida.diagnostico.tensao_central}
              </dd>
            </div>
          </dl>
          {saida.diagnostico.desconhecidos.length > 0 && (
            <details className="mt-5 rounded-md border border-warning/40 bg-warning/5 p-3">
              <summary className="flex cursor-pointer list-none items-center gap-2 text-sm font-medium text-warning">
                <CircleSlash className="h-4 w-4" aria-hidden />
                {saida.diagnostico.desconhecidos.length}{' '}
                {saida.diagnostico.desconhecidos.length === 1
                  ? 'ponto sem comprovação'
                  : 'pontos sem comprovação'}
              </summary>
              <ul className="mt-3 list-inside list-disc space-y-1 text-sm text-foreground">
                {saida.diagnostico.desconhecidos.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
              <p className="mt-2 text-xs text-muted-foreground">
                O Assistente não usará essas informações como afirmações nas peças.
              </p>
            </details>
          )}
        </section>

        {saida.grupos.map((grupo) => {
          const grupoAprovado = aprovados.has(caminhoDe('grupos', grupo.ref));
          const daDirecao = pecasPorGrupo.get(grupo.ref) ?? [];
          return (
            <section key={grupo.ref} className="studio-surface overflow-hidden p-0">
              <div className="flex flex-col items-start justify-between gap-4 px-5 pt-5 sm:flex-row">
                <div className="min-w-0 w-full flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="font-display text-xl font-semibold">{grupo.nome}</h2>
                    {grupoAprovado ? (
                      <Chip tom="aprovado">
                        <Lock className="h-3 w-3" aria-hidden />
                        Direção aprovada
                      </Chip>
                    ) : (
                      <Chip tom="proposta">Direção proposta</Chip>
                    )}
                  </div>
                  <p className="mt-2 max-w-[72ch] text-sm leading-relaxed text-muted-foreground">
                    {grupo.territorio}
                  </p>
                  {/* Sem esta frase, aprovar a direção parece aprovar as peças
                      dela — e o operador chegaria à Produção achando que já
                      autorizou o que ainda não leu. */}
                  <p className="mt-2 text-xs text-muted-foreground">
                    Aprovar a direção preserva esta linha estratégica. Cada peça continua
                    com aprovação própria.
                  </p>
                </div>
                {!grupoAprovado && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    disabled={ocupado}
                    onClick={() => decidir('grupos', grupo.ref, 'APROVADO', 'GRUPO')}
                  >
                    <Check className="h-4 w-4" aria-hidden />
                    Aprovar direção
                  </Button>
                )}
              </div>

              {/* Cartões comparáveis, não um dossiê por peça. */}
              <ul className={`mt-5 grid gap-4 border-t border-border bg-transparent p-4 ${daDirecao.length > 1 ? 'sm:grid-cols-2' : ''}`}>
                {daDirecao.map((peca) => {
                  const caminho = caminhoDe('pecas', peca.ref);
                  const pecaAprovada = aprovados.has(caminho);
                  const estado = estadoPorRef.get(peca.estado_mental_ref);
                  const copy = copyPorRef.get(peca.shared_copy_ref);
                  const copyAprovada = !!copy && aprovados.has(caminhoDe('copies_compartilhadas', copy.ref));
                  const aberta = abertas.has(peca.ref);
                  return (
                    <li key={peca.ref} className="min-w-0 rounded-xl border border-border bg-card p-4">
                      <div className="flex items-start justify-between gap-3">
                        <h3 className="min-w-0 text-base font-semibold leading-snug text-foreground">
                          {peca.hook}
                        </h3>
                        {pecaAprovada ? (
                          <Chip tom="aprovado">
                            <CheckCircle2 className="h-3 w-3" aria-hidden />
                            Aprovada
                          </Chip>
                        ) : (
                          <Chip tom="pendente">
                            <Clock className="h-3 w-3" aria-hidden />
                            Pendente
                          </Chip>
                        )}
                      </div>

                      {peca.big_idea && <div className="mt-3 max-w-prose"><p className="text-[11px] font-semibold uppercase tracking-wide text-primary">Ideia central</p><p className="mt-1 text-sm leading-relaxed">{peca.big_idea.ideia_central}</p></div>}
                      <dl className="mt-3 space-y-1.5 text-xs">
                        <div className="flex gap-2">
                          <dt className="shrink-0 text-muted-foreground">Ângulo</dt>
                          <dd className="min-w-0 text-foreground">
                            {peca.angulo} · {peca.subangulo}
                          </dd>
                        </div>
                        <div className="flex gap-2">
                          <dt className="shrink-0 text-muted-foreground">Momento</dt>
                          <dd className="min-w-0 text-foreground">
                            {estado ? estado.nome : 'Não informado'}
                          </dd>
                        </div>
                      </dl>

                      <div className="mt-4 rounded-lg border border-primary/20 bg-primary/5 p-4" aria-label={`Texto previsto na imagem: ${peca.hook}`}>
                        <p className="text-[11px] font-semibold uppercase tracking-wide text-primary">Texto dentro da imagem</p>
                        <p className="mt-2 whitespace-pre-wrap break-words font-display text-xl font-semibold leading-tight">{peca.headline_interna}</p>
                        {peca.complemento_interno && <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-relaxed">{peca.complemento_interno}</p>}
                        {peca.cta_visual && <p className="mt-3 inline-block rounded-md bg-primary/10 px-3 py-1.5 text-sm font-semibold text-primary">{peca.cta_visual}</p>}
                        <p className="mt-3 text-xs text-muted-foreground">Prévia do texto; a composição final será gerada na produção.</p>
                      </div>

                      <div className="mt-4 flex flex-wrap items-center gap-2">
                        {pecaAprovada ? (
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            disabled={ocupado}
                            aria-label={`Desfazer a aprovação de ${peca.hook}`}
                            onClick={() => decidir('pecas', peca.ref, 'REPROVADO', 'PONTUAL')}
                          >
                            <Undo2 className="h-4 w-4" aria-hidden />
                            Desfazer
                          </Button>
                        ) : (
                          <Button
                            type="button"
                            size="sm"
                            disabled={ocupado}
                            aria-label={`Aprovar ${peca.hook} para produção`}
                            onClick={() => decidir('pecas', peca.ref, 'APROVADO', 'PONTUAL')}
                          >
                            <Check className="h-4 w-4" aria-hidden />
                            Aprovar
                          </Button>
                        )}
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          aria-expanded={aberta}
                          aria-label={`Ver detalhes de ${peca.hook}`}
                          onClick={() => alternar(peca.ref)}
                        >
                          <ChevronDown
                            className={`h-4 w-4 transition-transform duration-150 ${aberta ? 'rotate-180' : ''}`}
                            aria-hidden
                          />
                          {aberta ? 'Menos' : 'Ver detalhes'}
                        </Button>
                      </div>

                      {aberta && (
                        <dl className="mt-4 space-y-3 border-t border-border pt-4 text-xs">
                          {peca.big_idea && <>
                            <div><dt className="text-muted-foreground">Pergunta que motiva o clique</dt><dd className="mt-0.5 text-foreground">{peca.big_idea.pergunta_latente}</dd></div>
                            <div><dt className="text-muted-foreground">O que o clique promete entregar</dt><dd className="mt-0.5 text-foreground">{peca.big_idea.promessa_do_clique}</dd></div>
                            <div><dt className="text-muted-foreground">Cena-chave</dt><dd className="mt-0.5 text-foreground">{peca.big_idea.cena_chave}</dd></div>
                          </>}
                          <div>
                            <dt className="text-muted-foreground">Texto completo da arte</dt>
                            <dd className="mt-0.5 text-foreground">
                              {peca.headline_interna}
                              {peca.complemento_interno ? ` · ${peca.complemento_interno}` : ''}
                              {peca.cta_visual ? ` · ${peca.cta_visual}` : ''}
                            </dd>
                          </div>
                          <div>
                            <dt className="text-muted-foreground">Direção visual</dt>
                            <dd className="mt-0.5 text-foreground">{peca.direcao_visual}</dd>
                          </div>
                          {peca.direcao_de_arte && <div><dt className="font-medium text-foreground">Como a peça será composta</dt><dd className="mt-2 space-y-2 text-muted-foreground">
                            <p><span className="font-medium text-foreground">Composição: </span>{peca.direcao_de_arte.composicao}</p>
                            <p><span className="font-medium text-foreground">Tipografia: </span>{peca.direcao_de_arte.tipografia}</p>
                            <p><span className="font-medium text-foreground">Paleta e contraste: </span>{peca.direcao_de_arte.paleta_e_contraste}</p>
                            <p><span className="font-medium text-foreground">Cena: </span>{peca.direcao_de_arte.cena}</p>
                          </dd></div>}
                          {copy && (
                            <div>
                              <dt className="text-muted-foreground">
                                Texto do anúncio (fora da imagem)
                              </dt>
                              <dd className="mt-0.5 text-foreground">
                                <span className="font-medium">{copy.titulo}</span>.{' '}
                                {copy.texto_principal}
                                <span className="mt-2 block">{copy.descricao} · Botão: {copy.cta_nativa}</span>
                                <span className="mt-3 flex flex-wrap gap-2">
                                  <Button type="button" variant="outline" size="sm" disabled={ocupado}
                                    onClick={() => decidir('copies_compartilhadas', copy.ref,
                                      copyAprovada ? 'REPROVADO' : 'APROVADO', 'PONTUAL')}>
                                    {copyAprovada ? 'Desfazer aprovação do texto' : 'Aprovar texto do anúncio'}
                                  </Button>
                                  {assistenteIntegrado() && <Button type="button" size="sm"
                                    disabled={ocupado || !copyAprovada || !pecaAprovada}
                                    onClick={() => window.parent.postMessage({ type: 'volc:creative-copy',
                                      projectRef: saida.project_ref, runRef, creativeRef: peca.ref,
                                    }, window.location.origin)}>
                                    Usar texto na campanha
                                  </Button>}
                                </span>
                                <span className="mt-2 block text-muted-foreground">
                                  A aprovação deste texto é separada da imagem e vale para as peças que o compartilham.
                                </span>
                              </dd>
                            </div>
                          )}
                          <div>
                            <dt className="text-muted-foreground">Procedência</dt>
                            <dd className="mt-0.5 font-mono text-[11px] text-muted-foreground">
                              {peca.ref} · fatos: {peca.fato_refs.join(', ') || 'nenhum'}
                            </dd>
                          </div>
                        </dl>
                      )}
                    </li>
                  );
                })}
              </ul>
            </section>
          );
        })}

        <details className="studio-surface group">
          <summary className="cursor-pointer list-none">
            <div className="flex items-center justify-between gap-4">
              <div>
                <h2 className="font-display text-lg font-semibold">Pedir ajustes</h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Refine apenas o que ainda não foi aprovado.
                </p>
              </div>
              <span className="text-sm font-medium text-primary group-open:hidden">Abrir</span>
            </div>
          </summary>
          <p className="mt-4 max-w-[70ch] text-sm text-muted-foreground">
            A próxima execução recebe este lote e o seu comentário. O que já foi aprovado
            fica preservado. Refinar não desfaz aprovação.
          </p>
          <div className="mt-4 grid gap-4 md:grid-cols-[1fr_auto]">
            <div className="space-y-1.5">
              <Label htmlFor="ac-feedback">O que mudar</Label>
              <Textarea
                id="ac-feedback"
                rows={3}
                maxLength={4000}
                value={feedback}
                onChange={(event) => setFeedback(event.target.value)}
              />
            </div>
            <div className="space-y-1.5 md:w-56">
              <Label htmlFor="ac-escopo">Alcance</Label>
              <Select value={escopo} onValueChange={(valor) => setEscopo(valor as EscopoFeedback)}>
                <SelectTrigger id="ac-escopo">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ESCOPOS.map((item) => (
                    <SelectItem key={item.valor} value={item.valor}>
                      {item.rotulo}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                {ESCOPOS.find((item) => item.valor === escopo)?.ajuda}
              </p>
            </div>
          </div>
          <Button
            type="button"
            variant="outline"
            className="mt-4"
            disabled={ocupado || feedback.trim().length < 3}
            onClick={() => onRefinar(feedback.trim(), escopo)}
          >
            <RefreshCw className="h-4 w-4" aria-hidden />
            {ocupado ? 'Preparando ajustes…' : 'Refinar estratégia'}
          </Button>
        </details>

        <details className="rounded-lg border border-border bg-muted/20 p-4">
          <summary className="cursor-pointer text-sm font-semibold text-foreground">
            Validação técnica do lote
          </summary>
          <p className="mt-3 max-w-[70ch] text-sm text-muted-foreground">
            {saida.recibo.valido
              ? 'O lote passou nas contraprovas determinísticas de contrato do servidor: referências existem, fatos são citados, itens aprovados não mudaram e as peças têm diferenças materiais.'
              : 'Este lote não carrega validação de contrato.'}
          </p>
          <p className="mt-2 max-w-[70ch] text-sm text-muted-foreground">
            Isso não substitui a sua aprovação nem garante elegibilidade na Meta. A imagem
            ainda não existe.
          </p>
          {saida.recibo.avisos.length > 0 && (
            <ul className="mt-3 list-inside list-disc space-y-1 text-sm text-foreground">
              {saida.recibo.avisos.map((aviso) => (
                <li key={aviso}>{aviso}</li>
              ))}
            </ul>
          )}
          {saida.recibo.codigos.length > 0 && (
            <p className="mt-2 font-mono text-[11px] text-muted-foreground">
              {saida.recibo.codigos.join(' · ')}
            </p>
          )}
        </details>
      </main>

      <aside className="studio-review-rail lg:sticky lg:top-6">
        <p className="kicker">Sua revisão</p>
        <div className="mt-3 flex items-end justify-between gap-3">
          <p
            aria-label={`${totalAprovado} de ${totalDePecas} peças aprovadas`}
            className="font-display text-3xl font-semibold tabular-nums"
          >
            {totalAprovado}
            <span className="text-base font-medium text-muted-foreground">/{totalDePecas}</span>
          </p>
          <Chip tom={haPecaAprovada ? 'aprovado' : 'pendente'}>
            {haPecaAprovada ? 'Pode avançar' : 'Aguardando'}
          </Chip>
        </div>
        <p className="mt-2 text-sm text-muted-foreground">
          {totalAprovado === 1 ? 'peça aprovada para produção' : 'peças aprovadas para produção'}
        </p>
        <div className="my-5 h-px bg-border" />
        <p className="text-sm font-medium text-foreground">
          Aprovação não gera imagens nem cobrança.
        </p>
        <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
          Na Produção, você escolhe os formatos, confere a quantidade e autoriza o custo
          antes de chamar o motor.
        </p>
        <Button
          type="button"
          className="mt-5 w-full"
          disabled={!haPecaAprovada || ocupado}
          onClick={() => onContinuar?.()}
        >
          Continuar para produção
          <ArrowRight className="h-4 w-4" aria-hidden />
        </Button>
        {!haPecaAprovada && (
          <p className="mt-2 text-center text-xs text-muted-foreground">
            Aprove ao menos uma peça para continuar.
          </p>
        )}
      </aside>
    </div>
  );
}
