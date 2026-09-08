import { defineConfig } from 'vitest/config';
import { fileURLToPath } from 'node:url';

// Config mínima e compatível com o vite.config.ts existente (alias "@" -> ./src).
// Não carrega plugins do app: os testes daqui são de lógica pura (Node).
export default defineConfig({
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  test: {
    environment: 'node',
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    // ⚠️ O Assistente Criativo lê `VITE_PAUTADOR_API_URL` no import do módulo
    // (`api.ts`), e sem ela `assistenteConfigurado()` devolve `false`: a página
    // desenha o aviso "endereço não configurado" e NENHUMA chamada sai. Cinco
    // testes de retomada e autorização falhavam por isso — não por regressão de
    // produto, mas porque o Vite só carrega `.env.development.local` no modo
    // `development`, e o vitest roda em modo `test`.
    //
    // Medido em 08/09/2026, mesmo commit, sem tocar em uma linha de teste:
    //     npx vitest run src/features/creative-studio          -> 7 failed, 27 passed
    //     VITE_PAUTADOR_API_URL=... npx vitest run (idem)       -> 2 failed, 32 passed
    //
    // O valor é um endereço de dublê: nenhum teste desta suíte alcança a rede
    // (o `fetch` é sempre stub). Declará-lo aqui é o que faz o gate medir o
    // código em vez de medir o ambiente de quem rodou.
    env: {
      VITE_PAUTADOR_API_URL: 'http://assistente.teste.local',
    },
  },
});
