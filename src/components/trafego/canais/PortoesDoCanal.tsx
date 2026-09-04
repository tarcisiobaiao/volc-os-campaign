/**
 * Os quatro portões de um canal — veredito, motivo e a quem pedir.
 *
 * ## A regra desta tela, em uma frase
 *
 * **Nada aparece verde sem evidência.** Um portão só ganha a marca de aberto
 * quando o SERVIDOR o declarou `PERMITIDO`; qualquer outro estado — inclusive
 * "não sei" — é desenhado como não-aberto, com o nome do estado escrito.
 *
 * ## Quatro estados, quatro desenhos — e nunca dois colapsados
 *
 *   PERMITIDO       aberto
 *   BLOQUEADO       fechado, com causa
 *   INDETERMINADO   não medido — tom PRÓPRIO, nunca o do fechado
 *   NAO_APLICAVEL   a pergunta não cabe
 *
 * ⚠️ `INDETERMINADO` desenhado como `BLOQUEADO` é o erro caro. As duas pedem
 * ações opostas — uma pede permissão, a outra pede uma leitura — e pintar
 * ignorância de vermelho ensina o operador a tratar todo vermelho como ruído.
 *
 * ## Por que a tabela de desenho não mora mais aqui
 *
 * Ela morava — em `DESENHO`, linhas 51-80 da versão anterior — e discordava da
 * tabela do painel irmão sobre o MESMO veredito: aqui `BLOQUEADO` era âmbar e
 * `INDETERMINADO` era ardósia; em `PainelDaMensuracao.tsx:67-74` `BLOQUEADO`
 * era vermelho e `INDETERMINADO` era âmbar. O operador que aprende "âmbar =
 * bloqueado" numa aba e vê "vermelho = bloqueado" na outra deixa de confiar na
 * cor, que era o ponto de usá-la.
 *
 * A correspondência única agora vem de
 * `bancada/paradas/portoesVisual.ts` — `TOM_DO_PORTAO_DE_CANAL`,
 * `GLIFO_DO_PORTAO_DE_CANAL` e `PALAVRA_DO_PORTAO_DE_CANAL`. Duas palavras
 * mudaram junto com a unificação, porque a tabela canônica é quem manda:
 * `PERMITIDO` diz "permitido" (era "liberado") e `INDETERMINADO` diz "não se
 * sabe" (era "não medido").
 *
 * ⚠️ E `BLOQUEADO` deixou de ser âmbar: um portão de canal fechado é uma recusa
 * DECLARADA pelo servidor, não uma dúvida, e o âmbar desta tela é agora a cor
 * exclusiva de "não sei".
 *
 * ## Cor é o terceiro sinal, nunca o primeiro
 *
 * Glifo, palavra e descrição vêm antes, como no resto do inventário. Um
 * operador com deuteranopia, um monitor mal calibrado e um print em preto e
 * branco precisam ler o mesmo fato. É por isso que o `ChipDeEstado` carrega os
 * três, e não só a tinta.
 */
import React from 'react';

import { cn } from '@/lib/utils';
import { ChipDeEstado } from '@/components/trafego/bancada/ChipDeEstado';
import {
  GLIFO_DO_PORTAO_DE_CANAL,
  PALAVRA_DO_PORTAO_DE_CANAL,
  TOM_DO_PORTAO_DE_CANAL,
} from '@/components/trafego/bancada/paradas/portoesVisual';
import {
  A_QUEM_PEDIR,
  ORDEM_DOS_PORTOES,
  PERGUNTA_DO_PORTAO,
  ROTULO_DO_PORTAO,
  type BloqueadorDeCanal,
  type ContratoDeCanal,
  type PortaoDeCanal,
  portao,
  tomDoBloqueio,
} from '@/lib/trafego/canais';
import {
  DESCRICAO_DO_PORTAO_DE_CANAL,
  FIO_DE_CARTAO,
  FIO_DO_BLOQUEIO,
  FIO_DO_TOM,
} from '@/components/trafego/canais/tonsDoCockpit';

function Bloqueio({ b }: { b: BloqueadorDeCanal }) {
  return (
    <li
      // ⚠️ `border-l` de 1px, e não os `border-l-2` de antes: `design.md:130`
      // proíbe faixa lateral colorida com mais de 1px. O tom vem de
      // `FIO_DO_BLOQUEIO`, que é o tom do BLOQUEIO — nunca o do portão.
      className={cn(
        'border-l py-1 pl-3',
        FIO_DO_BLOQUEIO[tomDoBloqueio(b.origem)] ?? FIO_DO_BLOQUEIO.ausencia,
      )}
    >
      {/* Causa de bloqueio é texto que sustenta decisão: 14px é o piso
          (`design.md:172`, `VISUAL-DIRECTION.md §3`). Era 12px. */}
      <p className="text-sm leading-6 text-foreground text-pretty">{b.causa}</p>
      <p className="mt-1 text-sm leading-6 text-muted-foreground text-pretty">
        {A_QUEM_PEDIR[b.origem]}
        {/* A data existe só para os bloqueios que vêm de uma LEITURA. Regra não
            tem data de observação: ela vale enquanto estiver escrita. */}
        {b.observado_em ? ` · observado em ${b.observado_em}` : ''}
      </p>
      {b.revalidacao ? (
        <p className="mt-0.5 text-sm italic leading-6 text-muted-foreground">
          Como conferir de novo: {b.revalidacao}
        </p>
      ) : null}
      {/* O código é metadado — estável, e é a ele que a UI se liga. 12px é o
          piso de `VISUAL-DIRECTION.md §3`; era 10px, ilegível de propósito. */}
      <code className="mt-1 block text-xs text-muted-foreground">
        {b.codigo}
      </code>
    </li>
  );
}

function Portao({ p }: { p: PortaoDeCanal }) {
  // ⚠️ O `??` não inventa estado: ele cobre um servidor que mande um valor fora
  // do contrato, e o desenha como IGNORÂNCIA — nunca como permissão.
  const tom = TOM_DO_PORTAO_DE_CANAL[p.estado] ?? TOM_DO_PORTAO_DE_CANAL.INDETERMINADO;
  const Glifo =
    GLIFO_DO_PORTAO_DE_CANAL[p.estado] ?? GLIFO_DO_PORTAO_DE_CANAL.INDETERMINADO;
  const palavra =
    PALAVRA_DO_PORTAO_DE_CANAL[p.estado] ??
    PALAVRA_DO_PORTAO_DE_CANAL.INDETERMINADO;
  const descricao =
    DESCRICAO_DO_PORTAO_DE_CANAL[p.estado] ??
    DESCRICAO_DO_PORTAO_DE_CANAL.INDETERMINADO;
  return (
    <div
      // Poço dentro do cartão do canal — `bg-muted/20` e sem sombra.
      // `design.md:100`: cartão dentro de cartão é sempre errado.
      className={cn(
        'rounded-md border border-border bg-muted/20 p-3',
        FIO_DE_CARTAO,
        FIO_DO_TOM[tom],
        // A borda tracejada sobrevive como QUARTO portador de "a pergunta não
        // cabe": forma, e não tinta, é o que atravessa um print em cinza.
        p.estado === 'NAO_APLICAVEL' && 'border-dashed',
      )}
      data-portao={p.nome}
      data-estado={p.estado}
    >
      <p className="text-sm font-medium text-foreground">
        {ROTULO_DO_PORTAO[p.nome]}
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <ChipDeEstado
          glifo={Glifo}
          palavra={palavra}
          descricao={descricao}
          tom={tom}
        />
        {/* ⚠️ O estado CRU continua na tela. Quem lê o contrato na API e quem lê
            a tela precisam ver o mesmo nome, e o operador não deveria precisar
            aprender o vocabulário do backend para entender a própria tela. */}
        <span className="font-mono text-xs text-muted-foreground">
          ({p.estado})
        </span>
      </div>
      <p className="mt-2 text-sm leading-6 text-muted-foreground text-pretty">
        {PERGUNTA_DO_PORTAO[p.nome]}
      </p>
      {p.bloqueadores.length > 0 ? (
        <ul className="mt-3 space-y-3">
          {p.bloqueadores.map((b) => (
            <Bloqueio key={`${p.nome}-${b.codigo}`} b={b} />
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/**
 * Os quatro portões de um canal, sempre os quatro.
 *
 * ⚠️ Nenhum é escondido por estar fechado. Um portão ausente da tela seria
 * indistinguível de um portão que ninguém avaliou — e é justamente a diferença
 * entre esses dois que o contrato inteiro existe para carregar.
 */
export function PortoesDoCanal({ contrato }: { contrato: ContratoDeCanal }) {
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {ORDEM_DOS_PORTOES.map((nome) => {
        const p = portao(contrato, nome);
        if (!p) {
          // O servidor não mandou este portão. Isso é ignorância, não recusa —
          // e dizê-lo é melhor que desenhar um portão inventado.
          //
          // ⚠️ Ele reusa o vocabulário de `INDETERMINADO` de propósito, em vez
          // de ganhar um quinto estado: "ninguém mediu" é o mesmo fato
          // operacional, e inventar um estado que o contrato não tem seria
          // afirmar uma distinção que o servidor não fez. O que separa os dois
          // casos é a frase abaixo e a borda tracejada, não um tom novo.
          return (
            <div
              key={nome}
              className={cn(
                'rounded-md border border-dashed border-border bg-muted/20 p-3',
                FIO_DE_CARTAO,
                FIO_DO_TOM[TOM_DO_PORTAO_DE_CANAL.INDETERMINADO],
              )}
            >
              <p className="text-sm font-medium text-foreground">
                {ROTULO_DO_PORTAO[nome]}
              </p>
              <ChipDeEstado
                className="mt-2"
                glifo={GLIFO_DO_PORTAO_DE_CANAL.INDETERMINADO}
                palavra={PALAVRA_DO_PORTAO_DE_CANAL.INDETERMINADO}
                descricao="o servidor não mandou este portão nesta leitura"
                tom={TOM_DO_PORTAO_DE_CANAL.INDETERMINADO}
              />
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                o servidor não respondeu sobre este portão
              </p>
            </div>
          );
        }
        return <Portao key={nome} p={p} />;
      })}
    </div>
  );
}

export default PortoesDoCanal;
