/**
 * Onde o operador escolhe o que virar imagem — e vê o preço antes do clique.
 *
 * ## A regra que este componente existe para cumprir
 *
 * "Mostrar N conceitos × M formatos = total de renders e eventuais bloqueios
 *  ANTES do clique; custo desconhecido é null."
 *
 * O plano é calculado NO SERVIDOR e só depois desenhado aqui. Um teto conferido
 * no browser não é um teto: quem manda o pedido pode não ser esta tela.
 *
 * ## Custo desconhecido não é zero
 *
 * Quando o servidor devolve `custo_estimado_usd: null`, a tela escreve "não
 * publicado", nunca "US$ 0,00". Zero é um preço, e um preço de zero ao lado de
 * um botão que gasta é a frase mais cara que esta página poderia dizer.
 */
import { useEffect, useMemo, useState } from 'react';
import { AlertCircle, ImageIcon, Lock, ShieldAlert } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';

import { FORMATOS_DO_MOTOR } from '../api';
import type { PecaCriativa, PlanoDeGeracao, SaidaDoAgente } from '../tipos';

export interface PainelDeProducaoProps {
  saida: SaidaDoAgente;
  /** Caminhos aprovados por uma pessoa. Só o que está aqui pode virar imagem. */
  aprovados: ReadonlySet<string>;
  plano: PlanoDeGeracao | null;
  planejando: boolean;
  gerando: boolean;
  erro?: string | null;
  onPlanejar: (creativeRefs: string[], formatIds: string[]) => void;
  onGerar: (creativeRefs: string[], formatIds: string[]) => void;
}

function moeda(v: number | null | undefined): string {
  if (v === null || v === undefined) return 'não publicado pelo motor';
  return v.toLocaleString('pt-BR', { style: 'currency', currency: 'USD' });
}

export function PainelDeProducao({
  saida,
  aprovados,
  plano,
  planejando,
  gerando,
  erro,
  onPlanejar,
  onGerar,
}: PainelDeProducaoProps) {
  const aprovadas = useMemo(
    () => saida.pecas.filter((p: PecaCriativa) => aprovados.has(`/pecas/${p.ref}`)),
    [saida.pecas, aprovados],
  );

  const [selecionadas, setSelecionadas] = useState<string[]>([]);
  const [formatos, setFormatos] = useState<string[]>(['1x1', '4x5', '9x16']);
  const [selecaoConferida, setSelecaoConferida] = useState<string | null>(null);
  const assinatura = JSON.stringify([selecionadas, formatos]);

  // Uma peça que perdeu a aprovação sai da seleção sozinha: manter selecionado
  // algo que não pode gerar deixaria o total mentindo sobre o que vai sair.
  useEffect(() => {
    setSelecionadas((atual) => atual.filter((ref) => aprovados.has(`/pecas/${ref}`)));
  }, [aprovados]);

  const podePedirPlano = selecionadas.length > 0 && formatos.length > 0;

  if (aprovadas.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-card p-6 shadow-card">
        <p className="flex items-center gap-2 text-sm font-medium text-foreground">
          <Lock className="h-4 w-4" aria-hidden />
          Nenhuma peça foi aprovada ainda.
        </p>
        <p className="mt-1 max-w-[70ch] text-sm text-muted-foreground">
          A imagem custa dinheiro, então só peça aprovada por uma pessoa entra na
          produção. O recibo de contrato do Assistente não substitui essa decisão.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <section className="rounded-lg border border-border bg-card p-4 shadow-card md:p-5">
        <h2 className="font-display text-lg font-semibold">Peças aprovadas</h2>
        <p className="mt-1 max-w-[70ch] text-sm text-muted-foreground">
          Escolha quais conceitos virar imagem. Cada conceito é gerado uma vez por
          formato — a mesma ideia composta para cada proporção, não a mesma imagem
          recortada em três.
        </p>

        <fieldset className="mt-4">
          <legend className="sr-only">Peças a produzir</legend>
          <ul className="space-y-2">
            {aprovadas.map((peca) => {
              const marcada = selecionadas.includes(peca.ref);
              return (
                <li key={peca.ref}>
                  <label className="flex cursor-pointer items-start gap-3 rounded-md border border-border bg-muted/20 p-3">
                    <input
                      type="checkbox"
                      className="mt-1 h-4 w-4 accent-primary"
                      checked={marcada}
                      onChange={() =>
                        setSelecionadas((atual) =>
                          atual.includes(peca.ref)
                            ? atual.filter((r) => r !== peca.ref)
                            : [...atual, peca.ref],
                        )
                      }
                    />
                    <span className="min-w-0">
                      <span className="block text-sm font-medium text-foreground">
                        {peca.hook}
                      </span>
                      <span className="mt-0.5 block text-xs text-muted-foreground">
                        {peca.direcao_visual}
                      </span>
                      <span className="mt-1 block font-mono text-[11px] text-muted-foreground">
                        {peca.ref}
                      </span>
                    </span>
                  </label>
                </li>
              );
            })}
          </ul>
        </fieldset>
      </section>

      <section className="rounded-lg border border-border bg-card p-4 shadow-card md:p-5">
        <h2 className="font-display text-lg font-semibold">Formatos</h2>
        <fieldset className="mt-3">
          <legend className="sr-only">Formatos a produzir</legend>
          <div className="grid gap-3 sm:grid-cols-3">
            {FORMATOS_DO_MOTOR.map((f) => (
              <label
                key={f.slot}
                className="flex cursor-pointer items-start gap-3 rounded-md border border-border bg-muted/20 p-3"
              >
                <input
                  type="checkbox"
                  className="mt-1 h-4 w-4 accent-primary"
                  checked={formatos.includes(f.slot)}
                  onChange={() =>
                    setFormatos((atual) =>
                      atual.includes(f.slot)
                        ? atual.filter((s) => s !== f.slot)
                        : [...atual, f.slot],
                    )
                  }
                />
                <span className="min-w-0">
                  <span className="block text-sm font-medium text-foreground">{f.rotulo}</span>
                  <span className="block text-xs tabular-nums text-muted-foreground">
                    {f.proporcao} · {f.largura}×{f.altura} px
                  </span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>

        <div className="mt-4">
          <Button
            type="button"
            variant="outline"
            disabled={!podePedirPlano || planejando}
            onClick={() => { setSelecaoConferida(assinatura); onPlanejar(selecionadas, formatos); }}
          >
            {planejando ? 'Conferindo…' : 'Conferir antes de gerar'}
          </Button>
          <p className="mt-2 text-xs text-muted-foreground">
            Conferir não gera nada: o servidor recalcula o total, o teto e o custo.
          </p>
        </div>
      </section>

      {plano && selecaoConferida === assinatura && (
        <section
          className="rounded-lg border border-border bg-muted/20 p-4"
          aria-live="polite"
        >
          <h2 className="text-sm font-semibold text-foreground">O que este clique vai produzir</h2>
          <dl className="mt-3 grid gap-3 sm:grid-cols-4">
            <div>
              <dt className="text-xs text-muted-foreground">Conceitos</dt>
              <dd className="tabular-nums text-lg font-semibold text-foreground">
                {plano.conceitos}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Formatos</dt>
              <dd className="tabular-nums text-lg font-semibold text-foreground">
                {plano.formatos}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Imagens</dt>
              <dd className="tabular-nums text-lg font-semibold text-foreground">
                {plano.total_de_renders}
                <span className="ml-1 text-xs font-normal text-muted-foreground">
                  de {plano.teto} no teto
                </span>
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Custo estimado</dt>
              <dd className="text-sm font-medium text-foreground">
                {moeda(plano.custo_estimado_usd)}
              </dd>
            </div>
          </dl>

          {plano.bloqueios.length > 0 && (
            <div className="mt-4 rounded-md border border-destructive/40 bg-destructive/5 p-3">
              <p className="flex items-center gap-2 text-sm font-medium text-destructive">
                <ShieldAlert className="h-4 w-4" aria-hidden />
                Este pedido não pode virar imagem ainda
              </p>
              <ul className="mt-2 space-y-1 text-sm text-foreground">
                {plano.bloqueios.map((b) => (
                  <li key={b.codigo}>{b.mensagem}</li>
                ))}
              </ul>
              <p className="mt-2 text-xs text-muted-foreground">
                Nada foi criado e nada foi cobrado.
              </p>
            </div>
          )}

          <p className="mt-4 text-xs text-muted-foreground">
            Gerar produz arquivos no seu acervo. Não cria campanha, não sobe mídia para a
            Meta e não chama nenhuma API de anúncios.
          </p>

          {erro && (
            <p
              role="alert"
              className="mt-3 flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive"
            >
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
              {erro}
            </p>
          )}

          <div className="mt-4">
            <Button
              type="button"
              disabled={!plano.pode_executar || gerando || planejando || !podePedirPlano}
              onClick={() => onGerar(selecionadas, formatos)}
            >
              <ImageIcon className="h-4 w-4" aria-hidden />
              {gerando
                ? 'Mandando produzir…'
                : `Gerar ${plano.total_de_renders} imagem(ns)`}
            </Button>
          </div>
        </section>
      )}
    </div>
  );
}
