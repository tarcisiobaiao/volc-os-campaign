# Handoff

Start implementation from this package only after reviewing official Meta v26 object refs again. Do not resolve Meta credentials in browser. Implement read-only sync first, then local validation, then request separate authorization for any Meta validate/upload/create.

Recommended first command:

```bash
cd /root/work/volc-runs/hermes-meta-v26-ground-truth-v1
python3 -m json.tool docs/closure/hermes-meta-v26-ground-truth-v1/META-V26-CAPABILITY-MATRIX.json >/dev/null
```
