/**
 * O plano canônico de mensuração, na tela.
 *
 * ## Por que este componente mora sozinho
 *
 * Ele aparece em DOIS lugares que não se parecem: o cartão de mensuração do
 * cockpit de canais, e o painel do lançamento — a tela em que o próximo clique
 * gasta dinheiro. Duas implementações da mesma coisa divergiriam no primeiro
 * campo novo, e a que divergisse seria justamente a que ninguém olha.
 *
 * ## O que ele NÃO faz
 *
 * Nenhum campo é derivado aqui. `completo`, `resolvida`, `bloqueadores` e
 * `comprovado` vêm prontos do servidor. O que este arquivo faz é TRADUZIR para
 * português os estados que o servidor já distinguiu — e as funções de tradução
 * moram em `lib/trafego/canais.ts`, junto do contrato que elas leem.
 *
 * ⚠️ `plano: null` NÃO é "não há plano": é "ninguém leu os três recursos que
 * decidem a meta efetiva". Quem chama decide o que fazer com a ausência; este
 * componente só é montado quando há um plano.
 */
import React from 'react';

import {
  textoDaFonteDoSinal,
  textoDaMetaEfetiva,
  textoDoFrescor,
  type PlanoDeMensuracao,
} from '@/lib/trafego/canais';

/** Um par rótulo/valor em que o valor pode legitimamente ser desconhecido. */
function Fato({
  rotulo,
  valor,
  ressalva,
}: {
  rotulo: string;
  valor: React.ReactNode;
  ressalva?: string | null;
}) {
  return (
    <div>
      <dt className="text-[11px] uppercase tracking-wide text-slate-500 dark:text-slate-500">
        {rotulo}
      </dt>
      <dd className="text-sm text-slate-800 dark:text-slate-200">{valor}</dd>
      {ressalva ? (
        <p className="mt-0.5 text-[11px] leading-snug text-slate-500 dark:text-slate-500">
          {ressalva}
        </p>
      ) : null}
    </div>
  );
}

export function CartaoDoPlanoDeMensuracao({
  plano,
  titulo = 'Plano de mensuração',
}: {
  plano: PlanoDeMensuracao;
  titulo?: string;
}) {
  return (
    <div>
      <p className="text-[11px] uppercase tracking-wide text-slate-500 dark:text-slate-500">
        {titulo}
        {/* ⚠️ Campanha ainda não nascida é o caso NORMAL — o plano existe ANTES
            do nascimento, e é esse o ponto. Omitir a informação faria o
            operador ler a ausência do id como defeito. */}
        {plano.campaign_id
          ? ` · campanha ${plano.campaign_id}`
          : ' · antes do nascimento'}
      </p>
      <dl className="mt-2 grid gap-2 sm:grid-cols-2">
        <Fato
          rotulo="meta efetiva"
          valor={textoDaMetaEfetiva(plano.meta_efetiva)}
          ressalva={plano.meta_efetiva.causa}
        />
        <Fato rotulo="fonte do sinal" valor={textoDaFonteDoSinal(plano)} />
        <Fato
          rotulo="frescor da última conversão"
          valor={textoDoFrescor(plano.frescor)}
          ressalva={plano.frescor.causa}
        />
        <Fato
          rotulo="destino de conversão offline"
          // ⚠️ O ID NUMÉRICO e a conta DONA, e não o nome da ação. É por eles
          // que a ingestão offline resolve o destino, e mostrar só o nome
          // ensinaria o operador a identificar a ação pelo campo errado — o
          // mesmo campo que a Data Manager não aceita.
          valor={
            plano.destino.resolvido
              ? `ação #${plano.destino.product_destination_id} na conta ${plano.destino.operating_account_id}`
              : 'não resolvido'
          }
          ressalva={plano.destino.causa}
        />
      </dl>
      {plano.bloqueadores.length > 0 ? (
        <div className="mt-2">
          <p className="text-[11px] uppercase tracking-wide text-slate-500 dark:text-slate-500">
            O que ainda impede
          </p>
          {/* ⚠️ TODAS as razões, e não só a primeira. Fechar uma não abre o
              portão, e uma lista truncada faria o operador consertar uma coisa
              por vez sem nunca ver o tamanho do caminho. */}
          <ul className="mt-1 space-y-1">
            {plano.bloqueadores.map((b) => (
              <li
                key={b}
                className="border-l-2 border-l-violet-400 pl-3 text-xs leading-relaxed text-slate-700 dark:border-l-violet-600 dark:text-slate-300"
              >
                {b}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

export default CartaoDoPlanoDeMensuracao;
