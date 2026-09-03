/**
 * A verdade sobre o DESTINO PAGO, numa tela só.
 *
 * ## O que ele existe para impedir
 *
 * Antes desta entrega o frontend não tinha conceito nenhum de política de
 * destino — nem papel, nem prontidão, nem bloqueador — e mesmo assim decidia. A
 * tela do lançamento chamava a landing page de "LP no ar" comparando
 * `status_wp !== 'draft'`, o que pinta de verde justamente o caso em que o
 * servidor NUNCA leu o WordPress. O operador aprovava o gasto sem ver contra o
 * que a página tinha sido avaliada — quando tinha.
 *
 * ## As três regras deste arquivo
 *
 * **1. Nada é derivado aqui.** Quem avalia é o portão do backend, que tem o
 * HTML. A tradução mora em `lib/landing-policy/prontidao.ts`, junto do contrato
 * que ela lê. Este arquivo só desenha.
 *
 * **2. Verde só com prova.** `APTO` é o único estado que pinta positivo, e ele
 * exige recibo presente, datável, fresco e da versão vigente da política.
 * Recibo que não chegou é cinza, não é verde-claro.
 *
 * **3. Cinco perguntas, nunca uma.** "Apto segundo o VOLC" não é "publicado",
 * que não é "verificado ao vivo", que não é "elegível para campanha" — e nenhum
 * dos quatro é "o Google aprovou", que este portão não tem como saber.
 * Colapsá-las num único selo verde foi como uma LP com sete links de governo
 * virou destino de campanha.
 *
 * ## O que ele NÃO mostra
 *
 * ⚠️ Nem o sha256 inteiro nem a impressão inteira: doze caracteres bastam para
 * reconciliar com o recibo do backend e não convidam a copiar identidade. E
 * nenhum trecho do HTML avaliado — a evidência de cada achado já vem estrutural
 * do portão, e reproduzir corpo de página aqui faria a tela virar coletora de
 * conteúdo.
 */
import React from 'react';

import { Selo } from '@/components/landing-policy/Selo';
import {
  EXIGENCIA_DA_PERGUNTA,
  ORDEM_DAS_PERGUNTAS,
  ROTULO_DA_PERGUNTA,
  textoDaDeriva,
  textoDaProntidao,
  textoDoPapel,
  textoDoPonto,
  tomDaProntidao,
  type EstadoDaProntidao,
  type LeituraDoDestinoPago,
  type PerguntaDaProntidao,
  type TomDaProntidao,
} from '@/lib/landing-policy/prontidao';

/**
 * As quatro cores, e o que cada uma afirma.
 *
 * ⚠️ `ignorado` NÃO é amarelo-de-atenção: é cinza-de-ignorância. Amarelo dá a
 * entender que alguém precisa agir sobre um problema conhecido, e o problema
 * aqui é que ninguém olhou.
 */
const TOM: Record<TomDaProntidao, string> = {
  provado: 'border-success/40 bg-success/[0.08]',
  negado: 'border-destructive/40 bg-destructive/[0.07]',
  ignorado: 'border-border/70 bg-muted/40',
  ausente: 'border-border/50 bg-transparent',
};

function Pergunta({
  nome,
  estado,
}: {
  nome: PerguntaDaProntidao;
  estado: EstadoDaProntidao;
}) {
  const tom = tomDaProntidao(estado);
  return (
    <li
      className={`rounded-md border px-2.5 py-2 ${TOM[tom]}`}
      data-pergunta={nome}
      data-estado={estado}
    >
      <p className="text-xs font-medium leading-tight">{ROTULO_DA_PERGUNTA[nome]}</p>
      <p className="mt-0.5 text-[11px] uppercase tracking-wide text-muted-foreground">
        {textoDaProntidao(estado)}
      </p>
      {/* ⚠️ A exigência aparece SÓ quando a pergunta não está apta. Repeti-la
          numa linha já resolvida viraria ruído, e o operador aprenderia a pular
          a frase justamente onde ela importa. A do Google é a exceção: ela
          nunca fica apta, e é a frase dela que impede a leitura errada. */}
      {estado !== 'APTO' ? (
        <p className="mt-1 max-w-[62ch] text-[11px] leading-snug text-muted-foreground">
          {EXIGENCIA_DA_PERGUNTA[nome]}
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
      <dt className="kicker text-muted-foreground">{rotulo}</dt>
      <dd className="text-sm text-foreground">{valor}</dd>
      {ressalva ? (
        <p className="mt-0.5 text-[11px] leading-snug text-muted-foreground">{ressalva}</p>
      ) : null}
    </div>
  );
}

/** Uma lista de achados. Bloqueio e aviso usam a mesma forma e tons diferentes. */
function Achados({
  titulo,
  itens,
  tom,
}: {
  titulo: string;
  itens: { codigo: string; severidade: string; mensagem: string }[];
  tom: 'negado' | 'ignorado';
}) {
  if (itens.length === 0) return null;
  return (
    <section className="mt-4">
      <h4 className="kicker text-muted-foreground">{titulo}</h4>
      <ul className="mt-2 space-y-2">
        {itens.map((a, i) => (
          <li
            key={`${a.codigo}-${i}`}
            className={`rounded-md border px-2.5 py-2 ${TOM[tom]}`}
            data-codigo={a.codigo}
          >
            {/* O código vem primeiro e em fonte tabular porque é ele que se cita
                num handoff — a mensagem é para ler, o código é para procurar. */}
            <p className="tabular text-[11px] font-medium tracking-tight">{a.codigo}</p>
            <p className="mt-0.5 max-w-[74ch] text-xs leading-relaxed text-muted-foreground">
              {a.mensagem}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}

/**
 * O painel inteiro.
 *
 * `compacto` esconde os fatos de auditoria (hash, versões, completude) e mantém
 * as cinco perguntas e os bloqueios. É para a coluna estreita do redator, onde
 * o assunto da tela é o texto da página e não a procedência da avaliação.
 */
export const PainelDoDestinoPago: React.FC<{
  leitura: LeituraDoDestinoPago;
  titulo?: string;
  compacto?: boolean;
  className?: string;
}> = ({ leitura, titulo = 'destino pago', compacto = false, className }) => {
  const tomDoTopo = leitura.apto_para_campanha
    ? 'provado'
    : leitura.perguntas.volc === 'BLOQUEADO'
      ? 'negado'
      : 'ignorado';

  return (
    <section
      className={className}
      data-apto={leitura.apto_para_campanha ? 'sim' : 'nao'}
      data-sem-recibo={leitura.sem_recibo ? 'sim' : 'nao'}
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        {/* Título vazio é uso legítimo: na lateral do redator a seção já tem
            um cabeçalho, e repetir "destino pago" ali seria eco. */}
        {titulo ? <h3 className="kicker">{titulo}</h3> : null}
        <span className="hairline hidden flex-1 sm:block" />
        {/* ⚠️ O selo do topo afirma "apto" ou "não apto" — nunca "quase". E ele
            nunca diz nada sobre o Google: essa pergunta tem selo próprio, logo
            abaixo, e é a única com uma frase que promete continuar sem resposta. */}
        <Selo
          palavra={leitura.apto_para_campanha ? 'destino pago apto' : 'não apto'}
          descricao={
            leitura.apto_para_campanha
              ? 'Nesta avaliação, neste ponto de portão, contra esta versão da '
                + 'política, não sobrou bloqueio nem desconhecido.'
              : leitura.sem_recibo
                ? 'Nenhum recibo de política chegou nesta resposta: ninguém avaliou esta página.'
                : 'A avaliação não concluiu que este destino pode receber tráfego pago.'
          }
          tom={tomDoTopo}
        />
        <Selo
          palavra="Google: desconhecida"
          descricao={leitura.nota_do_google}
          tom="ignorado"
        />
      </div>

      <p className="mt-2 max-w-[74ch] text-xs leading-relaxed text-muted-foreground">
        {leitura.nota_do_google}
      </p>

      <ul className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {ORDEM_DAS_PERGUNTAS.map((p) => (
          <Pergunta key={p} nome={p} estado={leitura.perguntas[p]} />
        ))}
      </ul>

      {/* As recusas vêm antes dos fatos de auditoria: elas são o que o operador
          precisa FAZER, e a procedência é o que ele confere depois. */}
      {leitura.recusas.length > 0 && (
        <section className="mt-4 rounded-md border border-destructive/40 bg-destructive/[0.05] p-3">
          <h4 className="text-xs font-medium">
            {leitura.recusas.length === 1
              ? 'Falta uma coisa para este destino servir a uma campanha'
              : `Faltam ${leitura.recusas.length} coisas para este destino servir a uma campanha`}
          </h4>
          <ol className="mt-2 space-y-1.5">
            {leitura.recusas.map((r, i) => (
              <li key={i} className="max-w-[74ch] text-xs leading-relaxed text-muted-foreground">
                {r}
              </li>
            ))}
          </ol>
        </section>
      )}

      <Achados titulo="bloqueadores" itens={leitura.bloqueadores} tom="negado" />
      <Achados titulo="avisos" itens={leitura.avisos} tom="ignorado" />

      {/* ⚠️ Os desconhecidos têm seção PRÓPRIA, e não entram na lista de avisos.
          Um desconhecido é uma verificação exigida que não pôde ser concluída —
          ele reprova igual a um bloqueio, e enfileirá-lo entre observações
          ensinaria o operador a tratá-lo como ruído. */}
      {leitura.desconhecidos.length > 0 && (
        <section className="mt-4">
          <h4 className="kicker text-muted-foreground">
            verificações que não puderam ser concluídas
          </h4>
          <ul className="mt-2 space-y-2">
            {leitura.desconhecidos.map((d, i) => (
              <li
                key={`${d.verificacao}-${i}`}
                className={`rounded-md border px-2.5 py-2 ${TOM.ignorado}`}
              >
                <p className="tabular text-[11px] font-medium tracking-tight">
                  {d.verificacao}
                </p>
                <p className="mt-0.5 max-w-[74ch] text-xs leading-relaxed text-muted-foreground">
                  {d.motivo}
                </p>
              </li>
            ))}
          </ul>
        </section>
      )}

      {!compacto && (
        <dl className="mt-4 grid gap-3 border-t border-border pt-4 sm:grid-cols-2 lg:grid-cols-3">
          <Fato
            rotulo="papel avaliado"
            valor={textoDoPapel(leitura.papel_avaliado)}
            // ⚠️ Divergir NÃO é erro: no ponto de campanha o papel é FORÇADO
            // para destino pago, e ver as duas linhas é como o operador entende
            // por que o rigor subiu. O papel é do servidor; nada que o cliente
            // declare o afrouxa.
            ressalva={
              leitura.papel_declarado && leitura.papel_declarado !== leitura.papel_avaliado
                ? `alguém declarou "${textoDoPapel(leitura.papel_declarado)}"; o servidor avaliou como acima.`
                : null
            }
          />
          <Fato rotulo="ponto do portão" valor={textoDoPonto(leitura.ponto_do_portao)} />
          <Fato
            rotulo="última avaliação"
            valor={leitura.avaliado_em ?? 'não carimbada'}
            ressalva={
              leitura.avaliado_em
                ? null
                : 'sem carimbo comparável não dá para dizer se a evidência ainda vale.'
            }
          />
          <Fato
            rotulo="versão do contrato"
            valor={leitura.versao_do_contrato ?? 'não declarada'}
            ressalva={
              leitura.versao_da_fonte ? `fonte das regras: ${leitura.versao_da_fonte}` : null
            }
          />
          <Fato
            rotulo="conteúdo aprovado"
            valor={<span className="tabular">{leitura.hash_curto ?? 'não carimbado'}</span>}
            ressalva={
              leitura.impressao_curta ? `impressão estrutural: ${leitura.impressao_curta}` : null
            }
          />
          <Fato rotulo="deriva" valor={textoDaDeriva(leitura.deriva)} />
          <Fato
            rotulo="completude da evidência"
            valor={leitura.completude ?? 'não declarada'}
            ressalva={
              leitura.verificacoes_inconclusivas.length > 0
                ? `inconclusivas: ${leitura.verificacoes_inconclusivas.join(', ')}`
                : null
            }
          />
          <Fato rotulo="origem da evidência" valor={leitura.origem_da_evidencia} />
          {leitura.url && (
            <Fato
              rotulo="página avaliada"
              valor={<span className="tabular break-all text-xs">{leitura.url}</span>}
            />
          )}
        </dl>
      )}
    </section>
  );
};

/**
 * A faixa — o painel reduzido a uma linha, para o topo de uma tela.
 *
 * Ela existe porque o painel inteiro tem 400px de altura e a decisão de gastar
 * é tomada na barra fixa, longe dele. A faixa diz o estado e a primeira coisa a
 * fazer; o painel continua sendo onde se confere a procedência.
 */
export const FaixaDoDestinoPago: React.FC<{
  leitura: LeituraDoDestinoPago;
  className?: string;
}> = ({ leitura, className }) => {
  const tom = leitura.apto_para_campanha
    ? 'provado'
    : leitura.perguntas.volc === 'BLOQUEADO'
      ? 'negado'
      : 'ignorado';
  return (
    <div
      className={`flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-md border px-3 py-2 ${TOM[tom]} ${className ?? ''}`}
      data-apto={leitura.apto_para_campanha ? 'sim' : 'nao'}
    >
      <Selo
        palavra={leitura.apto_para_campanha ? 'destino pago apto' : 'não apto'}
        descricao={
          leitura.apto_para_campanha
            ? 'Sem bloqueio e sem desconhecido nesta avaliação.'
            : 'A avaliação não concluiu que este destino pode receber tráfego pago.'
        }
        tom={tom}
      />
      <p className="max-w-[74ch] text-xs leading-relaxed text-muted-foreground">
        {leitura.recusas.length > 0
          ? leitura.recusas[0]
          : 'A aprovação do Google continua desconhecida: este portão lê HTML, '
            + 'não lê a decisão do revisor.'}
        {leitura.recusas.length > 1 && (
          <span className="text-muted-foreground/80">
            {' '}
            +{leitura.recusas.length - 1} pendência(s).
          </span>
        )}
      </p>
    </div>
  );
};
