import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "jsr:@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const MAX_BODY_BYTES = 64 * 1024;
const MAX_BATCH = 20;
const ALLOWED_ORIGINS = new Set(
  (Deno.env.get("VOLC_ALLOWED_ORIGINS") ||
    "https://creditoup.com.br,https://www.creditoup.com.br")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean),
);

const EVENT_FIELDS: Record<string, Set<string>> = {
  volc_sensor_ready: new Set(["s", "e", "r", "ms", "bot", "utm", "vw", "vh"]),
  volc_scroll_mark: new Set(["m", "p"]),
  volc_engaged_mark: new Set(["m", "s"]),
  volc_dwell_time: new Set(["block", "tag", "sec"]),
  volc_internal_click: new Set(["dest", "text", "tipo", "vw", "vh", "ttc"]),
  volc_rage_click: new Set(["x", "y", "vw", "tag", "el"]),
  volc_dead_click: new Set(["tag", "el", "text"]),
  volc_ad_view: new Set(["slot", "id", "ratio", "ms", "fill", "top", "vw", "vh"]),
  volc_gpt_render: new Set(["id", "unit", "empty", "size"]),
  volc_gpt_viewable: new Set(["id", "unit"]),
};

const db = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, {
  auth: { persistSession: false, autoRefreshToken: false },
});

function cors(origin: string): HeadersInit {
  return {
    "Access-Control-Allow-Origin": origin,
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
    "Vary": "Origin",
  };
}

function response(origin: string, status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...cors(origin) },
  });
}

function text(value: unknown, max: number): string {
  return typeof value === "string" ? value.replace(/[\u0000-\u001f\u007f]/g, "").slice(0, max) : "";
}

function number(value: unknown, min: number, max: number): number | undefined {
  if (typeof value !== "number" || !Number.isFinite(value)) return undefined;
  return Math.min(max, Math.max(min, value));
}

function integer(value: unknown, min: number, max: number): number | undefined {
  if (typeof value !== "number" || !Number.isSafeInteger(value)) return undefined;
  if (value < min || value > max) return undefined;
  return value;
}

function cleanValue(value: unknown, depth = 0): unknown {
  if (depth > 2) return undefined;
  if (typeof value === "string") return text(value, 200);
  if (typeof value === "number") return number(value, -1_000_000, 1_000_000);
  if (typeof value === "boolean") return value;
  if (Array.isArray(value)) return value.slice(0, 20).map((item) => cleanValue(item, depth + 1));
  if (value && typeof value === "object") {
    const result: Record<string, unknown> = {};
    for (const [key, item] of Object.entries(value as Record<string, unknown>).slice(0, 20)) {
      if (!/^[a-zA-Z][a-zA-Z0-9_]{0,31}$/.test(key)) continue;
      const cleaned = cleanValue(item, depth + 1);
      if (cleaned !== undefined) result[key] = cleaned;
    }
    return result;
  }
  return undefined;
}

function payload(eventName: string, raw: unknown): Record<string, unknown> {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return {};
  const allowed = EVENT_FIELDS[eventName];
  const result: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(raw as Record<string, unknown>)) {
    if (!allowed.has(key)) continue;
    const cleaned = cleanValue(value);
    if (cleaned !== undefined) result[key] = cleaned;
  }
  return result;
}

function sameHost(origin: string, claimedHost: string): boolean {
  try {
    return new URL(origin).hostname.replace(/^www\./, "") === claimedHost.replace(/^www\./, "");
  } catch {
    return false;
  }
}

Deno.serve(async (req: Request) => {
  const origin = req.headers.get("origin") || "";
  if (!ALLOWED_ORIGINS.has(origin)) {
    return new Response(JSON.stringify({ ok: false, error: "origin_not_allowed" }), {
      status: 403,
      headers: { "Content-Type": "application/json", "Vary": "Origin" },
    });
  }

  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: cors(origin) });
  if (req.method !== "POST") return response(origin, 405, { ok: false, error: "method_not_allowed" });

  const declaredLength = Number(req.headers.get("content-length") || "0");
  if (declaredLength > MAX_BODY_BYTES) return response(origin, 413, { ok: false, error: "payload_too_large" });

  const rawText = await req.text();
  if (new TextEncoder().encode(rawText).byteLength > MAX_BODY_BYTES) {
    return response(origin, 413, { ok: false, error: "payload_too_large" });
  }

  let body: Record<string, unknown>;
  try {
    body = JSON.parse(rawText || "{}") as Record<string, unknown>;
  } catch {
    return response(origin, 400, { ok: false, error: "invalid_json" });
  }

  const batch = Array.isArray(body.batch) ? body.batch.slice(0, MAX_BATCH) : [];
  if (!batch.length) return response(origin, 200, { ok: true, inserted: 0 });

  const measurementVersion = text(body.v, 16) || "3.0";
  const rows = batch.flatMap((raw) => {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return [];
    const item = raw as Record<string, unknown>;
    const eventName = text(item.e ?? item.event, 64);
    if (!EVENT_FIELDS[eventName]) return [];

    const sid = text(item.sid ?? body.sid, 128);
    const pid = text(item.pid ?? body.pid, 128);
    const eventSeq = integer(item.seq, 0, 2_147_483_647);
    const path = text(item.path ?? body.path, 512);
    const host = text(item.host ?? body.host, 128).toLowerCase();
    if (!sid || !pid || !path.startsWith("/") || !host || !sameHost(origin, host)) return [];
    if (measurementVersion === "3.1" && eventSeq === undefined) return [];

    const rawTs = typeof item.ts === "number" ? item.ts : Date.now();
    const ts = new Date(rawTs);
    if (!Number.isFinite(ts.getTime())) return [];
    const now = Date.now();
    if (ts.getTime() < now - 86_400_000 || ts.getTime() > now + 300_000) return [];

    return [{
      ts: ts.toISOString(),
      ts_sec: Math.floor(ts.getTime() / 1000),
      event_seq: eventSeq ?? 0,
      sid,
      pid,
      path,
      host,
      ref: text(item.ref ?? body.ref, 128),
      event_name: eventName,
      payload: payload(eventName, item.p),
      v: measurementVersion,
    }];
  });

  if (!rows.length) return response(origin, 422, { ok: false, error: "no_valid_events" });

  const { error } = await db.from("raw_events").upsert(rows, {
    onConflict: "sid,pid,event_name,ts_sec,event_seq",
    ignoreDuplicates: true,
  });
  if (error) {
    console.error("volc-ingest insert failed", error.code);
    return response(origin, 500, { ok: false, error: "insert_failed" });
  }

  return response(origin, 200, { ok: true, inserted: rows.length });
});
