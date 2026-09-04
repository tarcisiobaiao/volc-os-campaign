/**
 * Parada 2 — Política. Se esta vertical pode anunciar neste país.
 *
 * Vem antes de Anúncio porque a copy é escrita e provada SOB a vertical: mudar
 * a vertical depois de escrever invalida a escrita, e a ordem inversa faria o
 * operador pagar duas vezes pela mesma copy.
 *
 * ## ⚠️ Ausência de regra NUNCA é verde
 *
 * Não achar a vertical na lista do servidor significa que ninguém adjudicou este
 * país × vertical. Um portão que ninguém leu não é um portão aberto — e a versão
 * anterior desenhava exatamente isso, porque só pintava quando ENCONTRAVA
 * severidade.
 *
 * ## ⚠️ `limitacao` barra
 *
 * `PortaoDePolitica.tsx` escrevia que uma vertical `limitacao` "sobe com
 * restrição". `volc_ads/campanha/conteudo.py:56` já a punha entre as severidades
 * que barram, com a medição: o efeito FULLY_LIMITED deixou 57 anúncios sem
 * veicular em 39 contas sob GOVERNMENT_DOCUMENTS_AND_OFFICIAL_SERVICES. Anúncio
 * que não veicula é reprovação com outro nome. A régua agora é uma só, e mora
 * em `politicaBarra`.
 */
import React from 'react';
import { CircleCheck, CircleHelp, Lock } from 'lucide-react';

import { BlocoDeEvidencia, LinhaDeFato } from '../BlocoDeEvidencia';
import { ChipDeEstado } from '../ChipDeEstado';
import { politicaBarra, verticalDaOportunidade } from '../paradas';
import { PortaoDePolitica } from '@/components/trafego/PortaoDePolitica';
import type { Cockpit, VerticalDePolitica } from '@/types/trafego';

export const ParadaPolitica: React.FC<{
  cockpit: Cockpit;
  verticais: VerticalDePolitica[];
  vertical: string | null;
  onVertical: (v: string | null) => void;
  certificacoes: string[];
  onCertificacoes: (c: string[]) => void;
}> = ({ cockpit, verticais, vertical, onVertical, certificacoes, onCertificacoes }) => {
  const declarada = cockpit.origem?.vertical ?? null;
  const v = verticalDaOportunidade(cockpit, verticais);
  const barra = politicaBarra(v);
  // Três estados, e o terceiro não é o primeiro. "ninguém adjudicou" é
  // indeterminado; só um portão LIDO e sem exigência é liberado.
  const indeterminado = !declarada || verticais.length === 0 || !v;

  return (
    <div className="space-y-4">
      <BlocoDeEvidencia
        titulo="O portão desta vertical"
        tom={indeterminado ? 'atencao' : barra ? 'ruim' : 'bom'}
      >
        <div className="mb-3">
          {indeterminado ? (
            <ChipDeEstado
              glifo={CircleHelp}
              palavra="não se sabe"
              descricao={
                !declarada ? 'a oportunidade não declara vertical'
                  : verticais.length === 0 ? 'os portões de política não foram lidos do servidor'
                    : `ninguém adjudicou a vertical "${declarada}" para este país`
              }
              tom="atencao"
            />
          ) : barra ? (
            <ChipDeEstado
              glifo={Lock}
              palavra="bloqueado"
              descricao={v?.severidade === 'limitacao'
                ? 'a vertical veicula limitada, e anúncio que não veicula é reprovação com outro nome'
                : 'a vertical exige habilitação antes de anunciar'}
              tom="ruim"
            />
          ) : (
            <ChipDeEstado
              glifo={CircleCheck}
              palavra="sem portão"
              descricao="o servidor leu esta vertical e ela não exige habilitação neste país"
              tom="bom"
            />
          )}
        </div>

        <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
          <LinhaDeFato
            rotulo="vertical"
            valor={v?.titulo ?? declarada}
            fonte="o funil"
            ausencia="não declarada"
          />
          <LinhaDeFato rotulo="país" valor={cockpit.origem?.pais || null} fonte="o funil" />
          <LinhaDeFato
            rotulo="o que exige"
            valor={v?.exige ?? null}
            fonte="o portão do servidor"
            ausencia={indeterminado ? 'não apurado' : 'nada'}
          />
          <LinhaDeFato
            rotulo="severidade"
            valor={v?.severidade ?? null}
            fonte="o portão do servidor"
            ausencia="não declarada"
          />
        </dl>

        {/* A divergência entre o que o card DIZIA e o que o portão resolveu é
            informação, não erro a esconder. */}
        {cockpit.origem?.vertical_declarada
          && cockpit.origem.vertical_declarada !== declarada && (
          <p className="mt-3 max-w-[70ch] text-sm leading-6 text-muted-foreground text-pretty">
            O card declarava <strong className="text-foreground">{cockpit.origem.vertical_declarada}</strong>{' '}
            e o portão resolveu <strong className="text-foreground">{declarada}</strong>. Quem
            manda no portão é o segundo.
          </p>
        )}

        {v?.severidade === 'limitacao' && (
          <p className="mt-3 max-w-[70ch] text-sm leading-6 text-foreground text-pretty">
            Esta vertical veicula <strong>limitada</strong> sem a habilitação. A campanha
            existiria e não entregaria — por isso ela barra aqui, e não depois.
          </p>
        )}
      </BlocoDeEvidencia>

      {/* A escolha de vertical e as certificações declaradas continuam no
          componente que já as conhece; o que mudou é quem decide se barra. */}
      <PortaoDePolitica
        verticais={verticais}
        escolhida={vertical ?? declarada}
        onEscolher={onVertical}
        certificacoes={certificacoes}
        onCertificacoes={onCertificacoes}
        pais={cockpit.origem?.pais ?? ''}
      />
    </div>
  );
};
