import React from 'react';
import { ArrowLeft, FlaskConical, WifiOff } from 'lucide-react';
import { Link } from 'react-router-dom';

import { cn } from '@/lib/utils';
import {
  ehResultadoDecisionLab,
  type CenarioDoLab,
  type RespostaDoDecisionLab,
} from '@/types/inteligenciaDecisao';

import {
  CabecalhoDeVerdade,
  DiagnosticoDaBancada,
  FamiliasDeEvidencia,
  IsolamentoDaBancada,
  LinhaDeRaciocinio,
  PropostasDaBancada,
  RespostaExecutiva,
} from './BancadaDeDecisao';
import { CarregandoBancada, EstadoTerminalBancada } from './EstadosDaBancada';
import { catalogoDasProvas, provaPorId } from './fixtures';
import {
  MARCA_SINTETICA_COM_PROTOTIPO,
  MARCA_SHADOW_FUTURO,
  projetarBancada,
} from './projection';
import './bancada.css';

export interface DecisionIntelligenceLabProps {
  scenarioId: string;
  resposta: RespostaDoDecisionLab | null;
  carregando: boolean;
  atualizando?: boolean;
  erro: Error | null;
  aoEscolher: (scenarioId: string) => void;
}

const catalogoMinimo = (scenarioId: string): CenarioDoLab[] => [
  { scenario_id: scenarioId, rotulo: scenarioId.replace(/-/g, ' '), grupo: 'dourado' },
];

export const DecisionIntelligenceLab: React.FC<DecisionIntelligenceLabProps> = ({
  scenarioId,
  resposta,
  carregando,
  atualizando,
  erro,
  aoEscolher,
}) => {
  const [provaLocalId, setProvaLocalId] = React.useState<string | null>(null);
  const [comparando, setComparando] = React.useState(false);
  const [mudouResposta, setMudouResposta] = React.useState(false);
  const primeira = React.useRef(true);

  const prova = provaLocalId ? provaPorId(provaLocalId) : undefined;
  const efetiva = prova?.resposta ?? resposta;
  const catalogoServidor = resposta?.catalogo ?? catalogoMinimo(scenarioId);
  const ultimaBoa = efetiva && 'ultima_fotografia' in efetiva ? efetiva.ultima_fotografia : null;
  const resultado = efetiva && ehResultadoDecisionLab(efetiva) ? efetiva : ultimaBoa ?? null;
  const modo = prova?.modo ?? 'sintetico';
  const bancada = resultado ? projetarBancada(resultado, modo) : null;
  const valorDoSeletor = provaLocalId ?? scenarioId;

  React.useEffect(() => {
    if (primeira.current) {
      primeira.current = false;
      return;
    }
    setMudouResposta(true);
    const id = window.setTimeout(() => setMudouResposta(false), 200);
    return () => window.clearTimeout(id);
  }, [valorDoSeletor]);

  const escolher = (proximo: string) => {
    if (proximo.startsWith('prova-l6-')) {
      setProvaLocalId(proximo);
      return;
    }
    setProvaLocalId(null);
    aoEscolher(proximo);
  };

  const marcaFixa = modo === 'shadow_futuro' ? MARCA_SHADOW_FUTURO : MARCA_SINTETICA_COM_PROTOTIPO;

  return (
    <div className="di-bancada">
      <div
        className="fixed bottom-3 right-3 z-50 max-w-[min(100%-1.5rem,22rem)] rounded-md border border-info/60 bg-background px-3 py-2 text-[11px] font-semibold tracking-[0.08em] shadow-sm"
        aria-hidden="true"
      >
        <span className="inline-flex items-center gap-2">
          <FlaskConical className="h-3.5 w-3.5 text-info" aria-hidden />
          {marcaFixa}
        </span>
      </div>

      <a
        href="#resposta-executiva"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-background focus:px-3 focus:py-2 focus:ring-2 focus:ring-ring"
      >
        Ir para a resposta executiva
      </a>

      <header className="border-b border-border pb-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Link
            to="/trafego"
            className="inline-flex min-h-11 items-center gap-2 text-[12px] text-muted-foreground transition-colors duration-150 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring md:min-h-8"
          >
            <ArrowLeft className="h-3.5 w-3.5" aria-hidden />
            voltar ao Hub
          </Link>
          <div className={cn('flex items-center gap-2 text-[11px] font-semibold tracking-[0.08em]', modo === 'shadow_futuro' ? 'text-warning' : 'text-info')}>
            <FlaskConical className="h-3.5 w-3.5" aria-hidden />
            {modo === 'shadow_futuro' ? MARCA_SHADOW_FUTURO : MARCA_SINTETICA_COM_PROTOTIPO}
          </div>
        </div>
        <div className="mt-5 flex flex-wrap items-end justify-between gap-5">
          <div className="min-w-0">
            <p className="kicker">VOLC Decision Intelligence Lab</p>
            <h1 className="mt-1 max-w-[24ch] text-balance font-display text-[30px] font-semibold leading-[1.05] tracking-tight md:text-[36px]">
              Bancada de decisão Search
            </h1>
            <p className="mt-2 max-w-[70ch] text-pretty text-[14px] leading-relaxed text-muted-foreground">
              Evidência, suficiência, diagnóstico, proposta e bloqueio, sem atalho para a conta.
            </p>
            <span className="di-assinatura" aria-hidden="true" />
          </div>
          <label className="grid w-full min-w-0 max-w-full flex-1 gap-1.5 text-[12px] font-medium sm:max-w-[320px]">
            Cenário de replay
            <span className="relative">
              <select
                value={valorDoSeletor}
                onChange={(evento) => escolher(evento.target.value)}
                className="h-11 w-full rounded-md border border-input bg-background px-3 pr-8 text-[13px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring md:h-10"
              >
                <optgroup label="Replay do servidor">
                  {catalogoServidor.map((cenario) => (
                    <option key={cenario.scenario_id} value={cenario.scenario_id}>
                      {cenario.rotulo}
                    </option>
                  ))}
                </optgroup>
                <optgroup label="Provas de superfície L6">
                  {catalogoDasProvas().map((cenario) => (
                    <option key={cenario.scenario_id} value={cenario.scenario_id}>
                      {cenario.rotulo}
                    </option>
                  ))}
                </optgroup>
              </select>
              {atualizando && <span className="sr-only" role="status">atualizando cenário</span>}
            </span>
          </label>
        </div>
      </header>

      {carregando && !resposta && !prova ? (
        <CarregandoBancada />
      ) : efetiva && efetiva.versao_contrato !== 1 ? (
        <EstadoTerminalBancada
          tipo="versao"
          titulo="Versão de contrato desconhecida"
          texto="Esta tela não interpreta uma versão futura como saudável. Atualize o cliente antes de usar a fotografia."
          codigo={'versao_recebida' in efetiva ? efetiva.versao_recebida : String(efetiva.versao_contrato)}
        />
      ) : efetiva?.estado_da_superficie === 'vazio_confirmado' ? (
        <EstadoTerminalBancada
          tipo="vazio"
          titulo="Vazio confirmado pelo dataset"
          texto="A fonte foi lida e confirmou zero linhas. Isto é diferente de loading, falha ou ausência de fotografia."
        />
      ) : efetiva?.estado_da_superficie === 'falha_sem_fotografia' ? (
        <EstadoTerminalBancada
          tipo="falha"
          titulo="Falha sem fotografia anterior"
          texto={efetiva.falha?.mensagem ?? 'A primeira leitura não terminou.'}
          codigo={efetiva.falha?.codigo}
        />
      ) : erro && !resultado && !prova ? (
        <EstadoTerminalBancada
          tipo="falha"
          titulo="O laboratório não pôde ser lido"
          texto="Não há fotografia boa guardada nesta sessão. A falha não vira vazio confirmado."
          codigo="LAB-LEITURA-INDISPONIVEL"
        />
      ) : bancada && resultado ? (
        <>
          {(erro || efetiva?.estado_da_superficie === 'falha_ultimo_bom') && (
            <div className="mt-6 flex items-start gap-3 border-y border-destructive/40 bg-destructive/[0.05] px-4 py-3" role="alert">
              <WifiOff className="mt-0.5 h-4 w-4 shrink-0 text-destructive" aria-hidden />
              <div>
                <p className="text-[13px] font-semibold">A tentativa mais recente falhou</p>
                <p className="mt-0.5 text-[13px] text-foreground/80">A última fotografia boa permanece abaixo, com idade e procedência preservadas.</p>
              </div>
            </div>
          )}
          <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_280px]">
            <div className="min-w-0">
              <CabecalhoDeVerdade bancada={bancada} />
              <div>
                <RespostaExecutiva bancada={bancada} mudou={mudouResposta} />
                <FamiliasDeEvidencia bancada={bancada} />
                <LinhaDeRaciocinio bancada={bancada} />
                <DiagnosticoDaBancada
                  bancada={bancada}
                  comparando={comparando}
                  aoComparar={() => setComparando((v) => !v)}
                />
                <PropostasDaBancada bancada={bancada} />
              </div>
            </div>
            <IsolamentoDaBancada bancada={bancada} />
          </div>
        </>
      ) : (
        <EstadoTerminalBancada
          tipo="falha"
          titulo="Estado do laboratório não reconhecido"
          texto="A ausência de um estado conhecido não é interpretada como sucesso."
        />
      )}
    </div>
  );
};

export default DecisionIntelligenceLab;
