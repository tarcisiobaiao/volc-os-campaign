/**
 * `/trafego/campanhas/:volcCampaignId` — identidade canônica.
 *
 * Aceita somente o identificador interno. 404 é "não encontrada"; qualquer
 * outro erro é indisponibilidade. O manifesto do backend define o que oferecer;
 * `null` continua `null`. Zero Google Ads, zero escrita, zero varredura da
 * listagem paginada.
 */
import React from 'react';
import { Link, useParams } from 'react-router-dom';

import { Layout } from '@/components/layout/Layout';
import { IdentidadeDeCanal } from '@/components/trafego/hub/IdentidadeDeCanal';
import {
  AUSENTE,
  contagem,
  dinheiro,
  frescorLegivel,
  lidoHa,
  palavraDaEstrategia,
  palavraDaVeiculacao,
  palavraDoCanal,
  procedenciaLegivel,
} from '@/components/trafego/inventario/formato';
import {
  SeloDeEstadoExterno,
  SeloDePresenca,
} from '@/components/trafego/inventario/Selos';
import {
  SEM_DATA,
  medidaSemData,
  tetoDaCampanha,
} from '@/components/trafego/inventario/LinhaDeCampanha';
import { CodigoDaOcorrencia } from '@/components/trafego/inventario/EstadosDoInventario';
import { EscadaDeEntrega } from '@/components/trafego/diagnostico/EscadaDeEntrega';
import { CaixaDePropostas } from '@/components/trafego/diagnostico/CaixaDePropostas';
import { VisaoDoCanal } from '@/components/trafego/canal/VisaoDoCanal';
import { EstruturaDoCanal } from '@/components/trafego/hub/EstruturaDoCanal';
import { RevisarCorrespondencia } from '@/components/trafego/vinculo/RevisarCorrespondencia';
import { FaixaDeLaboratorio } from '@/components/trafego/laboratorio/SeloDePrototipo';
import { useCapacidades } from '@/hooks/useCapacidades';
import { useCampanhaCanonica } from '@/hooks/useCampanhaCanonica';
import { useDiagnosticoDeEntrega } from '@/hooks/useDiagnosticoDeEntrega';
import type { CampanhaCanonica } from '@/types/trafego';

const CampanhaCanonPage: React.FC = () => {
  const { volcCampaignId = '' } = useParams();
  const leitura = useCampanhaCanonica(volcCampaignId);
  // ⚠️ `emLaboratorio` é `false` enquanto a leitura não chega. A faixa some por
  // omissão, e nunca aparece por otimismo — anunciar laboratório sem saber se
  // ele está ligado é anunciar que nada tem consequência.
  const { emLaboratorio } = useCapacidades();

  return (
    <Layout>
      <div className="overflow-x-clip p-4 md:p-8">
        <FaixaDeLaboratorio ligado={emLaboratorio} className="mb-4" />
        <nav aria-label="você está em" className="text-[12px] text-muted-foreground">
          <ol className="flex flex-wrap items-center gap-1.5">
            <li>
              <Link to="/trafego" className="underline-offset-2 hover:underline">
                Tráfego
              </Link>
            </li>
            <li aria-hidden>/</li>
            <li>
              <Link to="/trafego?aba=campanhas" className="underline-offset-2 hover:underline">
                Campanhas
              </Link>
            </li>
            <li aria-hidden>/</li>
            <li className="tabular text-foreground">{volcCampaignId || '—'}</li>
          </ol>
        </nav>

        {leitura.carregando && (
          <p className="mt-6 text-sm text-muted-foreground" role="status">
            lendo a campanha
          </p>
        )}

        {leitura.naoEncontrada && !leitura.carregando && (
          <EstadoNaoEncontrada id={volcCampaignId} />
        )}

        {leitura.falhou && leitura.ocorrencia && (
          <EstadoIndisponivel ocorrencia={leitura.ocorrencia} />
        )}

        {leitura.detalhe && <Detalhe detalhe={leitura.detalhe} />}
      </div>
    </Layout>
  );
};

const EstadoNaoEncontrada: React.FC<{ id: string }> = ({ id }) => (
  <>
    <header className="mt-4 border-b border-border pb-4">
      <p className="kicker">campanha</p>
      <h1 className="mt-1 font-display text-2xl font-bold tracking-tight md:text-3xl">
        Campanha não encontrada
      </h1>
    </header>
    <p className="mt-6 max-w-[70ch] text-sm leading-relaxed text-muted-foreground" role="status">
      Não há campanha com o identificador interno {id || '—'}. Um id externo da
      conta de anúncio não abre esta página: a identidade é só a interna.
    </p>
  </>
);

const EstadoIndisponivel: React.FC<{
  ocorrencia: NonNullable<ReturnType<typeof useCampanhaCanonica>['ocorrencia']>;
}> = ({ ocorrencia }) => (
  <>
    <header className="mt-4 border-b border-border pb-4">
      <p className="kicker">campanha</p>
      <h1 className="mt-1 font-display text-2xl font-bold tracking-tight md:text-3xl">
        Não consegui ler esta campanha
      </h1>
    </header>
    <div className="mt-6 max-w-[70ch]" role="alert">
      <p className="text-sm leading-relaxed">{ocorrencia.mensagem}</p>
      <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
        {ocorrencia.proximoPasso}
      </p>
      <CodigoDaOcorrencia ocorrencia={ocorrencia} />
    </div>
  </>
);

/**
 * A ordem das seções é a da SPEC §8, e ela não é arbitrária.
 *
 * 1. identidade · 2. entrega e frescor · 3. resumo medido · 4. diagnóstico ·
 * 5. vínculo e linhagem · 6. estrutura do canal · 7. histórico e recibos ·
 * 8. trilho de ações.
 *
 * A sequência responde a uma pergunta de cada vez, na ordem em que o operador
 * as faz: **o que é isto** → **está entregando, e de quando é essa informação**
 * → **quanto foi medido** → **por que está assim** → **de quem é** → **como é
 * feita por dentro** → **o que já aconteceu** → **o que posso fazer**.
 *
 * ⚠️ Diagnóstico depois do número medido, e não antes. Um veredito antes do
 * dado que o sustenta é um palpite com autoridade: o operador lê a conclusão,
 * forma opinião, e só então descobre de que leitura ela saiu.
 */
const Detalhe: React.FC<{ detalhe: CampanhaCanonica }> = ({ detalhe }) => {
  const { campanha, identidade, conta, manifesto } = detalhe;
  const c = campanha;

  return (
    <>
      {/* ── 1 · IDENTIDADE ──────────────────────────────────────────────── */}
      <header className="mt-4 border-b border-border pb-4">
        <p className="kicker">campanha</p>
        <h1 className="mt-1 font-display text-2xl font-bold tracking-tight md:text-3xl">
          {c.nome}
        </h1>
        <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1.5">
          <IdentidadeDeCanal rede="google" canal={c.canal} />
          <span className="text-[12px] text-muted-foreground">
            Google Ads · conta {identidade.conta_externa ?? conta.customer_id ?? AUSENTE}
          </span>
        </div>

        {/* Os identificadores ficam no cabeçalho, em linha, porque são
            resposta de conferência — não decisão. */}
        <dl className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-[12px]">
          <IdentificadorEmLinha rotulo="identificador interno" valor={identidade.volc_campaign_id} />
          <IdentificadorEmLinha rotulo="id no Google" valor={identidade.id_externo} />
          <IdentificadorEmLinha
            rotulo="linhagem"
            valor={identidade.campaign_lineage_id}
            ausenteDiz="não declarada no lançamento"
          />
        </dl>
      </header>

      {/* ── 2 · ENTREGA, FRESCOR E FONTE ────────────────────────────────── */}
      <Secao titulo="Entrega e frescor" kicker="estado observado" id="entrega">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <SeloDeEstadoExterno estado={c.estado_externo} />
          <SeloDePresenca presenca={c.presenca} />
          {palavraDaVeiculacao(c.veiculacao) && (
            <span className="text-[13px]">{palavraDaVeiculacao(c.veiculacao)}</span>
          )}
        </div>
        <p className="mt-2 max-w-[70ch] text-[12px] leading-relaxed text-muted-foreground">
          {/* ⚠️ Frescor da CONTA, não da campanha: é a leitura da conta que
              carimba estes números, e dizer o contrário sugeriria uma medida
              mais recente do que a que existe. */}
          O que está nesta tela veio da última leitura desta conta ·{' '}
          {frescorLegivel(conta.frescor).palavra} ·{' '}
          {procedenciaLegivel(c.procedencia).palavra}.
        </p>
      </Secao>

      {/* ── 3 · RESUMO MEDIDO ───────────────────────────────────────────── */}
      <Secao titulo="Resumo medido" kicker="numeros" id="resumo">
        {/* ⚠️ Estes campos JÁ CHEGAVAM no contrato e não eram desenhados em
            lugar nenhum desta página. O operador via o inventário, abria a
            campanha, e a página sabia menos que a lista de onde ele veio. */}
        {medidaSemData(c) ? (
          /* ⚠️ NÚMERO SEM DATA DE LEITURA NÃO É EXIBIDO.
             Achado por revisão adversarial: esta grade imprimia impressões,
             cliques e custo mesmo com `entrega.leitura` nulo, e ainda carimbava
             "medido na leitura de sem data de leitura". O inventário recusa o
             mesmo caso há tempos, por `medidaSemData` — a regra existia, escrita
             uma vez, e esta página era a segunda cópia que nunca a consultou.
             O DESIGN.md é literal: "Do not present a number without freshness". */
          <p className="max-w-[70ch] text-[13px] leading-relaxed" role="status">
            {SEM_DATA}.{' '}
            <span className="text-muted-foreground">
              A conta devolveu números para esta campanha e não devolveu a hora em
              que os mediu. Eles existem — mas sem saber de quando são, não dá para
              decidir gasto com eles.
            </span>
          </p>
        ) : (
          <>
            <dl className="grid gap-x-8 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
              <Medida
                rotulo="lance"
                valor={dinheiro(c.lance_micros, c.entrega?.moeda ?? null)}
                nota={palavraDaEstrategia(c.estrategia)}
              />
              <Medida
                rotulo="orçamento diário"
                valor={dinheiro(c.verba_diaria_micros, c.entrega?.moeda ?? null)}
              />
              {/* ⚠️ `tetoDaCampanha`, e não `contagem`.
                  "não se aplica" (lance automático: não há lance fixo para
                  dividir) e "—" (não deu para calcular) são respostas OPOSTAS, e
                  o docblock daquela função diz exatamente isso. Imprimir `—` nos
                  dois casos faria o operador concluir que a leitura está furada
                  quando ela está completa. O inventário já dizia certo; esta
                  página dizia errado sobre o MESMO campo. */}
              <Medida
                rotulo="teto estimado de cliques"
                valor={tetoDaCampanha(c).texto}
                nota={tetoDaCampanha(c).explica}
              />
              <Medida rotulo="impressões" valor={contagem(c.entrega?.impressoes ?? null)} />
              <Medida rotulo="cliques" valor={contagem(c.entrega?.cliques ?? null)} />
              <Medida
                rotulo="custo"
                valor={dinheiro(c.entrega?.custo_micros ?? null, c.entrega?.moeda ?? null)}
              />
            </dl>
            <p className="mt-3 text-[11px] text-muted-foreground">
              {/* Nenhum número decisório sem frescor (SPEC §4.1). */}
              medido na leitura de {lidoHa(c.entrega?.leitura?.idade_s ?? null)}
            </p>
          </>
        )}
      </Secao>

      {/* ── 4 · DIAGNÓSTICO ─────────────────────────────────────────────── */}
      <Diagnostico volcCampaignId={identidade.volc_campaign_id} />

      {/* ── 5 · VÍNCULO E LINHAGEM ──────────────────────────────────────── */}
      <div className="mt-10 border-t border-border pt-6">
        <RevisarCorrespondencia
          volcCampaignId={identidade.volc_campaign_id}
          nomeDaCampanha={c.nome}
          contaExterna={identidade.conta_externa ?? conta.customer_id}
          idExterno={identidade.id_externo}
          estadoExterno={c.estado_externo}
        />
      </div>

      {/* ── 6 · ESTRUTURA DO CANAL ──────────────────────────────────────── */}
      {manifesto && (
        <Secao titulo="Estrutura deste canal" kicker="como é feita por dentro" id="estrutura">
          <EstruturaDoCanal
            rede="google"
            canal={c.canal}
            aba="estrutura"
            manifesto={manifesto}
          />
        </Secao>
      )}

      {/* ── 7 · HISTÓRICO E RECIBOS ─────────────────────────────────────── */}
      <Secao titulo="Histórico e recibos" kicker="o que já aconteceu" id="historico">
        {/* ⚠️ Ausência DECLARADA, e não seção omitida.
            Uma página que simplesmente não mostra histórico lê-se como "nada
            aconteceu com esta campanha" — que é uma afirmação, e não a que se
            pretende. O evento operacional existe no banco (`trafego_evento`) e
            ainda não tem rota de leitura; enquanto não tiver, a tela diz isso. */}
        <p className="max-w-[70ch] text-[13px] leading-relaxed text-muted-foreground">
          Ainda não há leitura de histórico nesta versão. Isto é ausência de
          capacidade, não de acontecimento —{' '}
          <strong className="font-medium text-foreground">
            nada aqui afirma que esta campanha não mudou
          </strong>
          . Mudanças feitas no painel do Google aparecem lá, no histórico de alterações da conta.
        </p>
      </Secao>

      {/* ── 8 · TRILHO DE AÇÕES ─────────────────────────────────────────── */}
      <Secao titulo="O que dá para fazer aqui" kicker="ações" id="acoes">
        <VisaoDoCanal
          manifesto={manifesto}
          rotuloDeReserva={palavraDoCanal(c.canal) ?? 'este canal'}
        />
        {c.cockpit_href && (
          <p className="mt-4 text-[13px]">
            <Link
              to={c.cockpit_href}
              className="text-primary underline-offset-2 hover:underline"
            >
              Abrir o cockpit de lançamento desta campanha
            </Link>
          </p>
        )}
      </Secao>
    </>
  );
};

/** Uma seção da página canônica. Mesma moldura para as oito. */
/**
 * ⚠️ O `id` sai de um identificador SEM ESPAÇO, e não do kicker.
 *
 * Ele era `sec-${kicker}`, e três kickers têm espaço: "estado observado", "o que
 * já aconteceu", "como é feita por dentro". `aria-labelledby` é uma LISTA de
 * IDREFs separada por espaço — `aria-labelledby="sec-estado observado"` procura
 * dois ids, `sec-estado` e `observado`, e nenhum existe. Resultado medido: três
 * das oito seções ficavam sem nome acessível, entre elas a que carrega o
 * frescor. Um `id` com espaço também é HTML inválido.
 */
const Secao: React.FC<{
  titulo: string;
  kicker: string;
  /** Identificador estável, sem espaço. É ele que o `aria-labelledby` cita. */
  id: string;
  children: React.ReactNode;
}> = ({ titulo, kicker, id, children }) => (
  <section className="mt-10 border-t border-border pt-6" aria-labelledby={`sec-${id}`}>
    <p className="kicker">{kicker}</p>
    <h2
      id={`sec-${id}`}
      className="mt-1 font-display text-lg font-semibold tracking-tight md:text-xl"
    >
      {titulo}
    </h2>
    <div className="mt-4">{children}</div>
  </section>
);

/**
 * Um número medido, com o rótulo acima e a ressalva abaixo.
 *
 * ⚠️ `AUSENTE` já vem dos formatadores quando o valor é nulo — ausência não
 * vira zero em nenhum caminho desta grade.
 */
const Medida: React.FC<{ rotulo: string; valor: string; nota?: string | null }> = ({
  rotulo,
  valor,
  nota,
}) => (
  <div className="min-w-0">
    <dt className="kicker">{rotulo}</dt>
    <dd className="tabular mt-0.5 font-display text-[17px] font-semibold leading-tight">
      {valor}
    </dd>
    {nota && <p className="mt-0.5 text-[11px] leading-snug text-muted-foreground">{nota}</p>}
  </div>
);

/** Identificador de conferência: rótulo e valor na mesma linha. */
const IdentificadorEmLinha: React.FC<{
  rotulo: string;
  valor: string | null;
  ausenteDiz?: string;
}> = ({ rotulo, valor, ausenteDiz }) => (
  <div className="flex min-w-0 items-baseline gap-1.5">
    <dt className="text-muted-foreground">{rotulo}</dt>
    <dd className="tabular min-w-0 break-all font-medium">
      {valor ?? (
        <span className="font-normal text-muted-foreground">{ausenteDiz ?? AUSENTE}</span>
      )}
    </dd>
  </div>
);

// ── o diagnóstico de entrega ────────────────────────────────────────────────

/**
 * Por que esta campanha não entrega — e as três formas de não saber.
 *
 * `carregando`, `naoImplementado` e `ocorrencia` são estados distintos, e
 * nenhum deles é silêncio. Uma seção que simplesmente não aparece quando não há
 * diagnóstico lê-se como "não há nada de errado", que é a conclusão mais cara
 * que esta tela pode induzir por omissão.
 */
const Diagnostico: React.FC<{ volcCampaignId: string }> = ({ volcCampaignId }) => {
  const leitura = useDiagnosticoDeEntrega(volcCampaignId);

  if (leitura.carregando) {
    return (
      <section className="mt-10 border-t border-border pt-6" aria-label="diagnóstico de entrega">
        <p className="kicker">diagnóstico de entrega</p>
        <div className="mt-3 space-y-2" role="status" aria-live="polite">
          <span className="sr-only">apurando por que esta campanha entrega ou não</span>
          {[0, 1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className="h-10 animate-pulse rounded-sm bg-muted motion-reduce:animate-none"
            />
          ))}
        </div>
      </section>
    );
  }

  if (leitura.naoImplementado) {
    return (
      <section className="mt-10 border-t border-border pt-6" aria-label="diagnóstico de entrega">
        <p className="kicker">diagnóstico de entrega</p>
        <h2 className="mt-1 font-display text-lg font-semibold tracking-tight md:text-xl">
          Este servidor ainda não apura diagnóstico
        </h2>
        <p className="mt-2 max-w-[70ch] text-[13px] leading-relaxed text-muted-foreground">
          A ausência é da capacidade, não da campanha: nada aqui afirma que a
          campanha esteja bem. Enquanto a apuração não existir, o estado dela se
          confere no painel do Google.
        </p>
      </section>
    );
  }

  if (leitura.ocorrencia) {
    return (
      <section className="mt-10 border-t border-border pt-6" aria-label="diagnóstico de entrega">
        <p className="kicker">diagnóstico de entrega</p>
        <div className="mt-2 max-w-[70ch]" role="alert">
          <p className="text-sm leading-relaxed">{leitura.ocorrencia.mensagem}</p>
          <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
            {leitura.ocorrencia.proximoPasso}
          </p>
          <CodigoDaOcorrencia ocorrencia={leitura.ocorrencia} />
        </div>
      </section>
    );
  }

  // ⚠️ Não devolver `null`. O docblock desta função proíbe exatamente isto, e o
  // caminho existe: com o navegador offline, o React Query põe a query em
  // `fetchStatus: 'paused'` — `isLoading` fica false, `isError` fica false e
  // `data` fica undefined. Os três estados nomeados acima não pegam esse caso, e
  // a seção inteira desaparecia sem uma linha de texto, enquanto o resto da
  // página renderizava normalmente. Uma seção ausente lê-se como "não há nada de
  // errado", que é a conclusão mais cara que esta tela pode induzir por omissão.
  if (!leitura.diagnostico) {
    return (
      <section className="mt-10 border-t border-border pt-6" aria-labelledby="diag-indisponivel">
        <h2 id="diag-indisponivel" className="font-display text-[13px] font-semibold">
          Diagnóstico de entrega
        </h2>
        <p className="mt-2 max-w-[70ch] text-[12px] leading-relaxed text-muted-foreground">
          Não foi possível carregar o diagnóstico, e não sabemos por quê — a leitura
          não chegou a falhar nem a completar. Se o aparelho estiver sem rede, ela
          retoma sozinha quando a conexão voltar.{' '}
          <strong className="font-medium text-foreground">
            Isto não significa que a campanha esteja bem.
          </strong>
        </p>
      </section>
    );
  }

  return (
    <>
      <div className="mt-10 border-t border-border pt-6">
        <EscadaDeEntrega diagnostico={leitura.diagnostico} />
      </div>
      {leitura.propostas && (
        <div className="mt-10 border-t border-border pt-6">
          <CaixaDePropostas caixa={leitura.propostas} />
        </div>
      )}
    </>
  );
};

const Fato: React.FC<{ rotulo: string; valor: string | null }> = ({ rotulo, valor }) => (
  <div className="flex flex-wrap gap-x-3">
    <dt className="text-muted-foreground">{rotulo}</dt>
    <dd className="tabular font-medium">{valor ?? AUSENTE}</dd>
  </div>
);

export default CampanhaCanonPage;
