/**
 * Parada 6 — Revisão. É isto que você quer criar.
 *
 * ## A Revisão não decide nada
 *
 * Ela confere e dispara a prova. Nenhum controle novo aparece aqui: qualquer
 * campo editável nesta parada seria uma decisão tomada DEPOIS da conferência, o
 * que é exatamente como uma proposta editada após a assinatura vai ao ar com
 * carimbo de aprovada.
 *
 * ## A pergunta que ela responde em menos de dez segundos
 *
 * O que será criado · em qual conta · qual canal · qual destino · qual conjunto
 * · qual anúncio · orçamento e CPC · o que falta · quem bloqueou · próximo ato.
 *
 * ⚠️ `FALTA` vem do servidor, via a projeção das paradas — nunca de uma segunda
 * expressão booleana montada aqui.
 */
import React from 'react';

import { BlocoDeEvidencia, LinhaDeFato } from '../BlocoDeEvidencia';
import { AcaoDominante } from '../AcaoDominante';
import { PainelDeBloqueio } from '../PainelDeBloqueio';
import type { AvisoDoCockpit, LinhaDoPedido } from '@/types/trafego';

/** A frase normativa que antecede a prova. Ela não pode prometer aprovação. */
export const FRASE_DA_PROVA =
  'A prova confere a forma do pedido e a política. Ela não garante que a criação vai passar.';

export const ParadaRevisao: React.FC<{
  linhas: LinhaDoPedido[];
  faltas: string[];
  bloqueios: AvisoDoCockpit[];
  lidoEm: string | null;
  travaFechada: boolean;
  explicacaoDaTrava: string | null;
  onProvar: () => void;
}> = ({ linhas, faltas, bloqueios, lidoEm, travaFechada, explicacaoDaTrava, onProvar }) => (
  <div className="space-y-4">
    <PainelDeBloqueio bloqueios={bloqueios} lidoEm={lidoEm} />

    <BlocoDeEvidencia titulo="O que será criado" tom={faltas.length === 0 ? 'bom' : 'atencao'}>
      <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
        {linhas.map((l) => (
          <LinhaDeFato
            key={l.rotulo}
            rotulo={l.rotulo}
            valor={l.valor}
            fonte={l.fonte}
            frescor={l.frescor}
            ausencia="—"
          />
        ))}
      </dl>
    </BlocoDeEvidencia>

    <BlocoDeEvidencia titulo="Provar contra a conta">
      <p className="max-w-[70ch] text-sm leading-6 text-foreground text-pretty">
        {FRASE_DA_PROVA}
      </p>
      <p className="mt-2 max-w-[70ch] text-sm leading-6 text-muted-foreground text-pretty">
        A prova roda <code>validate_only</code>: a API confere o pedido e descarta.
        Nada é criado, e nada passa a existir na conta por causa dela.
      </p>
      {/* ⚠️ A trava é declarada ANTES do clique, e não descoberta depois dele.
          Ela não impede provar — `validate_only` é leitura —, mas impede
          escrever, e esconder isso faria o operador chegar ao fim de uma prova
          de 120 segundos para descobrir que não pode criar. */}
      {travaFechada && (
        <p className="mt-2 max-w-[70ch] text-sm leading-6 text-warning text-pretty">
          {explicacaoDaTrava
            ?? 'A trava de escrita está fechada neste processo. A prova roda; a criação será recusada.'}
        </p>
      )}
      <div className="mt-4">
        <AcaoDominante pode={faltas.length === 0} faltas={faltas} onClick={onProvar}>
          Provar contra a conta
        </AcaoDominante>
      </div>
    </BlocoDeEvidencia>
  </div>
);
