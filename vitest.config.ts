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
  },
});
