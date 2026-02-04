# Guia de Segurança - Sistema WebGo

## 🔒 Visão Geral

Este documento descreve a arquitetura de segurança implementada para proteger credenciais sensíveis e dados do banco de dados.

## 🏗️ Arquitetura de Segurança

### Problema Identificado
Anteriormente, as credenciais do Supabase estavam expostas no frontend através das variáveis `VITE_*`, que são compiladas no bundle JavaScript e ficam visíveis no navegador.

### Solução Implementada
Implementamos uma arquitetura de 3 camadas:

```
Frontend (React) → Backend API Seguro → Supabase Database
```

1. **Frontend**: Usa apenas chaves públicas (anon key) para autenticação
2. **Backend**: Proxy seguro que protege credenciais sensíveis (service role key)
3. **Database**: Supabase com RLS (Row Level Security) habilitado

## 📁 Estrutura de Arquivos

### Arquivos de Ambiente

#### `.env.local` (Frontend - Seguro para commit)
```env
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=your-anon-key
VITE_API_URL=http://localhost:3001
```
- ✅ Usa apenas chave anon (pública)
- ✅ Seguro para ser exposto no bundle do frontend

#### `.env.server` (Backend - NUNCA COMMITAR)
```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
SERVER_PORT=3001
ALLOWED_ORIGINS=http://localhost:5173,https://your-domain.com
```
- ❌ Contém service role key (acesso total ao banco)
- ❌ NUNCA deve ser commitado ao Git
- ✅ Protegido pelo `.gitignore`

## 🔐 Configuração Inicial

### 1. Configurar Credenciais do Servidor

Copie o arquivo de exemplo e preencha com suas credenciais:

```bash
cp .env.server.example .env.server
```

Edite `.env.server` e adicione:
- `SUPABASE_SERVICE_ROLE_KEY`: Encontrada no painel do Supabase → Settings → API → service_role key

### 2. Instalar Dependências

```bash
npm install
```

Isso instalará:
- `express`: Servidor backend
- `cors`: Controle de acesso CORS
- `concurrently`: Executar frontend e backend simultaneamente

### 3. Executar em Desenvolvimento

```bash
# Executar frontend e backend juntos
npm run dev:all

# Ou separadamente:
npm run dev          # Frontend (porta 5173)
npm run dev:server   # Backend (porta 3001)
```

## 🔌 API Backend Segura

### Endpoints Disponíveis

#### Health Check
```http
GET /health
```

#### Consultar Usuários
```http
POST /api/users/query
Content-Type: application/json

{
  "email": "user@example.com"
}
```

#### Consulta Genérica
```http
POST /api/supabase/query
Content-Type: application/json

{
  "table": "campaigns",
  "select": "*",
  "filters": [
    { "field": "status", "operator": "eq", "value": "Active" }
  ]
}
```

#### Inserir Dados
```http
POST /api/supabase/insert
Content-Type: application/json

{
  "table": "projects",
  "data": { "project_name": "Novo Projeto", "status": "Active" }
}
```

#### Atualizar Dados
```http
POST /api/supabase/update
Content-Type: application/json

{
  "table": "campaigns",
  "data": { "status": "Paused" },
  "filters": [
    { "field": "id", "operator": "eq", "value": 123 }
  ]
}
```

#### Deletar Dados
```http
POST /api/supabase/delete
Content-Type: application/json

{
  "table": "campaigns",
  "filters": [
    { "field": "id", "operator": "eq", "value": 123 }
  ]
}
```

#### Chamar RPC Functions
```http
POST /api/supabase/rpc
Content-Type: application/json

{
  "functionName": "get_dashboard_totals",
  "params": { "start_date": "2025-01-01" }
}
```

## 💻 Uso no Frontend

### Importar Cliente Seguro

```typescript
import { secureApi } from '@/lib/secureApi';
```

### Exemplos de Uso

```typescript
// Consultar dados
const campaigns = await secureApi.query({
  table: 'campaigns',
  select: '*',
  filters: [
    { field: 'status', operator: 'eq', value: 'Active' }
  ]
});

// Inserir dados
const newProject = await secureApi.insert({
  table: 'projects',
  data: { project_name: 'Novo Projeto', status: 'Active' }
});

// Atualizar dados
const updated = await secureApi.update({
  table: 'campaigns',
  data: { status: 'Paused' },
  filters: [{ field: 'id', operator: 'eq', value: 123 }]
});

// Chamar RPC
const metrics = await secureApi.rpc({
  functionName: 'get_dashboard_totals',
  params: { start_date: '2025-01-01' }
});

// Consultar usuários (endpoint otimizado)
const users = await secureApi.queryUsers('user@example.com');
```

## 🚀 Deploy em Produção

### Vercel (Frontend)

1. Configure as variáveis de ambiente no painel da Vercel:
   ```
   VITE_SUPABASE_URL=https://your-project.supabase.co
   VITE_SUPABASE_ANON_KEY=your-anon-key
   VITE_API_URL=https://your-backend-api.com
   ```

### Backend API

Você pode hospedar o backend em:

#### Opção 1: Railway
```bash
# Instalar Railway CLI
npm install -g railway

# Deploy
railway init
railway up
```

Configure as variáveis de ambiente no painel do Railway.

#### Opção 2: Heroku
```bash
# Criar app
heroku create your-api-name

# Configurar variáveis
heroku config:set SUPABASE_URL=https://...
heroku config:set SUPABASE_SERVICE_ROLE_KEY=...

# Deploy
git push heroku main
```

#### Opção 3: DigitalOcean App Platform
1. Conecte seu repositório
2. Configure como "Web Service"
3. Adicione variáveis de ambiente
4. Deploy automático

## 🔐 Integração com N8N

### Webhook Seguro

O backend pode ser configurado para aceitar webhooks do N8N com autenticação:

1. Configure um secret no `.env.server`:
   ```env
   N8N_WEBHOOK_SECRET=your-secret-key
   ```

2. Adicione endpoint no `server/index.js`:
   ```javascript
   app.post('/api/n8n/webhook', (req, res) => {
     const { authorization } = req.headers;
     if (authorization !== `Bearer ${process.env.N8N_WEBHOOK_SECRET}`) {
       return res.status(401).json({ error: 'Unauthorized' });
     }
     // Processar webhook
   });
   ```

3. Configure no N8N:
   - URL: `https://your-api.com/api/n8n/webhook`
   - Header: `Authorization: Bearer your-secret-key`

## ✅ Checklist de Segurança

- [ ] `.env.server` está no `.gitignore`
- [ ] Service role key NUNCA está no frontend
- [ ] CORS configurado apenas para origens permitidas
- [ ] RLS habilitado nas tabelas do Supabase
- [ ] Webhooks do N8N usam autenticação
- [ ] Variáveis de produção configuradas no hosting
- [ ] Backend API rodando em HTTPS
- [ ] Rate limiting implementado (futuro)

## 🛡️ Boas Práticas

1. **Nunca exponha credenciais sensíveis**
   - Service role key deve ficar apenas no backend
   - Anon key pode ser pública (mas com RLS ativo)

2. **Use HTTPS em produção**
   - Sempre use SSL/TLS
   - Configure certificados válidos

3. **Monitore acessos**
   - Implemente logging de requisições
   - Monitore tentativas de acesso não autorizado

4. **Atualize dependências**
   ```bash
   npm audit
   npm update
   ```

5. **Backup de credenciais**
   - Mantenha backup seguro das keys
   - Use gerenciador de senhas (1Password, Bitwarden)

## 🆘 Troubleshooting

### Backend não conecta ao Supabase
- Verifique se `SUPABASE_SERVICE_ROLE_KEY` está correta
- Verifique se não há espaços extras no `.env.server`

### CORS error no frontend
- Adicione o origin do frontend em `ALLOWED_ORIGINS`
- Reinicie o servidor backend

### N8N webhook falha
- Verifique se o secret está correto
- Confirme se a URL está acessível publicamente

## 📚 Recursos Adicionais

- [Supabase Security Best Practices](https://supabase.com/docs/guides/auth/row-level-security)
- [Express Security Best Practices](https://expressjs.com/en/advanced/best-practice-security.html)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)

## 🤝 Suporte

Para questões de segurança, entre em contato com o time de desenvolvimento.
