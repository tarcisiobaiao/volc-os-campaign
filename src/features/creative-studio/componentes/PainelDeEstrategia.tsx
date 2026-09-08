/**
 * Revisão da estratégia criativa.
 *
 * Direção e peça são decisões independentes. Aprovar nunca dispara geração:
 * o ato pago continua isolado na Produção, depois da conferência de formatos,
 * quantidade e custo.
 */
import { useMemo, useState } from 'react';
import {
  AlertCircle,
  ArrowRight,
  Check,
  CheckCircle2,
  CircleSlash,
  Lock,
  RefreshCw,
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
  onDecidir: (pedido: PedidoDeDecisao) => void;
  onRefinar: (feedback: string, escopo: EscopoFeedback) => void;
  onContinuar?: () => void;
}

const ESCOPOS: { valor: EscopoFeedback; rotulo: string; ajuda: string }[] = [
  { valor: 'PONTUAL', rotulo: 'Só este item', ajuda: 'Vale para o elemento escolhido.' },
  { valor: 'GRUPO', rotulo: 'A direção', ajuda: 'Vale para esta direção estratégica.' },
  { valor: 'PROJETO', rotulo: 'A operação', ajuda: 'Vale para o lote inteiro.' },
];

function Chip({ tom, children }: { tom: 'neutro' | 'aprovado' | 'proposta'; children: React.ReactNode }) {
  const estilo = tom === 'aprovado'
    ? 'bg-success/10 text-success'
    : tom === 'proposta'
      ? 'bg-primary/10 text-primary'
      : 'bg-muted/60 text-muted-foreground';
  return <span className={`inline-flex h-6 items-center gap-1.5 rounded-full px-2.5 text-[11px] font-medium ${estilo}`}>{children}</span>;
}

export function PainelDeEstrategia({
  saida,
  runRef,
  aprovados,
  ocupado,
  erro,
  onDecidir,
  onRefinar,
  onContinuar,
}: PainelDeEstrategiaProps) {
  const [feedback, setFeedback] = useState('');
  const [escopo, setEscopo] = useState<EscopoFeedback>('PONTUAL');

  const pecasPorGrupo = useMemo(() => {
    const mapa = new Map<string, PecaCriativa[]>();
    for (const peca of saida.pecas) {
      const lista = mapa.get(peca.group_ref) ?? [];
      lista.push(peca);
      mapa.set(peca.group_ref, lista);
    }
    return mapa;
  }, [saida.pecas]);
  const copyPorRef = useMemo(() => new Map(saida.copies_compartilhadas.map((copy) => [copy.ref, copy])), [saida.copies_compartilhadas]);
  const estadoPorRef = useMemo(() => new Map(saida.jornada.map((estado) => [estado.ref, estado])), [saida.jornada]);
  const totalDePecas = saida.pecas.length;
  const totalAprovado = saida.pecas.filter((peca) => aprovados.has(caminhoDe('pecas', peca.ref))).length;
  const haPecaAprovada = totalAprovado > 0;

  function aprovar(colecao: string, ref: string, escopoDaDecisao: EscopoFeedback) {
    onDecidir({ run_ref: runRef, decisao: 'APROVADO', escopo: escopoDaDecisao, caminho: caminhoDe(colecao, ref) });
  }

  return (
    <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_18rem]">
      <main className="min-w-0 space-y-5">
        <section className="studio-surface">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="kicker">Leitura do briefing</p>
              <h2 className="mt-1 font-display text-xl font-semibold">Diagnóstico criativo</h2>
            </div>
            <Chip tom="proposta">Proposta do Assistente</Chip>
          </div>
          <dl className="mt-5 grid gap-5 md:grid-cols-3">
            <div><dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Oferta real</dt><dd className="mt-1 text-sm leading-relaxed text-foreground">{saida.diagnostico.oferta_real}</dd></div>
            <div><dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Promessa segura</dt><dd className="mt-1 text-sm leading-relaxed text-foreground">{saida.diagnostico.promessa_maxima}</dd></div>
            <div><dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Tensão central</dt><dd className="mt-1 text-sm leading-relaxed text-foreground">{saida.diagnostico.tensao_central}</dd></div>
          </dl>
          {saida.diagnostico.desconhecidos.length > 0 && (
            <details className="mt-5 rounded-md border border-warning/40 bg-warning/5 p-3">
              <summary className="flex cursor-pointer list-none items-center gap-2 text-sm font-medium text-warning">
                <CircleSlash className="h-4 w-4" aria-hidden />
                {saida.diagnostico.desconhecidos.length} {saida.diagnostico.desconhecidos.length === 1 ? 'ponto sem comprovação' : 'pontos sem comprovação'}
              </summary>
              <ul className="mt-3 list-inside list-disc space-y-1 text-sm text-foreground">{saida.diagnostico.desconhecidos.map((item) => <li key={item}>{item}</li>)}</ul>
              <p className="mt-2 text-xs text-muted-foreground">O Assistente não usará essas informações como afirmações nas peças.</p>
            </details>
          )}
        </section>

        {saida.grupos.map((grupo) => {
          const grupoAprovado = aprovados.has(caminhoDe('grupos', grupo.ref));
          return (
            <section key={grupo.ref} className="studio-surface overflow-hidden p-0">
              <div className="flex flex-wrap items-start justify-between gap-4 px-5 pt-5">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="font-display text-xl font-semibold">{grupo.nome}</h2>
                    {grupoAprovado ? <Chip tom="aprovado"><Lock className="h-3 w-3" aria-hidden />Direção aprovada</Chip> : <Chip tom="proposta">Direção proposta</Chip>}
                  </div>
                  <p className="mt-2 max-w-[72ch] text-sm leading-relaxed text-muted-foreground">{grupo.territorio}</p>
                  <p className="mt-1 max-w-[72ch] text-sm leading-relaxed text-muted-foreground"><span className="font-medium text-foreground">O que diferencia:</span> {grupo.diferenca_material}</p>
                  <p className="mt-3 text-xs text-muted-foreground">Aprovar a direção preserva esta linha estratégica. Cada peça continua com aprovação própria.</p>
                </div>
                {!grupoAprovado && <Button type="button" variant="outline" size="sm" disabled={ocupado} onClick={() => aprovar('grupos', grupo.ref, 'GRUPO')}><Check className="h-4 w-4" aria-hidden />Aprovar direção</Button>}
              </div>

              <ul className="mt-5 border-t border-border">
                {(pecasPorGrupo.get(grupo.ref) ?? []).map((peca) => {
                  const copy = copyPorRef.get(peca.shared_copy_ref);
                  const estado = estadoPorRef.get(peca.estado_mental_ref);
                  const pecaAprovada = aprovados.has(caminhoDe('pecas', peca.ref));
                  return (
                    <li key={peca.ref} className="border-b border-border px-5 py-5 last:border-b-0">
                      <div className="flex flex-wrap items-start justify-between gap-4">
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <h3 className="text-base font-semibold text-foreground">{peca.hook}</h3>
                            {pecaAprovada && <Chip tom="aprovado"><CheckCircle2 className="h-3 w-3" aria-hidden />Pronta para produção</Chip>}
                            <Chip tom="neutro">{peca.formato}</Chip>
                          </div>
                          <dl className="mt-4 grid gap-x-8 gap-y-3 text-sm sm:grid-cols-2">
                            <div><dt className="text-xs text-muted-foreground">Ângulo</dt><dd className="mt-0.5 text-foreground">{peca.angulo} · {peca.subangulo}</dd></div>
                            <div><dt className="text-xs text-muted-foreground">Momento do público</dt><dd className="mt-0.5 text-foreground">{estado ? estado.nome : 'Não informado'}</dd></div>
                            <div className="sm:col-span-2"><dt className="text-xs text-muted-foreground">Texto dentro da arte</dt><dd className="mt-0.5 text-foreground">{peca.headline_interna}{peca.complemento_interno ? ` · ${peca.complemento_interno}` : ''}{peca.cta_visual ? ` · ${peca.cta_visual}` : ''}</dd></div>
                            <div className="sm:col-span-2"><dt className="text-xs text-muted-foreground">Direção visual</dt><dd className="mt-0.5 text-foreground">{peca.direcao_visual}</dd></div>
                            {copy && <div className="sm:col-span-2"><dt className="text-xs text-muted-foreground">Texto do anúncio</dt><dd className="mt-0.5 text-foreground"><span className="font-medium">{copy.titulo}</span>. {copy.texto_principal}</dd></div>}
                          </dl>
                          <details className="mt-4 text-xs text-muted-foreground"><summary className="cursor-pointer font-medium hover:text-foreground">Dados e procedência</summary><p className="mt-2 font-mono text-[11px]">{peca.ref} · fatos: {peca.fato_refs.join(', ')}</p></details>
                        </div>
                        {!pecaAprovada && <Button type="button" variant="outline" size="sm" disabled={ocupado} onClick={() => aprovar('pecas', peca.ref, 'PONTUAL')}><Check className="h-4 w-4" aria-hidden />Aprovar para produção</Button>}
                      </div>
                    </li>
                  );
                })}
              </ul>
            </section>
          );
        })}

        <details className="studio-surface group">
          <summary className="cursor-pointer list-none"><div className="flex items-center justify-between gap-4"><div><h2 className="font-display text-lg font-semibold">Pedir ajustes</h2><p className="mt-1 text-sm text-muted-foreground">Refine apenas o que ainda não foi aprovado.</p></div><span className="text-sm font-medium text-primary group-open:hidden">Abrir</span></div></summary>
          <p className="mt-4 max-w-[70ch] text-sm text-muted-foreground">A próxima execução recebe este lote e o seu comentário. O que já foi aprovado fica preservado. Refinar não desfaz aprovação.</p>
          <div className="mt-4 grid gap-4 md:grid-cols-[1fr_auto]">
            <div className="space-y-1.5"><Label htmlFor="ac-feedback">O que mudar</Label><Textarea id="ac-feedback" rows={3} maxLength={4000} value={feedback} onChange={(event) => setFeedback(event.target.value)} /></div>
            <div className="space-y-1.5 md:w-56"><Label htmlFor="ac-escopo">Alcance</Label><Select value={escopo} onValueChange={(valor) => setEscopo(valor as EscopoFeedback)}><SelectTrigger id="ac-escopo"><SelectValue /></SelectTrigger><SelectContent>{ESCOPOS.map((item) => <SelectItem key={item.valor} value={item.valor}>{item.rotulo}</SelectItem>)}</SelectContent></Select><p className="text-xs text-muted-foreground">{ESCOPOS.find((item) => item.valor === escopo)?.ajuda}</p></div>
          </div>
          {erro && <p role="alert" className="mt-4 flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive"><AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />{erro}</p>}
          <Button type="button" className="mt-4" disabled={ocupado || feedback.trim().length < 3} onClick={() => onRefinar(feedback.trim(), escopo)}><RefreshCw className="h-4 w-4" aria-hidden />{ocupado ? 'Preparando ajustes…' : 'Refinar estratégia'}</Button>
        </details>

        <details className="rounded-lg border border-border bg-muted/20 p-4">
          <summary className="cursor-pointer text-sm font-semibold text-foreground">Validação técnica do lote</summary>
          <p className="mt-3 max-w-[70ch] text-sm text-muted-foreground">{saida.recibo.valido ? 'O lote passou nas contraprovas determinísticas de contrato do servidor: referências existem, fatos são citados, itens aprovados não mudaram e as peças têm diferenças materiais.' : 'Este lote não carrega validação de contrato.'}</p>
          <p className="mt-2 max-w-[70ch] text-sm text-muted-foreground">Isso não substitui a sua aprovação nem garante elegibilidade na Meta. A imagem ainda não existe.</p>
          {saida.recibo.codigos.length > 0 && <p className="mt-2 font-mono text-[11px] text-muted-foreground">{saida.recibo.codigos.join(' · ')}</p>}
        </details>
      </main>

      <aside className="studio-review-rail lg:sticky lg:top-6">
        <p className="kicker">Sua revisão</p>
        <div className="mt-3 flex items-end justify-between gap-3"><p aria-label={`${totalAprovado} de ${totalDePecas} peças aprovadas`} className="font-display text-3xl font-semibold tabular-nums">{totalAprovado}<span className="text-base font-medium text-muted-foreground">/{totalDePecas}</span></p><Chip tom={haPecaAprovada ? 'aprovado' : 'neutro'}>{haPecaAprovada ? 'Pode avançar' : 'Aguardando'}</Chip></div>
        <p className="mt-2 text-sm text-muted-foreground">{totalAprovado === 1 ? 'peça aprovada para produção' : 'peças aprovadas para produção'}</p>
        <div className="my-5 h-px bg-border" />
        <p className="text-sm font-medium text-foreground">Aprovação não gera imagens nem cobrança.</p>
        <p className="mt-1 text-sm leading-relaxed text-muted-foreground">Na Produção, você escolhe os formatos, confere a quantidade e autoriza o custo antes de chamar o motor.</p>
        <Button type="button" className="mt-5 w-full" disabled={!haPecaAprovada || ocupado} onClick={() => onContinuar?.()}>Continuar para produção<ArrowRight className="h-4 w-4" aria-hidden /></Button>
        {!haPecaAprovada && <p className="mt-2 text-center text-xs text-muted-foreground">Aprove ao menos uma peça para continuar.</p>}
      </aside>
    </div>
  );
}
