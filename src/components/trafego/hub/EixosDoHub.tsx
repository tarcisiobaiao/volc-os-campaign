/**
 * Os eixos do Hub: rede, canal, nível.
 *
 * Não são três barras de abas iguais. Rede é um seletor segmentado compacto
 * (qual conta de anúncio). Canal é uma fileira de chips subordinada (dentro
 * do Google). Nível é outra fileira, só no Meta, com o vocabulário do Meta
 * (conjunto, não ad group).
 *
 * A tarefa (Campanhas / Preparar / Atenção) fica nas abas da página.
 */
import React from 'react';

import { cn } from '@/lib/utils';

import {
  CANAIS_GOOGLE,
  NIVEIS_META,
  type CanalDoHub,
  type NivelMeta,
  type RedeDoHub,
} from './contrato';
import { rotuloDoCanal } from './IdentidadeDeCanal';

const ROTULO_DO_NIVEL: Record<NivelMeta, string> = {
  campanhas: 'Campanhas',
  conjuntos: 'Conjuntos',
  anuncios: 'Anúncios',
  criativos: 'Criativos',
};

const alvo = 'inline-flex min-h-11 min-w-11 items-center justify-center px-3 text-[13px] md:min-h-8 md:min-w-0';

const SeletorDeRede: React.FC<{
  valor: RedeDoHub;
  aoMudar: (rede: RedeDoHub) => void;
}> = ({ valor, aoMudar }) => (
  /* ⚠️ O rótulo "Rede" saiu de cima e virou nome acessível.
     Empilhado, ele somava uma linha de 20px e — pior — dava a Rede o mesmo peso
     visual do Canal e das abas. A SPEC §5 é explícita: rede, tarefa e canal
     "não devem ser apresentados como três barras equivalentes". Rede define o
     ecossistema; ela é contexto, não navegação de igual hierarquia. */
  <div className="flex min-w-0 items-center gap-2">
    <span className="sr-only" id="eixo-rede">
      Rede de anúncios
    </span>
    <div
      role="group"
      aria-labelledby="eixo-rede"
      className="inline-flex w-fit overflow-hidden rounded-md border border-border bg-card"
    >
      <button
        type="button"
        aria-pressed={valor === 'google'}
        className={cn(
          alvo,
          'border-r border-border font-medium',
          valor === 'google'
            ? 'bg-primary text-primary-foreground'
            : 'bg-transparent text-muted-foreground hover:bg-muted/60 hover:text-foreground',
        )}
        onClick={() => aoMudar('google')}
      >
        Google Ads
      </button>
      <button
        type="button"
        aria-pressed={valor === 'meta'}
        className={cn(
          alvo,
          'font-medium',
          valor === 'meta'
            ? 'bg-primary text-primary-foreground'
            : 'bg-transparent text-muted-foreground hover:bg-muted/60 hover:text-foreground',
        )}
        onClick={() => aoMudar('meta')}
      >
        Meta Ads
      </button>
    </div>
  </div>
);

const ChipDeEixo: React.FC<{
  ativo: boolean;
  children: React.ReactNode;
  onClick: () => void;
}> = ({ ativo, children, onClick }) => (
  <button
    type="button"
    aria-pressed={ativo}
    onClick={onClick}
    className={cn(
      alvo,
      'rounded-md border text-[13px]',
      ativo
        ? 'border-foreground/30 bg-foreground/[0.06] font-medium text-foreground'
        : 'border-transparent text-muted-foreground hover:border-border hover:text-foreground',
    )}
  >
    {children}
  </button>
);

/**
 * Canal — um RECORTE do inventário, e é por isso que ele mora nos filtros.
 *
 * ⚠️ Ele ocupava uma faixa própria de largura inteira no cabeçalho, com rótulo
 * empilhado, logo abaixo de outra faixa igual chamada "Rede" e logo acima das
 * abas. Três barras do mesmo tamanho ensinam que as três decidem a mesma
 * espécie de coisa — e a SPEC §5 diz o contrário: rede é ecossistema, tarefa é
 * trabalho, canal é recorte. Exportado para a barra de filtros, ele volta a ser
 * o que é, e o cabeçalho devolve ~90px ao trabalho.
 */
export const SeletorDeCanal: React.FC<{
  valor: CanalDoHub | null;
  aoMudar: (canal: CanalDoHub | null) => void;
}> = ({ valor, aoMudar }) => (
  <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
    <p className="kicker shrink-0" id="eixo-canal">
      Canal
    </p>
    <div
      role="group"
      aria-labelledby="eixo-canal"
      className="-mx-1 flex min-w-0 flex-wrap items-center gap-0.5 px-1"
    >
      <ChipDeEixo ativo={valor == null} onClick={() => aoMudar(null)}>
        Todos
      </ChipDeEixo>
      {CANAIS_GOOGLE.map((canal) => (
        <ChipDeEixo
          key={canal}
          ativo={valor === canal}
          onClick={() => aoMudar(canal)}
        >
          {rotuloDoCanal(canal)}
        </ChipDeEixo>
      ))}
    </div>
  </div>
);

const SeletorDeNivel: React.FC<{
  valor: NivelMeta;
  aoMudar: (nivel: NivelMeta) => void;
}> = ({ valor, aoMudar }) => (
  <div className="flex min-w-0 flex-col gap-1.5">
    <p className="kicker" id="eixo-nivel">
      Nível
    </p>
    <div
      role="group"
      aria-labelledby="eixo-nivel"
      className="-mx-1 flex flex-wrap items-center gap-0.5 overflow-x-auto px-1"
    >
      {NIVEIS_META.map((nivel) => (
        <ChipDeEixo
          key={nivel}
          ativo={valor === nivel}
          onClick={() => aoMudar(nivel)}
        >
          {ROTULO_DO_NIVEL[nivel]}
        </ChipDeEixo>
      ))}
    </div>
  </div>
);

export const EixosDoHub: React.FC<{
  rede: RedeDoHub;
  canal: CanalDoHub | null;
  nivel: NivelMeta;
  aoMudarRede: (rede: RedeDoHub) => void;
  aoMudarCanal: (canal: CanalDoHub | null) => void;
  aoMudarNivel: (nivel: NivelMeta) => void;
  /** Os chips de canal só fazem sentido na aba Campanhas do Google. */
  mostrarCanal?: boolean;
}> = ({
  rede,
  canal,
  nivel,
  aoMudarRede,
  aoMudarCanal,
  aoMudarNivel,
  mostrarCanal = true,
}) => (
  <div className="flex flex-col gap-4">
    <SeletorDeRede valor={rede} aoMudar={aoMudarRede} />
    {rede === 'google' && mostrarCanal && (
      <SeletorDeCanal valor={canal} aoMudar={aoMudarCanal} />
    )}
    {rede === 'meta' && (
      <SeletorDeNivel valor={nivel} aoMudar={aoMudarNivel} />
    )}
  </div>
);

export default EixosDoHub;
