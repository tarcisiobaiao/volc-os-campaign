/**
 * Os campos da configuração de canal — cada um sabe o CAMINHO do contrato que
 * ele preenche (`configuracao_search.lance.target_cpa`) e mostra, embaixo de
 * si, o erro que o servidor devolveu para esse caminho no 422.
 *
 * O erro vem de um contexto (`ProvedorDeErros`), alimentado pela página com o
 * 422 da última prova e com a conferência prévia pelo esquema vivo. O texto é
 * o `msg` do servidor, inteiro: a tela decide ONDE ele aparece, não o que diz.
 */
import React, { createContext, useContext } from 'react';
import { AlertTriangle, Plus, X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';
import { SEM_ERROS, errosNoCaminho, type ErrosDoServidor } from '@/lib/trafego/configuracao/erros422';
import { linhas } from '@/lib/trafego/configuracao/montagem';
import { DIAS_DA_SEMANA } from '@/types/trafegoCanais';
import type { DiaDaSemana } from '@/types/trafegoCanais';
import type { LinhaDeFaixa } from '@/lib/trafego/configuracao/formularios';

const ContextoDeErros = createContext<ErrosDoServidor>(SEM_ERROS);

export const ProvedorDeErros: React.FC<{ erros: ErrosDoServidor; children: React.ReactNode }> =
  ({ erros, children }) => <ContextoDeErros.Provider value={erros}>{children}</ContextoDeErros.Provider>;

export function useErrosDoCampo(caminho?: string): string[] {
  const erros = useContext(ContextoDeErros);
  return caminho ? errosNoCaminho(erros, caminho) : [];
}

/** O erro do servidor para um caminho. `data-caminho` é o elo com o 422. */
export const ErroDoCampo: React.FC<{ caminho?: string; id?: string }> = ({ caminho, id }) => {
  const msgs = useErrosDoCampo(caminho);
  if (!msgs.length) return null;
  return (
    <span id={id} role="alert" data-caminho={caminho}
          className="mt-1 flex items-start gap-1.5 text-xs font-medium leading-relaxed text-destructive">
      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
      <span>{msgs.join(' · ')}</span>
    </span>
  );
};

const ROTULO = 'text-sm font-semibold text-foreground';
const AJUDA = 'block text-xs font-normal leading-relaxed text-muted-foreground';

export const Secao: React.FC<{
  titulo: string;
  descricao?: React.ReactNode;
  caminho?: string;
  children: React.ReactNode;
  className?: string;
}> = ({ titulo, descricao, caminho, children, className }) => (
  <fieldset className={cn('space-y-4 border-t border-border pt-5', className)}>
    <legend className="sr-only">{titulo}</legend>
    <div>
      <h4 className="font-display text-base font-semibold text-foreground">{titulo}</h4>
      {descricao && <p className="mt-1 max-w-[68ch] text-sm leading-relaxed text-muted-foreground">{descricao}</p>}
      <ErroDoCampo caminho={caminho} />
    </div>
    {children}
  </fieldset>
);

export const CampoTexto: React.FC<{
  id: string;
  rotulo: string;
  valor: string;
  onChange: (v: string) => void;
  caminho?: string;
  limite?: number;
  placeholder?: string;
  ajuda?: React.ReactNode;
  tipo?: 'text' | 'date' | 'time' | 'url' | 'color';
  prefixo?: string;
  numerico?: boolean;
  desabilitado?: boolean;
}> = ({ id, rotulo, valor, onChange, caminho, limite, placeholder, ajuda, tipo = 'text', prefixo, numerico, desabilitado }) => {
  const erros = useErrosDoCampo(caminho);
  const idErro = `${id}-erro`;
  return (
    <label htmlFor={id} className="block space-y-1.5">
      <span className={cn('flex items-end justify-between gap-3', ROTULO)}>
        {rotulo}
        {limite != null && (
          <span className={cn('text-xs font-medium tabular-nums',
            valor.length > limite ? 'text-destructive' : 'text-muted-foreground')}>
            {valor.length}/{limite}
          </span>
        )}
      </span>
      <span className={cn('flex items-center gap-1.5 rounded-md', prefixo && 'border border-input bg-background px-2')}>
        {prefixo && <span className="text-xs text-muted-foreground">{prefixo}</span>}
        <Input
          id={id}
          type={tipo}
          inputMode={numerico ? 'decimal' : undefined}
          value={valor}
          disabled={desabilitado}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          aria-invalid={erros.length > 0 || undefined}
          aria-describedby={erros.length ? idErro : undefined}
          className={cn('h-10 bg-background', prefixo && 'border-0 px-1 shadow-none focus-visible:ring-0',
            erros.length > 0 && !prefixo && 'border-destructive')}
        />
      </span>
      {ajuda && <span className={AJUDA}>{ajuda}</span>}
      <ErroDoCampo caminho={caminho} id={idErro} />
    </label>
  );
};

export interface OpcaoDeSelecao { valor: string; rotulo: string; desabilitada?: boolean }

export const CampoSelecao: React.FC<{
  id: string;
  rotulo: string;
  valor: string;
  opcoes: OpcaoDeSelecao[];
  onChange: (v: string) => void;
  caminho?: string;
  ajuda?: React.ReactNode;
  vazio?: string;
}> = ({ id, rotulo, valor, opcoes, onChange, caminho, ajuda, vazio }) => {
  const erros = useErrosDoCampo(caminho);
  return (
    <label htmlFor={id} className="block space-y-1.5">
      <span className={ROTULO}>{rotulo}</span>
      <select
        id={id}
        value={valor}
        onChange={(e) => onChange(e.target.value)}
        aria-invalid={erros.length > 0 || undefined}
        className={cn('flex h-10 w-full rounded-md border bg-background px-3 text-sm',
          erros.length ? 'border-destructive' : 'border-input')}
      >
        {vazio != null && <option value="">{vazio}</option>}
        {opcoes.map((o) => (
          <option key={o.valor} value={o.valor} disabled={o.desabilitada}>{o.rotulo}</option>
        ))}
      </select>
      {ajuda && <span className={AJUDA}>{ajuda}</span>}
      <ErroDoCampo caminho={caminho} />
    </label>
  );
};

export const CampoLista: React.FC<{
  id: string;
  rotulo: string;
  valor: string;
  onChange: (v: string) => void;
  caminho?: string;
  maximo?: number;
  limitePorItem?: number;
  placeholder?: string;
  ajuda?: React.ReactNode;
  linhasVisiveis?: number;
}> = ({ id, rotulo, valor, onChange, caminho, maximo, limitePorItem, placeholder, ajuda, linhasVisiveis = 3 }) => {
  const itens = linhas(valor);
  const longos = limitePorItem == null ? 0 : itens.filter((i) => i.length > limitePorItem).length;
  const excede = maximo != null && itens.length > maximo;
  const erros = useErrosDoCampo(caminho);
  return (
    <label htmlFor={id} className="block space-y-1.5">
      <span className={cn('flex flex-wrap items-end justify-between gap-3', ROTULO)}>
        {rotulo}
        <span className={cn('text-xs font-medium tabular-nums',
          excede || longos ? 'text-destructive' : 'text-muted-foreground')}>
          {itens.length}{maximo != null ? `/${maximo}` : ''} itens{longos ? ` · ${longos} acima do limite` : ''}
        </span>
      </span>
      <Textarea
        id={id}
        value={valor}
        rows={linhasVisiveis}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        aria-invalid={erros.length > 0 || undefined}
        className={cn('resize-y bg-background text-sm leading-relaxed', erros.length > 0 && 'border-destructive')}
      />
      <span className={AJUDA}>
        Uma linha por item{limitePorItem ? ` · até ${limitePorItem} caracteres` : ''}{ajuda ? ' · ' : ''}{ajuda}
      </span>
      <ErroDoCampo caminho={caminho} />
    </label>
  );
};

export const Interruptor: React.FC<{
  id: string;
  rotulo: React.ReactNode;
  marcado: boolean;
  onChange: (v: boolean) => void;
  caminho?: string;
  ajuda?: React.ReactNode;
  desabilitado?: boolean;
}> = ({ id, rotulo, marcado, onChange, caminho, ajuda, desabilitado }) => (
  <div>
    <label htmlFor={id} className={cn('flex min-h-11 cursor-pointer items-start gap-3 rounded-lg border border-border bg-background px-4 py-3 text-sm',
      desabilitado && 'cursor-not-allowed opacity-60')}>
      <input id={id} type="checkbox" checked={marcado} disabled={desabilitado}
             onChange={(e) => onChange(e.target.checked)} className="mt-0.5 h-4 w-4 shrink-0 accent-primary" />
      <span className="min-w-0">
        <span className="block font-medium text-foreground">{rotulo}</span>
        {ajuda && <span className={cn(AJUDA, 'mt-0.5')}>{ajuda}</span>}
      </span>
    </label>
    <ErroDoCampo caminho={caminho} />
  </div>
);

/** Sim/não sem default: `null` é "ninguém decidiu", e a tela diz isso. */
export const DecisaoSimNao: React.FC<{
  rotulo: string;
  valor: boolean | null;
  onChange: (v: boolean) => void;
  sim: string;
  nao: string;
  caminho?: string;
  ajuda?: React.ReactNode;
}> = ({ rotulo, valor, onChange, sim, nao, caminho, ajuda }) => (
  <fieldset className="space-y-2">
    <legend className={ROTULO}>{rotulo}</legend>
    <div className="grid gap-2 sm:grid-cols-2">
      {([[true, sim], [false, nao]] as const).map(([opcao, texto]) => (
        <button
          key={String(opcao)}
          type="button"
          aria-pressed={valor === opcao}
          onClick={() => onChange(opcao)}
          className={cn('min-h-10 rounded-lg border px-3 py-2 text-left text-sm transition-colors',
            valor === opcao ? 'border-primary/45 bg-primary/[0.07] font-semibold text-foreground'
              : 'border-border bg-background text-muted-foreground hover:border-primary/25')}
        >{texto}</button>
      ))}
    </div>
    {valor == null && <p className="text-xs font-medium text-warning">Sem decisão — o contrato não tem default aqui.</p>}
    {ajuda && <p className={AJUDA}>{ajuda}</p>}
    <ErroDoCampo caminho={caminho} />
  </fieldset>
);

/** Marcação múltipla de um enum (rótulos, idades, dispositivos…). */
export function MultiEscolha<T extends string>({
  rotulo, opcoes, valores, onChange, caminho, rotuloDe, ajuda,
}: {
  rotulo: string;
  opcoes: readonly T[];
  valores: readonly T[];
  onChange: (v: T[]) => void;
  caminho?: string;
  rotuloDe?: (v: T) => string;
  ajuda?: React.ReactNode;
}) {
  return (
    <fieldset className="space-y-2">
      <legend className={ROTULO}>{rotulo}</legend>
      <div className="flex flex-wrap gap-2">
        {opcoes.map((o) => {
          const ativo = valores.includes(o);
          return (
            <button key={o} type="button" aria-pressed={ativo}
                    onClick={() => onChange(ativo ? valores.filter((v) => v !== o) : [...valores, o])}
                    className={cn('min-h-9 rounded-full border px-3 text-xs transition-colors',
                      ativo ? 'border-primary/45 bg-primary/[0.08] font-semibold text-foreground'
                        : 'border-border bg-background text-muted-foreground hover:border-primary/25')}>
              {rotuloDe ? rotuloDe(o) : o}
            </button>
          );
        })}
      </div>
      {ajuda && <p className={AJUDA}>{ajuda}</p>}
      <ErroDoCampo caminho={caminho} />
    </fieldset>
  );
}

/** Uma lista de linhas editáveis (faixas, dispositivos, regras…). */
export function Repetidor<T>({
  rotulo, itens, onChange, novo, render, caminho, maximo, rotuloDoBotao = 'Adicionar',
}: {
  rotulo: string;
  itens: T[];
  onChange: (v: T[]) => void;
  novo: () => T;
  render: (item: T, i: number, alterar: (v: T) => void) => React.ReactNode;
  caminho?: string;
  maximo?: number;
  rotuloDoBotao?: string;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-3">
        <span className={ROTULO}>{rotulo}</span>
        <Button type="button" variant="outline" size="sm" className="min-h-9"
                disabled={maximo != null && itens.length >= maximo}
                onClick={() => onChange([...itens, novo()])}>
          <Plus className="h-3.5 w-3.5" aria-hidden /> {rotuloDoBotao}
        </Button>
      </div>
      {itens.length === 0 && <p className="text-xs text-muted-foreground">Nenhum item — o contrato trata vazio como ausência.</p>}
      <ul className="space-y-2">
        {itens.map((item, i) => (
          // eslint-disable-next-line react/no-array-index-key
          <li key={i} className="flex items-start gap-2 rounded-lg border border-border bg-muted/20 p-3">
            <div className="min-w-0 flex-1">
              {render(item, i, (v) => onChange(itens.map((x, j) => (j === i ? v : x))))}
            </div>
            <Button type="button" variant="ghost" size="icon" className="h-9 w-9 shrink-0"
                    aria-label={`Remover item ${i + 1} de ${rotulo}`}
                    onClick={() => onChange(itens.filter((_, j) => j !== i))}>
              <X className="h-4 w-4" aria-hidden />
            </Button>
          </li>
        ))}
      </ul>
      <ErroDoCampo caminho={caminho} />
    </div>
  );
}

export const ROTULO_DO_DIA: Record<DiaDaSemana, string> = {
  MONDAY: 'segunda', TUESDAY: 'terça', WEDNESDAY: 'quarta', THURSDAY: 'quinta',
  FRIDAY: 'sexta', SATURDAY: 'sábado', SUNDAY: 'domingo',
};

/** Agenda por faixas HH:MM. `comAjuste` só em Search (bid_modifier). */
export const EditorDeAgenda: React.FC<{
  id: string;
  rotulo: string;
  faixas: LinhaDeFaixa[];
  onChange: (f: LinhaDeFaixa[]) => void;
  caminho: string;
  comAjuste?: boolean;
  ajuda?: React.ReactNode;
  /** Display grava hora e minuto separados (`inicio_hora`); o erro do 422
   *  aponta esse nome, e é nele que o campo precisa ouvir. */
  nomesDaHora?: { inicio: string; fim: string };
}> = ({ id, rotulo, faixas, onChange, caminho, comAjuste = false, ajuda, nomesDaHora = { inicio: 'inicio', fim: 'fim' } }) => (
  <div className="space-y-2">
    <Repetidor
      rotulo={rotulo}
      itens={faixas}
      onChange={onChange}
      caminho={caminho}
      rotuloDoBotao="Adicionar faixa"
      novo={() => ({ dia: 'MONDAY', inicio: '08:00', fim: '22:00', ajuste: '' })}
      render={(f, i, alterar) => (
        <div className={cn('grid gap-2', comAjuste ? 'sm:grid-cols-4' : 'sm:grid-cols-3')}>
          <CampoSelecao id={`${id}-${i}-dia`} rotulo="dia" valor={f.dia}
                        caminho={`${caminho}[${i}].dia`}
                        opcoes={DIAS_DA_SEMANA.map((d) => ({ valor: d, rotulo: ROTULO_DO_DIA[d] }))}
                        onChange={(v) => alterar({ ...f, dia: v as DiaDaSemana })} />
          <CampoTexto id={`${id}-${i}-inicio`} rotulo="início" valor={f.inicio} placeholder="08:00"
                      caminho={`${caminho}[${i}].${nomesDaHora.inicio}`} onChange={(v) => alterar({ ...f, inicio: v })} />
          <CampoTexto id={`${id}-${i}-fim`} rotulo="fim" valor={f.fim} placeholder="22:00"
                      caminho={`${caminho}[${i}].${nomesDaHora.fim}`} onChange={(v) => alterar({ ...f, fim: v })} />
          {comAjuste && (
            <CampoTexto id={`${id}-${i}-ajuste`} rotulo="ajuste de lance" valor={f.ajuste} numerico
                        placeholder="1,2 = +20%" caminho={`${caminho}[${i}].ajuste`}
                        onChange={(v) => alterar({ ...f, ajuste: v })} />
          )}
        </div>
      )}
    />
    <p className={AJUDA}>
      Minutos em 00, 15, 30 ou 45; 24:00 fecha o dia. Até 6 faixas por dia, sem sobreposição.
      {ajuda ? ' ' : ''}{ajuda}
    </p>
  </div>
);
