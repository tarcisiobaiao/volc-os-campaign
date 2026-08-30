# 🚀 **GUIA DE PRODUÇÃO - SISTEMA CAMPAIGN DASHBOARD**

> **ARQUIVADO:** documentação do produto-base WebGo anterior ao VOLC O.S. atual.

## **📊 STATUS ATUAL**
✅ **Sistema 100% "Modo Pedreira"** - Pronto para produção!

- **Banco**: Supabase com todas as tabelas + índices otimizados
- **Integridade**: Constraints, checks, triggers automáticos  
- **Performance**: NUMERIC(18,6), índices UNIQUE, views otimizadas
- **Monitoramento**: Health checks + queries de manutenção

---

## **🔧 OPERAÇÕES DIÁRIAS**

### **1. Health Checks Automáticos**

**Frontend (React):**
```typescript
import { useHealthChecks } from '@/utils/healthChecks'

// No dashboard administrativo
const { healthStatus, loading, runChecks } = useHealthChecks()

// Status: HEALTHY | DEGRADED | UNHEALTHY
```

**Backend/Cron (SQL):**
```bash
# Executar diariamente às 9h
0 9 * * * psql $DATABASE_URL -f /path/to/production-maintenance.sql
```

### **2. Monitoramento de Lag**
```sql
-- Verificar atraso de dados (deve ser < 2 dias)
SELECT src, last_date, days_behind FROM lag_check;
```

---

## **📈 PERFORMANCE & ESCALABILIDADE**

### **Quando Implementar Particionamento:**
- **Trigger**: Tabelas > 50M registros
- **Alvo**: `daily_ad_group_metrics`, `daily_campaign_metrics`, `url_daily_performance`
- **Estratégia**: Particionamento mensal por `date`

### **Manutenção Semanal:**
```sql
-- Toda sexta às 23h
VACUUM (ANALYZE) public.daily_ad_group_metrics;
VACUUM (ANALYZE) public.daily_campaign_metrics;
VACUUM (ANALYZE) public.url_daily_performance;
```

---

## **🔒 SEGURANÇA (RLS)**

### **Row Level Security - Implementação Básica:**
```sql
-- Projetos por usuário
ALTER TABLE public.projects ENABLE ROW LEVEL SECURITY;

CREATE POLICY projects_select_by_user
ON public.projects FOR SELECT
USING (
  -- Adapte esta lógica conforme seu sistema de auth
  auth.uid()::text = created_by 
  OR 
  EXISTS (
    SELECT 1 FROM user_projects up 
    WHERE up.project_id = projects.id 
    AND up.user_id = auth.uid()
  )
);
```

### **Tabelas Prioritárias para RLS:**
1. `projects` ✅
2. `campaigns` 
3. `daily_campaign_metrics`
4. `url_daily_performance`

---

## **🎯 VIEWS ÚTEIS (BI & REPORTING)**

### **1. Agregados por Campanha:**
```sql
-- Já criada: v_campaign_daily_from_adgroups
SELECT * FROM v_campaign_daily_from_adgroups 
WHERE date >= '2025-08-01';
```

### **2. Performance Consolidada por Projeto:**
```sql
CREATE VIEW v_project_performance_summary AS
SELECT 
  p.project_name,
  DATE_TRUNC('month', dpm.date) as month,
  SUM(dpm.invested_amount) as total_spend,
  SUM(dpm.billed_amount) as total_revenue,
  AVG(dpm.roas) as avg_roas,
  SUM(dpm.page_views) as total_pageviews
FROM projects p
JOIN daily_project_metrics dpm ON p.id = dpm.project_id
WHERE dpm.date >= CURRENT_DATE - INTERVAL '12 months'
GROUP BY p.id, p.project_name, DATE_TRUNC('month', dpm.date);
```

---

## **⚡ FLUXO n8n → SUPABASE**

### **Webhook Endpoint:**
```typescript
// /api/webhooks/gam-data
export async function POST(request: Request) {
  const { projectId, gamData, syncTimestamp } = await request.json()
  
  const result = await processIncomingGamData(gamData, projectId)
  
  return Response.json(result)
}
```

### **Formato de Dados GAM:**
```json
{
  "projectId": 1,
  "syncTimestamp": "2025-08-22T10:00:00Z",
  "gamData": {
    "rows": [
      {
        "Column": [
          {"name": "date", "Val": "8/22/25"},
          {"name": "XFP_URL_NAME", "Val": "site.com/page"},
          {"name": "adxReservationPubCostDelivered", "Val": "R$1.39"},
          {"name": "activeViewAdxViewableImpressionsRate", "Val": "90.32%"}
        ]
      }
    ]
  }
}
```

---

## **🚨 ALERTAS RECOMENDADOS**

### **1. Duplicatas (CRÍTICO):**
```sql
-- Se retornar linhas = PROBLEMA
SELECT * FROM check_duplicates_dagm();
SELECT * FROM check_duplicates_dcm();
```

### **2. Lag de Dados (WARNING):**
```sql  
-- Se days_behind > 2 = PROBLEMA
SELECT * FROM check_ingestion_lag();
```

### **3. Volume Anômalo (INFO):**
```sql
-- Mudanças bruscas no volume
SELECT * FROM check_volume_anomalies();
```

---

## **📋 CHECKLIST DE PRODUÇÃO**

### **✅ Pré-Deploy:**
- [ ] Todas as migrações aplicadas
- [ ] Índices UNIQUE criados
- [ ] RLS configurado (se necessário)
- [ ] Health checks testados
- [ ] Webhook n8n configurado

### **✅ Pós-Deploy:**
- [ ] Smoke tests executados (zero duplicatas)
- [ ] Primeiro load de dados GAM testado
- [ ] Dashboard carregando corretamente
- [ ] Logs estruturados funcionando
- [ ] Alertas configurados

### **✅ Operação Contínua:**
- [ ] Health checks automatizados (diário)
- [ ] VACUUM semanal configurado
- [ ] Monitoramento de performance ativo
- [ ] Backup strategy definida

---

## **🛠️ TROUBLESHOOTING**

### **Problemas Comuns:**

**1. Duplicatas Aparecendo:**
```sql
-- Investigar origem
SELECT * FROM daily_campaign_metrics 
WHERE (campaign_id, date) IN (
  SELECT campaign_id, date 
  FROM daily_campaign_metrics 
  GROUP BY campaign_id, date 
  HAVING COUNT(*) > 1
);
```

**2. Performance Lenta:**
```sql
-- Verificar índices
SELECT * FROM pg_stat_user_indexes 
WHERE relname IN ('daily_campaign_metrics', 'daily_ad_group_metrics');
```

**3. Webhook Falhando:**
- Verificar logs n8n
- Testar processamento manual: `testGamDataProcessing()`
- Validar formato de dados

---

## **📞 CONTATOS DE EMERGÊNCIA**
- **Database**: Supabase Dashboard
- **Logs**: Console Supabase + Application logs  
- **Monitoring**: Health checks endpoint

**Sistema 100% Operacional! 🚀**
