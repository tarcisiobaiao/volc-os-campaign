/**
 * A AÇÃO de reauditar o destino ao vivo — as duas etapas, na tela.
 *
 * ## O que ela existe para impedir
 *
 * O recibo de escopo `live` é o único que a barreira 3 aceita, e nenhum caminho
 * de produção o emitia: o portão da publicação carimba o corpo que o motor
 * escreveu, e a página que o AdsBot visita é esse corpo dentro do tema do
 * WordPress. Sem este ato, nenhum destino fica elegível para campanha.
 *
 * ## Por que DUAS etapas, e por que a ordem não pode ser pulada
 *
 * Um portão que se autoaprova em silêncio não é portão.
 *
 *     provar (só lê)  →  a tela mostra veredito, diff, bloqueios COM DONO,
 *                        recibo PENDENTE e o hash da prova
 *                     →  confirmação HUMANA, vinculada àquele MESMO hash
 *                     →  confirmar (o backend re-lê, re-avalia e grava)
 *
 * O botão de confirmar nasce desabilitado e só habilita depois de uma prova
 * ELEGÍVEL — e carrega o hash dela. Prova reprovada não vira aprovação por
 * clique: a tela não é o lugar de contornar o portão.
 *
 * ## As duas regras deste arquivo
 *
 * **1. Nada é derivado aqui.** Quem lê a página e avalia é o backend, que tem o
 * HTML e as três leituras. A tradução mora em `lib/landing-policy/reauditoria.ts`.
 *
 * **2. Estado desconhecido nunca pinta verde.** Um desconhecido é uma
 * verificação exigida que não pôde ser concluída; ele reprova igual a um
 * bloqueio, e enfileirá-lo entre observações ensinaria o operador a tratá-lo
 * como ruído.
 *
 * ⚠️ Nem hash inteiro nem HTML: doze caracteres bastam para reconciliar com o
 * backend, e a evidência de cada achado já vem estrutural.
 */
import React from 'react';

import { Selo } from '@/components/landing-policy/Selo';
import { tomDaProntidao, type TomDaProntidao } from '@/lib/landing-policy/prontidao';
import {
  acaoDoDono,
  bloqueiosPorDono,
  curto,
  ehConflitoDeProva,
  estadoDaProva,
  etapaDaReauditoria,
  mensagemDoErro,
  podeConfirmar,
  PROXIMA_ACAO,
  ROTULO_DA_ETAPA,
  textoDoDiff,
  textoDoDono,
  type ClienteDeReauditoria,
  type ProvaDaReauditoria,
} from '@/lib/landing-policy/reauditoria';

const TOM: Record<TomDaProntidao, string> = {
  provado: 'border-success/40 bg-success/[0.08]',
  negado: 'border-destructive/40 bg-destructive/[0.07]',
  ignorado: 'border-border/70 bg-muted/40',
  ausente: 'border-border/50 bg-transparent',
};

function Linha({ rotulo, valor }: { rotulo: string; valor: React.ReactNode }) {
  return (
    <div>
      <dt className="kicker text-muted-foreground">{rotulo}</dt>
      <dd className="text-sm text-foreground">{valor}</dd>
    </div>
  );
}

export interface AcaoDeReauditoriaProps {
  runRowId: number;
  pageNumber: number;
  /** O transporte. Injetado — este componente não conhece a base do backend. */
  api: ClienteDeReauditoria;
  /** Chamado depois de uma gravação, para quem quiser recarregar o recibo. */
  aoGravar?: (gravado: boolean) => void;
  className?: string;
}

export const AcaoDeReauditoria: React.FC<AcaoDeReauditoriaProps> = ({
  runRowId,
  pageNumber,
  api,
  aoGravar,
  className,
}) => {
  const [prova, setProva] = React.useState<ProvaDaReauditoria | null>(null);
  const [lendo, setLendo] = React.useState(false);
  const [conflito, setConflito] = React.useState(false);
  const [erro, setErro] = React.useState<string | null>(null);
  const [confirmadaCom, setConfirmadaCom] = React.useState<string | null>(null);

  const etapa = etapaDaReauditoria({ prova, lendo, conflito, erro, confirmadaCom });
  const estado = estadoDaProva(prova);
  const habilitado = podeConfirmar(prova, etapa);

  async function provar() {
    setLendo(true);
    // ⚠️ O conflito e o erro são limpos AQUI, e não no sucesso. Uma prova nova
    // que falhasse deixando o conflito antigo na tela mostraria dois estados
    // contraditórios ao mesmo tempo.
    setConflito(false);
    setErro(null);
    try {
      const resposta = await api.provar(runRowId, pageNumber);
      setProva(resposta.prova);
      // ⚠️ E a confirmação anterior é ESQUECIDA: uma prova nova volta a pedir
      // confirmação. Manter o "confirmado" sobre uma leitura que ninguém
      // aprovou é exatamente o verde por ausência que este painel combate.
      setConfirmadaCom(null);
    } catch (falha) {
      setProva(null);
      setErro(mensagemDoErro(falha));
    } finally {
      setLendo(false);
    }
  }

  async function confirmar() {
    if (!prova || !habilitado) return;
    setLendo(true);
    setErro(null);
    try {
      const resposta = await api.confirmar(runRowId, pageNumber, prova.impressao_da_prova);
      setProva(resposta.prova);
      setConfirmadaCom(resposta.prova.impressao_da_prova);
      aoGravar?.(resposta.gravado);
    } catch (falha) {
      if (ehConflitoDeProva(falha)) {
        // A página mudou entre as duas etapas. A prova em tela descreve algo
        // que já não está no ar — mantê-la visível convidaria a clicar de novo.
        setProva(null);
        setConflito(true);
      } else {
        setErro(mensagemDoErro(falha));
      }
    } finally {
      setLendo(false);
    }
  }

  const tomDoTopo: TomDaProntidao =
    etapa === 'CONFIRMADO' ? 'provado'
      : etapa === 'REPROVADO' || etapa === 'CONFLITO' || etapa === 'ERRO' ? 'negado'
        : etapa === 'PROVADO' ? tomDaProntidao(estado)
          : 'ignorado';

  return (
    <section
      className={`mt-4 rounded-md border p-3 ${TOM[tomDoTopo]} ${className ?? ''}`}
      data-etapa={etapa}
      data-estado={estado}
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <h4 className="kicker">reauditoria ao vivo</h4>
        <span className="hairline hidden flex-1 sm:block" />
        <Selo palavra={ROTULO_DA_ETAPA[etapa]} descricao={PROXIMA_ACAO[etapa]} tom={tomDoTopo} />
      </div>

      <p className="mt-2 max-w-[74ch] text-xs leading-relaxed text-muted-foreground">
        {PROXIMA_ACAO[etapa]}
      </p>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={provar}
          disabled={lendo}
          data-acao="provar"
          className="rounded-md border border-border px-2.5 py-1.5 text-xs font-medium disabled:opacity-50"
        >
          {lendo ? 'lendo…' : prova ? 'ler de novo' : 'ler a página no ar'}
        </button>
        {/* ⚠️ O botão de confirmar CARREGA o hash da prova, e é o mesmo que o
            backend vai exigir. Ele nasce desabilitado e só habilita depois de
            uma prova elegível — confirmar sem prova é 422 lá, e aqui nem
            chega a sair. */}
        <button
          type="button"
          onClick={confirmar}
          disabled={!habilitado || lendo}
          data-acao="confirmar"
          data-impressao={prova?.impressao_da_prova ?? ''}
          className="rounded-md border border-border px-2.5 py-1.5 text-xs font-medium disabled:opacity-50"
        >
          confirmar e gravar o recibo ao vivo
        </button>
        {prova ? (
          <span className="tabular text-[11px] text-muted-foreground">
            prova {curto(prova.impressao_da_prova)}
          </span>
        ) : null}
      </div>

      {erro ? (
        <p className="mt-3 max-w-[74ch] text-xs leading-relaxed text-destructive">{erro}</p>
      ) : null}

      {prova ? (
        <>
          <dl className="mt-4 grid gap-3 border-t border-border pt-3 sm:grid-cols-2 lg:grid-cols-3">
            <Linha rotulo="veredito ao vivo" valor={prova.veredito} />
            <Linha
              rotulo="recibo pendente"
              valor={
                <span className="tabular text-xs">
                  escopo {String(prova.recibo_candidato?.fingerprint_scope ?? '—')} ·{' '}
                  {curto(String(prova.recibo_candidato?.content_fingerprint ?? ''))}
                </span>
              }
            />
            <Linha rotulo="lido em" valor={<span className="text-xs">{prova.lido_em}</span>} />
          </dl>

          {/* ⚠️ O recibo é PENDENTE até a confirmação. Chamá-lo de "recibo" sem
              o adjetivo faria a tela afirmar uma aprovação que ainda não
              existe em lugar nenhum. */}
          <p className="mt-2 max-w-[74ch] text-[11px] leading-snug text-muted-foreground">
            Este recibo ainda não está gravado. Ele passa a existir para a barreira de
            campanha quando você confirmar — e a confirmação re-lê a página antes de gravar.
          </p>

          <p className="mt-3 max-w-[74ch] text-xs leading-relaxed text-muted-foreground">
            {textoDoDiff(prova.diff_com_o_recibo_anterior)}
          </p>

          {prova.bloqueios.length > 0 && (
            <section className="mt-4">
              <h5 className="kicker text-muted-foreground">bloqueios, por dono do conserto</h5>
              {bloqueiosPorDono(prova.bloqueios).map(({ dono, itens }) => (
                <div key={dono} className="mt-2">
                  <p className="text-[11px] font-medium">{textoDoDono(dono)}</p>
                  {acaoDoDono(dono) ? (
                    <p className="mt-0.5 max-w-[74ch] text-[11px] leading-snug text-muted-foreground">
                      {acaoDoDono(dono)}
                    </p>
                  ) : null}
                  <ul className="mt-1.5 space-y-2">
                    {itens.map((b, i) => (
                      <li
                        key={`${b.code}-${i}`}
                        className={`rounded-md border px-2.5 py-2 ${TOM.negado}`}
                        data-codigo={b.code}
                        data-dono={b.owner}
                      >
                        <p className="tabular text-[11px] font-medium tracking-tight">{b.code}</p>
                        <p className="mt-0.5 max-w-[74ch] text-xs leading-relaxed text-muted-foreground">
                          {b.message}
                        </p>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </section>
          )}

          {/* ⚠️ Seção PRÓPRIA, e não a lista de avisos: um desconhecido reprova
              igual a um bloqueio, e ele é o que sobra quando a página está
              limpa e ainda assim não fica elegível. */}
          {prova.desconhecidos.length > 0 && (
            <section className="mt-4">
              <h5 className="kicker text-muted-foreground">
                verificações que não puderam ser concluídas
              </h5>
              <ul className="mt-2 space-y-2">
                {prova.desconhecidos.map((d, i) => (
                  <li
                    key={`${d.verificacao}-${i}`}
                    className={`rounded-md border px-2.5 py-2 ${TOM.ignorado}`}
                  >
                    <p className="tabular text-[11px] font-medium tracking-tight">
                      {d.verificacao}
                    </p>
                    <p className="mt-0.5 max-w-[74ch] text-xs leading-relaxed text-muted-foreground">
                      {d.motivo}
                    </p>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {prova.inventario_de_links.length > 0 && (
            <p className="mt-3 max-w-[74ch] text-[11px] leading-snug text-muted-foreground">
              {prova.inventario_de_links.length} link(is) no inventário desta leitura.
              O texto das âncoras não vem nesta resposta: ele é conteúdo da página.
            </p>
          )}
        </>
      ) : null}
    </section>
  );
};
