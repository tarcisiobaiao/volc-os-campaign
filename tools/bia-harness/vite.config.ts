// Bancada visual da Bia. Rode com cwd na RAIZ do repositório (o Tailwind
// resolve o config pelo cwd):
//   node_modules/.bin/vite --config tools/bia-harness/vite.config.ts
import path from 'path';

import react from '@vitejs/plugin-react-swc';
import { defineConfig } from 'vite';

const raiz = path.resolve(__dirname, '../..');

export default defineConfig({
  root: __dirname,
  envDir: raiz,
  plugins: [react()],
  resolve: { alias: { '@': path.join(raiz, 'src') } },
  server: { host: '127.0.0.1', port: Number(process.env.HARNESS_PORT || 8093), strictPort: true, fs: { allow: [raiz] } },
});
