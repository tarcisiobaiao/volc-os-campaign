/**
 * Os campos do briefing, com rótulo visível e erro ligado ao input.
 *
 * ## Por que não `placeholder` como rótulo
 *
 * Porque ele some quando alguém começa a digitar, e some justamente para quem
 * mais precisa dele: quem foi interrompido no meio do preenchimento. Além
 * disso, leitor de tela não é obrigado a anunciá-lo. O DESIGN.md fecha a
 * questão em uma linha: "Never rely on placeholder text as a label."
 *
 * ## Como o erro chega a quem não vê a cor
 *
 * `aria-invalid` marca o campo, `aria-describedby` liga o texto ao campo, e o
 * texto está lá. Borda vermelha sozinha não é mensagem.
 */
import React from 'react';

import { cn } from '@/lib/utils';

const CONTROLE = cn(
  'w-full rounded-md border border-input bg-card px-3 text-sm text-foreground',
  'placeholder:text-muted-foreground/70',
  'transition-colors duration-150 ease-out',
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
  'disabled:cursor-not-allowed disabled:opacity-60',
);

const Moldura: React.FC<{
  id: string;
  rotulo: string;
  ajuda?: string;
  erro?: string;
  obrigatorio?: boolean;
  children: (props: {
    id: string;
    'aria-invalid': boolean;
    'aria-describedby': string | undefined;
  }) => React.ReactNode;
}> = ({ id, rotulo, ajuda, erro, obrigatorio, children }) => {
  const idAjuda = ajuda ? `${id}-ajuda` : undefined;
  const idErro = erro ? `${id}-erro` : undefined;
  const descrito = [idAjuda, idErro].filter(Boolean).join(' ') || undefined;
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-[13px] font-medium text-foreground">
        {rotulo}
        {obrigatorio && (
          <span className="ml-1 text-muted-foreground" aria-hidden>
            (obrigatório)
          </span>
        )}
        {obrigatorio && <span className="sr-only"> (obrigatório)</span>}
      </label>
      {ajuda && (
        <p id={idAjuda} className="text-[12px] leading-relaxed text-muted-foreground">
          {ajuda}
        </p>
      )}
      {children({ id, 'aria-invalid': Boolean(erro), 'aria-describedby': descrito })}
      {erro && (
        <p id={idErro} className="text-[12px] leading-relaxed text-destructive">
          {erro}
        </p>
      )}
    </div>
  );
};

export const CampoDeTexto: React.FC<{
  id: string;
  rotulo: string;
  valor: string;
  aoMudar: (v: string) => void;
  ajuda?: string;
  erro?: string;
  obrigatorio?: boolean;
  maximo?: number;
}> = ({ id, rotulo, valor, aoMudar, ajuda, erro, obrigatorio, maximo }) => (
  <Moldura id={id} rotulo={rotulo} ajuda={ajuda} erro={erro} obrigatorio={obrigatorio}>
    {(props) => (
      <input
        {...props}
        type="text"
        className={cn(CONTROLE, 'h-10', erro && 'border-destructive')}
        value={valor}
        maxLength={maximo}
        onChange={(e) => aoMudar(e.target.value)}
      />
    )}
  </Moldura>
);

export const CampoDeArea: React.FC<{
  id: string;
  rotulo: string;
  valor: string;
  aoMudar: (v: string) => void;
  ajuda?: string;
  erro?: string;
  obrigatorio?: boolean;
  linhas?: number;
}> = ({ id, rotulo, valor, aoMudar, ajuda, erro, obrigatorio, linhas = 4 }) => (
  <Moldura id={id} rotulo={rotulo} ajuda={ajuda} erro={erro} obrigatorio={obrigatorio}>
    {(props) => (
      <textarea
        {...props}
        rows={linhas}
        className={cn(CONTROLE, 'py-2 leading-relaxed', erro && 'border-destructive')}
        value={valor}
        onChange={(e) => aoMudar(e.target.value)}
      />
    )}
  </Moldura>
);

export interface OpcaoDeEscolha {
  valor: string;
  rotulo: string;
  descricao: string;
  disponivel?: boolean;
  motivo?: string | null;
}

/**
 * Grupo de escolha com input nativo.
 *
 * Nativo de propósito: caixa e rádio de verdade já trazem papel, estado,
 * navegação por teclado e anúncio de grupo. Um `div` com `role` copiado à mão
 * acerta o papel e erra o resto na primeira tela que ninguém testou.
 */
export const GrupoDeEscolha: React.FC<{
  nome: string;
  legenda: string;
  ajuda?: string;
  multipla: boolean;
  opcoes: OpcaoDeEscolha[];
  selecionados: string[];
  aoAlternar: (valor: string) => void;
  erro?: string;
  colunas?: 1 | 2;
}> = ({ nome, legenda, ajuda, multipla, opcoes, selecionados, aoAlternar, erro, colunas = 1 }) => {
  const idErro = erro ? `${nome}-erro` : undefined;
  const idAjuda = ajuda ? `${nome}-ajuda` : undefined;
  return (
    <fieldset
      aria-describedby={[idAjuda, idErro].filter(Boolean).join(' ') || undefined}
      aria-invalid={Boolean(erro)}
    >
      <legend className="text-[13px] font-medium text-foreground">{legenda}</legend>
      {ajuda && (
        <p id={idAjuda} className="mt-1 text-[12px] leading-relaxed text-muted-foreground">
          {ajuda}
        </p>
      )}
      <div className={cn('mt-3 grid gap-2', colunas === 2 && 'sm:grid-cols-2')}>
        {opcoes.map((opcao) => {
          const id = `${nome}-${opcao.valor}`;
          const desabilitado = opcao.disponivel === false;
          const idMotivo = opcao.motivo ? `${id}-motivo` : undefined;
          return (
            <div
              key={opcao.valor}
              className={cn(
                'flex items-start gap-3 rounded-md border border-border px-3 py-2.5',
                'transition-colors duration-150 ease-out',
                desabilitado
                  ? 'bg-muted/60 opacity-80'
                  : 'bg-muted/30 hover:border-primary/40 hover:bg-primary/[0.06]',
                !desabilitado &&
                  selecionados.includes(opcao.valor) &&
                  'border-primary/60 bg-primary/[0.07]',
              )}
            >
              <input
                id={id}
                name={multipla ? id : nome}
                type={multipla ? 'checkbox' : 'radio'}
                className="mt-0.5 h-5 w-5 shrink-0 accent-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                checked={selecionados.includes(opcao.valor)}
                disabled={desabilitado}
                aria-describedby={idMotivo}
                onChange={() => aoAlternar(opcao.valor)}
              />
              <label htmlFor={id} className={cn('min-w-0 flex-1', !desabilitado && 'cursor-pointer')}>
                <span className="block text-[13px] font-medium text-foreground">{opcao.rotulo}</span>
                <span className="mt-0.5 block text-[12px] leading-relaxed text-muted-foreground">
                  {opcao.descricao}
                </span>
                {opcao.motivo && (
                  <span
                    id={idMotivo}
                    /* ⚠️ Não use `text-warning-foreground` aqui: no tema escuro
                       ele é quase preto (`30 40% 10%`) sobre superfície escura,
                       e o motivo de indisponibilidade, que é a única explicação
                       da opção travada, ficaria ilegível justamente lá. */
                    className="mt-1 block text-[12px] leading-relaxed text-foreground"
                  >
                    Ainda não disponível: {opcao.motivo}
                  </span>
                )}
              </label>
            </div>
          );
        })}
      </div>
      {erro && (
        <p id={idErro} className="mt-2 text-[12px] leading-relaxed text-destructive">
          {erro}
        </p>
      )}
    </fieldset>
  );
};
