/**
 * A biblioteca de criativos — o que existe para anunciar, e o que cada peça prova.
 *
 * ## Por que é tabela e não grade de cartões
 *
 * O trabalho aqui é comparar: qual título já foi usado, qual serve em Display,
 * qual não tem procedência. Cartões lado a lado obrigam o olho a reencontrar o
 * mesmo campo em posições diferentes; colunas alinhadas deixam a comparação ser
 * uma leitura vertical.
 *
 * ## `uso: null` não é "não está em uso"
 *
 * Um asset que ninguém apurou onde está e um asset que está comprovadamente
 * livre parecem a mesma coisa numa coluna vazia — e levam a ações opostas: o
 * segundo pode ser aposentado, o primeiro não. A coluna diz qual é qual.
 */
import React from 'react';
import { CircleCheck, CircleHelp, CircleOff, Fingerprint } from 'lucide-react';

import { cn } from '@/lib/utils';
import { Chip, type Tom } from '@/components/trafego/inventario/Selos';
import { AUSENTE } from '@/components/trafego/inventario/formato';
import type {
  Criativo,
  ProcedenciaDoCriativo,
  TipoDeCriativo,
  ValidacaoDoCriativo,
} from '@/types/diagnostico';

const TIPO: Record<TipoDeCriativo, string> = {
  titulo: 'título',
  descricao: 'descrição',
  sitelink: 'sitelink',
  imagem: 'imagem',
  video: 'vídeo',
  logo: 'logo',
};

const PROCEDENCIA: Record<ProcedenciaDoCriativo, { palavra: string; descricao: string; tom: Tom }> = {
  volc_os: {
    palavra: 'nasceu aqui',
    descricao: 'produzido pelo VOLC O.S., com run de origem registrada',
    tom: 'bom',
  },
  importado: {
    palavra: 'importado',
    descricao: 'trazido de fora e registrado por uma pessoa',
    tom: 'info',
  },
  conta: {
    palavra: 'encontrado na conta',
    descricao: 'apareceu numa leitura da conta de anúncio; não foi produzido aqui',
    tom: 'neutro',
  },
  desconhecida: {
    palavra: 'sem procedência',
    descricao: 'não sabemos como esta peça entrou na biblioteca',
    tom: 'atencao',
  },
};

function procedenciaLegivel(valor: string) {
  return (
    PROCEDENCIA[valor as ProcedenciaDoCriativo] ?? {
      palavra: 'procedência não reconhecida',
      descricao: `o sistema informou "${valor}", que esta versão da tela não conhece`,
      tom: 'atencao' as Tom,
    }
  );
}

export interface BibliotecaDeCriativosProps {
  criativos: Criativo[];
  /**
   * `null` = a leitura da biblioteca falhou. Diferente de `[]`, que é
   * "a biblioteca foi lida e está vazia".
   */
  lida?: boolean;
  className?: string;
}

export const BibliotecaDeCriativos: React.FC<BibliotecaDeCriativosProps> = ({
  criativos,
  lida = true,
  className,
}) => (
  <section aria-labelledby="criativos-titulo" className={cn('min-w-0', className)}>
    <p className="kicker">biblioteca de criativos</p>
    <h2
      id="criativos-titulo"
      className="mt-1 font-display text-lg font-semibold tracking-tight md:text-xl"
    >
      {!lida
        ? 'Não foi possível ler a biblioteca'
        : criativos.length === 0
          ? 'Biblioteca vazia'
          : `${criativos.length} ${criativos.length === 1 ? 'peça' : 'peças'}`}
    </h2>

    {!lida ? (
      <p className="mt-3 max-w-[70ch] text-[13px] leading-relaxed text-muted-foreground" role="status">
        A leitura da biblioteca não foi concluída. Lista vazia aqui não significa
        que não haja peça: significa que ninguém conseguiu olhar.
      </p>
    ) : criativos.length === 0 ? (
      <p className="mt-3 max-w-[70ch] text-[13px] leading-relaxed text-muted-foreground" role="status">
        A biblioteca foi lida e não há peça registrada. Ela se enche quando o
        Redator entrega uma copy ou quando alguém importa assets com procedência.
      </p>
    ) : (
      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[46rem] text-[12px]">
          <caption className="sr-only">
            peças de criativo, com procedência, impressão, validação por canal e uso
          </caption>
          <thead>
            <tr className="border-y border-border text-left text-[10px] uppercase tracking-[0.08em] text-muted-foreground">
              <th scope="col" className="py-2 pr-3 font-normal">
                peça
              </th>
              <th scope="col" className="py-2 pr-3 font-normal">
                tipo
              </th>
              <th scope="col" className="py-2 pr-3 font-normal">
                procedência
              </th>
              <th scope="col" className="py-2 pr-3 font-normal">
                impressão
              </th>
              <th scope="col" className="py-2 pr-3 font-normal">
                serve em
              </th>
              <th scope="col" className="py-2 font-normal">
                em uso
              </th>
            </tr>
          </thead>
          <tbody>
            {criativos.map((c) => (
              <Linha key={c.id} criativo={c} />
            ))}
          </tbody>
        </table>
      </div>
    )}
  </section>
);

const Linha: React.FC<{ criativo: Criativo }> = ({ criativo }) => {
  const proc = procedenciaLegivel(criativo.procedencia);
  return (
    <tr className="border-b border-border align-top">
      <th scope="row" className="max-w-[22rem] py-2.5 pr-3 text-left font-medium">
        <span className="block truncate" title={criativo.conteudo}>
          {criativo.conteudo}
        </span>
        {criativo.origem && (
          <span className="mt-0.5 block text-[11px] font-normal text-muted-foreground">
            {criativo.origem}
          </span>
        )}
      </th>
      <td className="py-2.5 pr-3 text-muted-foreground">
        {TIPO[criativo.tipo] ?? criativo.tipo}
      </td>
      <td className="py-2.5 pr-3">
        <Chip
          glifo={criativo.procedencia === 'desconhecida' ? CircleHelp : Fingerprint}
          palavra={proc.palavra}
          descricao={proc.descricao}
          tom={proc.tom}
        />
      </td>
      <td className="tabular py-2.5 pr-3 text-muted-foreground">
        {criativo.hash ? (
          <span title="impressão do conteúdo desta peça">{criativo.hash.slice(0, 10)}</span>
        ) : (
          <span title="sem impressão calculada — duas peças de texto igual não são distinguíveis">
            {AUSENTE}
          </span>
        )}
      </td>
      <td className="py-2.5 pr-3">
        <Validacoes validacoes={criativo.validacoes} />
      </td>
      <td className="py-2.5">
        <Uso uso={criativo.uso} />
      </td>
    </tr>
  );
};

const Validacoes: React.FC<{ validacoes: ValidacaoDoCriativo[] }> = ({ validacoes }) => {
  if (validacoes.length === 0) {
    return (
      <span className="text-muted-foreground" title="nenhum canal foi conferido para esta peça">
        não conferida
      </span>
    );
  }
  return (
    <ul className="flex flex-wrap gap-1" role="list">
      {validacoes.map((v) => (
        <li key={v.canal}>
          <Chip
            glifo={
              v.situacao === 'serve'
                ? CircleCheck
                : v.situacao === 'nao_serve'
                  ? CircleOff
                  : CircleHelp
            }
            palavra={v.canal.toLowerCase().replace(/_/g, ' ')}
            descricao={
              v.situacao === 'serve'
                ? `esta peça atende as regras de ${v.canal} neste momento`
                : v.situacao === 'nao_serve'
                  ? (v.motivo ?? `esta peça não atende as regras de ${v.canal}`)
                  : (v.motivo ??
                    `a regra de ${v.canal} não pôde ser conferida — não é o mesmo que servir`)
            }
            tom={v.situacao === 'serve' ? 'bom' : v.situacao === 'nao_serve' ? 'ruim' : 'atencao'}
          />
        </li>
      ))}
    </ul>
  );
};

const Uso: React.FC<{ uso: Criativo['uso'] }> = ({ uso }) => {
  if (uso == null) {
    return (
      <span
        className="text-muted-foreground"
        title="ninguém apurou onde esta peça está em uso — não autoriza aposentá-la"
      >
        uso não apurado
      </span>
    );
  }
  if (uso.length === 0) {
    return (
      <span title="apurado: esta peça não está em nenhuma campanha">
        em nenhuma campanha
      </span>
    );
  }
  return (
    <ul className="space-y-0.5" role="list">
      {uso.map((u) => (
        <li key={u.volc_campaign_id} className="truncate" title={u.nome_campanha}>
          {u.nome_campanha}
          {u.estado_externo && (
            <span className="ml-1.5 text-[11px] text-muted-foreground">{u.estado_externo}</span>
          )}
        </li>
      ))}
    </ul>
  );
};

export default BibliotecaDeCriativos;
