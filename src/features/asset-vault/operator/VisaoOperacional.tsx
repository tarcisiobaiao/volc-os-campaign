import { ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { fonteDoInventario } from "./referencia";
import type { VisaoDoCofre } from "./visao";
import { FOCO, HIT, PRESSIONAR } from "./chrome";

function Numero({ valor }: { valor: number | null }) {
  if (valor === null) {
    return <span className="text-sm text-muted-foreground">sem amostra</span>;
  }
  return <span className="font-display text-xl font-semibold tabular-nums leading-none">{valor}</span>;
}

export function VisaoOperacional({
  visao,
  lidoEm,
  aoSeguir,
}: {
  visao: VisaoDoCofre;
  lidoEm: number | null;
  aoSeguir?: (ativoId: string) => void;
}) {
  const frescor = lidoEm
    ? new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" }).format(new Date(lidoEm))
    : "ainda não lido";

  return (
    <section
      aria-label="Visão operacional"
      className="mt-6 border-y border-border py-4"
    >
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)_minmax(16rem,0.8fr)]">
        <div>
          <p className="kicker">O que possuímos</p>
          <p className="mt-2 flex items-baseline gap-2">
            <Numero valor={visao.total} />
            <span className="text-sm text-muted-foreground">ativos no registro</span>
          </p>
          {visao.porEstado.length ? (
            <ol className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-sm">
              {visao.porEstado.map((item) => (
                <li key={item.chave} className="flex items-baseline gap-1.5">
                  <span className="tabular-nums font-medium">{item.total}</span>
                  <span className="text-muted-foreground">{item.rotulo}</span>
                </li>
              ))}
            </ol>
          ) : (
            <p className="mt-3 text-sm text-muted-foreground">Nenhum estado para contar.</p>
          )}
        </div>

        <div>
          <p className="kicker">O que está pronto, e o que impede</p>
          <p className="mt-2 font-display text-base font-semibold text-balance">{visao.prontidaoDominante.rotulo}</p>
          <p className="mt-1 text-sm leading-5 text-muted-foreground text-pretty">{visao.prontidaoDominante.detalhe}</p>
          <dl className="mt-3 grid grid-cols-1 gap-x-4 gap-y-2 text-sm min-[360px]:grid-cols-2">
            <div>
              <dt className="text-muted-foreground">Verificados</dt>
              <dd><Numero valor={visao.verificados} /></dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Sem acesso</dt>
              <dd><Numero valor={visao.semAcesso} /></dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Revisão vencida</dt>
              <dd><Numero valor={visao.revisoesVencidas} /></dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Cofre bloqueado</dt>
              <dd><Numero valor={visao.cofreBloqueado} /></dd>
            </div>
          </dl>
          {visao.amostra === "presente" && visao.bloqueadores.length === 0 ? (
            <p className="mt-3 text-sm text-muted-foreground">Nenhum bloqueio derivado deste recorte. Isso não prova publicação.</p>
          ) : visao.bloqueadores.length ? (
            <ul className="mt-3 space-y-1 text-sm">
              {visao.bloqueadores.map((b) => (
                <li key={b} className="text-pretty">{b}</li>
              ))}
            </ul>
          ) : null}
        </div>

        <div>
          <p className="kicker">Próximo ato seguro</p>
          <p className="mt-2 text-sm font-medium text-pretty">{visao.proximoAto.frase}</p>
          {visao.proximoAto.nome ? (
            <p className="mt-1 text-xs text-muted-foreground">{visao.proximoAto.nome}</p>
          ) : null}
          {visao.proximoAto.ativoId && aoSeguir ? (
            <button
              type="button"
              onClick={() => aoSeguir(visao.proximoAto.ativoId!)}
              className={cn("mt-3 inline-flex items-center gap-1 text-sm font-medium text-primary", HIT, FOCO, PRESSIONAR)}
            >
              Abrir este ativo <ArrowRight aria-hidden="true" className="h-4 w-4" />
            </button>
          ) : null}
          <p className="mt-4 text-[11px] leading-4 text-muted-foreground">
            Frescor: {frescor} · fonte {fonteDoInventario()}
          </p>
        </div>
      </div>
    </section>
  );
}

export function FronteiraDeSeguranca() {
  return (
    <p className="mt-4 text-xs leading-5 text-muted-foreground text-pretty" aria-label="Fronteira de segurança">
      <strong className="font-semibold text-foreground">Zero segredo neste contrato</strong>
      {" "}1Password contém o valor. O Cofre contém referência, owner, finalidade e estado.
      Conectado não significa credencial válida. Referência cadastrada não significa acesso provado.
      Verificado precisa de recibo e data. Cofre bloqueado e autorização negada são fatos diferentes.
    </p>
  );
}
