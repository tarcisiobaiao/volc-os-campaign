/**
 * Paleta de comandos `/` — padrão combobox + listbox (WAI-ARIA 1.2).
 *
 * O foco fica no campo de texto; a opção ativa é apontada por
 * `aria-activedescendant`. Comandos indisponíveis aparecem `aria-disabled`,
 * com o motivo visível: quem usa no Telegram entende por que não roda aqui.
 */
import React from 'react';

import { cn } from '@/lib/utils';

import type { ComandoDoCatalogo } from '../tipos';

export interface OpcaoDaPaleta {
  comando: ComandoDoCatalogo;
  idDom: string;
}

interface Props {
  id: string;
  web: OpcaoDaPaleta[];
  telegram: OpcaoDaPaleta[];
  ativa: number;
  carregando: boolean;
  falhou: boolean;
  onEscolher: (c: ComandoDoCatalogo) => void;
  onApontar: (indice: number) => void;
}

const ROTULO_DA_CLASSE: Record<string, string> = {
  requires_tool: 'Usa ferramenta',
  external_mutation: 'Muda algo fora',
  telegram_only: 'Só no Telegram',
  hermes_safe: 'Fora da V1',
  local_ui: 'Nesta tela',
};

const Item: React.FC<{
  o: OpcaoDaPaleta;
  indice: number;
  ativa: boolean;
  onEscolher: Props['onEscolher'];
  onApontar: Props['onApontar'];
}> = ({ o, indice, ativa, onEscolher, onApontar }) => {
  const c = o.comando;
  return (
    <li
      id={o.idDom}
      role="option"
      aria-selected={ativa}
      aria-disabled={!c.disponivel || undefined}
      onMouseDown={(e) => e.preventDefault() /* não tira o foco do campo */}
      onClick={() => onEscolher(c)}
      onMouseMove={() => !ativa && onApontar(indice)}
      className={cn(
        'flex min-h-11 cursor-pointer flex-col justify-center gap-0.5 rounded-md px-2.5 py-1.5',
        ativa ? 'bg-muted' : 'bg-transparent',
      )}
    >
      <span className="flex items-baseline gap-2">
        <span className={cn('font-data text-denso', c.disponivel ? 'text-foreground' : 'text-muted-foreground')}>
          /{c.nome}
          {c.args && c.disponivel ? <span className="text-muted-foreground"> {c.args}</span> : null}
        </span>
        {!c.disponivel ? (
          <span className="ml-auto shrink-0 rounded-full border border-border px-1.5 text-micro font-medium tracking-normal text-muted-foreground">
            {ROTULO_DA_CLASSE[c.classe] ?? 'Indisponível'}
          </span>
        ) : null}
      </span>
      <span className="text-micro font-normal tracking-normal text-muted-foreground">
        {c.disponivel ? c.descricao : c.motivo}
      </span>
    </li>
  );
};

export const PaletaDeComandos: React.FC<Props> = ({ id, web, telegram, ativa, carregando, falhou, onEscolher, onApontar }) => (
  <div className="absolute inset-x-3 bottom-full z-[1] mb-2 max-h-[min(22rem,50dvh)] overflow-y-auto rounded-[10px] border border-border bg-popover p-1.5 shadow-elevated">
    {carregando || falhou ? (
      <p role="status" className="px-2.5 py-2 text-denso text-muted-foreground">
        {falhou ? 'Não foi possível carregar os comandos. Feche e abra a Bia.' : 'Carregando comandos…'}
      </p>
    ) : null}
    <ul id={id} role="listbox" aria-label="Comandos da Bia" className="space-y-0.5">
      {web.length ? (
        <li role="presentation" className="kicker px-2.5 pb-0.5 pt-1">Nesta conversa</li>
      ) : null}
      {web.map((o, i) => (
        <Item key={o.idDom} o={o} indice={i} ativa={i === ativa} onEscolher={onEscolher} onApontar={onApontar} />
      ))}
      {telegram.length ? (
        <li role="presentation" className="kicker px-2.5 pb-0.5 pt-2">Do Telegram — não rodam na web</li>
      ) : null}
      {telegram.map((o, i) => (
        <Item
          key={o.idDom}
          o={o}
          indice={web.length + i}
          ativa={web.length + i === ativa}
          onEscolher={onEscolher}
          onApontar={onApontar}
        />
      ))}
      {!carregando && !falhou && !web.length && !telegram.length ? (
        <li role="presentation" className="px-2.5 py-2 text-denso text-muted-foreground">
          Nenhum comando com esse nome. Apague a barra para escrever uma mensagem.
        </li>
      ) : null}
    </ul>
  </div>
);
