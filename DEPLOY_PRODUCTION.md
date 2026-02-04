# 🚀 Deploy em Produção - WebGo

## ⚠️ SITUAÇÃO ATUAL

Seu site na Vercel está em loading porque:
- Frontend na Vercel tenta conectar ao backend
- Backend está rodando apenas em `localhost:3001` (sua máquina)
- Vercel não consegue acessar localhost da sua máquina

## ✅ SOLUÇÃO RÁPIDA

### PASSO 1: Deploy do Backend no Railway (15 minutos)

#### 1.1 Criar conta no Railway
- Acesse: https://railway.app/
- Faça login com GitHub

#### 1.2 Criar novo projeto
- Clique em "New Project"
- Selecione "Deploy from GitHub repo"
- Escolha seu repositório `webgo`
- Railway detectará automaticamente o Node.js

#### 1.3 Configurar variáveis de ambiente
Clique em "Variables" e adicione:

```
SUPABASE_URL=https://txvvzpstquqmbhljudfn.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InR4dnZ6cHN0cXVxbWJobGp1ZGZuIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1NDA5Nzg5MywiZXhwIjoyMDY5NjczODkzfQ.FzDYxEIDUglaKvsQIbUMJxuHNQlpe7_vaVULs6InM4c
SERVER_PORT=3001
NODE_ENV=production
ALLOWED_ORIGINS=https://webgo-system.vercel.app
```

**IMPORTANTE**: Substitua `https://webgo-system.vercel.app` pela URL real do seu site na Vercel!

#### 1.4 Configurar comando de start
- Clique em "Settings"
- Em "Deploy", configure:
  - **Start Command**: `node server/index.js`
  - **Watch Paths**: Deixe vazio (deploy em qualquer mudança)

#### 1.5 Deploy
- Railway fará deploy automaticamente
- Aguarde 2-3 minutos
- Anote a URL gerada (ex: `https://webgo-production.railway.app`)

### PASSO 2: Atualizar Vercel (5 minutos)

#### 2.1 Acessar Vercel Dashboard
- Vá em: https://vercel.com/dashboard
- Clique no seu projeto

#### 2.2 Configurar variáveis de ambiente
- Clique em "Settings" → "Environment Variables"
- Adicione ou atualize estas variáveis (para Production, Preview e Development):

```
VITE_SUPABASE_URL=https://txvvzpstquqmbhljudfn.supabase.co
VITE_SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InR4dnZ6cHN0cXVxbWJobGp1ZGZuIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTQwOTc4OTMsImV4cCI6MjA2OTY3Mzg5M30.imEQa2iczaFzbZlm8I2af2eKEvS1NVlhhZ952US2Wzc
VITE_API_URL=https://sua-url-do-railway.app
```

**CRÍTICO**: Substitua `https://sua-url-do-railway.app` pela URL que o Railway gerou!

#### 2.3 Redeploy
- Vá em "Deployments"
- Clique nos três pontinhos do último deploy
- Clique em "Redeploy"
- Aguarde 2-3 minutos

### PASSO 3: Testar (2 minutos)

1. Abra seu site na Vercel
2. Pressione F12 para abrir DevTools
3. Vá na aba "Console"
4. **Verifique se NÃO há erros** de `Failed to fetch` ou `localhost:3001`
5. Tente fazer login
6. ✅ Deve funcionar!

## 🔧 Solução Alternativa: Vercel Serverless (Avançado)

Se preferir não usar Railway, pode hospedar o backend como Serverless na Vercel:

### Criar `api/server.js`:
```javascript
import express from 'express';
import cors from 'cors';
import { createClient } from '@supabase/supabase-js';

const app = express();

app.use(cors({
  origin: process.env.VERCEL_URL || '*',
  credentials: true
}));

app.use(express.json());

const supabase = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_SERVICE_ROLE_KEY
);

app.get('/api/health', (req, res) => {
  res.json({ status: 'ok' });
});

app.post('/api/users/query', async (req, res) => {
  const { email } = req.body;
  const { data, error } = await supabase
    .from('users')
    .select('*')
    .eq('email', email);

  if (error) return res.status(500).json({ error });
  res.json(data);
});

export default app;
```

### Atualizar `vercel.json`:
```json
{
  "rewrites": [
    { "source": "/api/:path*", "destination": "/api/server" }
  ]
}
```

**Mas Railway é mais simples!**

## 🎯 Resumo Visual

```
┌─────────────────────────────────────────────┐
│  ANTES (Local)                              │
│                                             │
│  Vercel (Frontend) → localhost:3001         │
│                      ❌ Não alcança         │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│  DEPOIS (Produção)                          │
│                                             │
│  Vercel (Frontend) → Railway (Backend)      │
│                      ✅ Funciona!           │
└─────────────────────────────────────────────┘
```

## ❓ Qual URL usar onde?

| Variável | Onde Configurar | Valor |
|----------|----------------|-------|
| `VITE_API_URL` | Vercel | URL do Railway (ex: https://webgo.railway.app) |
| `ALLOWED_ORIGINS` | Railway | URL da Vercel (ex: https://webgo.vercel.app) |
| `VITE_SUPABASE_URL` | Vercel | https://txvvzpstquqmbhljudfn.supabase.co |
| `SUPABASE_URL` | Railway | https://txvvzpstquqmbhljudfn.supabase.co |

## 📋 Checklist Final

- [ ] Conta criada no Railway
- [ ] Backend deployado no Railway
- [ ] URL do Railway anotada
- [ ] Variáveis configuradas no Railway
- [ ] Variáveis atualizadas na Vercel com URL do Railway
- [ ] Redeploy feito na Vercel
- [ ] Site testado e funcionando
- [ ] Login funcionando
- [ ] Dashboards carregando

## 🆘 Problemas Comuns

### Site ainda em loading após deploy
- **Causa**: `VITE_API_URL` não foi atualizada na Vercel
- **Solução**: Verificar variável e fazer redeploy

### Erro CORS no console
- **Causa**: `ALLOWED_ORIGINS` no Railway não tem URL da Vercel
- **Solução**: Adicionar URL completa da Vercel no Railway

### Backend não inicia no Railway
- **Causa**: Variáveis de ambiente faltando
- **Solução**: Verificar se todas as variáveis foram configuradas

### Login não funciona
- **Causa**: Service role key incorreta ou anon key incorreta
- **Solução**: Verificar keys no Supabase Dashboard

## 💡 Dica Pro

Depois de configurar, teste localmente com as URLs de produção:

```bash
# .env.local
VITE_API_URL=https://seu-backend.railway.app

npm run dev
```

Se funcionar local com URL de produção, funcionará na Vercel também!

## 📞 Precisa de Ajuda?

Se encontrar problemas:
1. Abra DevTools (F12) e copie os erros do Console
2. Verifique logs do Railway (Settings → Logs)
3. Verifique logs da Vercel (Deployments → Ver logs)
4. Me envie os erros e eu ajudo a resolver!

---

**Tempo total estimado**: 20-25 minutos
**Custo**: Railway tem trial grátis, depois ~$5-10/mês
