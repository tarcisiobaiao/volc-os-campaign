/**
 * O recibo durável de uma operação de nascimento Meta, desenhado com honestidade.
 *
 * ⚠️ Ele lê SÓ o recibo. O `read_back` que vinha na resposta HTTP da criação
 * saiu de cena: aquilo vivia num `useState` que o reload apaga, e era por isso
 * que as colunas de leitura voltavam vazias depois do F5 mesmo com a evidência
 * gravada no livro. Uma fonte só, e ela é durável.
 *
 * A linguagem visual é a da bancada, sem nada novo: `BlocoDeEvidencia`,
 * `LinhaDeFato`, `ChipDeEstado`, `PainelDeBloqueio` e as mesmas classes da
 * tabela que já estava na página.
 */
import React from 'react';
import { CircleCheck, CircleDot, CircleHelp, Lock, TriangleAlert } from 'lucide-react';

import {
  BlocoDeEvidencia, ChipDeEstado, LinhaDeFato, PainelDeBloqueio,
} from '@/components/trafego/bancada';
import type { ReciboCriacaoMeta } from '@/lib/pautadorApi';

import {
  DESCRICAO_DO_PASSO,
  PALAVRA_DO_PASSO,
  TOM_DA_OPERACAO,
  TOM_DO_PASSO,
  type EstadoDoPasso,
  type PassoDaOperacao,
  fraseDaOperacao,
  lerOperacao,
  passoVeicula,
} from './estadoDaOperacao';

const GLIFO_DO_PASSO: Record<EstadoDoPasso, React.ComponentType<{ className?: string }>> = {
  NAO_DESPACHADO: CircleDot,
  EM_VOO: CircleDot,
  CRIADO_SEM_LEITURA: CircleHelp,
  CONFIRMADO: CircleCheck,
  DIVERGENTE: TriangleAlert,
  AMBIGUO: CircleDot,
  RECUSADO: Lock,
  NAO_RECONHECIDO: CircleHelp,
};

/** "—" sozinho não é conteúdo para leitor de tela. Mesma regra que
 *  `LinhaDeFato` já aplica; a célula de tabela não a herda. */
const Ausente: React.FC<{ valor: string | null; palavra: string }> = ({ valor, palavra }) =>
  valor !== null && valor !== '' ? <>{valor}</> : (
    <>
      <span aria-hidden>—</span>
      <span className="sr-only">{palavra}</span>
    </>
  );

/** O que a coluna "Veicula" pode afirmar sem inventar o read-back. */
function veiculacao(passo: PassoDaOperacao): string | null {
  if (!passo.leitura) return null;
  if (!passoVeicula(passo)) return 'Não';
  // ⚠️ "Sim · pausado" SÓ quando o estado LIDO for PAUSED. Deduzir o pausado a
  // partir do plano seria afirmar o read-back em vez de mostrá-lo.
  return passo.leitura.status === 'PAUSED'
    ? 'Sim · pausado'
    : `Sim · ${passo.leitura.status ?? 'estado não lido'}`;
}

export const MetaOperationReceipt: React.FC<{
  recibo: ReciboCriacaoMeta;
  /** A referência que a URL está mostrando. */
  referencia: string;
}> = ({ recibo, referencia }) => {
  // ⚠️ ÚLTIMA TRAVA CONTRA RECIBO TROCADO. A página já casa referência e recibo
  // antes de renderizar; esta linha existe porque o custo de errar é exibir a
  // execução de OUTRA operação como se fosse desta — e uma trava que vive só no
  // chamador morre no primeiro refactor.
  if (recibo.approval_id !== referencia) {
    return (
      <PainelDeBloqueio
        titulo="O recibo lido não é o desta operação"
        bloqueios={[{
          codigo: 'META_RECEIPT_REFERENCE_MISMATCH',
          severidade: 'alta',
          titulo: 'a referência da URL e a do recibo não são a mesma',
          detalhe: 'Nada é exibido enquanto isso: mostrar o recibo de outra '
            + 'operação como se fosse desta é como um incidente vira dois.',
        }]}
      />
    );
  }

  const leitura = lerOperacao(recibo);
  const { esperados } = leitura;
  const deEsperados = (quantos: number) =>
    esperados === null ? null : `${quantos} de ${esperados}`;

  return (
    <>
      <BlocoDeEvidencia
        titulo="Recibo durável da operação"
        tom={TOM_DA_OPERACAO[leitura.estado.tipo]}
      >
        <LinhaDeFato
          rotulo="Desfecho"
          valor={fraseDaOperacao(leitura)}
          fonte="o recibo durável"
        />
        <LinhaDeFato
          rotulo="Identidade do plano"
          valor={recibo.plan_sha256}
          fonte="o backend"
        />
        {/* ⚠️ DUAS contagens, porque são DUAS perguntas. "Existe" é o que a Meta
            devolveu; "confere" é o que a leitura de volta gravou. Uma linha só
            obrigaria a escolher qual das duas mentir — e a antiga escolhia
            mentir nas duas, contando sobre os passos que existem. */}
        <LinhaDeFato
          rotulo="Passos conferidos por leitura"
          valor={deEsperados(leitura.confirmados)}
          ausencia="manifesto não declarado"
          fonte="o recibo durável"
        />
        <LinhaDeFato
          rotulo="Passos com id gravado"
          valor={deEsperados(leitura.comIdGravado)}
          ausencia="manifesto não declarado"
          fonte="o recibo durável"
        />
        {leitura.naoDespachados > 0 && (
          <LinhaDeFato
            rotulo="Passos aprovados sem linha no livro"
            valor={String(leitura.naoDespachados)}
            fonte="o recibo durável"
          />
        )}
        {/* ⚠️ Validade da APROVAÇÃO e estado da EXECUÇÃO são fatos diferentes.
            Uma aprovação expirada fecha novo despacho e não apaga o que já foi
            criado. */}
        <LinhaDeFato rotulo="Estado da aprovação" valor={recibo.state} fonte="o backend" />
      </BlocoDeEvidencia>

      <div className="overflow-x-auto rounded-lg border border-border/70">
        <table className="w-full min-w-[680px] text-sm">
          <caption className="sr-only">Estado de cada passo da operação</caption>
          <thead className="bg-muted/40 text-left text-muted-foreground">
            <tr>
              <th scope="col" className="px-3 py-2 font-medium">Objeto</th>
              <th scope="col" className="px-3 py-2 font-medium">Estado</th>
              <th scope="col" className="px-3 py-2 font-medium">Estado lido</th>
              <th scope="col" className="px-3 py-2 font-medium">Veicula</th>
              <th scope="col" className="px-3 py-2 font-medium">Conferido em</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/60">
            {leitura.passos.map((passo) => (
              <tr key={passo.nome}>
                <th scope="row" className="px-3 py-2 text-left font-medium text-foreground">
                  {passo.nome}
                </th>
                <td className="px-3 py-2">
                  <ChipDeEstado
                    glifo={GLIFO_DO_PASSO[passo.estado]}
                    palavra={PALAVRA_DO_PASSO[passo.estado]}
                    descricao={DESCRICAO_DO_PASSO[passo.estado]}
                    tom={TOM_DO_PASSO[passo.estado]}
                  />
                  {passo.erroDeLeitura && (
                    <span className="ml-2 text-xs text-warning">
                      existe, mas divergiu do aprovado
                    </span>
                  )}
                  {passo.foraDoManifesto && (
                    <span className="ml-2 text-xs text-warning">
                      fora do manifesto aprovado
                    </span>
                  )}
                  {passo.idsObservados > 0 && (
                    <span className="ml-2 text-xs text-warning">
                      um despacho sem autoridade viu objeto nascer aqui
                    </span>
                  )}
                </td>
                <td className="px-3 py-2 text-muted-foreground">
                  <Ausente valor={passo.leitura?.status ?? null} palavra="não conferido" />
                </td>
                <td className="px-3 py-2 text-muted-foreground">
                  {/* ⚠️ Sem leitura gravada NÃO é "não veicula" — é "não
                      conferido", e a diferença decide se alguém precisa ir à
                      conta olhar. */}
                  <Ausente valor={veiculacao(passo)} palavra="não conferido" />
                </td>
                <td className="px-3 py-2 tabular text-muted-foreground">
                  <Ausente valor={passo.conferidoEm} palavra="não conferido" />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
};
