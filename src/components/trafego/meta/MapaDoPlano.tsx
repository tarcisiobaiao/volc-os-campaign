/**
 * A revisão do plano V2 (`F37`, `A33`) e o mapa peça → conjunto → anúncio (`F34`).
 *
 * ## ⚠️ ESTE COMPONENTE NÃO RECALCULA NADA
 *
 * Ele recebe `resumo` — o objeto que `_resumo_v2` derivou do CONTRATO, não do
 * rascunho do navegador — e o desenha. `A33`/`F37` cobram que rascunho e resumo
 * não possam divergir, e a única forma de garantir isso é a revisão não ter
 * outra fonte. Se um número aqui saísse de `draft`, a tela poderia afirmar
 * sobre o corpo enviado uma coisa que o corpo enviado não diz.
 *
 * A ÚNICA coisa que vem do rascunho é o NOME LEGÍVEL da peça e do anúncio — o
 * resumo carrega `variation_key`, que identifica sem descrever. Nome é rótulo,
 * não afirmação sobre o plano.
 */
import React from 'react';

import { BlocoDeEvidencia, LinhaDeFato, PainelDeBloqueio } from '@/components/trafego/bancada';

import { NomeCurto } from './primitivas';
import type { ResumoDoPlanoMetaV2 } from '@/lib/pautadorApi';

export const MapaDoPlano: React.FC<{
  resumo: ResumoDoPlanoMetaV2;
  /** Rótulos legíveis por `variation_key`: nome do anúncio e nome da peça. */
  rotuloDoAnuncio: (variationKey: string) => { anuncio: string; peca: string | null };
}> = ({ resumo, rotuloDoAnuncio }) => (
  <>
    <BlocoDeEvidencia titulo="O plano, como o servidor o entendeu" tom="verificado">
      <LinhaDeFato rotulo="Receita" valor={`${resumo.receita.rotulo} · ${resumo.receita.id}`} fonte="o resumo do backend" />
      <LinhaDeFato rotulo="Objetivo e otimização" valor={`${resumo.receita.objetivo} · ${resumo.receita.otimizacao}`} fonte="o resumo do backend" />
      <LinhaDeFato rotulo="Onde a verba mora" valor={resumo.orcamento.onde_a_verba_mora} fonte="o resumo do backend" />
      <LinhaDeFato rotulo="Modo de orçamento" valor={`${resumo.orcamento.modo} · prova ${resumo.orcamento.prova}`} fonte="o resumo do backend" />
      <LinhaDeFato rotulo="Conjuntos" valor={resumo.conjuntos.length} fonte="o resumo do backend" />
      <LinhaDeFato
        rotulo="Anúncios"
        valor={resumo.conjuntos.reduce((total, item) => total + item.anuncios.length, 0)}
        fonte="o resumo do backend"
      />
    </BlocoDeEvidencia>

    {/* ⚠️ O MAPA É REVISÁVEL: cada linha diz de qual peça sai qual anúncio e em
        qual conjunto ele nasce. Sem isso, um lote de dez peças e três conjuntos
        é uma aposta — e o erro de mapeamento só apareceria na entrega. */}
    <div className="overflow-x-auto rounded-lg border border-border/70">
      <table className="w-full min-w-[640px] text-sm">
        <caption className="sr-only">
          Mapa de peça, conjunto e anúncio, derivado do resumo do servidor
        </caption>
        <thead className="bg-muted/40 text-left text-muted-foreground">
          <tr>
            <th scope="col" className="px-3 py-2 font-medium">Conjunto</th>
            <th scope="col" className="px-3 py-2 font-medium">Peça</th>
            <th scope="col" className="px-3 py-2 font-medium">Anúncio</th>
            <th scope="col" className="px-3 py-2 font-medium">Chave</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border/60">
          {resumo.conjuntos.flatMap((conjunto) => conjunto.anuncios.map((chave) => {
            const rotulo = rotuloDoAnuncio(chave);
            return (
              <tr key={`${conjunto.adset_key}:${chave}`} data-testid="linha-do-mapa">
                <th scope="row" className="max-w-[220px] px-3 py-2 text-left font-medium text-foreground">
                  <NomeCurto nome={conjunto.nome} ausencia="conjunto sem nome" />
                </th>
                <td className="max-w-[220px] px-3 py-2 text-muted-foreground">
                  {/* ⚠️ `A30`: nome curto, truncado, com o valor inteiro no
                      `title`. Um caminho de armazenamento como título estoura a
                      coluna e não diz nada que o operador precise. */}
                  <NomeCurto nome={rotulo.peca} ausencia="peça não escolhida" />
                </td>
                <td className="max-w-[220px] px-3 py-2 text-muted-foreground">
                  <NomeCurto nome={rotulo.anuncio} ausencia="anúncio sem nome" />
                </td>
                <td className="px-3 py-2 font-mono text-xs text-muted-foreground">
                  {conjunto.adset_key} → {chave}
                </td>
              </tr>
            );
          }))}
        </tbody>
      </table>
    </div>

    {resumo.conjuntos.map((conjunto) => (
      <BlocoDeEvidencia
        key={conjunto.adset_key}
        titulo={`Conjunto · ${conjunto.nome}`}
        tom={conjunto.promete_alcance_exclusivo ? 'verificado' : 'info'}
      >
        <LinhaDeFato
          rotulo="Verba deste conjunto"
          valor={conjunto.orcamento_minor === null
            ? 'Decidida na campanha (CBO)'
            : `${conjunto.orcamento_minor} centavos`}
          fonte="o resumo do backend"
        />
        <LinhaDeFato rotulo="Modo de público" valor={conjunto.publico_modo} fonte="o resumo do backend" />
        <LinhaDeFato
          rotulo="Públicos"
          valor={`${conjunto.publicos_incluidos} incluídos · ${conjunto.publicos_excluidos} excluídos`}
          fonte="o resumo do backend"
        />
        <LinhaDeFato
          rotulo="Advantage+ público"
          valor={conjunto.expansao_advantage ? 'Aceito (1)' : 'Recusado (0)'}
          fonte="o resumo do backend"
        />
        {/* ⚠️ `A16` — a frase de alcance sai do servidor, sempre. */}
        <LinhaDeFato
          rotulo="Alcance"
          valor={conjunto.promete_alcance_exclusivo
            ? 'Somente o público selecionado será alcançado'
            : 'A Meta pode alcançar pessoas fora do público selecionado'}
          fonte="o resumo do backend"
        />
        <LinhaDeFato
          rotulo="Posicionamentos"
          valor={conjunto.posicionamentos.join(', ') || null}
          fonte="o resumo do backend"
          ausencia="nenhum"
        />
        <LinhaDeFato
          rotulo="Mensuração"
          valor={`${conjunto.mensuracao_proposito} · ${conjunto.mensuracao_altera_entrega ? 'altera a entrega' : 'não altera a entrega'}`}
          fonte="o resumo do backend"
        />
      </BlocoDeEvidencia>
    ))}

    {resumo.bloqueios_para_criar.length > 0 && (
      <PainelDeBloqueio
        titulo="O que ainda impede este plano de NASCER"
        bloqueios={resumo.bloqueios_para_criar.map((motivo, indice) => ({
          codigo: `META_CREATE_BLOCKED_${indice + 1}`,
          severidade: 'alta' as const,
          titulo: motivo,
          detalhe:
            'Conferir o plano e validar na Meta continuam liberados — é a validação que '
            + 'produz a prova que falta. O que permanece fechado é criar.',
        }))}
      />
    )}
  </>
);
