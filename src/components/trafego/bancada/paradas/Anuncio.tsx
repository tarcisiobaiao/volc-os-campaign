/**
 * Parada 4 — Anúncio. O que o anúncio vai dizer.
 *
 * ## Uma regra só de pronto, e ela é do servidor
 *
 * `status === 'done'`. Nada mais. O trilho anterior usava `copy={!!escrita}` e
 * ficava verde para `'running'`, `'error'` e para uma linha `perdida` — três
 * estados em que não há copy utilizável —, enquanto o cartão logo abaixo usava
 * `escrita?.status === 'done'`. Duas réguas na mesma tela, discordando.
 *
 * ## Não se oferece "editar anúncio publicado"
 *
 * O contrato correto é substituir e aposentar: o Google não edita um anúncio
 * servido, ele cria outro e retira o primeiro. Um botão "editar" aqui prometeria
 * uma operação que a plataforma não tem, e o operador descobriria a diferença
 * depois de gastar a escrita.
 */
import React from 'react';
import { CircleCheck, CircleHelp, CircleOff, Loader } from 'lucide-react';

import { BlocoDeEvidencia, LinhaDeFato } from '../BlocoDeEvidencia';
import { ChipDeEstado } from '../ChipDeEstado';
import { CartaoCopy } from '../../CartaoCopy';
import type { CopyGerada, CopyPersistida } from '@/types/trafego';

/** O instante ISO em leitura humana, ou a ausência dita. */
function instante(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString('pt-BR');
}

const ESTADO: Record<string, {
  palavra: string; descricao: string;
  tom: 'bom' | 'atencao' | 'ruim' | 'neutro';
  glifo: React.ComponentType<{ className?: string }>;
}> = {
  done: {
    palavra: 'escrito',
    descricao: 'a cascata fechou e a copy está persistida no servidor',
    tom: 'bom', glifo: CircleCheck,
  },
  running: {
    palavra: 'escrevendo',
    descricao: 'a escrita está em curso no servidor; ela sobrevive a fechar esta aba',
    tom: 'atencao', glifo: Loader,
  },
  error: {
    palavra: 'falhou',
    descricao: 'a escrita terminou em erro e não há copy utilizável',
    tom: 'ruim', glifo: CircleOff,
  },
};

export const ParadaAnuncio: React.FC<{
  copy: CopyPersistida | null;
  escrevendo: boolean;
  podeEscrever: boolean;
  motivoBloqueio: string;
  onEscrever: () => void;
  onEditar: (c: CopyGerada) => void;
  modelo: string;
  onModelo: (m: string) => void;
  /** `true` quando os termos mudaram depois da escrita. */
  desatualizada?: boolean;
}> = ({
  copy, escrevendo, podeEscrever, motivoBloqueio, onEscrever, onEditar,
  modelo, onModelo, desatualizada,
}) => {
  const e = copy ? (ESTADO[copy.status] ?? {
    palavra: copy.status,
    descricao: 'o servidor declarou um estado que esta tela não conhece',
    tom: 'atencao' as const, glifo: CircleHelp,
  }) : null;

  return (
    <div className="space-y-4">
      <BlocoDeEvidencia titulo="O estado da copy" tom={e?.tom ?? 'neutro'}>
        <div className="mb-3">
          {e ? (
            <ChipDeEstado glifo={e.glifo} palavra={e.palavra} descricao={e.descricao} tom={e.tom} />
          ) : (
            <ChipDeEstado
              glifo={CircleHelp} palavra="não escrito" tom="neutro"
              descricao="ninguém escreveu o anúncio desta oportunidade ainda"
            />
          )}
        </div>

        <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
          <LinhaDeFato
            rotulo="títulos"
            valor={copy?.copy ? copy.copy.headlines.length : null}
            fonte="a escrita"
            ausencia="nenhum"
          />
          <LinhaDeFato
            rotulo="descrições"
            valor={copy?.copy ? copy.copy.descriptions.length : null}
            fonte="a escrita"
            ausencia="nenhuma"
          />
          <LinhaDeFato
            rotulo="URL final da copy"
            valor={copy?.copy?.ancoragem
              ? <span className="break-all">{String((copy.copy.ancoragem as Record<string, unknown>).url_final ?? '')}</span>
              : null}
            fonte="a escrita"
            ausencia="não declarada na copy"
          />
          <LinhaDeFato
            rotulo="criada em"
            valor={instante(copy?.criado_em)}
            fonte="o servidor"
            ausencia="sem carimbo"
          />
          <LinhaDeFato
            rotulo="última atualização"
            valor={instante(copy?.atualizado_em)}
            fonte="o servidor"
            ausencia="sem carimbo"
          />
          <LinhaDeFato
            rotulo="fatos do funil usados"
            valor={copy ? copy.fatos_usados : null}
            fonte="a escrita"
          />
        </dl>

        {/* ⚠️ `fatos_descartados` NÃO é ruído a esconder. Medido no card 73: 4
            dos 6 fatos do funil têm `tipo: 'afirmacao'`, que a seção 2 do
            PROMPT.md não conhece — a copy foi escrita sem eles, e quem lê o
            anúncio precisa saber disso para não achar que o funil não tinha
            lastro. */}
        {copy && copy.fatos_descartados.length > 0 && (
          <p className="mt-3 max-w-[70ch] text-sm leading-6 text-muted-foreground text-pretty">
            {copy.fatos_descartados.length} fato(s) do funil ficaram de fora da escrita:{' '}
            {copy.fatos_descartados.join('; ')}.
          </p>
        )}

        {copy?.erro && (
          <p className="mt-3 max-w-[70ch] text-sm leading-6 text-destructive text-pretty">
            {copy.erro}
          </p>
        )}

        {copy?.perdida && (
          <p className="mt-3 max-w-[70ch] text-sm leading-6 text-warning text-pretty">
            A linha desta escrita foi perdida no servidor. O que aparece abaixo pode não
            ser o que seria enviado — reescreva antes de provar.
          </p>
        )}
      </BlocoDeEvidencia>

      <CartaoCopy
        escrita={copy}
        escrevendo={escrevendo}
        podeEscrever={podeEscrever}
        motivoBloqueio={motivoBloqueio}
        desatualizada={desatualizada}
        onEscrever={onEscrever}
        onEditar={onEditar}
        modelo={modelo}
        onModelo={onModelo}
      />
    </div>
  );
};
