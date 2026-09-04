/**
 * A verdade operacional da mensuração, numa tela só.
 *
 * ## O que ele existe para impedir
 *
 * Antes desta entrega o servidor emitia os portões e a tela DESCARTAVA quase
 * tudo: `data_manager_status` e `observability_status` estavam declarados em
 * `src/lib/trafego/canais.ts` e não apareciam em JSX nenhum; `activation_blockers`
 * e `smart_bidding_eligible` não tinham consumidor; e a cobertura de click IDs,
 * o dono da ação e o auto-tagging — os doze campos de `InventarioDeMarcacao` —
 * nunca chegaram à tela. O operador aprovava o gasto sem ver para o que a
 * campanha ia otimizar.
 *
 * ## As três regras deste arquivo
 *
 * **1. Nada é derivado aqui.** Os sete portões, os bloqueadores e a
 * aplicabilidade do perfil vêm prontos do servidor, que é quem tem a evidência.
 * A tradução mora em `lib/trafego/portoes.ts`, junto do contrato que ela lê.
 *
 * **2. Verde só com prova.** `PRONTO` é o único estado que pinta positivo.
 * `PARCIAL` e `INDETERMINADO` são "não sei" — e não degraus para o verde.
 * Nenhum selo desta tela nasce de configuração: auto-tagging ligado aparece
 * dizendo, na mesma linha, que ele não é conversão chegando.
 *
 * **3. Três frases, nunca "sem dados".** `não medido`, `zero medido` e `a
 * leitura falhou` pedem coisas opostas — ler, consertar a instrumentação,
 * tentar de novo. O servidor pagou caro para manter a distinção e a tela não a
 * desfaz.
 *
 * ## O que ele NÃO mostra
 *
 * ⚠️ Nenhum `gclid`, `wbraid` ou `gbraid`: são dado de usuário. O que aparece é
 * o TIPO suportado. E nenhum `chave_intencao` inteira nem impressão completa —
 * doze caracteres bastam para reconciliar e não convidam a copiar identidade.
 *
 * ## Por que a tabela de tom não mora mais aqui
 *
 * O `TOM` local (linhas 66-74 da versão anterior) discordava do painel irmão
 * sobre o MESMO veredito: aqui `BLOQUEADO` era vermelho e `INDETERMINADO` era
 * ardósia-de-ignorância; em `PortoesDoCanal.tsx:57-62` `BLOQUEADO` era âmbar e
 * `INDETERMINADO` era ardósia. A correspondência única agora vem de
 * `bancada/paradas/portoesVisual.ts`.
 *
 * ⚠️ Isso mudou um SIGNIFICADO, e de propósito: `PARCIAL` e `INDETERMINADO`
 * eram cinza e passaram a âmbar. O comentário antigo argumentava que amarelo
 * sugeriria um problema conhecido enquanto o problema é que ninguém olhou — mas
 * cinza é a cor de "neutro/não se aplica" no resto do produto, e usá-la para
 * ignorância fazia "ninguém leu" parecer um degrau vencido ao lado de um
 * `NAO_APLICAVEL`. Âmbar é a cor de "não sei" na tabela canônica
 * (`portoesVisual.ts:19-22`), e a palavra e o glifo continuam separando os dois
 * casos sem depender da tinta.
 */
import React from 'react';

import { cn } from '@/lib/utils';
import { ChipDeEstado } from '@/components/trafego/bancada/ChipDeEstado';
import {
  GLIFO_DO_ESTADO,
  TOM_DO_ESTADO,
} from '@/components/trafego/bancada/paradas/portoesVisual';
import {
  EXIGENCIA_DO_PORTAO,
  ORDEM_DOS_PORTOES,
  ROTULO_DO_FUNIL,
  ROTULO_DO_PORTAO,
  separarBloqueadores,
  textoDaCoberturaDeClickIds,
  textoDaFonte,
  textoDaJanela,
  textoDaRegraDeValor,
  textoDoConsentimento,
  textoDoDonoDaAcao,
  textoDoEstado,
  type EstadoDePortao,
  type PerfilDeMensuracao,
  type PortoesDaMensuracao,
} from '@/lib/trafego/portoes';
import type { PlanoDeMensuracao } from '@/lib/trafego/canais';
import { Fato } from '@/components/trafego/canais/Fato';
import {
  DESCRICAO_DA_MENSURACAO,
  FIO_DE_CARTAO,
  FIO_DO_BLOQUEIO,
  FIO_DO_TOM,
} from '@/components/trafego/canais/tonsDoCockpit';
import {
  textoDaProcedenciaDaMeta,
  textoDoUltimoMomento,
} from '@/components/trafego/canais/textosDaMensuracao';

/* ⚠️ Re-export de compatibilidade. As duas funções moram em
   `./textosDaMensuracao.ts` porque tradução de estado em frase é lógica pura, e
   não JSX; mas quem as consome hoje as importa DAQUI
   (`__tests__/painel-da-mensuracao.test.tsx:41-45`), e esse arquivo de teste não
   é propriedade desta entrega. A advertência do `react-refresh` está silenciada
   com o motivo à vista em vez de escondida atrás de um `--max-warnings` frouxo:
   o custo real é o fast-refresh deste módulo, e ele já existia antes. */
// eslint-disable-next-line react-refresh/only-export-components
export { textoDaProcedenciaDaMeta, textoDoUltimoMomento };

function Portao({
  nome,
  estado,
}: {
  nome: keyof PortoesDaMensuracao;
  estado: EstadoDePortao;
}) {
  // ⚠️ O `??` não inventa estado: ele cobre um servidor que mande um valor fora
  // do contrato, e o desenha como IGNORÂNCIA — nunca como prova.
  const tom = TOM_DO_ESTADO[estado] ?? TOM_DO_ESTADO.INDETERMINADO;
  const Glifo = GLIFO_DO_ESTADO[estado] ?? GLIFO_DO_ESTADO.INDETERMINADO;
  return (
    <li
      // Poço com fio de 2px no topo (`design.md:99`), e não cartão elevado:
      // esta lista já vive dentro de uma superfície de trabalho.
      className={cn(
        'rounded-md border border-border bg-muted/20 p-3',
        FIO_DE_CARTAO,
        FIO_DO_TOM[tom],
      )}
      data-portao={nome}
      data-estado={estado}
    >
      <p className="text-sm font-medium leading-tight text-foreground">
        {ROTULO_DO_PORTAO[nome]}
      </p>
      {/* Glifo + palavra + descrição: cor nunca é o único portador
          (`design.md:105`). A palavra é a mesma que `textoDoEstado` já dava. */}
      <ChipDeEstado
        className="mt-2"
        glifo={Glifo}
        palavra={textoDoEstado(estado)}
        descricao={
          DESCRICAO_DA_MENSURACAO[estado] ?? DESCRICAO_DA_MENSURACAO.INDETERMINADO
        }
        tom={tom}
      />
      {/* ⚠️ A exigência aparece SÓ quando o portão não está provado. Repeti-la
          num portão aberto viraria ruído, e o operador aprenderia a pular a
          linha justamente onde ela importa. */}
      {estado !== 'PRONTO' ? (
        <p className="mt-2 text-sm leading-6 text-muted-foreground text-pretty">
          {EXIGENCIA_DO_PORTAO[nome]}
        </p>
      ) : null}
    </li>
  );
}

/**
 * O perfil — o que esta campanha DECIDIU medir.
 *
 * ⚠️ `perfil: null` é "ninguém declarou os eixos de negócio deste lançamento", e
 * NÃO "esta campanha não mede nada". A frase de ausência diz isso, porque
 * inventar `evento: conversão` faria dois nichos da mesma conta voltarem a
 * colidir com a aparência de estarem separados.
 */
function BlocoDoPerfil({
  perfil,
  customerId,
}: {
  perfil: PerfilDeMensuracao | null;
  customerId: string;
}) {
  if (!perfil) {
    return (
      <p
        data-testid="perfil-ausente"
        // `border-white/10 bg-black/10` só existia no tema escuro: no claro, que
        // é o padrão desta cena (`design.md:139`), virava mancha sem borda.
        className="rounded-md border border-border bg-muted/20 p-3 text-sm leading-6 text-muted-foreground text-pretty"
      >
        Nenhum perfil de mensuração foi declarado para este lançamento. Isso não
        significa que a campanha não mede — significa que ninguém disse qual
        oferta, qual etapa do funil e qual evento de negócio ela persegue, e sem
        isso duas ofertas da mesma conta ficam indistinguíveis.
      </p>
    );
  }
  return (
    <dl className="grid gap-3 sm:grid-cols-2" data-testid="perfil">
      <Fato
        rotulo="perfil de mensuração"
        valor={`${perfil.negocio} · ${perfil.intencao}`}
        ressalva={`funil de ${ROTULO_DO_FUNIL[perfil.funil]}`}
      />
      <Fato rotulo="evento de negócio" valor={perfil.evento} />
      <Fato
        rotulo="quem mede"
        valor={textoDoDonoDaAcao(perfil, customerId)}
        ressalva={perfil.semantica}
      />
      <Fato
        rotulo="fonte do sinal"
        valor={textoDaFonte(perfil.fonte_do_sinal)}
        // ⚠️ A ressalva existe SÓ no caminho declarado, e é ela que impede o
        // operador de ler "há caminho" como "está medindo".
        ressalva={
          perfil.fonte_do_sinal === 'caminho_declarado'
            ? 'a via existe e não está trazendo evento: é instrumentação a conferir, não configuração a criar.'
            : null
        }
      />
      <Fato
        rotulo="regra de valor"
        valor={textoDaRegraDeValor(perfil.regra_de_valor)}
      />
      <Fato
        rotulo="janela e atribuição"
        valor={textoDaJanela(perfil.janela)}
        ressalva={
          perfil.janela.estado === 'declarada' ? null : perfil.janela.causa
        }
      />
      <Fato
        rotulo="consentimento da conta"
        valor={textoDoConsentimento(perfil.consentimento)}
        // ⚠️ A distinção que a Data Manager exige e que a tela não pode apagar:
        // o aceite é do ANUNCIANTE; o consentimento do visitante viaja com o
        // evento e não é conhecível aqui.
        ressalva="é o aceite de termos do anunciante, não o consentimento do visitante."
      />
      <Fato
        rotulo="identidade do perfil"
        // Doze caracteres bastam para reconciliar e não convidam a copiar
        // identidade inteira para fora da tela.
        valor={`${perfil.chave.slice(0, 12)}…`}
      />
    </dl>
  );
}

/**
 * Os bloqueadores, em DOIS grupos.
 *
 * ⚠️ Uma lista só faria o operador tentar consertar a política com
 * instrumentação. "Não pode medir" e "não está autorizado" fecham a mesma porta
 * por motivos que não se comparam, e só o primeiro contradiz o portão do lance.
 */
function Bloqueadores({
  todos,
  materiais,
}: {
  todos: string[];
  materiais?: string[];
}) {
  const { medicao, outros } = separarBloqueadores(todos, materiais);
  if (todos.length === 0) return null;
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {medicao.length > 0 ? (
        <div data-testid="bloqueadores-medicao">
          {/* ⚠️ A palavra do título NÃO é vermelha. A cor semântica vive na
              borda e no glifo — escrever o rótulo com a cor do estado é o jeito
              mais eficiente de tornar ilegível exatamente o que decide
              (`ChipDeEstado.tsx:25-28`). O vermelho está no fio de cada item. */}
          <p className="text-sm font-semibold text-foreground">
            O que impede medir ou observar
          </p>
          <ul className="mt-1.5 space-y-1.5">
            {medicao.map((b) => (
              <li
                key={b}
                // `border-l` de 1px: `design.md:130` proíbe faixa lateral
                // colorida acima disso, e a versão anterior usava `border-l-2`.
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
      {outros.length > 0 ? (
        <div data-testid="bloqueadores-outros">
          <p className="text-sm font-semibold text-foreground">
            O que impede ativar, e não é sobre medir
          </p>
          <ul className="mt-1.5 space-y-1.5">
            {outros.map((b) => (
              <li
                key={b}
                // Neutro de propósito: não é falha de medição, é autorização —
                // e pintá-lo de vermelho ensinaria o operador a tentar
                // consertar política com instrumentação.
                className={cn(
                  'border-l pl-3 text-sm leading-6 text-foreground text-pretty',
                  FIO_DO_BLOQUEIO.ausencia,
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

export function PainelDaMensuracao({
  portoes,
  perfil,
  plano,
  bloqueadores,
  bloqueadoresMateriais,
  customerId,
  persistido,
  planoId,
  porque,
}: {
  portoes: PortoesDaMensuracao;
  perfil: PerfilDeMensuracao | null;
  /** ⚠️ `null` = ninguém leu os recursos que decidem. Nunca "não há plano". */
  plano: PlanoDeMensuracao | null;
  bloqueadores: string[];
  bloqueadoresMateriais?: string[];
  customerId: string;
  persistido: boolean;
  planoId?: string | null;
  /** Por que não está persistido, quando não está. Vem do servidor. */
  porque?: string;
}) {
  return (
    <section className="space-y-4" data-testid="painel-da-mensuracao">
      <div>
        <p className="text-sm font-semibold text-foreground">Portões</p>
        <ul className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {ORDEM_DOS_PORTOES.map((nome) => (
            <Portao key={nome} nome={nome} estado={portoes[nome]} />
          ))}
        </ul>
      </div>

      <BlocoDoPerfil perfil={perfil} customerId={customerId} />

      {plano ? (
        <dl className="grid gap-3 sm:grid-cols-2" data-testid="observacao">
          <Fato
            rotulo="último momento observado"
            // ⚠️ TRÊS frases distintas, e nenhuma delas é "sem dados". O
            // servidor separa `vazio_confirmado` (zero MEDIDO) de
            // `nao_coletado` (ninguém perguntou) e de `falhou` (perguntou e
            // quebrou), e as três pedem ações opostas.
            valor={textoDoUltimoMomento(plano)}
            ressalva={plano.frescor.causa}
          />
          <Fato
            rotulo="cobertura de click IDs"
            valor={textoDaCoberturaDeClickIds(
              plano.marcacao.click_ids_suportados,
              plano.marcacao.auto_tagging,
            )}
            ressalva="transportar o identificador é pré-requisito de reconciliação offline; não é conversão chegando."
          />
          <Fato
            rotulo="meta herdada ou da campanha"
            valor={textoDaProcedenciaDaMeta(plano)}
          />
          <Fato
            rotulo="registro do plano"
            valor={
              persistido
                ? `gravado · ${(planoId ?? '').slice(0, 8) || 'sem id'}…`
                : 'não gravado'
            }
            // ⚠️ A razão vem do servidor. "Não gravado" sem causa é
            // indistinguível de "este servidor não respondeu isto".
            ressalva={persistido ? null : porque ?? null}
          />
        </dl>
      ) : null}

      <Bloqueadores todos={bloqueadores} materiais={bloqueadoresMateriais} />
    </section>
  );
}

export default PainelDaMensuracao;
