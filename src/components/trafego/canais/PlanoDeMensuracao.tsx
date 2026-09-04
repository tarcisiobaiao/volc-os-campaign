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
 *
 * ## O que mudou na superfície
 *
 * O `Fato` que morava aqui (linhas 33-55 da versão anterior) era a terceira
 * cópia byte a byte do mesmo componente e foi consolidado em `./Fato.tsx`. A
 * paleta crua saiu inteira: ardósia no texto, preto a 10% no poço e violeta na
 * faixa lateral. O poço de preto sobre borda branca só funciona no tema escuro
 * — no claro ele é uma mancha cinza sem borda —, e o vocabulário semântico de
 * `design.md:105` é fechado, sem violeta.
 */
import React from 'react';

import { cn } from '@/lib/utils';
import {
  textoDaFonteDoSinal,
  textoDaMetaEfetiva,
  textoDoFrescor,
  type PlanoDeMensuracao,
} from '@/lib/trafego/canais';
import type { PlanoPersistido, VinculoDoPlano } from '@/types/trafego';
import { Fato } from '@/components/trafego/canais/Fato';
import { FIO_DO_BLOQUEIO } from '@/components/trafego/canais/tonsDoCockpit';

/**
 * O registro do plano — CALCULADO, PERSISTIDO e VINCULADO são três coisas.
 *
 * ⚠️ Nenhuma delas é derivada aqui. Um `plano.campaign_id` preenchido NÃO prova
 * vínculo gravado, e ausência de `persistencia` NÃO é "não gravado": é "este
 * servidor não respondeu isto". Inventar qualquer um dos dois faria a tela
 * afirmar a existência de um registro que ninguém escreveu.
 */
function Registro({
  persistencia,
  vinculo,
}: {
  persistencia?: PlanoPersistido | null;
  vinculo?: VinculoDoPlano | null;
}) {
  if (!persistencia && !vinculo) return null;
  return (
    // Poço, não cartão: `bg-muted/20` + `border-border`, sem sombra
    // (`design.md:100`). Era `border-white/10 bg-black/10`, que só existia no
    // tema escuro e sumia no claro, que é o padrão desta cena.
    <div className="mt-3 rounded-md border border-border bg-muted/20 p-3">
      <p className="text-sm font-semibold text-foreground">Registro</p>
      {persistencia ? (
        <p className="mt-1 text-sm leading-6 text-muted-foreground text-pretty">
          {persistencia.persistido
            ? `gravado · ${persistencia.plano_id ?? 'sem id'}`
            : 'ainda não gravado'}
          {persistencia.porque ? ` — ${persistencia.porque}` : ''}
        </p>
      ) : null}
      {vinculo ? (
        <p className="mt-1 text-sm leading-6 text-muted-foreground text-pretty">
          {vinculo.vinculado
            ? `vinculado à campanha ${vinculo.campaign_id ?? '—'}${
                vinculo.ja_estava ? ' (já estava)' : ''
              }`
            : `não vinculado${vinculo.porque ? ` — ${vinculo.porque}` : ''}`}
          {!vinculo.vinculado && vinculo.proxima_acao
            ? ` · próxima ação: ${vinculo.proxima_acao}`
            : ''}
        </p>
      ) : null}
      {vinculo?.observado_antes_do_nascimento ? (
        /* ⚠️ A ressalva que impede a linha de mentir daqui a seis meses. Os
           estados de leitura desta versão descrevem uma observação feita ANTES
           de a campanha existir: `metas_da_campanha_estado` é `inelegivel`
           porque a pergunta não cabia naquele instante, e não porque a campanha
           tenha metas inelegíveis. */
        <p className="mt-1 text-sm leading-snug text-muted-foreground text-pretty">
          Esta leitura foi feita antes de a campanha existir; os estados acima
          descrevem aquele instante, não o de agora.
        </p>
      ) : null}
    </div>
  );
}

export function CartaoDoPlanoDeMensuracao({
  plano,
  titulo = 'Plano de mensuração',
  persistencia,
  vinculo,
}: {
  plano: PlanoDeMensuracao;
  titulo?: string;
  /** ⚠️ `undefined` = o servidor não respondeu isto. Nunca "não gravado". */
  persistencia?: PlanoPersistido | null;
  /** ⚠️ `undefined` = o servidor não respondeu isto. Nunca "não vinculado". */
  vinculo?: VinculoDoPlano | null;
}) {
  return (
    <div>
      <p className="text-sm font-semibold text-foreground">
        {titulo}
        {/* ⚠️ Campanha ainda não nascida é o caso NORMAL — o plano existe ANTES
            do nascimento, e é esse o ponto. Omitir a informação faria o
            operador ler a ausência do id como defeito. */}
        {plano.campaign_id
          ? ` · campanha ${plano.campaign_id}`
          : ' · antes do nascimento'}
      </p>
      <dl className="mt-2 grid gap-3 sm:grid-cols-2">
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
          // ⚠️ TRÊS respostas, e não duas. "não resolvido" sozinho dizia ao
          // mesmo tempo "ninguém leu", "li e não há destino endereçável" e "a
          // leitura falhou" — e as três pedem coisas diferentes. A causa vem do
          // servidor e é ela que separa.
          //
          // ⚠️ E resolvido NÃO é pronto: ter endereço não é ter entregue nada
          // nele. Um operador que leia "resolvido" como "a ingestão offline
          // funciona" para de procurar o motivo de as conversões não chegarem.
          ressalva={
            plano.destino.resolvido
              ? 'endereço resolvido não é upload funcionando: nenhum envio pela Data Manager foi provado nesta conta.'
              : plano.destino.causa ?? 'o servidor não disse por que não resolveu.'
          }
        />
      </dl>
      <Registro persistencia={persistencia} vinculo={vinculo} />
      {plano.bloqueadores.length > 0 ? (
        <div className="mt-3">
          <p className="text-sm font-semibold text-foreground">
            O que ainda impede
          </p>
          {/* ⚠️ TODAS as razões, e não só a primeira. Fechar uma não abre o
              portão, e uma lista truncada faria o operador consertar uma coisa
              por vez sem nunca ver o tamanho do caminho. */}
          <ul className="mt-1.5 space-y-1.5">
            {plano.bloqueadores.map((b) => (
              <li
                key={b}
                // ⚠️ O violeta saiu por dois motivos, e só um deles é de cor:
                // `design.md:105` fecha o vocabulário semântico em seis tokens,
                // e nenhum é violeta; e `design.md:130` proíbe faixa lateral
                // colorida acima de 1px — este `border-l` é de 1px.
                //
                // O tom é o de `sem_prova`: o que impede um plano de mensuração
                // é sempre falta de prova de medição, que é a mesma classe de
                // bloqueio que `PainelDaMensuracao` já pintava de vermelho.
                className={cn(
                  'border-l pl-3 text-sm leading-6 text-foreground text-pretty',
                  FIO_DO_BLOQUEIO.sem_prova,
                )}
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
