/**
 * O envelope de um catálogo, desenhado sem achatar os estados (`A11`).
 *
 * ## Por que um componente, e não um `if` em cada painel
 *
 * `_envelope_de_leitura` no adaptador diz, com todas as letras, o que está em
 * jogo: `[]` completo, permissão negada, timeout e página truncada "NAO podem
 * chegar iguais na UI: a primeira significa 'escolha nada porque nao ha nada',
 * a segunda 'pede acesso', a terceira 'tenta de novo' e a quarta 'existe mais
 * do que voce esta vendo'". São quatro frases diferentes com quatro próximos
 * passos diferentes — e ainda existe um quinto estado, o de NÃO TER LIDO, que
 * não é nenhum dos quatro.
 *
 * Três painéis escrevendo isso à mão seriam três chances de colapsar dois
 * estados por descuido. Aqui é um lugar só, e cada estado tem palavra própria.
 *
 * ## ⚠️ FRESCOR É OUTRO EIXO
 *
 * `estado_do_catalogo` (VIGENTE/OBSOLETO) é ORTOGONAL a `estado`: uma leitura
 * pode ter itens E estar vencida. Ela aparece numa linha própria, com os itens
 * ainda à vista — nunca escondida, e nunca re-buscada em silêncio, porque uma
 * re-busca automática trocaria a lista debaixo de uma seleção já feita.
 */
import React from 'react';
import { RefreshCw } from 'lucide-react';

import { ChipDeEstado, PainelDeBloqueio } from '@/components/trafego/bancada';
import { Button } from '@/components/ui/button';
import { CircleAlert, CircleCheck, CircleDot, CircleHelp, TriangleAlert } from 'lucide-react';

import type { EnvelopeDeCatalogoMeta } from '@/lib/pautadorApi';

/** A causa da indisponibilidade, em linguagem de operador.
 *
 * ⚠️ O código cru viaja junto no `PainelDeBloqueio`; esta função só acrescenta
 * o próximo passo. Traduzir e ESCONDER o código deixaria quem investiga sem o
 * termo que ele procura no log do servidor. */
function proximoPasso(motivo: string | null, retryable: boolean): string {
  if (retryable) {
    return 'A leitura pode ser tentada de novo: nada mudou na conta, e nada foi criado.';
  }
  if (motivo && /PERMISSION|PERMISSAO|FORBIDDEN|OAUTH/i.test(motivo)) {
    return 'Falta acesso a esta leitura nesta conta. Tentar de novo não resolve: '
      + 'alguém precisa liberar a permissão.';
  }
  return 'Tentar de novo não deve resolver sozinho. Isto é uma falha de LEITURA, '
    + 'não a ausência de itens na conta.';
}

export const CatalogoDaConta = <T,>({
  titulo, substantivo, envelope, carregando, erro, podeLer, onLer, children,
}: {
  titulo: string;
  /** "públicos", "lugares", "fontes de mensuração" — entra nas frases. */
  substantivo: string;
  envelope: EnvelopeDeCatalogoMeta<T> | null;
  carregando: boolean;
  erro: string | null;
  podeLer: boolean;
  onLer: () => void;
  /** A lista, desenhada por quem sabe o que é um item deste catálogo. */
  children?: React.ReactNode;
}) => {
  const obsoleto = envelope?.estado_do_catalogo === 'OBSOLETO';
  return (
    <section className="space-y-3 rounded-lg border border-border bg-muted/20 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="kicker">{titulo}</p>
          <p className="mt-0.5 max-w-[70ch] text-sm text-muted-foreground">
            A leitura é da conta real e só acontece por clique. Nada é criado, alterado nem
            enviado à Meta além da consulta.
          </p>
        </div>
        <Button
          type="button" variant="outline" size="sm"
          disabled={!podeLer || carregando}
          onClick={onLer}
        >
          <RefreshCw className="mr-1.5 h-4 w-4" aria-hidden />
          {carregando ? 'Lendo a conta…' : `Ler ${substantivo} desta conta`}
        </Button>
      </div>

      {/* ── 1. NÃO LIDO. Não é vazio, e a diferença decide o próximo passo. ── */}
      {!envelope && !erro && !carregando && (
        <p className="text-sm text-muted-foreground">
          Ainda não lido. Ausência de leitura não é ausência de {substantivo}.
        </p>
      )}

      {/* ── 2. A chamada nem chegou ao envelope (rede, sessão, 404) ───────── */}
      {erro && (
        <PainelDeBloqueio
          titulo={`Não foi possível ler ${substantivo} desta conta`}
          bloqueios={[{
            codigo: 'META_CATALOG_REQUEST_FAILED',
            severidade: 'alta',
            titulo: erro,
            detalhe:
              'Isto é uma falha de LEITURA, não a ausência de itens. A conta pode ter '
              + `${substantivo} que esta consulta não conseguiu ver.`,
          }]}
        />
      )}

      {/* ── 3. INDISPONIVEL — a Meta recusou ou não respondeu ─────────────── */}
      {envelope?.estado === 'INDISPONIVEL' && (
        <PainelDeBloqueio
          titulo={`A Meta não entregou ${substantivo} desta conta`}
          bloqueios={[{
            codigo: envelope.motivo || 'META_CATALOG_UNAVAILABLE',
            severidade: 'alta',
            titulo: `Leitura indisponível · ${envelope.motivo ?? 'causa não informada'}`,
            detalhe: proximoPasso(envelope.motivo, envelope.retryable),
          }]}
        />
      )}

      {/* ── 4. VAZIO COMPLETO — respondeu, e não há nada. Não é falha. ────── */}
      {envelope?.estado === 'VAZIO_COMPLETO' && (
        <p className="text-sm text-muted-foreground">
          A conta respondeu e não tem nenhum item de {substantivo}. Isto é diferente de não ter
          lido e diferente de a leitura ter falhado: aqui a resposta veio inteira, e ela está
          vazia.
        </p>
      )}

      {/* ── 5. PARCIAL — existe mais do que você está vendo ───────────────── */}
      {envelope?.estado === 'PARCIAL' && (
        <div className="flex items-start gap-3 rounded-md border border-warning/40 bg-warning/10 p-3">
          <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden />
          <p className="max-w-[74ch] text-sm leading-relaxed text-pretty text-muted-foreground">
            <strong className="text-foreground">Lista incompleta.</strong>{' '}
            A leitura parou antes do fim ({envelope.motivo ?? 'limite de paginação'}), então
            existem {substantivo} nesta conta que não estão aqui. O que aparece é utilizável; o
            que falta não pode ser concluído como inexistente.
          </p>
        </div>
      )}

      {envelope && (
        <div className="flex flex-wrap items-center gap-2">
          <ChipDeEstado
            glifo={envelope.estado === 'COM_ITENS' ? CircleCheck
              : envelope.estado === 'VAZIO_COMPLETO' ? CircleDot
                : envelope.estado === 'PARCIAL' ? TriangleAlert : CircleAlert}
            palavra={`${envelope.total} de ${substantivo}`}
            descricao={`${envelope.paginas_lidas} página(s) lida(s) nesta consulta`}
            tom={envelope.estado === 'COM_ITENS' ? 'verificado'
              : envelope.estado === 'PARCIAL' ? 'atencao'
                : envelope.estado === 'INDISPONIVEL' ? 'ruim' : 'neutro'}
          />
          {envelope.completo ? null : (
            <ChipDeEstado
              glifo={TriangleAlert}
              palavra="lista incompleta"
              descricao="a leitura não chegou ao fim; existem itens que não estão aqui"
              tom="atencao"
            />
          )}
          {envelope.invalidos > 0 && (
            <ChipDeEstado
              glifo={CircleAlert}
              palavra={`${envelope.invalidos} ilegível(is)`}
              descricao="itens que vieram malformados; contados em vez de escondidos"
              tom="ruim"
            />
          )}
          {envelope.desconhecidos > 0 && (
            <ChipDeEstado
              glifo={CircleHelp}
              palavra={`${envelope.desconhecidos} sem estado`}
              descricao="a Meta não permitiu concluir a disponibilidade destes itens"
              tom="neutro"
            />
          )}
          {/* ⚠️ EIXO ORTOGONAL: a lista pode ter itens E estar vencida. */}
          <ChipDeEstado
            glifo={obsoleto ? TriangleAlert : CircleCheck}
            palavra={obsoleto ? 'leitura vencida' : 'leitura vigente'}
            descricao={obsoleto
              ? 'esta lista passou do prazo de validade; ela não foi re-buscada em silêncio '
                + 'porque isso trocaria a lista debaixo de uma seleção já feita'
              : 'esta lista está dentro do prazo declarado pelo servidor'}
            tom={obsoleto ? 'atencao' : 'verificado'}
          />
          <span className="text-sm text-muted-foreground">
            observada em {envelope.observado_em}
          </span>
        </div>
      )}

      {children}
    </section>
  );
};
