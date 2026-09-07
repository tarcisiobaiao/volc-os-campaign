/**
 * A estratégia proposta, e o que dela já foi decidido por uma pessoa.
 *
 * ## Proposta não é fato aprovado
 *
 * Tudo que o modelo escreveu chega aqui como PROPOSTA. O `recibo` que vem do
 * servidor diz apenas que o lote passou nas contraprovas determinísticas de
 * contrato — não que um humano aprovou, e muito menos que a Meta aceitaria a
 * peça. São três fatos diferentes e a tela os mantém separados, porque juntá-los
 * é como uma validação de schema vira "pode gastar".
 *
 * ## Aprovar é por ref
 *
 * O caminho da decisão endereça o elemento pelo `ref` dele, nunca pela posição.
 * A posição muda a cada geração, e um congelamento por índice compararia, na run
 * seguinte, um objeto diferente do que a pessoa leu.
 */
import { useMemo, useState } from 'react';
import { AlertCircle, Check, CircleSlash, Lock, RefreshCw } from 'lucide-react';

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
  /** Caminhos já aprovados, para a tela mostrar o que está congelado. */
  aprovados: ReadonlySet<string>;
  ocupado: boolean;
  erro?: string | null;
  onDecidir: (pedido: PedidoDeDecisao) => void;
  onRefinar: (feedback: string, escopo: EscopoFeedback) => void;
}

const ESCOPOS: { valor: EscopoFeedback; rotulo: string; ajuda: string }[] = [
  { valor: 'PONTUAL', rotulo: 'Só este item', ajuda: 'Vale para o elemento escolhido.' },
  { valor: 'GRUPO', rotulo: 'O grupo', ajuda: 'Vale para o grupo estratégico inteiro.' },
  { valor: 'PROJETO', rotulo: 'Esta operação', ajuda: 'Vale para todo o lote desta operação.' },
];

function Chip({
  tom,
  children,
}: {
  tom: 'neutro' | 'aprovado' | 'proposta';
  children: React.ReactNode;
}) {
  const estilo =
    tom === 'aprovado'
      ? 'bg-success/10 text-success'
      : tom === 'proposta'
        ? 'bg-muted/50 text-foreground'
        : 'bg-muted/50 text-muted-foreground';
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
  onDecidir,
  onRefinar,
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

  const copyPorRef = useMemo(
    () => new Map(saida.copies_compartilhadas.map((c) => [c.ref, c])),
    [saida.copies_compartilhadas],
  );
  const estadoPorRef = useMemo(
    () => new Map(saida.jornada.map((e) => [e.ref, e])),
    [saida.jornada],
  );

  function aprovar(colecao: string, ref: string, escopoDaDecisao: EscopoFeedback) {
    onDecidir({
      run_ref: runRef,
      decisao: 'APROVADO',
      escopo: escopoDaDecisao,
      caminho: caminhoDe(colecao, ref),
    });
  }

  return (
    <div className="space-y-6">
      {/* ── Diagnóstico ────────────────────────────────────────────────── */}
      <section className="rounded-lg border border-border bg-card p-4 shadow-card md:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <h2 className="font-display text-lg font-semibold">Diagnóstico</h2>
          <Chip tom="proposta">Proposta do Assistente</Chip>
        </div>
        <dl className="mt-4 grid gap-4 md:grid-cols-3">
          <div>
            <dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Oferta real
            </dt>
            <dd className="mt-1 text-sm text-foreground">{saida.diagnostico.oferta_real}</dd>
          </div>
          <div>
            <dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Promessa máxima
            </dt>
            <dd className="mt-1 text-sm text-foreground">
              {saida.diagnostico.promessa_maxima}
            </dd>
          </div>
          <div>
            <dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Tensão central
            </dt>
            <dd className="mt-1 text-sm text-foreground">{saida.diagnostico.tensao_central}</dd>
          </div>
        </dl>

        {saida.diagnostico.desconhecidos.length > 0 && (
          <div className="mt-4 rounded-md border border-warning/40 bg-warning/5 p-3">
            <p className="flex items-center gap-2 text-sm font-medium text-warning">
              <CircleSlash className="h-4 w-4" aria-hidden />
              O que o Assistente declarou não saber
            </p>
            <ul className="mt-2 list-inside list-disc space-y-1 text-sm text-foreground">
              {saida.diagnostico.desconhecidos.map((d) => (
                <li key={d}>{d}</li>
              ))}
            </ul>
            <p className="mt-2 text-xs text-muted-foreground">
              Isto é ausência declarada, não um problema: falta de prova vira registro em
              vez de afirmação inventada.
            </p>
          </div>
        )}
      </section>

      {/* ── Grupos e peças ─────────────────────────────────────────────── */}
      {saida.grupos.map((grupo) => {
        const caminhoDoGrupo = caminhoDe('grupos', grupo.ref);
        const grupoAprovado = aprovados.has(caminhoDoGrupo);
        return (
          <section
            key={grupo.ref}
            className="rounded-lg border border-border bg-card p-4 shadow-card md:p-5"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="font-display text-lg font-semibold">{grupo.nome}</h2>
                  {grupoAprovado ? (
                    <Chip tom="aprovado">
                      <Lock className="h-3 w-3" aria-hidden />
                      Aprovado e congelado
                    </Chip>
                  ) : (
                    <Chip tom="proposta">Proposta</Chip>
                  )}
                </div>
                <p className="mt-1 max-w-[70ch] text-sm text-muted-foreground">
                  {grupo.territorio}
                </p>
                <p className="mt-1 max-w-[70ch] text-sm text-muted-foreground">
                  <span className="font-medium text-foreground">Diferença material:</span>{' '}
                  {grupo.diferenca_material}
                </p>
                <p className="mt-1 font-mono text-[11px] text-muted-foreground">{grupo.ref}</p>
              </div>
              {!grupoAprovado && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={ocupado}
                  onClick={() => aprovar('grupos', grupo.ref, 'GRUPO')}
                >
                  <Check className="h-4 w-4" aria-hidden />
                  Aprovar grupo
                </Button>
              )}
            </div>

            <ul className="mt-4 space-y-3">
              {(pecasPorGrupo.get(grupo.ref) ?? []).map((peca) => {
                const copy = copyPorRef.get(peca.shared_copy_ref);
                const estado = estadoPorRef.get(peca.estado_mental_ref);
                const caminhoDaPeca = caminhoDe('pecas', peca.ref);
                const pecaAprovada = aprovados.has(caminhoDaPeca);
                return (
                  <li
                    key={peca.ref}
                    className="rounded-md border border-border bg-muted/20 p-3"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="text-sm font-semibold text-foreground">{peca.hook}</p>
                          {pecaAprovada && (
                            <Chip tom="aprovado">
                              <Lock className="h-3 w-3" aria-hidden />
                              Congelada
                            </Chip>
                          )}
                          <Chip tom="neutro">{peca.formato}</Chip>
                        </div>

                        <dl className="mt-2 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
                          <div>
                            <dt className="text-xs text-muted-foreground">Ângulo</dt>
                            <dd className="text-foreground">
                              {peca.angulo} · {peca.subangulo}
                            </dd>
                          </div>
                          <div>
                            <dt className="text-xs text-muted-foreground">Estado mental</dt>
                            <dd className="text-foreground">
                              {estado ? estado.nome : peca.estado_mental_ref}
                            </dd>
                          </div>
                          <div className="sm:col-span-2">
                            <dt className="text-xs text-muted-foreground">
                              Texto interno da arte
                            </dt>
                            <dd className="text-foreground">
                              {peca.headline_interna}
                              {peca.complemento_interno ? ` · ${peca.complemento_interno}` : ''}
                              {peca.cta_visual ? ` · ${peca.cta_visual}` : ''}
                            </dd>
                          </div>
                          <div className="sm:col-span-2">
                            <dt className="text-xs text-muted-foreground">Direção visual</dt>
                            <dd className="text-foreground">{peca.direcao_visual}</dd>
                          </div>
                          {copy && (
                            <div className="sm:col-span-2">
                              <dt className="text-xs text-muted-foreground">
                                Copy da campanha (fora da imagem)
                              </dt>
                              <dd className="text-foreground">
                                <span className="font-medium">{copy.titulo}</span> —{' '}
                                {copy.texto_principal}
                              </dd>
                            </div>
                          )}
                        </dl>

                        <p className="mt-2 font-mono text-[11px] text-muted-foreground">
                          {peca.ref} · fatos: {peca.fato_refs.join(', ')}
                        </p>
                      </div>

                      {!pecaAprovada && (
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          disabled={ocupado}
                          onClick={() => aprovar('pecas', peca.ref, 'PONTUAL')}
                        >
                          <Check className="h-4 w-4" aria-hidden />
                          Aprovar peça
                        </Button>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          </section>
        );
      })}

      {/* ── Refinar ────────────────────────────────────────────────────── */}
      <section className="rounded-lg border border-border bg-card p-4 shadow-card md:p-5">
        <h2 className="font-display text-lg font-semibold">Refinar</h2>
        <p className="mt-1 max-w-[70ch] text-sm text-muted-foreground">
          A próxima run recebe este lote inteiro e o seu comentário. O que você já aprovou
          fica congelado e volta literalmente igual — refinar não desfaz aprovação.
        </p>

        <div className="mt-4 grid gap-4 md:grid-cols-[1fr_auto]">
          <div className="space-y-1.5">
            <Label htmlFor="ac-feedback">O que mudar</Label>
            <Textarea
              id="ac-feedback"
              rows={3}
              maxLength={4000}
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
            />
          </div>
          <div className="space-y-1.5 md:w-56">
            <Label htmlFor="ac-escopo">Alcance</Label>
            <Select value={escopo} onValueChange={(v) => setEscopo(v as EscopoFeedback)}>
              <SelectTrigger id="ac-escopo">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ESCOPOS.map((e) => (
                  <SelectItem key={e.valor} value={e.valor}>
                    {e.rotulo}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              {ESCOPOS.find((e) => e.valor === escopo)?.ajuda}
            </p>
          </div>
        </div>

        {erro && (
          <p
            role="alert"
            className="mt-4 flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive"
          >
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            {erro}
          </p>
        )}

        <div className="mt-4">
          <Button
            type="button"
            disabled={ocupado || feedback.trim().length < 3}
            onClick={() => onRefinar(feedback.trim(), escopo)}
          >
            <RefreshCw className="h-4 w-4" aria-hidden />
            {ocupado ? 'Enfileirando…' : 'Refinar estratégia'}
          </Button>
        </div>
      </section>

      {/* ── Recibo, dito pelo que ele é ────────────────────────────────── */}
      <section className="rounded-lg border border-border bg-muted/20 p-4">
        <h2 className="text-sm font-semibold text-foreground">O que este recibo prova</h2>
        <p className="mt-1 max-w-[70ch] text-sm text-muted-foreground">
          {saida.recibo.valido
            ? 'O lote passou nas contraprovas determinísticas de contrato do servidor: refs existem, fatos são citados, elementos aprovados não mudaram e as peças têm diferença material entre si.'
            : 'Este lote não carrega recibo de contrato válido.'}
        </p>
        <p className="mt-2 max-w-[70ch] text-sm text-muted-foreground">
          Ele <span className="font-medium text-foreground">não</span> é aprovação humana e{' '}
          <span className="font-medium text-foreground">não</span> é elegibilidade de mídia
          paga na Meta. Aprovar a estratégia também não aprova pixel nenhum: a imagem ainda
          não existe.
        </p>
        {saida.recibo.codigos.length > 0 && (
          <p className="mt-2 font-mono text-[11px] text-muted-foreground">
            {saida.recibo.codigos.join(' · ')}
          </p>
        )}
      </section>
    </div>
  );
}
