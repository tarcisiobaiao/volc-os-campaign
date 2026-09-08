/**
 * Os formatos, desenhados na proporção real em vez de listados como texto.
 *
 * O catálogo VEM DO SERVIDOR (`props.formatos`). Aqui já houve uma constante
 * escrita à mão com três dos quatro formatos: o `1.91x1` nunca aparecia na tela
 * e nenhum teste falhava, porque uma lista desatualizada não quebra nada, ela só
 * some. Componente que não conhece o catálogo não pode desatualizá-lo.
 */
import { Check } from 'lucide-react';

import type { FormatoDisponivel } from '../tipos';

export interface SeletorDeFormatosProps {
  formatos: readonly FormatoDisponivel[];
  selecionados: string[];
  onChange: (slots: string[]) => void;
  /** Desabilita a interação enquanto o catálogo ainda está sendo lido. */
  carregando?: boolean;
}

export function SeletorDeFormatos({
  formatos,
  selecionados,
  onChange,
  carregando = false,
}: SeletorDeFormatosProps) {
  if (carregando) {
    return (
      <p role="status" className="mt-4 text-sm text-muted-foreground">
        Lendo os formatos que este servidor produz…
      </p>
    );
  }
  if (formatos.length === 0) {
    return (
      <p role="status" className="mt-4 text-sm text-muted-foreground">
        Este servidor não publicou nenhum formato. Sem catálogo não há o que pedir.
      </p>
    );
  }

  return (
    <fieldset className="mt-4">
      <legend className="sr-only">Formatos permitidos</legend>
      <p className="mb-4 text-xs text-muted-foreground">
        Escolha uma ou mais proporções. Cada conceito é composto uma vez por formato.
      </p>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 sm:gap-3">
        {formatos.map((f) => {
          const ativo = selecionados.includes(f.slot);
          const altura = 44;
          const largura = Math.round((altura * f.largura) / f.altura);
          return (
            <button
              key={f.slot}
              type="button"
              aria-pressed={ativo}
              aria-label={`${f.rotulo}, ${f.proporcao}, ${f.largura} por ${f.altura} pixels`}
              onClick={() =>
                onChange(
                  ativo
                    ? selecionados.filter((s) => s !== f.slot)
                    : [...selecionados, f.slot],
                )
              }
              className={`relative flex min-h-36 min-w-0 flex-col items-center justify-center rounded-xl border px-2 py-4 transition-[border-color,background-color,color] duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 ${
                ativo
                  ? 'border-primary bg-primary/5 text-primary ring-1 ring-primary'
                  : 'border-border bg-card text-muted-foreground hover:border-primary/40'
              }`}
            >
              {ativo && (
                <span className="absolute right-2 top-2 rounded-full bg-primary p-0.5 text-primary-foreground">
                  <Check className="h-3 w-3" aria-hidden />
                </span>
              )}
              <span className="mb-3 flex h-12 items-center justify-center" aria-hidden>
                <span
                  className={`block rounded-lg border-2 ${
                    ativo ? 'border-primary bg-primary/10' : 'border-border bg-muted/40'
                  }`}
                  style={{ width: largura, height: altura }}
                />
              </span>
              <span className="text-center text-xs font-semibold leading-5">{f.rotulo}</span>
              <span className="mt-1 text-[11px] tabular-nums opacity-80">
                {f.largura} × {f.altura}
              </span>
              <span className="text-[10px] opacity-70">{f.proporcao}</span>
            </button>
          );
        })}
      </div>
      {selecionados.length === 0 && (
        <p className="mt-3 text-xs text-destructive">Escolha ao menos um formato.</p>
      )}
    </fieldset>
  );
}
