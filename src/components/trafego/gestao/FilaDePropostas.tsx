/**
 * A fila de propostas da conta, com o diff gravado e o gesto que cada linha pede.
 *
 * O que esta tela garante:
 *  - o diff que aparece é o que vai como `diff_apresentado` (sem retoque);
 *  - aprovar/recusar e aplicar/reverter só aparecem para quem o servidor
 *    deixaria (`permissoesDe`); para o admin com a escrita fechada, o gesto
 *    aparece fechado com o motivo, e não some;
 *  - recusar e reverter exigem motivo; aplicar pede confirmação;
 *  - desfecho e erro ficam na própria linha, com a frase humana do código.
 */
import React from 'react';
import { RefreshCw } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { SeloDeProposta } from '@/components/sistema/SeloDeProposta';
import { cn } from '@/lib/utils';
import { horaExata } from '@/components/trafego/inventario/formato';
import { ROTULO_DO_TIPO } from '@/lib/trafego/gestao/acoes';
import { diffApresentado, linhasDoDiff } from '@/lib/trafego/gestao/diff';
import { detalheDoErro, erroLegivel } from '@/lib/trafego/gestao/erros';
import {
  DESFECHO_LEGIVEL,
  ESTADO_LEGIVEL,
  confereLegivel,
  ofertaDaLinha,
  seloDoLedger,
  textoSemSelo,
  type GestoDaFila,
  type Permissoes,
} from '@/lib/trafego/gestao/fila';
import {
  useAplicar,
  useAprovar,
  useRecusar,
  useReverter,
  useVerificar,
} from '@/hooks/useGestaoDeCampanha';
import type { PropostaDoPainel, TipoDeAcao } from '@/types/gestao';

import { AntesDepois, AvisoDeErro, classeDeEntrada } from './partes';

export interface FilaDePropostasProps {
  customerId: string;
  propostas: PropostaDoPainel[];
  permissoes: Permissoes;
  carregando?: boolean;
  erro?: unknown;
  aoRecarregar?: () => void;
}

export const FilaDePropostas: React.FC<FilaDePropostasProps> = ({
  customerId,
  propostas,
  permissoes,
  carregando,
  erro,
  aoRecarregar,
}) => (
  <section aria-labelledby="fila-titulo" className="mt-6">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h3 id="fila-titulo" className="font-display text-[15px] font-semibold">
        Fila de propostas
      </h3>
      {aoRecarregar && (
        <Button type="button" variant="ghost" size="sm" onClick={aoRecarregar}>
          <RefreshCw aria-hidden /> recarregar fila
        </Button>
      )}
    </div>
    {carregando ? (
      <p className="mt-2 text-[12px] text-muted-foreground" role="status">
        lendo a fila no ledger
      </p>
    ) : erro ? (
      <AvisoDeErro className="mt-2" erro={erroLegivel(erro)} />
    ) : propostas.length === 0 ? (
      <p className="mt-2 text-[12px] text-muted-foreground" role="status">
        Nenhuma proposta registrada para esta campanha.
      </p>
    ) : (
      <ul className="mt-2 border-t border-border" role="list" aria-label="propostas">
        {propostas.map((p) => (
          <LinhaDaFila key={p.proposta_id} customerId={customerId} proposta={p} permissoes={permissoes} />
        ))}
      </ul>
    )}
  </section>
);

type Abertura = null | 'aprovar' | 'recusar' | 'aplicar' | 'reverter';

const ROTULO_DO_GESTO: Record<GestoDaFila, string> = {
  aprovar: 'Aprovar',
  recusar: 'Recusar',
  aplicar: 'Aplicar no Google',
  verificar: 'Verificar na conta',
  reverter: 'Reverter',
};

export const LinhaDaFila: React.FC<{
  customerId: string;
  proposta: PropostaDoPainel;
  permissoes: Permissoes;
}> = ({ customerId, proposta: p, permissoes }) => {
  const [aberto, setAberto] = React.useState<Abertura>(null);
  const [motivo, setMotivo] = React.useState('');
  const [faltaMotivo, setFaltaMotivo] = React.useState(false);

  const aprovar = useAprovar(customerId);
  const recusar = useRecusar(customerId);
  const aplicar = useAplicar(customerId);
  const verificar = useVerificar(customerId);
  const reverter = useReverter(customerId);

  const oferta = ofertaDaLinha(p, permissoes);
  const linhas = linhasDoDiff(p);
  const ehRecomendacao = String(p.operacao).startsWith('recomendacao.');
  const rotulo = ROTULO_DO_TIPO[p.operacao as TipoDeAcao] ?? p.operacao;
  const ocupado =
    aprovar.isPending || recusar.isPending || aplicar.isPending || verificar.isPending || reverter.isPending;

  const ultimoErro = aprovar.error ?? recusar.error ?? aplicar.error ?? verificar.error ?? reverter.error;

  const abrir = (g: Abertura) => {
    setAberto(g);
    setMotivo('');
    setFaltaMotivo(false);
  };

  const confirmar = () => {
    const m = motivo.trim();
    if ((aberto === 'recusar' || aberto === 'reverter') && !m) {
      setFaltaMotivo(true);
      return;
    }
    if (aberto === 'aprovar') {
      aprovar.mutate({
        propostaId: p.proposta_id,
        pedido: { diff_apresentado: diffApresentado(p), ...(m ? { motivo: m } : {}) },
      });
    } else if (aberto === 'recusar') {
      recusar.mutate({ propostaId: p.proposta_id, pedido: { motivo: m, diff_apresentado: diffApresentado(p) } });
    } else if (aberto === 'aplicar') {
      aplicar.mutate(p.proposta_id);
    } else if (aberto === 'reverter' && p.aplicacao_id) {
      reverter.mutate({ aplicacaoId: p.aplicacao_id, pedido: { motivo: m } });
    }
    setAberto(null);
  };

  const idBase = `fila-${p.proposta_id}`;
  const selo = seloDoLedger(p);

  return (
    <li className="border-b border-border py-3" aria-labelledby={`${idBase}-titulo`}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <p id={`${idBase}-titulo`} className="text-[13px] font-semibold">
          {rotulo}
          <span className="ml-2 text-[11px] font-normal text-muted-foreground">{p.alvo_nivel}</span>
        </p>
        {selo ? (
          <SeloDeProposta estado={selo} className="text-[12px]" />
        ) : (
          <span className="text-[11px] font-medium" data-estado={p.estado}>
            {textoSemSelo(p)}
          </span>
        )}
      </div>
      {p.explicacao && <p className="mt-1 text-[12px] leading-relaxed text-muted-foreground">“{p.explicacao}”</p>}

      <AntesDepois linhas={linhas} legenda={`o que muda se a proposta de ${rotulo} for aplicada`} />
      <p className="mt-1.5 text-[11px] text-muted-foreground">
        {p.delta_pct != null && <>variação {p.delta_pct.toLocaleString('pt-BR')}% · </>}
        antes lido {horaExata(p.valor_atual_lido_em) ?? 'sem data'} · regra{' '}
        {/* O objetivo é a frase que o operador entende; a chave fica no title
            para quem precisa achá-la no ledger. */}
        <span title={p.regra_chave ? `${p.regra_chave}${p.regra_versao != null ? ` v${p.regra_versao}` : ''}` : undefined}>
          {p.regra_objetivo ?? p.regra_chave ?? '—'}
        </span>
        {!p.regra_objetivo && p.regra_versao != null && ` v${p.regra_versao}`} · evidência {p.evidencia_suficiencia ?? 'não avaliada'}
        {p.expira_em && ` · vence ${horaExata(p.expira_em)}`}
      </p>
      {p.aprovacao_decisao && (
        <p className="mt-1 text-[11px] text-muted-foreground">
          {p.aprovacao_decisao} por {p.aprovacao_por ?? '—'} em {horaExata(p.aprovacao_em) ?? '—'}
        </p>
      )}
      {p.aplicacao_desfecho && (
        <p className="mt-1 text-[11px]" data-desfecho={p.aplicacao_desfecho}>
          última aplicação: {DESFECHO_LEGIVEL[p.aplicacao_desfecho] ?? p.aplicacao_desfecho}
        </p>
      )}
      {oferta.aviso && <p className="mt-1 text-[11px] text-muted-foreground">{oferta.aviso}</p>}

      {(oferta.gestos.length > 0 || oferta.fechados.length > 0) && (
        <div className="mt-2 flex flex-wrap gap-2">
          {oferta.gestos.map((g) => (
            <Button
              key={g}
              type="button"
              size="sm"
              variant={g === 'aprovar' || g === 'aplicar' ? 'default' : 'outline'}
              disabled={ocupado}
              onClick={() =>
                g === 'verificar'
                  ? p.aplicacao_id && verificar.mutate(p.aplicacao_id)
                  : abrir(g as Exclude<GestoDaFila, 'verificar'>)
              }
            >
              {ROTULO_DO_GESTO[g]}
            </Button>
          ))}
          {oferta.fechados.map((f) => (
            <span key={f.gesto} className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
              <Button type="button" size="sm" variant="outline" disabled>
                {ROTULO_DO_GESTO[f.gesto]}
              </Button>
              {f.porque}
            </span>
          ))}
        </div>
      )}

      {aberto && (
        <div className="mt-2 rounded-md border border-border bg-muted/30 px-3 py-2.5" role="group" aria-label={`confirmar ${aberto}`}>
          {aberto === 'aprovar' && (
            <p className="text-[12px]">
              Você aprova exatamente o antes → depois acima. Se ele não for o gravado, o servidor recusa.
            </p>
          )}
          {aberto === 'aplicar' && (
            <p className="text-[12px]">
              {ehRecomendacao
                ? 'Recomendação não tem ensaio (validate_only) na API: aplicar é escrever, e não há reverso.'
                : 'O servidor relê a conta, ensaia a mudança e só então escreve. Se a conta mudou desde a aprovação, nada é enviado.'}
            </p>
          )}
          {aberto === 'reverter' && (
            <p className="text-[12px]">
              Restaura o valor capturado no envio. Só uma reversão por aplicação.
            </p>
          )}
          {aberto !== 'aplicar' && (
            <div className="mt-2">
              <label htmlFor={`${idBase}-motivo`} className="text-[12px] font-medium">
                motivo{aberto === 'aprovar' ? ' (opcional)' : ''}
              </label>
              <textarea
                id={`${idBase}-motivo`}
                rows={2}
                className={cn(classeDeEntrada, 'mt-1')}
                value={motivo}
                aria-invalid={faltaMotivo || undefined}
                onChange={(e) => setMotivo(e.target.value)}
              />
              {faltaMotivo && (
                <p className="mt-1 text-[11px] text-destructive" role="alert">
                  {aberto === 'recusar' ? 'Recusa exige motivo.' : 'Reversão exige motivo.'}
                </p>
              )}
            </div>
          )}
          <div className="mt-2 flex gap-2">
            <Button type="button" size="sm" variant={aberto === 'recusar' || aberto === 'reverter' ? 'destructive' : 'default'} onClick={confirmar}>
              Confirmar {aberto === 'aplicar' ? 'aplicação' : aberto === 'aprovar' ? 'aprovação' : aberto === 'recusar' ? 'recusa' : 'reversão'}
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setAberto(null)}>
              Voltar
            </Button>
          </div>
        </div>
      )}

      {ocupado && (
        <p className="mt-2 text-[11px] text-muted-foreground" role="status">
          enviando
        </p>
      )}

      {aplicar.data && (
        <p className="mt-2 text-[12px]" role="status">
          {aplicar.data.ja_aplicada
            ? 'Já estava aplicada; o Google não foi chamado de novo.'
            : `Desfecho: ${DESFECHO_LEGIVEL[aplicar.data.desfecho] ?? aplicar.data.desfecho}.`}
        </p>
      )}
      {verificar.data && (
        <p className="mt-2 text-[12px]" role="status">
          {confereLegivel(verificar.data.confere)}
          {verificar.data.motivo && ` — ${verificar.data.motivo}`}
        </p>
      )}
      {reverter.data && (
        <p className="mt-2 text-[12px]" role="status">
          {reverter.data.ja_revertida
            ? 'Já estava revertida.'
            : `Reversão: ${DESFECHO_LEGIVEL[reverter.data.reversao.desfecho] ?? reverter.data.reversao.desfecho}.`}
        </p>
      )}
      {(aprovar.data || recusar.data) && (
        <p className="mt-2 text-[12px]" role="status">
          Decisão registrada: {ESTADO_LEGIVEL[(aprovar.data ?? recusar.data)!.proposta.estado] ?? (aprovar.data ?? recusar.data)!.proposta.estado}
          {(aprovar.data ?? recusar.data)!.ja_existia && ' (já existia)'}.
        </p>
      )}
      {ultimoErro && (
        <AvisoDeErro className="mt-2" erro={erroLegivel(ultimoErro)}>
          {erroLegivel(ultimoErro).sugere === 'verificar' && aplicacaoDoErro(ultimoErro, p) && (
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="mt-2"
              disabled={ocupado}
              onClick={() => verificar.mutate(aplicacaoDoErro(ultimoErro, p) as string)}
            >
              Verificar na conta agora
            </Button>
          )}
        </AvisoDeErro>
      )}
    </li>
  );
};

/** A aplicação a verificar: a que a recusa citou, ou a última da linha. */
function aplicacaoDoErro(erro: unknown, p: PropostaDoPainel): string | null {
  const d = detalheDoErro(erro) as Record<string, unknown> | undefined;
  if (d && typeof d.aplicacao_id === 'string') return d.aplicacao_id;
  const ap = d?.aplicacao as Record<string, unknown> | undefined;
  if (ap && typeof ap.aplicacao_id === 'string') return ap.aplicacao_id;
  return p.aplicacao_id;
}
