/**
 * O formulário de decisão de aprovação.
 *
 * ## Por que o motivo é obrigatório nas duas decisões negativas
 *
 * Porque "ajuste pedido" sem motivo e "rejeitado" sem motivo são a mesma coisa
 * na prática: alguém recebe a peça de volta e não sabe o que corrigir. O campo
 * obrigatório não é burocracia, é o que faz a decisão ser acionável pela pessoa
 * seguinte.
 *
 * ## Ator e instante não são campos
 *
 * Eles são gravados pelo SERVIDOR a partir da sessão. Se a tela os enviasse, o
 * registro de quem autorizou uma peça seria editável pelo navegador, e a trilha
 * de aprovação deixaria de valer como prova.
 */
import React from 'react';

import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { ErroDeLeitura } from '@/components/criativos/comum/Estados';
import { CODIGO, codigoDaFalha, ehCodigo, mensagemDaFalha } from '@/lib/criativosApi';
import { DECISOES, motivoObrigatorio } from '@/components/criativos/aprovacoes/regras';
import { ROTULO_DA_APROVACAO, type DecisaoDeAprovacao, type PedidoDeAprovacao } from '@/types/criativos';

const CONTROLE = cn(
  'w-full rounded-md border border-input bg-card px-3 py-2 text-sm text-foreground',
  'transition-colors duration-150 ease-out',
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
);

export const FormularioDeDecisao: React.FC<{
  /** Prefixo dos `id`, para a fila poder montar vários formulários na página. */
  prefixo: string;
  /** Peça pronta? Uma peça que não ficou pronta não é aprovável. */
  aprovavel: boolean;
  enviando: boolean;
  erro: unknown;
  aoDecidir: (pedido: PedidoDeAprovacao) => void;
}> = ({ prefixo, aprovavel, enviando, erro, aoDecidir }) => {
  const [decisao, setDecisao] = React.useState<DecisaoDeAprovacao>('aprovado');
  const [finalidade, setFinalidade] = React.useState('');
  const [motivo, setMotivo] = React.useState('');
  const [tentou, setTentou] = React.useState(false);

  const erroFinalidade =
    tentou && finalidade.trim().length < 3
      ? 'Declare para que a peça está sendo autorizada. A aprovação vale para a finalidade escrita aqui.'
      : undefined;
  const erroMotivo =
    tentou && motivoObrigatorio(decisao) && motivo.trim().length < 5
      ? 'Escreva o motivo. Sem ele, quem recebe a peça de volta não sabe o que corrigir.'
      : undefined;

  const enviar = () => {
    setTentou(true);
    if (finalidade.trim().length < 3) return;
    if (motivoObrigatorio(decisao) && motivo.trim().length < 5) return;
    aoDecidir({
      decisao,
      finalidade: finalidade.trim(),
      ...(motivo.trim() ? { motivo: motivo.trim() } : {}),
    });
  };

  if (!aprovavel) {
    return (
      <p className="text-[13px] leading-relaxed text-muted-foreground">
        Esta peça não ficou pronta, então não há o que aprovar. Uma decisão sobre um arquivo que
        não existe não protege nada.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <fieldset>
        <legend className="text-[13px] font-medium text-foreground">Decisão</legend>
        <div className="mt-2 grid gap-2 sm:grid-cols-3">
          {DECISOES.map((d) => {
            const id = `${prefixo}-decisao-${d}`;
            return (
              <div
                key={d}
                className={cn(
                  'flex items-start gap-2 rounded-md border border-border px-3 py-2',
                  'transition-colors duration-150 ease-out',
                  decisao === d ? 'border-primary/60 bg-primary/[0.07]' : 'bg-muted/30 hover:bg-muted/60',
                )}
              >
                <input
                  id={id}
                  type="radio"
                  name={`${prefixo}-decisao`}
                  className="mt-0.5 h-5 w-5 shrink-0 accent-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                  checked={decisao === d}
                  onChange={() => setDecisao(d)}
                />
                <label htmlFor={id} className="min-w-0 cursor-pointer">
                  <span className="block text-[13px] font-medium text-foreground">
                    {ROTULO_DA_APROVACAO[d].palavra}
                  </span>
                  <span className="mt-0.5 block text-[12px] leading-snug text-muted-foreground">
                    {ROTULO_DA_APROVACAO[d].descricao}
                  </span>
                </label>
              </div>
            );
          })}
        </div>
      </fieldset>

      <div className="space-y-1.5">
        <label
          htmlFor={`${prefixo}-finalidade`}
          className="block text-[13px] font-medium text-foreground"
        >
          Finalidade da decisão <span className="text-muted-foreground">(obrigatório)</span>
        </label>
        <p id={`${prefixo}-finalidade-ajuda`} className="text-[12px] leading-relaxed text-muted-foreground">
          Para que esta versão está sendo autorizada. Por exemplo: campanha de display do segundo
          semestre.
        </p>
        <input
          id={`${prefixo}-finalidade`}
          type="text"
          className={cn(CONTROLE, 'h-10', erroFinalidade && 'border-destructive')}
          value={finalidade}
          aria-invalid={Boolean(erroFinalidade)}
          aria-describedby={cn(
            `${prefixo}-finalidade-ajuda`,
            erroFinalidade && `${prefixo}-finalidade-erro`,
          )}
          onChange={(e) => setFinalidade(e.target.value)}
        />
        {erroFinalidade && (
          <p id={`${prefixo}-finalidade-erro`} className="text-[12px] text-destructive">
            {erroFinalidade}
          </p>
        )}
      </div>

      <div className="space-y-1.5">
        <label htmlFor={`${prefixo}-motivo`} className="block text-[13px] font-medium text-foreground">
          Motivo{' '}
          <span className="text-muted-foreground">
            {motivoObrigatorio(decisao) ? '(obrigatório)' : '(opcional)'}
          </span>
        </label>
        <textarea
          id={`${prefixo}-motivo`}
          rows={3}
          className={cn(CONTROLE, 'leading-relaxed', erroMotivo && 'border-destructive')}
          value={motivo}
          aria-invalid={Boolean(erroMotivo)}
          aria-describedby={erroMotivo ? `${prefixo}-motivo-erro` : undefined}
          onChange={(e) => setMotivo(e.target.value)}
        />
        {erroMotivo && (
          <p id={`${prefixo}-motivo-erro`} className="text-[12px] text-destructive">
            {erroMotivo}
          </p>
        )}
      </div>

      {Boolean(erro) && (
        <ErroDeLeitura
          mensagem={mensagemDaFalha(erro)}
          codigo={codigoDaFalha(erro)}
          ressalva={
            ehCodigo(erro, CODIGO.decisaoDuplicada)
              ? 'Já existe uma decisão vigente para esta versão e finalidade. Recarregue para ver qual é.'
              : ehCodigo(erro, CODIGO.ativoNaoAprovavel)
                ? 'A peça não ficou pronta, então não há arquivo para autorizar.'
                : 'Nenhuma decisão foi gravada.'
          }
        />
      )}

      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={enviar} disabled={enviando}>
          {enviando ? 'Registrando' : 'Registrar decisão'}
        </Button>
        <p className="text-[12px] leading-relaxed text-muted-foreground">
          Quem decidiu e quando são gravados pelo servidor a partir da sua sessão.
        </p>
      </div>
    </div>
  );
};
