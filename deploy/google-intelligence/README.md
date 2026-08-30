# Worker de inteligência Google Ads

Alternativa de worker, ainda não escolhida nem instalada. A operação atual usa
n8n; antes de ativar estas units, decidir uma única autoridade de agenda e provar
que os workflows n8n equivalentes foram adaptados ou desativados.

Dois ritmos, ambos estritamente read-only no Google Ads:

- `frequente`: a cada quatro horas, persiste diagnóstico, recomendações já
  publicadas pelo Google, simulações disponíveis e experimentos;
- `completa`: diariamente às 06:15 de São Paulo, acrescenta recomendações
  geradas sob demanda e cenários de forecast de keywords.

As observações são gravadas no Supabase oficial por
`volc_registrar_google_inteligencia(jsonb)`. A service role não possui INSERT,
UPDATE ou DELETE direto nas tabelas; só SELECT e EXECUTE na RPC atômica.

O serviço usa o `SERVICE_ROLE_KEY` que já existe em
`/root/supabase/docker/.env`. O único segredo adicional é
`/opt/volc-google-intelligence/google-ads.yaml`, modo 600. Nenhum segredo vive
no unit file ou no repositório.

Operação:

```bash
systemctl list-timers 'volc-google-intelligence-*'
systemctl start volc-google-intelligence@frequente.service
journalctl -u volc-google-intelligence@frequente.service -n 100 --no-pager
```
