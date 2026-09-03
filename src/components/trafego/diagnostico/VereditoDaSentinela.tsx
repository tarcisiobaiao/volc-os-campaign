/**
 * O veredito da sentinela — o que aconteceu, em que nível, e o que fazer agora.
 *
 * ## Por que esta seção existe acima da escada
 *
 * A escada responde *onde* a entrega para. Ela é excelente nisso e é o segundo
 * passo da leitura. O primeiro é a pergunta que o operador realmente faz ao
 * abrir a tela às sete da manhã: **o que aconteceu, e o que eu faço agora.**
 *
 * Até 03/09/2026 essa pergunta não tinha resposta na tela. O veredito era
 * derivado no cliente sobre uma escada cujo degrau `conta` nunca era
 * preenchido — então toda campanha lia "Não foi possível apurar — parou em
 * conta", inclusive uma conta suspensa por política. O operador via um
 * problema nosso onde havia um fato da conta.
 *
 * ## As regras visuais que este arquivo obedece
 *
 * · **nenhum estado é comunicado só por cor.** Glifo, palavra e frase carregam
 *   o significado; a cor acompanha. É a mesma lei dos selos do inventário;
 * · **verde exige duas condições**, não uma: veredito saudável E evidência
 *   completa. Um `HEALTHY` com prova parcial é a conclusão certa apoiada numa
 *   prova que faltou, e `podeSerLidoComoBom` recusa pintá-lo;
 * · **o desconhecido aparece**. Uma seção que esconde o que não sabe é lida
 *   como "não há o que dizer", que é a conclusão mais cara que esta tela pode
 *   induzir por omissão;
 * · **nenhuma ação foi aplicada, e isso é DITO.** O operador lê a frase em vez
 *   de deduzi-la da ausência de um botão.
 */
import {
  Ban,
  CircleCheck,
  CircleHelp,
  CircleOff,
  Clock,
  Lock,
  TriangleAlert,
} from 'lucide-react';
import React from 'react';

import { Chip, type Tom } from '@/components/trafego/inventario/Selos';
import {
  escopoLegivel,
  fraseDasRecomendacoes,
  fraseDoDenominador,
  janelaLegivel,
  leituraDoStatus,
  podeSerLidoComoBom,
  tomDaSeveridade,
  tomDoVeredito,
} from '@/lib/diagnostico/sentinela';
import type {
  CausaDaSentinela,
  VeredictoDaSentinela as Veredito,
} from '@/types/diagnostico';
import { cn } from '@/lib/utils';

type Glifo = React.ComponentType<{ className?: string }>;

/** O glifo do tom. A forma dá o significado antes de a cor dar. */
const GLIFO: Record<Tom, Glifo> = {
  ruim: CircleOff,
  atencao: TriangleAlert,
  bom: CircleCheck,
  neutro: Clock,
  verificado: CircleCheck,
  info: CircleHelp,
};

/** Quanto tempo faz, em português. `null` quando não há carimbo. */
export function haQuantoTempo(iso: string | null, agora?: number): string | null {
  if (!iso) return null;
  const quando = Date.parse(iso);
  if (Number.isNaN(quando)) return null;
  const segundos = Math.max(0, Math.round(((agora ?? Date.now()) - quando) / 1000));
  if (segundos < 90) return 'há menos de dois minutos';
  const minutos = Math.round(segundos / 60);
  if (minutos < 90) return `há ${minutos} minutos`;
  const horas = Math.round(minutos / 60);
  if (horas < 36) return `há ${horas} horas`;
  return `há ${Math.round(horas / 24)} dias`;
}

const EVIDENCIA: Record<string, { palavra: string; descricao: string; tom: Tom }> = {
  apurada: {
    palavra: 'prova completa',
    descricao: 'todos os campos que este veredito depende foram lidos',
    tom: 'bom',
  },
  parcial: {
    palavra: 'prova parcial',
    descricao:
      'parte do que este veredito depende não foi lida — o que falta pode ' +
      'contradizer a conclusão',
    tom: 'atencao',
  },
  ausente: {
    palavra: 'sem prova',
    descricao:
      'a leitura falhou, está velha ou nunca aconteceu; nada aqui afirma que ' +
      'a campanha esteja bem',
    tom: 'atencao',
  },
};

function evidenciaLegivel(valor: string) {
  return (
    EVIDENCIA[valor] ?? {
      palavra: 'prova não reconhecida',
      descricao: `o sistema informou "${valor}", que esta versão não conhece`,
      // ⚠️ Nunca `bom`.
      tom: 'atencao' as Tom,
    }
  );
}

export interface VereditoDaSentinelaProps {
  veredito: Veredito;
  /** Injetável para que a prova do "há quanto tempo" não dependa do relógio. */
  agora?: number;
  className?: string;
}

export const VereditoDaSentinela: React.FC<VereditoDaSentinelaProps> = ({
  veredito,
  agora,
  className,
}) => {
  const leitura = leituraDoStatus(veredito.status);
  const tom = tomDoVeredito(veredito);
  const Glifo = GLIFO[tom] ?? CircleHelp;
  const janela = janelaLegivel(veredito.janela_do_guardiao);
  const prova = evidenciaLegivel(veredito.estado_da_evidencia);
  const idade = haQuantoTempo(veredito.observado_em, agora);
  const secundarias = veredito.causas_secundarias;

  return (
    <section
      aria-labelledby="sentinela-titulo"
      className={cn('max-w-[78ch]', className)}
    >
      <p className="kicker">veredito da sentinela</p>

      <div className="mt-1 flex items-start gap-2.5">
        <Glifo
          className={cn(
            'mt-1 h-5 w-5 shrink-0',
            tom === 'ruim' && 'text-destructive',
            tom === 'atencao' && 'text-warning',
            tom === 'bom' && 'text-success',
            (tom === 'neutro' || tom === 'info' || tom === 'verificado') &&
              'text-muted-foreground',
          )}
          aria-hidden
        />
        <div className="min-w-0">
          <h2
            id="sentinela-titulo"
            className="font-display text-lg font-semibold tracking-tight md:text-xl"
          >
            {leitura.titulo}
          </h2>
          <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">
            No nível da <strong className="font-medium text-foreground">
              {escopoLegivel(veredito.escopo)}
            </strong>
            : {leitura.afirma}
          </p>
        </div>
      </div>

      {/* A faixa de contexto: severidade, idade, frescor, janela e prova. */}
      <div className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1.5 text-[12px]">
        <Chip
          glifo={GLIFO[tomDaSeveridade(veredito.severidade)] ?? CircleHelp}
          palavra={veredito.severidade}
          descricao={`severidade ${veredito.severidade} — ${leitura.afirma}`}
          tom={tomDaSeveridade(veredito.severidade)}
        />
        <span aria-hidden>·</span>
        <span className="text-muted-foreground">
          {idade ? `lido ${idade}` : 'sem carimbo de leitura'}
        </span>
        <span aria-hidden>·</span>
        <span
          className="text-muted-foreground"
          title={`frescor da leitura: ${veredito.frescor}`}
        >
          leitura {veredito.frescor}
        </span>
        <span aria-hidden>·</span>
        <span className="text-muted-foreground" title={janela.descricao}>
          {janela.rotulo}
        </span>
        <span aria-hidden>·</span>
        <Chip
          glifo={GLIFO[prova.tom] ?? CircleHelp}
          palavra={prova.palavra}
          descricao={prova.descricao}
          tom={prova.tom}
        />
      </div>

      {/* ⚠️ A ressalva da prova é TEXTO, não só um selo colorido. */}
      {!podeSerLidoComoBom(veredito) && veredito.status === 'HEALTHY' && (
        <p
          className="mt-3 rounded-sm border border-warning/40 bg-warning/5 px-3 py-2 text-[12px] leading-relaxed"
          role="status"
        >
          Nenhuma causa conhecida se aplica — e a prova está{' '}
          {prova.palavra.toLowerCase()}.{' '}
          <strong className="font-medium">
            Isto não é o mesmo que "está tudo bem".
          </strong>
        </p>
      )}

      {veredito.causa_primaria && (
        <div className="mt-4">
          <p className="text-sm leading-relaxed">{veredito.causa_primaria.frase}</p>
          <Evidencias causa={veredito.causa_primaria} />
          <MotivoDaConta causa={veredito.causa_primaria} />
        </div>
      )}

      {veredito.proximo_ato && (
        <div className="mt-4 border-l-2 border-border pl-3">
          <p className="kicker">próximo ato</p>
          <p className="mt-1 text-[13px] leading-relaxed">{veredito.proximo_ato}</p>
        </div>
      )}

      {secundarias.length > 0 && (
        <div className="mt-5">
          <p className="kicker">também observado, abaixo da causa principal</p>
          <ul className="mt-2 space-y-2" aria-label="causas secundárias">
            {secundarias.map((causa, i) => (
              <li key={`${causa.status}-${causa.escopo}-${i}`} className="text-[12px]">
                <span className="font-medium">
                  {leituraDoStatus(causa.status).titulo}
                </span>
                <span className="text-muted-foreground">
                  {' '}
                  · {escopoLegivel(causa.escopo)}
                </span>
                <p className="mt-0.5 leading-relaxed text-muted-foreground">
                  {causa.frase}
                </p>
                {causa.denominador && (
                  <p className="tabular mt-0.5 text-[11px] text-muted-foreground">
                    {fraseDoDenominador(causa.denominador)}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {veredito.desconhecidos.length > 0 && (
        <div className="mt-5">
          <p className="kicker">o que permanece desconhecido</p>
          <ul
            className="mt-2 space-y-1 text-[12px] leading-relaxed text-muted-foreground"
            aria-label="desconhecidos"
          >
            {veredito.desconhecidos.map((d) => (
              <li key={d} className="flex gap-2">
                <CircleHelp className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
                <span>{d}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-5">
        <p className="kicker">recomendações do Google</p>
        <p className="mt-1 text-[12px] leading-relaxed text-muted-foreground">
          {fraseDasRecomendacoes(veredito.recomendacoes)}
        </p>
        {veredito.recomendacoes.itens && veredito.recomendacoes.itens.length > 0 && (
          <ul className="mt-2 space-y-1.5 text-[12px]" aria-label="recomendações">
            {veredito.recomendacoes.itens.map((rec, i) => (
              <li key={`${rec.tipo}-${i}`} className="flex flex-wrap items-baseline gap-x-2">
                <span className="font-medium">{rec.tipo}</span>
                <Chip
                  glifo={CircleHelp}
                  palavra={rec.adjudicacao}
                  descricao={rec.proximo_ato}
                  tom="neutro"
                />
                {rec.impacto_informado && (
                  <span className="text-muted-foreground">{rec.impacto_informado}</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      {/*
        ⚠️ A declaração de não-mutação é TEXTO na tela, com glifo de cadeado.
        Deduzir "nada foi aplicado" da ausência de um botão é exatamente o tipo
        de silêncio que esta lane existe para não produzir.
      */}
      <p
        className="mt-5 flex items-start gap-2 border-t border-border pt-3 text-[11px] leading-relaxed text-muted-foreground"
        data-testid="declaracao-de-nao-mutacao"
      >
        {veredito.mutacao_externa ? (
          <Ban className="mt-0.5 h-3 w-3 shrink-0 text-destructive" aria-hidden />
        ) : (
          <Lock className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
        )}
        <span>
          {veredito.mutacao_externa
            ? 'Atenção: este veredito declara que houve alteração na conta de anúncio.'
            : 'Nenhuma alteração foi aplicada na conta de anúncio por esta leitura. ' +
              'A sentinela lê e explica; ela não muda lance, verba, anúncio nem keyword.'}
        </span>
      </p>
    </section>
  );
};

const Evidencias: React.FC<{ causa: CausaDaSentinela }> = ({ causa }) => {
  if (causa.evidencias.length === 0 && !causa.denominador) return null;
  return (
    <>
      {causa.denominador && (
        <p className="tabular mt-2 text-[12px] text-muted-foreground">
          {fraseDoDenominador(causa.denominador)}
        </p>
      )}
      {causa.evidencias.length > 0 && (
        <dl
          className="mt-2 grid grid-cols-1 gap-x-6 gap-y-1 text-[12px] sm:grid-cols-2"
          aria-label="evidência observada"
        >
          {causa.evidencias.map((e, i) => (
            <div key={`${e.campo}-${i}`} className="flex flex-wrap gap-x-2">
              <dt className="text-muted-foreground">{e.rotulo}</dt>
              {/*
                ⚠️ `null` vira o travessão de ausência, nunca `0` nem string
                vazia: "a conta não respondeu este campo" e "a conta respondeu
                zero" levam a decisões opostas.
              */}
              <dd className="tabular font-medium">{e.valor ?? '—'}</dd>
            </div>
          ))}
        </dl>
      )}
    </>
  );
};

const MotivoDaConta: React.FC<{ causa: CausaDaSentinela }> = ({ causa }) => {
  if (causa.motivo_da_conta.length === 0) return null;
  return (
    <div className="mt-2">
      {/*
        O que o Google disse com as próprias palavras, separado da nossa
        inferência: quando a conta já nomeou a causa, uma segunda opinião nossa
        por cima é ruído — ou pior, contradição.
      */}
      <p className="kicker">a conta declarou</p>
      <p className="mt-0.5 font-mono text-[11px] leading-relaxed text-muted-foreground">
        {causa.motivo_da_conta.join(', ')}
      </p>
    </div>
  );
};

export default VereditoDaSentinela;
