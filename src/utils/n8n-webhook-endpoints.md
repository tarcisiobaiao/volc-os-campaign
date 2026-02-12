# N8N Webhook Endpoints para Atualização de Timestamps

## 📋 Como o n8n deve chamar o Supabase para atualizar timestamps

### 1. **Atualizar GAM (Google Ad Manager)**

**Endpoint:** POST para Supabase RPC
```
URL: https://[seu-projeto].supabase.co/rest/v1/rpc/update_gam_timestamp
Method: POST
Headers:
  - apikey: [sua-anon-key]
  - Authorization: Bearer [sua-anon-key]
  - Content-Type: application/json
Body: {}
```

**Exemplo de call no n8n:**
```json
{
  "url": "https://[seu-projeto].supabase.co/rest/v1/rpc/update_gam_timestamp",
  "method": "POST",
  "headers": {
    "apikey": "[sua-anon-key]",
    "Authorization": "Bearer [sua-anon-key]",
    "Content-Type": "application/json"
  },
  "body": {}
}
```

### 2. **Atualizar Google Ads**

**Endpoint:** POST para Supabase RPC
```
URL: https://[seu-projeto].supabase.co/rest/v1/rpc/update_google_ads_timestamp  
Method: POST
Headers:
  - apikey: [sua-anon-key]
  - Authorization: Bearer [sua-anon-key]
  - Content-Type: application/json
Body: {}
```

**Exemplo de call no n8n:**
```json
{
  "url": "https://[seu-projeto].supabase.co/rest/v1/rpc/update_google_ads_timestamp",
  "method": "POST", 
  "headers": {
    "apikey": "[sua-anon-key]",
    "Authorization": "Bearer [sua-anon-key]",
    "Content-Type": "application/json"
  },
  "body": {}
}
```

## 🔧 Configuração necessária:

1. **Execute o SQL** (`/src/sql/system-settings-timestamps.sql`) no Supabase SQL Editor
2. **Configure as keys** do Supabase no n8n
3. **Adicione as chamadas** no final de cada fluxo do n8n

## ⚙️ Fluxo recomendado no n8n:

```
1. [Processar dados GAM/Google Ads]
2. [Inserir dados no Supabase]
3. [HTTP Request para update_gam_timestamp ou update_google_ads_timestamp]
```

## 🕐 Resultado:
- Timestamp será salvo no horário de São Paulo automaticamente
- Frontend mostrará o horário correto da última atualização
- Dados ficam rastreáveis por fonte (GAM vs Google Ads)

## 🧪 Para testar:
Execute no Supabase SQL Editor:
```sql
-- Para GAM
SELECT update_gam_timestamp();

-- Para Google Ads  
SELECT update_google_ads_timestamp();

-- Para verificar
SELECT * FROM get_last_data_update();
```