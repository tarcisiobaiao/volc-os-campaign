/** Prévia dos anexos no compositor: miniatura, nome, tamanho, progresso, remover, repetir. */
import React from 'react';

import { Button } from '@/components/ui/button';
import { Icone } from '@/components/ui/icone';
import { cn } from '@/lib/utils';

import { ICONES_BIA } from '../icones';
import { formatarTamanho, type ItemDeAnexo } from '../useAnexos';

import { iconeDoAnexo } from './Historico';

interface Props {
  itens: ItemDeAnexo[];
  onRemover: (chave: string) => void;
  onRepetir: (chave: string) => void;
}

export const FilaDeAnexos: React.FC<Props> = ({ itens, onRemover, onRepetir }) => (
  <ul aria-label="Arquivos para enviar" className="flex flex-col gap-1.5 px-3 pt-3">
    {itens.map((i) => {
      const pct = Math.round(i.progresso * 100);
      return (
        <li
          key={i.chave}
          className={cn(
            'flex min-w-0 items-center gap-2.5 rounded-md border bg-card py-1.5 pl-1.5 pr-1',
            i.estado === 'falhou' ? 'border-destructive/50' : 'border-border',
          )}
        >
          {i.previa && i.estado !== 'falhou' ? (
            <img
              src={i.previa}
              alt=""
              onError={(e) => { e.currentTarget.style.visibility = 'hidden'; }}
              className="h-10 w-10 shrink-0 rounded-[6px] bg-muted object-cover"
            />
          ) : (
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[6px] bg-muted text-muted-foreground">
              <Icone icon={iconeDoAnexo(i.familia, i.rotulo.toLowerCase())} />
            </span>
          )}
          <div className="min-w-0 flex-1">
            <p className="truncate text-denso font-medium text-foreground" title={i.nome}>{i.nome}</p>
            {i.estado === 'enviando' ? (
              <div className="mt-1 flex items-center gap-2">
                <div
                  role="progressbar"
                  aria-label={`Enviando ${i.nome}`}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={pct}
                  className="h-1 flex-1 overflow-hidden rounded-full bg-muted"
                >
                  <div
                    className="h-full w-full origin-left rounded-full bg-primary motion-safe:transition-transform motion-safe:duration-200"
                    style={{ transform: `scaleX(${Math.max(0.04, i.progresso)})` }}
                  />
                </div>
                <span className="numero shrink-0 text-micro text-muted-foreground">{pct}%</span>
              </div>
            ) : i.estado === 'falhou' ? (
              <p className="flex items-start gap-1 text-micro font-normal tracking-normal text-foreground">
                <Icone icon={ICONES_BIA.alerta} tamanho="sm" className="mt-px shrink-0 text-destructive" />
                <span><span className="sr-only">Falha: </span>{i.erro ?? 'Falha no envio.'}</span>
              </p>
            ) : (
              <p className="text-micro font-normal tracking-normal text-muted-foreground">
                {i.rotulo} · {formatarTamanho(i.tamanho)}
                {i.anexo?.truncado ? ' · só o início será lido' : ''}
                {i.anexo?.paginas ? ` · ${i.anexo.paginas} p.` : ''}
              </p>
            )}
          </div>
          {i.estado === 'falhou' ? (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="touch-target h-9 w-9 shrink-0"
              onClick={() => onRepetir(i.chave)}
            >
              <Icone icon={ICONES_BIA.repetir} tamanho="sm" rotulo={`Enviar de novo ${i.nome}`} />
            </Button>
          ) : null}
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="touch-target h-9 w-9 shrink-0"
            onClick={() => onRemover(i.chave)}
          >
            <Icone icon={ICONES_BIA.remover} tamanho="sm" rotulo={`Remover ${i.nome}`} />
          </Button>
        </li>
      );
    })}
  </ul>
);
