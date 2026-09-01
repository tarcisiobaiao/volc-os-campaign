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
 */
import React from 'react';

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
  tomDoEstado,
  type EstadoDePortao,
  type PerfilDeMensuracao,
  type PortoesDaMensuracao,
  type TomDoPortao,
} from '@/lib/trafego/portoes';
import type { PlanoDeMensuracao } from '@/lib/trafego/canais';

/**
 * As quatro cores, e o que cada uma afirma.
 *
 * ⚠️ `ignorado` NÃO é amarelo-de-atenção: é cinza-de-ignorância. Amarelo dá a
 * entender que alguém precisa agir sobre um problema conhecido, e o problema
 * aqui é que ninguém olhou.
 */
const TOM: Record<TomDoPortao, string> = {
  provado:
    'border-emerald-500/40 bg-emerald-500/10 text-emerald-800 dark:text-emerald-300',
  negado: 'border-rose-500/40 bg-rose-500/10 text-rose-800 dark:text-rose-300',
  ignorado:
    'border-slate-500/30 bg-slate-500/10 text-slate-700 dark:text-slate-400',
  ausente:
    'border-slate-500/20 bg-transparent text-slate-500 dark:text-slate-500',
};

function Portao({
  nome,
  estado,
}: {
  nome: keyof PortoesDaMensuracao;
  estado: EstadoDePortao;
}) {
  const tom = tomDoEstado(estado);
  return (
    <li
      className={`rounded-md border px-2.5 py-2 ${TOM[tom]}`}
      data-portao={nome}
      data-estado={estado}
    >
      <p className="text-xs font-medium leading-tight">{ROTULO_DO_PORTAO[nome]}</p>
      <p className="mt-0.5 text-[11px] uppercase tracking-wide opacity-80">
        {textoDoEstado(estado)}
      </p>
      {/* ⚠️ A exigência aparece SÓ quando o portão não está provado. Repeti-la
          num portão aberto viraria ruído, e o operador aprenderia a pular a
          linha justamente onde ela importa. */}
      {estado !== 'PRONTO' ? (
        <p className="mt-1 text-[11px] leading-snug opacity-90">
          {EXIGENCIA_DO_PORTAO[nome]}
        </p>
      ) : null}
    </li>
  );
}

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
        className="rounded-md border border-white/10 bg-black/10 p-2 text-xs leading-relaxed text-slate-600 dark:text-slate-400"
      >
        Nenhum perfil de mensuração foi declarado para este lançamento. Isso não
        significa que a campanha não mede — significa que ninguém disse qual
        oferta, qual etapa do funil e qual evento de negócio ela persegue, e sem
        isso duas ofertas da mesma conta ficam indistinguíveis.
      </p>
    );
  }
  return (
    <dl className="grid gap-2 sm:grid-cols-2" data-testid="perfil">
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
    <div className="grid gap-3 sm:grid-cols-2">
      {medicao.length > 0 ? (
        <div data-testid="bloqueadores-medicao">
          <p className="text-[11px] uppercase tracking-wide text-rose-700 dark:text-rose-400">
            O que impede medir ou observar
          </p>
          <ul className="mt-1 space-y-1">
            {medicao.map((b) => (
              <li
                key={b}
                className="border-l-2 border-l-rose-400 pl-3 text-xs leading-relaxed text-slate-700 dark:border-l-rose-600 dark:text-slate-300"
              >
                {b}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {outros.length > 0 ? (
        <div data-testid="bloqueadores-outros">
          <p className="text-[11px] uppercase tracking-wide text-slate-500 dark:text-slate-500">
            O que impede ativar, e não é sobre medir
          </p>
          <ul className="mt-1 space-y-1">
            {outros.map((b) => (
              <li
                key={b}
                className="border-l-2 border-l-slate-400 pl-3 text-xs leading-relaxed text-slate-700 dark:border-l-slate-600 dark:text-slate-300"
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
        <p className="text-[11px] uppercase tracking-wide text-slate-500 dark:text-slate-500">
          Portões
        </p>
        <ul className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {ORDEM_DOS_PORTOES.map((nome) => (
            <Portao key={nome} nome={nome} estado={portoes[nome]} />
          ))}
        </ul>
      </div>

      <BlocoDoPerfil perfil={perfil} customerId={customerId} />

      {plano ? (
        <dl className="grid gap-2 sm:grid-cols-2" data-testid="observacao">
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

/**
 * Quando chegou a última conversão — em três frases que não se confundem.
 *
 * ⚠️ `conversoes_na_janela === 0` com `vazio_confirmado` é um zero MEDIDO: a
 * ação existe, a janela foi consultada e nada chegou. É um fato caro, e escrevê-lo
 * como "sem dados" jogaria fora justamente a informação que custou a consulta.
 */
export function textoDoUltimoMomento(plano: PlanoDeMensuracao): string {
  const f = plano.frescor;
  if (f.estado === 'vazio_confirmado') {
    return 'nenhuma conversão — zero MEDIDO, não ausência de leitura';
  }
  if (f.estado === 'falhou') return 'a leitura do frescor falhou';
  if (f.estado === 'nao_coletado') return 'ninguém leu o frescor desta conta';
  if (f.estado === 'inelegivel') return 'a pergunta não cabe nesta conta';
  if (f.estado === 'nao_suportado') return 'a API não suporta esta leitura aqui';
  if (!f.ultima_conversao_em) return 'leitura parcial: sem data da última conversão';
  const dias =
    // ⚠️ `null` NUNCA vira um número grande. "Faz muito tempo" e "não sei" são
    // coisas diferentes, e um `999` viraria um gráfico com cara de dado.
    f.dias_desde_a_ultima === null
      ? 'há quantos dias, não se sabe'
      : `há ${f.dias_desde_a_ultima} d`;
  return `${f.ultima_conversao_em} (${dias})`;
}

/**
 * A meta é da conta ou da campanha? E foi LIDA ou INFERIDA?
 *
 * ⚠️ As duas perguntas viajam juntas porque a resposta honesta muda com as
 * duas. Antes do nascimento o nível é INFERIDO pela herança documentada — a
 * campanha não existe e o recurso não pode ser consultado —, e chamar isso de
 * "lido" afirmaria uma consulta que ninguém fez.
 */
export function textoDaProcedenciaDaMeta(plano: PlanoDeMensuracao): string {
  const m = plano.meta_efetiva;
  if (m.usa_meta_customizada) {
    return 'meta CUSTOMIZADA: ela não respeita primary_for_goal e este sistema não lê o recurso dela';
  }
  if (!m.nivel_decidido) {
    return 'não se sabe qual nível manda';
  }
  const onde = m.nivel === 'CAMPAIGN' ? 'da campanha' : 'herdada da conta';
  return m.nivel_herdado
    ? `${onde} — INFERIDA pela herança documentada, não lida do recurso`
    : `${onde} — lida do recurso`;
}

export default PainelDaMensuracao;
