# 🔗 Guia de Integração N8N - Arquitetura Segura

> **ARQUIVADO:** contém decisões da arquitetura anterior; valide destinos no Mapa Vivo.

## 📋 Visão Geral

Este guia explica como manter suas automações N8N funcionando com a nova arquitetura de segurança.

## ✅ Status Atual do N8N

**ÓTIMA NOTÍCIA**: Suas automações N8N podem continuar funcionando normalmente!

O N8N roda no **servidor** (não no navegador), então ele pode:
- ✅ Continuar usando a **service role key** diretamente
- ✅ Continuar chamando o Supabase REST API
- ✅ Continuar usando webhooks existentes

## 🔐 Opções de Integração

### Opção 1: Manter Como Está (Recomendado para Início)

O N8N continua chamando o Supabase diretamente:

```
N8N Workflow → Supabase REST API
```

**Vantagens**:
- ✅ Zero mudanças necessárias
- ✅ Funciona imediatamente
- ✅ Menos latência

**Quando usar**: Suas automações já funcionam e você quer fazer a migração gradual.

### Opção 2: Usar Backend como Proxy (Recomendado para Produção)

O N8N chama seu backend, que chama o Supabase:

```
N8N Workflow → Seu Backend API → Supabase
```

**Vantagens**:
- ✅ Logs centralizados
- ✅ Validações adicionais
- ✅ Rate limiting
- ✅ Auditoria completa

**Quando usar**: Você quer controle total e logs de todas operações.

## 🚀 Implementação - Opção 2

### 1. Adicionar Autenticação para N8N

Edite `server/index.js` e adicione middleware de autenticação:

```javascript
// Middleware para autenticar N8N
const authenticateN8N = (req, res, next) => {
  const authHeader = req.headers.authorization;
  const expectedToken = process.env.N8N_WEBHOOK_SECRET;

  if (!expectedToken) {
    return next(); // Sem secret configurado, permite acesso
  }

  if (authHeader !== `Bearer ${expectedToken}`) {
    return res.status(401).json({ error: 'Unauthorized' });
  }

  next();
};

// Aplicar em rotas que o N8N usa
app.post('/api/supabase/insert', authenticateN8N, async (req, res) => {
  // ... código existente
});

app.post('/api/supabase/update', authenticateN8N, async (req, res) => {
  // ... código existente
});
```

### 2. Configurar Secret no .env.server

```env
N8N_WEBHOOK_SECRET=seu-secret-seguro-aqui-use-uuid
```

### 3. Atualizar N8N Workflows

#### Antes (Chamada Direta ao Supabase):

```
HTTP Request Node:
- URL: https://txvvzpstquqmbhljudfn.supabase.co/rest/v1/daily_campaign_metrics
- Method: POST
- Headers:
  - apikey: eyJhbG...service-role-key
  - Authorization: Bearer eyJhbG...service-role-key
  - Content-Type: application/json
- Body: { "date": "2025-01-01", ... }
```

#### Depois (Chamada ao Backend):

```
HTTP Request Node:
- URL: https://seu-backend.com/api/supabase/insert
- Method: POST
- Headers:
  - Authorization: Bearer seu-secret-seguro-aqui
  - Content-Type: application/json
- Body: {
    "table": "daily_campaign_metrics",
    "data": { "date": "2025-01-01", ... }
  }
```

## 📝 Exemplos de Chamadas N8N

### Inserir Métricas Diárias

```json
POST https://seu-backend.com/api/supabase/insert
Authorization: Bearer seu-secret-n8n

{
  "table": "daily_campaign_metrics",
  "data": {
    "campaign_id": 123,
    "date": "2025-01-01",
    "spend": 100.50,
    "revenue": 250.00,
    "clicks": 500,
    "impressions": 10000
  }
}
```

### Atualizar Status de Campanha

```json
POST https://seu-backend.com/api/supabase/update
Authorization: Bearer seu-secret-n8n

{
  "table": "campaigns",
  "data": {
    "status": "Active",
    "updated_at": "2025-01-01T10:00:00Z"
  },
  "filters": [
    { "field": "id", "operator": "eq", "value": 123 }
  ]
}
```

### Chamar RPC Function

```json
POST https://seu-backend.com/api/supabase/rpc
Authorization: Bearer seu-secret-n8n

{
  "functionName": "refresh_campaign_metrics",
  "params": {
    "campaign_id": 123,
    "start_date": "2025-01-01"
  }
}
```

### Consultar Dados

```json
POST https://seu-backend.com/api/supabase/query
Authorization: Bearer seu-secret-n8n

{
  "table": "campaigns",
  "select": "id, campaign_name, status",
  "filters": [
    { "field": "status", "operator": "eq", "value": "Active" }
  ]
}
```

## 🔄 Migração Gradual

### Fase 1: Testar Localmente
1. Configure o backend localmente
2. Crie workflow de teste no N8N
3. Teste chamadas ao `http://localhost:3001/api/supabase/*`

### Fase 2: Deploy do Backend
1. Faça deploy do backend (Railway, Heroku, etc.)
2. Configure `N8N_WEBHOOK_SECRET` no servidor
3. Anote a URL pública (ex: `https://seu-app.railway.app`)

### Fase 3: Atualizar Workflows Gradualmente
1. Duplique um workflow existente
2. Atualize a cópia para usar o backend
3. Teste e valide
4. Desative o workflow antigo
5. Repita para cada workflow

### Fase 4: Desativar Acesso Direto (Opcional)
1. No Supabase, configure RLS mais restritivo
2. Limite acesso da service role key apenas ao backend
3. N8N só poderá acessar via backend

## 📊 Monitoramento

### Logs do Backend

O backend loga todas requisições:

```bash
# Ver logs em tempo real
tail -f logs/server.log

# Ou no Railway/Heroku:
railway logs
heroku logs --tail
```

### Adicionar Logging Detalhado

Edite `server/index.js`:

```javascript
// Middleware de logging
app.use((req, res, next) => {
  console.log(`[${new Date().toISOString()}] ${req.method} ${req.path}`);
  console.log('Body:', JSON.stringify(req.body, null, 2));
  next();
});
```

## 🔐 Segurança do N8N

### Boas Práticas

1. **Use Secret Forte**:
   ```bash
   # Gerar secret seguro
   node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"
   ```

2. **Rotacione Secrets Periodicamente**:
   - Troque a cada 90 dias
   - Atualize no backend e N8N

3. **Limite Acesso por IP** (Opcional):
   ```javascript
   const allowedIPs = process.env.N8N_ALLOWED_IPS?.split(',') || [];

   app.use((req, res, next) => {
     if (allowedIPs.length > 0 && !allowedIPs.includes(req.ip)) {
       return res.status(403).json({ error: 'Forbidden' });
     }
     next();
   });
   ```

4. **Rate Limiting**:
   ```bash
   npm install express-rate-limit
   ```

   ```javascript
   import rateLimit from 'express-rate-limit';

   const limiter = rateLimit({
     windowMs: 15 * 60 * 1000, // 15 minutos
     max: 100 // máximo 100 requisições
   });

   app.use('/api/', limiter);
   ```

## 🆘 Troubleshooting

### N8N recebe 401 Unauthorized
- Verifique se o `Authorization` header está correto
- Confirme que `N8N_WEBHOOK_SECRET` está configurado
- Formato: `Bearer seu-secret-aqui`

### N8N recebe 404 Not Found
- Verifique a URL do backend
- Confirme que o backend está rodando
- Teste com curl:
  ```bash
  curl https://seu-backend.com/health
  ```

### Dados não são inseridos
- Verifique o formato do body
- Confira logs do backend
- Teste com Postman primeiro

### Timeout no N8N
- Aumente timeout no HTTP Request Node
- Verifique performance do Supabase
- Considere usar queue para operações longas

## 📈 Próximos Passos

1. **Agora**: Continue usando N8N direto com Supabase
2. **Curto Prazo**: Teste backend localmente com N8N
3. **Médio Prazo**: Deploy backend em produção
4. **Longo Prazo**: Migre workflows gradualmente

## 💡 Dicas

- **Webhook Sync vs Async**: Use async para operações demoradas
- **Batch Insert**: Para múltiplos registros, use array no `data`
- **Error Handling**: Configure retry no N8N para falhas temporárias
- **Monitoring**: Use Sentry ou similar para alertas de erro

## 🎯 Conclusão

Você tem **flexibilidade total**:
- ✅ N8N pode continuar funcionando como está
- ✅ Migração pode ser gradual e sem pressa
- ✅ Backend oferece benefícios quando você precisar

**Recomendação**: Mantenha N8N como está inicialmente. Migre quando tiver tempo para testar adequadamente.
