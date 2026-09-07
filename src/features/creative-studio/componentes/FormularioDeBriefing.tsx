/**
 * O briefing: o que o Assistente recebe antes de propor qualquer coisa.
 *
 * ## As refs não são digitadas
 *
 * O contrato exige `fact_[a-z0-9_-]{3,64}` em cada fato. Pedir isso ao operador
 * seria pedir que ele decore um formato de identificador para escrever uma
 * frase sobre a própria oferta. Aqui ele escreve a frase e diz de onde ela veio;
 * a ref é derivada do texto e mostrada como metadado discreto, para quem for
 * conferir a procedência depois.
 *
 * ## O que o Aprova fazia e não veio junto
 *
 * O formulário de origem gerava UM formato por requisição e tinha um slider de
 * até 20 peças. Aqui os formatos são múltiplos e vêm do catálogo do motor, e o
 * teto é `MAX_VARIACOES = 15`, que é estratégico e não cosmético: acima disso o
 * lote deixa de ter diferença material entre as peças.
 */
import { useMemo, useState } from 'react';
import { AlertCircle, Plus, X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

import { FORMATOS_DO_MOTOR, MAX_PECAS } from '../api';
import type { EntradaNovaOperacao, FatoDaOferta, OrigemDoFato } from '../tipos';

/** `Conteúdo independente` -> `fact_conteudo_independente`. */
function refDoFato(texto: string, indice: number): string {
  const base = texto
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 48);
  // O sufixo evita colisão quando dois fatos começam igual; o contrato recusa
  // refs duplicadas e a recusa chegaria como erro de validação sem explicação.
  return `fact_${base || 'fato'}_${indice + 1}`;
}

const ORIGENS: { valor: OrigemDoFato; rotulo: string; ajuda: string }[] = [
  { valor: 'LANDING_PAGE', rotulo: 'Página de destino', ajuda: 'Está escrito na página.' },
  { valor: 'OPERADOR', rotulo: 'Operador', ajuda: 'Você está afirmando isto.' },
  { valor: 'POLICY_RECEIPT', rotulo: 'Recibo de política', ajuda: 'Veio de uma checagem de política.' },
  { valor: 'PERFORMANCE_RECEIPT', rotulo: 'Recibo de performance', ajuda: 'Veio de dado medido.' },
];

interface FatoEmEdicao {
  declaracao: string;
  origem: OrigemDoFato;
}

export interface FormularioDeBriefingProps {
  ocupado: boolean;
  erro?: string | null;
  onEnviar: (entrada: EntradaNovaOperacao) => void;
}

export function FormularioDeBriefing({ ocupado, erro, onEnviar }: FormularioDeBriefingProps) {
  const [nome, setNome] = useState('');
  const [destino, setDestino] = useState('');
  const [objetivo, setObjetivo] = useState('OUTCOME_TRAFFIC');
  const [contexto, setContexto] = useState('');
  const [fatos, setFatos] = useState<FatoEmEdicao[]>([
    { declaracao: '', origem: 'LANDING_PAGE' },
  ]);
  const [formatos, setFormatos] = useState<string[]>(['1x1', '4x5', '9x16']);
  const [quantidade, setQuantidade] = useState(6);

  const fatosValidos = fatos.filter((f) => f.declaracao.trim().length >= 3);
  const podeEnviar =
    nome.trim().length >= 3 &&
    destino.trim().length >= 3 &&
    contexto.trim().length >= 3 &&
    fatosValidos.length >= 1 &&
    formatos.length >= 1 &&
    !ocupado;

  const totalDeRenders = useMemo(
    () => quantidade * formatos.length,
    [quantidade, formatos.length],
  );

  function alternarFormato(slot: string) {
    setFormatos((atual) =>
      atual.includes(slot) ? atual.filter((s) => s !== slot) : [...atual, slot],
    );
  }

  function enviar() {
    const fatosDaOferta: FatoDaOferta[] = fatosValidos.map((f, i) => ({
      ref: refDoFato(f.declaracao, i),
      declaracao: f.declaracao.trim(),
      origem: f.origem,
    }));
    onEnviar({
      nome_da_operacao: nome.trim(),
      destination_ref: destino.trim(),
      objetivo_meta: objetivo,
      contexto_do_publico: contexto.trim(),
      fatos_da_oferta: fatosDaOferta,
      formatos_permitidos: formatos,
      quantidade_de_pecas: quantidade,
    });
  }

  return (
    <form
      className="space-y-6"
      onSubmit={(e) => {
        e.preventDefault();
        if (podeEnviar) enviar();
      }}
    >
      <section className="rounded-lg border border-border bg-card p-4 shadow-card md:p-5">
        <h2 className="font-display text-lg font-semibold">A operação</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          O Assistente só usa o que você declarar aqui. Ele não abre a página de destino,
          não pesquisa e não inventa fato.
        </p>

        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="ac-nome">Nome da operação</Label>
            <Input
              id="ac-nome"
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              maxLength={200}
              autoComplete="off"
            />
            <p className="text-xs text-muted-foreground">
              Como você vai reconhecer esta operação no histórico.
            </p>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="ac-destino">Destino</Label>
            <Input
              id="ac-destino"
              value={destino}
              onChange={(e) => setDestino(e.target.value)}
              maxLength={180}
              autoComplete="off"
            />
            <p className="text-xs text-muted-foreground">
              A referência do destino real desta campanha.
            </p>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="ac-objetivo">Objetivo Meta</Label>
            <Select value={objetivo} onValueChange={setObjetivo}>
              <SelectTrigger id="ac-objetivo">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="OUTCOME_TRAFFIC">Tráfego</SelectItem>
                <SelectItem value="OUTCOME_LEADS">Leads</SelectItem>
                <SelectItem value="OUTCOME_SALES">Vendas</SelectItem>
                <SelectItem value="OUTCOME_AWARENESS">Reconhecimento</SelectItem>
                <SelectItem value="OUTCOME_ENGAGEMENT">Engajamento</SelectItem>
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              Orienta a estratégia. Não cria nem configura campanha.
            </p>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="ac-quantidade">Quantidade de peças</Label>
            <Input
              id="ac-quantidade"
              type="number"
              inputMode="numeric"
              min={1}
              max={MAX_PECAS}
              value={quantidade}
              onChange={(e) => {
                const n = Number(e.target.value);
                if (Number.isFinite(n)) setQuantidade(Math.min(MAX_PECAS, Math.max(1, n)));
              }}
              className="tabular-nums"
            />
            <p className="text-xs text-muted-foreground">
              Máximo de {MAX_PECAS}. É um teto estratégico: acima disso as peças deixam de
              ter diferença material entre si.
            </p>
          </div>
        </div>

        <div className="mt-4 space-y-1.5">
          <Label htmlFor="ac-contexto">Contexto do público</Label>
          <Textarea
            id="ac-contexto"
            value={contexto}
            onChange={(e) => setContexto(e.target.value)}
            maxLength={4000}
            rows={3}
          />
          <p className="text-xs text-muted-foreground">
            Quem é essa pessoa e em que momento ela está.
          </p>
        </div>
      </section>

      <section className="rounded-lg border border-border bg-card p-4 shadow-card md:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="font-display text-lg font-semibold">Fatos da oferta</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Toda promessa da estratégia vai citar um destes. O que não estiver aqui não
              pode ser afirmado — e o Assistente registra a falta em vez de preencher.
            </p>
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setFatos((f) => [...f, { declaracao: '', origem: 'OPERADOR' }])}
          >
            <Plus className="h-4 w-4" aria-hidden />
            Adicionar fato
          </Button>
        </div>

        <ul className="mt-4 space-y-3">
          {fatos.map((fato, indice) => (
            <li
              key={indice}
              className="rounded-md border border-border bg-muted/20 p-3"
            >
              <div className="flex flex-wrap items-start gap-3">
                <div className="min-w-0 flex-1 space-y-1.5">
                  <Label htmlFor={`ac-fato-${indice}`} className="text-xs">
                    Declaração
                  </Label>
                  <Textarea
                    id={`ac-fato-${indice}`}
                    value={fato.declaracao}
                    rows={2}
                    maxLength={1200}
                    onChange={(e) =>
                      setFatos((atual) =>
                        atual.map((f, i) =>
                          i === indice ? { ...f, declaracao: e.target.value } : f,
                        ),
                      )
                    }
                  />
                  {fato.declaracao.trim().length >= 3 && (
                    <p className="font-mono text-[11px] text-muted-foreground">
                      {refDoFato(fato.declaracao, indice)}
                    </p>
                  )}
                </div>

                <div className="w-full space-y-1.5 sm:w-56">
                  <Label htmlFor={`ac-origem-${indice}`} className="text-xs">
                    Origem
                  </Label>
                  <Select
                    value={fato.origem}
                    onValueChange={(v) =>
                      setFatos((atual) =>
                        atual.map((f, i) =>
                          i === indice ? { ...f, origem: v as OrigemDoFato } : f,
                        ),
                      )
                    }
                  >
                    <SelectTrigger id={`ac-origem-${indice}`}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {ORIGENS.map((o) => (
                        <SelectItem key={o.valor} value={o.valor}>
                          {o.rotulo}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground">
                    {ORIGENS.find((o) => o.valor === fato.origem)?.ajuda}
                  </p>
                </div>

                {fatos.length > 1 && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="mt-6"
                    onClick={() => setFatos((atual) => atual.filter((_, i) => i !== indice))}
                  >
                    <X className="h-4 w-4" aria-hidden />
                    <span className="sr-only">Remover o fato {indice + 1}</span>
                  </Button>
                )}
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section className="rounded-lg border border-border bg-card p-4 shadow-card md:p-5">
        <h2 className="font-display text-lg font-semibold">Formatos</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          O que o motor sabe produzir. Cada formato é uma composição própria, não um
          recorte da mesma imagem.
        </p>

        <fieldset className="mt-4">
          <legend className="sr-only">Formatos permitidos</legend>
          <div className="grid gap-3 sm:grid-cols-3">
            {FORMATOS_DO_MOTOR.map((formato) => {
              const marcado = formatos.includes(formato.slot);
              return (
                <label
                  key={formato.slot}
                  className={`flex cursor-pointer items-start gap-3 rounded-md border p-3 transition-[background-color,border-color] duration-200 ${
                    marcado
                      ? 'border-primary/50 bg-primary/5'
                      : 'border-border bg-muted/20 hover:border-primary/30'
                  }`}
                >
                  <input
                    type="checkbox"
                    className="mt-1 h-4 w-4 accent-primary"
                    checked={marcado}
                    onChange={() => alternarFormato(formato.slot)}
                  />
                  <span className="min-w-0">
                    <span className="block text-sm font-medium text-foreground">
                      {formato.rotulo}
                    </span>
                    <span className="block text-xs tabular-nums text-muted-foreground">
                      {formato.proporcao} · {formato.largura}×{formato.altura} px
                    </span>
                    <span className="mt-1 block text-xs text-muted-foreground">
                      {formato.descricao}
                    </span>
                  </span>
                </label>
              );
            })}
          </div>
        </fieldset>
        {formatos.length === 0 && (
          <p className="mt-3 flex items-center gap-2 text-sm text-warning">
            <AlertCircle className="h-4 w-4" aria-hidden />
            Escolha ao menos um formato.
          </p>
        )}
      </section>

      {/* Consequência antes da ação: o operador vê o tamanho do lote e o que
          este clique NÃO faz, antes de o botão existir para ele. */}
      <section className="rounded-lg border border-border bg-muted/20 p-4">
        <h2 className="text-sm font-semibold text-foreground">O que este clique faz</h2>
        <ul className="mt-2 space-y-1.5 text-sm text-muted-foreground">
          <li>
            Pede <span className="tabular-nums text-foreground">{quantidade}</span> peça(s)
            estratégica(s) para{' '}
            <span className="tabular-nums text-foreground">{formatos.length}</span> formato(s).
          </li>
          <li>
            Se todas forem aprovadas e geradas depois, isso dará{' '}
            <span className="tabular-nums text-foreground">{totalDeRenders}</span> imagem(ns).
            Nenhuma é gerada agora.
          </li>
          <li>Não cria campanha, não sobe mídia e não chama a Meta.</li>
        </ul>
      </section>

      {erro && (
        <p
          role="alert"
          className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          {erro}
        </p>
      )}

      <div className="flex items-center gap-3">
        <Button type="submit" disabled={!podeEnviar} className="min-h-10">
          {ocupado ? 'Criando…' : 'Criar estratégia'}
        </Button>
        {!podeEnviar && !ocupado && (
          <p className="text-sm text-muted-foreground">
            Preencha nome, destino, contexto, ao menos um fato e um formato.
          </p>
        )}
      </div>
    </form>
  );
}
