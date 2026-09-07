/**
 * A etapa de conjuntos: N conjuntos com identidade estável (`F10`) e o mapa
 * anúncio → conjunto (`F34`).
 *
 * ## ⚠️ A CHAVE NÃO É A POSIÇÃO
 *
 * `adset_key` é gerada uma vez e não muda mais. Mover um conjunto para cima
 * reordena a APRESENTAÇÃO; a chave continua onde estava, e todos os anúncios
 * que apontavam para ela continuam apontando. Se a identidade fosse o índice,
 * subir o segundo conjunto trocaria em silêncio os anúncios de pai — e o
 * operador só descobriria depois de a campanha nascer, olhando entrega no lugar
 * errado. O backend cobra a mesma disciplina: `META_ADSET_DUPLICATE_KEY` recusa
 * chave repetida e `META_AD_ADSET_UNKNOWN` recusa anúncio órfão.
 *
 * O desenho de cada item é o MESMO do lote de criativos — `<section>`, cabeçalho
 * com kicker, `ChipDeEstado`, Duplicar e Remover — porque duas listas do mesmo
 * produto com dois desenhos diferentes é como uma bancada vira duas.
 */
import React from 'react';
import { ArrowDown, ArrowUp, CircleCheck, CircleDot, Copy, Plus, Trash2 } from 'lucide-react';

import { BlocoDeEvidencia, ChipDeEstado, LinhaDeFato } from '@/components/trafego/bancada';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

import { Campo } from './primitivas';
import {
  ConjuntoDraft, Draft, LIMITE_CONJUNTOS, VariacaoDraft, formatarBrl, inicioEmIso,
  nomeCanonico, reaisParaMinor,
} from './rascunho';

/** Um conjunto está completo quando pode virar um AdSet sem recusa local.
 *
 *  Interno de propósito: a AUTORIDADE da prontidão é `prontidaoDasEtapas`, e
 *  exportar um segundo cálculo daria a outro arquivo a chance de discordar do
 *  trilho — que é exatamente o defeito que a etapa de público tinha. */
function conjuntoCompleto(
  conjunto: ConjuntoDraft, draft: Draft, anuncios: readonly VariacaoDraft[],
): boolean {
  const temAnuncio = anuncios.some((item) => item.adsetKey === conjunto.key);
  const verbaOk = draft.nivelDeOrcamento === 'CAMPAIGN'
    || reaisParaMinor(conjunto.orcamentoBrl) > 0;
  const fimOk = draft.periodoDeOrcamento !== 'LIFETIME' || Boolean(inicioEmIso(conjunto.endTime));
  return Boolean(
    nomeCanonico(conjunto.nome) && inicioEmIso(conjunto.startTime) && temAnuncio && verbaOk && fimOk,
  );
}

export const PainelDeConjuntos: React.FC<{
  draft: Draft;
  /** Os anúncios que o modo criativo REALMENTE emite. Um lote guardado que não
   *  é emitido não pode fazer um conjunto parecer povoado. */
  emitidas: readonly VariacaoDraft[];
  onCampo: (chave: string, campo: 'nome' | 'startTime' | 'endTime', valor: string) => void;
  onAdicionar: (origem?: string) => void;
  onRemover: (chave: string) => void;
  onMover: (chave: string, direcao: -1 | 1) => void;
}> = ({ draft, emitidas, onCampo, onAdicionar, onRemover, onMover }) => {
  const noLimite = draft.conjuntos.length >= LIMITE_CONJUNTOS;
  const exigeFim = draft.periodoDeOrcamento === 'LIFETIME';

  return (
    <>
      <p id="meta-limite-conjuntos" className="max-w-[74ch] text-sm leading-relaxed text-pretty text-muted-foreground">
        <strong className="text-foreground">
          {draft.conjuntos.length} de {LIMITE_CONJUNTOS}
        </strong>{' '}
        conjuntos. Cada conjunto tem público, programação e posicionamentos próprios, e cada
        anúncio aponta explicitamente para um deles. O limite de {LIMITE_CONJUNTOS} é uma contenção
        operacional da VOLC, não um limite da Meta.
      </p>

      <div className="space-y-5">
        {draft.conjuntos.map((conjunto, posicao) => {
          const completo = conjuntoCompleto(conjunto, draft, emitidas);
          const doConjunto = emitidas.filter((item) => item.adsetKey === conjunto.key);
          return (
            <section
              key={conjunto.key}
              className="overflow-hidden rounded-lg border border-border bg-muted/20"
            >
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/70 px-4 py-3">
                <div className="min-w-0">
                  <p className="kicker">Conjunto {posicao + 1}</p>
                  <p className="mt-0.5 truncate text-sm font-semibold text-foreground">
                    {conjunto.nome || 'Sem nome'}
                  </p>
                  {/* A chave é a identidade que amarra o anúncio ao pai; ela
                      fica legível para quem audita e para o teste, sem virar
                      um título gigante na tela. */}
                  <p className="sr-only" data-testid="conjunto-chave">{conjunto.key}</p>
                </div>
                <div className="flex items-center gap-2">
                  <ChipDeEstado
                    glifo={completo ? CircleCheck : CircleDot}
                    palavra={completo ? 'completo' : 'incompleto'}
                    descricao={completo
                      ? 'este conjunto tem nome, início, verba e ao menos um anúncio'
                      : 'falta nome, início, verba ou um anúncio apontando para este conjunto'}
                    tom={completo ? 'bom' : 'atencao'}
                  />
                  <Button
                    type="button" variant="ghost" size="sm"
                    aria-label={`Mover o conjunto ${posicao + 1} para cima`}
                    disabled={posicao === 0}
                    onClick={() => onMover(conjunto.key, -1)}
                  >
                    <ArrowUp className="h-4 w-4" aria-hidden />
                  </Button>
                  <Button
                    type="button" variant="ghost" size="sm"
                    aria-label={`Mover o conjunto ${posicao + 1} para baixo`}
                    disabled={posicao === draft.conjuntos.length - 1}
                    onClick={() => onMover(conjunto.key, 1)}
                  >
                    <ArrowDown className="h-4 w-4" aria-hidden />
                  </Button>
                  <Button
                    type="button" variant="ghost" size="sm"
                    aria-describedby="meta-limite-conjuntos"
                    disabled={noLimite}
                    onClick={() => onAdicionar(conjunto.key)}
                  >
                    <Copy className="mr-1.5 h-4 w-4" aria-hidden />Duplicar conjunto
                  </Button>
                  {/* ⚠️ Remover um conjunto que ainda tem anúncio deixaria
                      `adset_key` órfã no lote — e a saída fácil (repontar os
                      anúncios para o primeiro conjunto) seria mudar o pai de um
                      anúncio sem ninguém pedir. O botão fecha e diz por quê; a
                      correção é escolher outro conjunto na etapa Anúncios. */}
                  <Button
                    type="button" variant="ghost" size="sm"
                    aria-describedby={doConjunto.length ? `meta-conjunto-preso-${conjunto.key}` : undefined}
                    disabled={draft.conjuntos.length === 1 || doConjunto.length > 0}
                    onClick={() => onRemover(conjunto.key)}
                  >
                    <Trash2 className="mr-1.5 h-4 w-4" aria-hidden />Remover conjunto
                  </Button>
                </div>
              </div>

              {doConjunto.length > 0 && draft.conjuntos.length > 1 && (
                <p
                  id={`meta-conjunto-preso-${conjunto.key}`}
                  className="border-b border-border/70 px-4 py-2 text-sm text-muted-foreground"
                >
                  Este conjunto não pode ser removido enquanto {doConjunto.length} anúncio(s)
                  apontarem para ele. Reaponte-os na etapa Anúncios primeiro.
                </p>
              )}

              <div className="grid gap-4 p-4 md:grid-cols-2">
                <Campo id={`meta-adset-name-${conjunto.key}`} rotulo="Nome do conjunto" largo>
                  <Input
                    id={`meta-adset-name-${conjunto.key}`}
                    value={conjunto.nome}
                    onChange={(e) => onCampo(conjunto.key, 'nome', e.target.value)}
                  />
                </Campo>
                <Campo
                  id={`meta-start-${conjunto.key}`}
                  rotulo="Início"
                  ajuda="O instante viaja com fuso explícito. A conta pode operar em outro fuso; a bancada não converte por conta própria."
                >
                  <Input
                    id={`meta-start-${conjunto.key}`}
                    type="datetime-local"
                    value={conjunto.startTime}
                    onChange={(e) => onCampo(conjunto.key, 'startTime', e.target.value)}
                  />
                </Campo>
                <Campo
                  id={`meta-end-${conjunto.key}`}
                  rotulo={exigeFim ? 'Término (obrigatório com verba total)' : 'Término (opcional)'}
                  ajuda={exigeFim
                    ? 'Orçamento total exige término: sem ele o plano é recusado com META_SCHEDULE_END_REQUIRED.'
                    : 'Sem término, o conjunto é contínuo. Com verba diária isso é o normal.'}
                >
                  <Input
                    id={`meta-end-${conjunto.key}`}
                    type="datetime-local"
                    value={conjunto.endTime}
                    onChange={(e) => onCampo(conjunto.key, 'endTime', e.target.value)}
                  />
                </Campo>
                <div className="md:col-span-2">
                  <BlocoDeEvidencia
                    titulo="O que este conjunto carrega"
                    tom={doConjunto.length ? 'info' : 'atencao'}
                  >
                    <LinhaDeFato
                      rotulo="Verba deste conjunto"
                      valor={draft.nivelDeOrcamento === 'CAMPAIGN'
                        ? 'Decidida na campanha (CBO)'
                        : (reaisParaMinor(conjunto.orcamentoBrl) > 0
                          ? formatarBrl(reaisParaMinor(conjunto.orcamentoBrl)) : null)}
                      fonte="você, agora"
                      ausencia="ainda não informada"
                    />
                    <LinhaDeFato
                      rotulo="Anúncios apontando para cá"
                      valor={doConjunto.length
                        ? doConjunto.map((item) => item.adName || item.key).join(' · ')
                        : null}
                      fonte="o mapa desta bancada"
                      ausencia="nenhum · um conjunto sem anúncio é recusado (META_ADSET_WITHOUT_AD)"
                    />
                    <LinhaDeFato
                      rotulo="Meta de desempenho"
                      valor="Visualizações da página de destino"
                      fonte="a receita provada"
                    />
                    <LinhaDeFato rotulo="Cobrança" valor="Por impressão" fonte="a receita provada" />
                  </BlocoDeEvidencia>
                </div>
              </div>
            </section>
          );
        })}

        <Button
          type="button" variant="outline" className="w-full border-dashed"
          aria-describedby="meta-limite-conjuntos"
          disabled={noLimite}
          onClick={() => onAdicionar()}
        >
          <Plus className="mr-2 h-4 w-4" aria-hidden />Adicionar outro conjunto
        </Button>
      </div>

      <p className="max-w-[74ch] text-sm leading-relaxed text-pretty text-muted-foreground">
        A Meta só aceita mensagem, WhatsApp e ligação como tipo de destino declarado no objetivo
        Tráfego. Tráfego para site é o comportamento padrão do objetivo, então a bancada não
        declara nenhum tipo de destino — declarar um inválido seria recusado na validação.
      </p>
    </>
  );
};
