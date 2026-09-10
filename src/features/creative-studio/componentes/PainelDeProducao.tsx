/**
 * Onde o operador escolhe o que virar imagem — e vê o que o clique faz.
 *
 * ## As regras que este componente existe para cumprir
 *
 * "Mostrar N conceitos × M formatos = total de renders e eventuais bloqueios
 *  ANTES do clique; custo desconhecido é null."
 *
 * O plano é calculado NO SERVIDOR e só depois desenhado aqui. Um teto conferido
 * no browser não é um teto: quem manda o pedido pode não ser esta tela.
 *
 * ## Custo desconhecido não é zero — e com o gpt-image-2 é a regra
 *
 * Quando o servidor devolve `custo_estimado_usd: null`, a tela escreve
 * "estimativa indisponível", nunca "US$ 0,00". Zero é um preço, e um preço de
 * zero ao lado de um botão que gasta é a frase mais cara que esta página
 * poderia dizer.
 *
 * O `gpt-image-2` transforma isso em caso NORMAL: ele é cobrado por token e a
 * OpenAI não publica dólar por imagem. Por isso, quando não há estimativa, o
 * campo de teto some — ele não teria contra o que ser conferido — e no lugar
 * dele entra um consentimento explícito de gastar sem estimativa. Antes, um
 * teto digitado nesse cenário era ignorado em silêncio.
 *
 * ## Três erros que ficavam invisíveis
 *
 * O erro da conferência era renderizado DENTRO do bloco do plano — que é
 * justamente o que não existe quando ela falha. Agora ele mora acima, fora de
 * qualquer bloco condicional. E a seleção de formatos herda a do briefing em
 * vez de marcar todos: o "até N imagens" prometido na entrada não pode triplicar
 * no ato que gasta.
 */
import { useEffect, useMemo, useState } from 'react';
import {
  AlertCircle,
  Camera,
  Check,
  ImageIcon,
  Lock,
  ShieldAlert,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';

import type {
  Anexo,
  Capacidades,
  PecaCriativa,
  PlanoDeGeracao,
  SaidaDoAgente,
} from '../tipos';
import { SeletorDeFormatos } from './SeletorDeFormatos';
import { ProgressoDeGeracao } from './ProgressoDeGeracao';

export interface PainelDeProducaoProps {
  saida: SaidaDoAgente;
  /** Caminhos aprovados por uma pessoa. Só o que está aqui pode virar imagem. */
  aprovados: ReadonlySet<string>;
  capacidades: Capacidades | null;
  /** Os formatos que o operador escolheu no briefing. A produção herda, não reinventa. */
  formatosDoBriefing: readonly string[];
  anexo: Anexo | null;
  modoDeComposicao: string;
  plano: PlanoDeGeracao | null;
  planejando: boolean;
  gerando: boolean;
  erro?: string | null;
  onPlanejar: (creativeRefs: string[], formatIds: string[]) => void;
  onGerar: (
    creativeRefs: string[],
    formatIds: string[],
    tetoUsd: number | null,
    aceitoSemEstimativa: boolean,
  ) => void;
}

function moeda(v: number | null | undefined): string {
  if (v === null || v === undefined) return 'estimativa indisponível';
  return v.toLocaleString('pt-BR', { style: 'currency', currency: 'USD' });
}

/** Teto sugerido: a estimativa arredondada PARA CIMA, nunca para baixo.
 *
 * Arredondar para baixo produziria um teto abaixo do próprio número que a tela
 * acabou de mostrar, e o servidor recusaria o clique que ele mesmo sugeriu. */
function tetoSugerido(estimado: number | null): string {
  if (estimado === null) return '';
  return (Math.ceil(estimado * 100) / 100).toFixed(2);
}

export function PainelDeProducao({
  saida,
  aprovados,
  capacidades,
  formatosDoBriefing,
  anexo,
  modoDeComposicao,
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

  const catalogo = capacidades?.formatos ?? [];
  const [selecionadas, setSelecionadas] = useState<string[]>([]);

  // ⚠️ A produção HERDA os formatos do briefing. Antes ela começava com três
  // marcados, ignorando a escolha da entrada: quem pediu um formato e leu "até
  // 4 imagens" chegava aqui com 12 no total, e o número que ele autorizava não
  // era o número que tinha lido.
  const [formatos, setFormatos] = useState<string[]>([]);
  useEffect(() => {
    const validos = formatosDoBriefing.filter((s) =>
      catalogo.some((f) => f.slot === s),
    );
    setFormatos(validos.length > 0 ? [...validos] : catalogo.slice(0, 1).map((f) => f.slot));
    // A dependência é o CONTEÚDO, e não o array: a página remonta a lista a
    // cada render e uma dependência por referência re-executaria sem parar.
  }, [formatosDoBriefing.join(','), catalogo.map((f) => f.slot).join(',')]);

  const [selecaoConferida, setSelecaoConferida] = useState<string | null>(null);
  const assinatura = JSON.stringify([selecionadas, formatos, anexo?.anexo_ref ?? null, modoDeComposicao]);

  // ── A autorização de gasto ────────────────────────────────────────────────
  const [teto, setTeto] = useState<string>('');
  const [autorizado, setAutorizado] = useState(false);
  const [aceitoSemEstimativa, setAceitoSemEstimativa] = useState(false);

  // Qualquer mudança de plano ou de seleção derruba a confirmação. Autorizar
  // seis imagens e gerar nove porque a caixa continuou marcada é exatamente o
  // gasto sem decisão que esta tela existe para impedir.
  useEffect(() => {
    setAutorizado(false);
    setAceitoSemEstimativa(false);
  }, [assinatura, plano, gerando]);

  useEffect(() => {
    setTeto(tetoSugerido(plano?.custo_estimado_usd ?? null));
  }, [plano]);

  const tetoNumero = teto.trim() === '' ? null : Number(teto.replace(',', '.'));
  const tetoValido = tetoNumero === null || (Number.isFinite(tetoNumero) && tetoNumero >= 0);

  // Uma peça que perdeu a aprovação sai da seleção sozinha: manter selecionado
  // algo que não pode gerar deixaria o total mentindo sobre o que vai sair.
  useEffect(() => {
    setSelecionadas((atual) => atual.filter((ref) => aprovados.has(`/pecas/${ref}`)));
  }, [aprovados]);

  const podePedirPlano = selecionadas.length > 0 && formatos.length > 0;
  const semEstimativa = plano ? plano.custo_tem_estimativa === false : false;
  const consentimentoDeCusto = !semEstimativa || aceitoSemEstimativa;
  const totalPrevisto = selecionadas.length * formatos.length;

  // O formulário sai de cena enquanto o pedido aguarda resposta. O plano
  // recebido aqui é o retrato autorizado, preservado pela página até o fim.
  if (gerando) return <ProgressoDeGeracao plano={plano} />;

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
      {/* ⚠️ O erro mora AQUI, fora de qualquer bloco condicional. Antes ele era
          renderizado dentro do bloco do plano — que é justamente o que não
          existe quando a conferência falha: o operador clicava, nada acontecia,
          e nenhuma mensagem aparecia. */}
      {erro && (
        <p
          role="alert"
          className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          {erro}
        </p>
      )}

      <section className="rounded-lg border border-border bg-card p-4 shadow-card md:p-5">
        <h2 className="font-display text-lg font-semibold">Peças aprovadas</h2>
        <p className="mt-1 max-w-[70ch] text-sm text-muted-foreground">
          Escolha quais conceitos virar imagem. Cada conceito é composto uma vez por
          formato, e não recortado de uma imagem só.
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
        <SeletorDeFormatos
          formatos={catalogo}
          selecionados={formatos}
          onChange={setFormatos}
          carregando={capacidades === null}
        />

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Button
            type="button"
            variant="outline"
            disabled={!podePedirPlano || planejando}
            onClick={() => {
              setSelecaoConferida(assinatura);
              onPlanejar(selecionadas, formatos);
            }}
          >
            {planejando ? 'Conferindo…' : 'Conferir antes de gerar'}
          </Button>
          <p className="text-xs tabular-nums text-muted-foreground">
            {selecionadas.length} peça(s) × {formatos.length} formato(s) ={' '}
            <span className="font-medium text-foreground">{totalPrevisto}</span> imagem(ns)
          </p>
        </div>
        <p className="mt-2 text-xs text-muted-foreground">
          Conferir não gera nada: o servidor recalcula o total, o teto e o custo.
        </p>
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

          <dl className="mt-4 grid gap-3 border-t border-border pt-3 text-xs sm:grid-cols-3">
            <div>
              <dt className="text-muted-foreground">Modelo</dt>
              <dd className="mt-0.5 font-mono text-foreground">
                {plano.modelo_de_imagem ?? 'nenhum motor configurado neste servidor'}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Qualidade</dt>
              <dd className="mt-0.5 font-mono text-foreground">
                {plano.qualidade_de_imagem ?? 'não declarada'}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Uso da imagem anexada</dt>
              <dd className="mt-0.5 flex items-center gap-1.5 text-foreground">
                {anexo ? (
                  <>
                    <Camera className="h-3.5 w-3.5" aria-hidden />
                    {capacidades?.modos_de_composicao.find(
                      (m) => m.id === plano.modo_de_composicao,
                    )?.rotulo ?? plano.modo_de_composicao}
                  </>
                ) : (
                  'sem fotografia'
                )}
              </dd>
            </div>
          </dl>

          <p className="mt-3 max-w-[70ch] text-xs text-muted-foreground">
            {semEstimativa
              ? 'Este motor é cobrado por token e não publica preço por imagem, então não há estimativa a mostrar. O limite que o servidor impõe com exatidão é a quantidade de imagens acima.'
              : 'Este valor é uma ESTIMATIVA de tabela de referência, não uma fatura: o provedor cobra por token e não devolve o preço da chamada. O limite exato que o servidor impõe é a quantidade de imagens.'}
          </p>

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

          {plano.briefings.length > 0 && (
            <details className="mt-4 rounded-md border border-border bg-card p-3">
              <summary className="cursor-pointer text-sm font-medium text-foreground">
                Ver o texto que vai para dentro da arte
              </summary>
              <p className="mt-2 max-w-[70ch] text-xs text-muted-foreground">
                É isto que os pixels vão carregar. O texto do anúncio é outro e não
                entra na imagem.
              </p>
              <ul className="mt-3 space-y-2">
                {plano.briefings.map((b) => (
                  <li
                    key={`${b.creative_ref}-${b.formato_slot}`}
                    className="rounded border border-border bg-muted/20 p-2 text-xs"
                  >
                    <span className="font-medium text-foreground">
                      {b.formato_slot}
                    </span>
                    <span className="mt-0.5 block text-foreground">{b.texto_na_arte}</span>
                  </li>
                ))}
              </ul>
            </details>
          )}

          <p className="mt-4 text-xs text-muted-foreground">
            Gerar produz arquivos no seu acervo. Não cria campanha, não sobe mídia para a
            Meta e não chama nenhuma API de anúncios.
          </p>

          {plano.pode_executar && (
            <div className="mt-4 rounded-md border border-border bg-card p-3">
              {semEstimativa ? (
                <label className="flex cursor-pointer items-start gap-2">
                  <input
                    type="checkbox"
                    className="mt-0.5 h-4 w-4 accent-primary"
                    checked={aceitoSemEstimativa}
                    onChange={(e) => setAceitoSemEstimativa(e.target.checked)}
                  />
                  <span className="text-sm text-foreground">
                    Aceito produzir sem estimativa de custo. O limite desta operação
                    é a quantidade de {plano.total_de_renders} imagem(ns).
                  </span>
                </label>
              ) : (
                <div className="flex flex-wrap items-end gap-3">
                  <div className="min-w-[9rem]">
                    <Label htmlFor="teto-de-custo" className="text-xs">
                      Teto autorizado (US$)
                    </Label>
                    <input
                      id="teto-de-custo"
                      type="text"
                      inputMode="decimal"
                      value={teto}
                      onChange={(e) => setTeto(e.target.value)}
                      placeholder="sem teto"
                      aria-invalid={!tetoValido}
                      className="mt-1 w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm tabular-nums"
                    />
                  </div>
                  <p className="flex-1 text-xs text-muted-foreground">
                    Em branco significa sem teto financeiro declarado. A quantidade de
                    imagens continua limitando o gasto.
                  </p>
                </div>
              )}

              <label className="mt-3 flex cursor-pointer items-start gap-2">
                <input
                  type="checkbox"
                  className="mt-0.5 h-4 w-4 accent-primary"
                  checked={autorizado}
                  disabled={!tetoValido || !consentimentoDeCusto}
                  onChange={(e) => setAutorizado(e.target.checked)}
                />
                <span className="text-sm text-foreground">
                  Autorizo produzir {plano.total_de_renders} imagem(ns) com{' '}
                  <span className="font-mono text-xs">{plano.modelo_de_imagem}</span>
                  {plano.qualidade_de_imagem ? (
                    <>
                      {' '}em qualidade{' '}
                      <span className="font-mono text-xs">{plano.qualidade_de_imagem}</span>
                    </>
                  ) : null}
                  {semEstimativa
                    ? ', sem estimativa de custo'
                    : tetoNumero !== null
                      ? `, até US$ ${tetoNumero.toFixed(2)}`
                      : ', sem teto declarado'}
                  .
                </span>
              </label>
              {!tetoValido && (
                <p role="alert" className="mt-2 text-xs text-destructive">
                  O teto precisa ser um número em dólares, ou ficar em branco.
                </p>
              )}
              {semEstimativa && !aceitoSemEstimativa && (
                <p className="mt-2 text-xs text-muted-foreground">
                  Confirme o aceite acima para liberar a autorização.
                </p>
              )}
            </div>
          )}

          <div className="mt-4">
            <Button
              type="button"
              disabled={
                !plano.pode_executar ||
                gerando ||
                planejando ||
                !podePedirPlano ||
                !autorizado ||
                !tetoValido ||
                !consentimentoDeCusto
              }
              onClick={() =>
                onGerar(selecionadas, formatos, semEstimativa ? null : tetoNumero, aceitoSemEstimativa)
              }
            >
              <ImageIcon className="h-4 w-4" aria-hidden />
              {`Gerar ${plano.total_de_renders} imagem(ns)`}
            </Button>
            {!autorizado && plano.pode_executar && (
              <p className="mt-2 flex items-center gap-1.5 text-xs text-muted-foreground">
                <Check className="h-3.5 w-3.5" aria-hidden />
                Confirme a autorização acima para liberar o botão.
              </p>
            )}
          </div>
        </section>
      )}
    </div>
  );
}
