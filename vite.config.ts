import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";

// https://vitejs.dev/config/
// Portas configuráveis por ambiente, com o padrão de sempre. Sem isso, subir em
// portas alternativas (máquina com outros projetos rodando) quebra em silêncio:
// o front sobe na porta nova mas o proxy continua falando com a 3001, que pode
// ser de OUTRA aplicação. `./start-dev.sh` exporta as mesmas variáveis.
const FRONT_PORT = Number(process.env.FRONT_PORT || 8080);
const API_TARGET = `http://localhost:${process.env.API_PORT || 3001}`;

export default defineConfig(({ mode }) => ({
  server: {
    host: "::",
    port: FRONT_PORT,
    // Worktrees e journals mudam enquanto os agentes trabalham. Eles não são
    // fonte do bundle e não podem provocar milhares de reloads no operador.
    watch: {
      ignored: [
        "**/.agent-worktrees/**",
        "**/.claude/worktrees/**",
        "**/tools/agent-harness/runs/**",
      ],
    },
    proxy: {
      "/api": {
        target: API_TARGET,
        changeOrigin: true,
      },
      "/health": {
        target: API_TARGET,
        changeOrigin: true,
      },
    },
  },
  plugins: [
    react(),
  ],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      // ⚠️ A bancada visual (`/qa/trafego/...`) é ferramenta de conferência e
      // não pode ser publicada. Guardar a rota com `import.meta.env.DEV`
      // elimina o ramo; guardar o `React.lazy` junto elimina a chamada — e
      // nenhum dos dois elimina o CHUNK: o Rollup monta o grafo a partir de
      // cada `import()` ANTES da eliminação de código morto, e o build emitia
      // `assets/BancadaVisual-*.js` com as fixtures dentro.
      //
      // Trocar o módulo é o que de fato o tira dali. Quem cobra é
      // `src/pages/qa/__tests__/bancada-fora-de-producao.test.ts` sob
      // `VOLC_PROVA_DE_BUNDLE=1`, rodando `vite build` e varrendo a saída.
      ...(mode === "production"
        ? {
            "./pages/qa/BancadaVisual": path.resolve(
              __dirname,
              "./src/pages/qa/BancadaVisual.producao.tsx",
            ),
          }
        : {}),
    },
  },
}));
