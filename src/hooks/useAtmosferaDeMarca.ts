/**
 * Liga a atmosfera de marca — aurora e grão — só onde ela pertence.
 *
 * ## Por que isto é opt-in
 *
 * Até 27/08/2026 a aurora e o grão de filme eram pintados em `body::before` e
 * `body::after` para a aplicação INTEIRA, por baixo de tabela, formulário,
 * métrica e aviso.
 *
 * O `DESIGN.md` proíbe isso nas duas pontas: a aurora pertence a marcos de
 * identidade e "never becomes a workspace background"; e a lista de proibições
 * inclui gradiente decorativo atrás de superfície longa de leitura. Uma tela
 * onde se confere gasto com atmosfera atrás dos números é o "dashboard
 * decorativo" que o `PRODUCT.md` declara anti-referência.
 *
 * ⚠️ A troca foi de PADRÃO, não de existência. O CSS continua lá, e as classes
 * utilitárias (`gradient-aurora`, `text-aurora`) seguem vivas nos 27 arquivos
 * que as usam. O que mudou é que a atmosfera passou a ser DECLARADA por quem a
 * quer, em vez de herdada por quem nunca pediu.
 *
 * Use nas superfícies de identidade — entrada, 404, troca de senha. Não use em
 * nenhuma tela sob o `Layout` do produto.
 */
import { useEffect } from 'react';

export function useAtmosferaDeMarca(): void {
  useEffect(() => {
    const anterior = document.body.getAttribute('data-atmosfera');
    document.body.setAttribute('data-atmosfera', 'marca');
    // ⚠️ A limpeza restaura o valor ANTERIOR em vez de apagar. Duas superfícies
    // de identidade montadas em sequência (404 dentro de um fluxo de login, por
    // exemplo) desmontariam uma depois da outra, e um `removeAttribute` cego na
    // primeira apagaria a atmosfera que a segunda acabou de ligar.
    return () => {
      if (anterior === null) document.body.removeAttribute('data-atmosfera');
      else document.body.setAttribute('data-atmosfera', anterior);
    };
  }, []);
}
