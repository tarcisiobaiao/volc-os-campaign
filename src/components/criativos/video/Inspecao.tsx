/**
 * O painel de inspeção: o que responde "esta versão pode ser usada?".
 *
 * Contrato resolvido, voz, fatos e fontes, ledger de assets com licença e
 * crédito, gates de QA e custo. Nada aqui é decoração: cada bloco existe porque
 * a resposta muda com ele.
 *
 * ⚠️ `[]` não é "sem fontes" e `null` não é "reprovado". As duas frases estão
 * escritas na tela porque a diferença decide se alguém publica.
 */
import React from 'react';
import { ExternalLink } from 'lucide-react';

import { SeloDeGate } from '@/components/criativos/comum/Selo';
import {
  custoLegivel,
  dimensoes,
  hashCurto,
  instante,
  segundosLegiveis,
} from '@/components/criativos/comum/formato';
import type {
  ContratoDeVideo,
  GateDeQa,
  ItemDoLedger,
  QaDeVideo,
  VideoObservado,
} from '@/types/criativos';

const Par: React.FC<{ rotulo: string; valor: React.ReactNode }> = ({ rotulo, valor }) => (
  <div className="grid grid-cols-[minmax(0,8rem)_minmax(0,1fr)] gap-3 border-b border-border/60 py-1.5 last:border-b-0">
    <dt className="text-[12px] text-muted-foreground">{rotulo}</dt>
    <dd className="break-words text-[13px] leading-relaxed text-foreground">{valor}</dd>
  </div>
);

const ListaDeGates: React.FC<{ titulo: string; veredito: string | null; gates: GateDeQa[] }> = ({
  titulo,
  veredito,
  gates,
}) => (
  <div>
    <div className="flex flex-wrap items-center gap-2">
      <p className="kicker">{titulo}</p>
      <SeloDeGate resultado={veredito} />
    </div>
    {gates.length ? (
      <ul className="mt-2 space-y-1.5">
        {gates.map((g) => (
          <li key={g.id} className="flex items-start gap-2">
            <SeloDeGate resultado={g.resultado} className="mt-0.5 shrink-0" />
            <span className="min-w-0">
              <span className="block text-[13px] text-foreground">{g.rotulo}</span>
              {g.detalhe && (
                <span className="block text-[12px] leading-relaxed text-muted-foreground">
                  {g.detalhe}
                </span>
              )}
            </span>
          </li>
        ))}
      </ul>
    ) : (
      <p className="mt-2 text-[12px] leading-relaxed text-muted-foreground">
        Nenhum gate registrado nesta categoria para este build.
      </p>
    )}
  </div>
);

const ItemLedger: React.FC<{ item: ItemDoLedger }> = ({ item }) => (
  <li className="border-b border-border/60 py-2 last:border-b-0">
    <p className="break-words text-[13px] font-medium text-foreground">{item.arquivo}</p>
    <p className="mt-0.5 text-[12px] leading-relaxed text-muted-foreground">
      Fonte {item.fonte}
      {item.cena !== null ? `, cena ${item.cena}` : ''}. Licença{' '}
      {item.licenca ?? 'não declarada'}. Crédito {item.credito ?? 'não declarado'}.{' '}
      {item.usoComercialOk === null
        ? 'Uso comercial não apurado.'
        : item.usoComercialOk
          ? 'Uso comercial permitido.'
          : 'Uso comercial não permitido.'}{' '}
      {item.sintetico ? 'Conteúdo sintético.' : 'Conteúdo não sintético.'}
    </p>
    {item.disclosure && (
      <p className="mt-0.5 text-[12px] leading-relaxed text-foreground">
        Disclosure: {item.disclosure}
      </p>
    )}
    {item.url && (
      <a
        href={item.url}
        target="_blank"
        rel="noreferrer"
        className="mt-1 inline-flex min-h-6 items-center gap-1 text-[12px] text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
      >
        Abrir a fonte
        <ExternalLink className="h-3 w-3" aria-hidden />
      </a>
    )}
  </li>
);

export const ContratoResolvido: React.FC<{ contrato: ContratoDeVideo }> = ({ contrato }) => (
  <dl>
    <Par rotulo="Tema" valor={contrato.tema ?? 'não registrado'} />
    <Par rotulo="Nicho" valor={contrato.nicho ?? 'não registrado'} />
    <Par rotulo="Skin" valor={contrato.skin ?? 'não registrada'} />
    <Par rotulo="Título" valor={contrato.titulo ?? 'não registrado'} />
    <Par rotulo="Selo" valor={contrato.badge ?? 'não registrado'} />
    <Par rotulo="Duração" valor={segundosLegiveis(contrato.duracaoS)} />
    <Par
      rotulo="Formato"
      valor={`${dimensoes(contrato.largura, contrato.altura)}, ${
        contrato.fps === null ? 'fps não registrado' : `${contrato.fps} fps`
      }`}
    />
    <Par
      rotulo="Voz"
      valor={
        contrato.voz
          ? `${contrato.voz.provider ?? 'provider não registrado'}, ${
              contrato.voz.id ?? 'id não registrado'
            }, estilo ${contrato.voz.estilo ?? 'não registrado'}, velocidade ${
              contrato.voz.velocidade ?? 'não registrada'
            }`
          : 'não registrada'
      }
    />
  </dl>
);

export const Inspecao: React.FC<{ leitura: VideoObservado }> = ({ leitura }) => {
  const { contrato, ledger, qa, job, master } = leitura;
  return (
    <div className="space-y-5">
      <div>
        <p className="kicker">Contrato resolvido</p>
        <div className="mt-1">
          <ContratoResolvido contrato={contrato} />
        </div>
      </div>

      <div>
        <p className="kicker">Fatos e fontes</p>
        {contrato.fatos.length ? (
          <ul className="mt-1 space-y-2">
            {contrato.fatos.map((fato, i) => (
              <li key={`${i}-${fato.afirmacao}`} className="border-b border-border/60 pb-2 last:border-b-0">
                <p className="text-[13px] leading-relaxed text-foreground">{fato.afirmacao}</p>
                <p className="mt-0.5 text-[12px] leading-relaxed text-muted-foreground">
                  {fato.fontes.length
                    ? `Fontes: ${fato.fontes.join(', ')}.`
                    : 'Nenhuma fonte registrada para esta afirmação.'}{' '}
                  {fato.calibragem ? `Calibragem: ${fato.calibragem}.` : 'Sem calibragem registrada.'}
                </p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">
            O build não registrou fatos nem fontes. Isso não significa que o vídeo não faz
            afirmações: significa que ninguém as registrou aqui.
          </p>
        )}
      </div>

      <div>
        <p className="kicker">Assets e direitos</p>
        {ledger.length ? (
          <ul className="mt-1">
            {ledger.map((item, i) => (
              <ItemLedger key={`${i}-${item.arquivo}`} item={item} />
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">
            Nenhum insumo registrado no ledger deste build.
          </p>
        )}
      </div>

      <ListaDeGates titulo="QA técnico" veredito={qa.vereditoTecnico} gates={qa.gatesTecnicos} />
      <ListaDeGates titulo="QA visual" veredito={qa.vereditoVisual} gates={qa.gatesVisuais} />

      <div>
        <p className="kicker">Custo</p>
        <dl className="mt-1">
          <Par rotulo="Custo do build" valor={custoLegivel(job.custoRealUsd)} />
          <Par rotulo="Custo estimado" valor={custoLegivel(job.custoEstimadoUsd)} />
          <Par rotulo="Custo do QA" valor={custoLegivel(qa.custoQaUsd)} />
        </dl>
      </div>

      <div>
        <p className="kicker">Saída</p>
        <dl className="mt-1">
          <Par rotulo="Tipo do arquivo" valor={master.mime} />
          <Par rotulo="Dimensões" valor={dimensoes(master.largura, master.altura)} />
          <Par
            rotulo="Hash do conteúdo"
            valor={<span className="font-mono">{hashCurto(master.contentHash)}</span>}
          />
          <Par rotulo="Versão" valor={`versão ${master.versao}`} />
          <Par rotulo="Criado em" valor={instante(master.criadoEm)} />
        </dl>
      </div>
    </div>
  );
};
