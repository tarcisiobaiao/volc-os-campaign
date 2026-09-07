import JSZip from "jszip";

// ── Types ──────────────────────────────────────────────

export type LogoVariant = "aprova-main" | "custom-upload";
export type ContentType = "meta-ads" | "news" | "pinterest";

export interface LogoPayload {
  data: string;
  mimeType: string;
  variant: LogoVariant;
  assetLabel: string;
}

export interface GenerateRequest {
  aspect_ratio: string;
  dimensions: string; // exact target pixels, e.g. "1080x1350"
  objective: string;
  quantity: number;
  logo: LogoPayload;
  content_type: ContentType;
}

export interface GeneratedImage {
  name: string;
  url: string;
}

// ── Config ─────────────────────────────────────────────

const API_URL =
  import.meta.env.VITE_API_URL ||
  import.meta.env.VITE_N8N_WEBHOOK_URL ||
  "";

// The SSE endpoint lives at `${VITE_API_URL}/stream`. Only the FastAPI backend
// (URL ending in /generate) supports streaming; an n8n webhook does not.
const STREAM_URL =
  import.meta.env.VITE_API_STREAM_URL ||
  (/\/generate\/?$/.test(API_URL) ? API_URL.replace(/\/$/, "") + "/stream" : "");

// Backend root (for /config endpoints) — only when API_URL is our FastAPI backend.
const API_ROOT = /\/generate\/?$/.test(API_URL)
  ? API_URL.replace(/\/generate\/?$/, "")
  : "";

export function isWebhookConfigured(): boolean {
  return API_URL.length > 0;
}

export function isStreamingSupported(): boolean {
  return STREAM_URL.length > 0;
}

export function isConfigSupported(): boolean {
  return API_ROOT.length > 0;
}

// ── Generate ───────────────────────────────────────────

export async function generateCreatives(
  request: GenerateRequest,
  signal?: AbortSignal
): Promise<{ images: GeneratedImage[]; zipBlob: Blob }> {
  if (!isWebhookConfigured()) {
    await new Promise<void>((resolve, reject) => {
      const t = setTimeout(resolve, 4000);
      signal?.addEventListener("abort", () => {
        clearTimeout(t);
        reject(new DOMException("Aborted", "AbortError"));
      });
    });
    return { images: [], zipBlob: new Blob() };
  }

  if (!request.objective?.trim()) {
    throw new Error("O contexto/objetivo é obrigatório.");
  }

  const res = await fetch(API_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/zip, application/octet-stream, application/json",
    },
    body: JSON.stringify(request),
    signal,
  });

  if (!res.ok) {
    throw new Error(await readErrorMessage(res));
  }

  const contentType = res.headers.get("content-type") || "";
  const blob = await res.blob();

  if (contentType.includes("application/json")) {
    const text = await blob.text();
    throw new Error(`Workflow retornou erro: ${truncate(text, 500)}`);
  }

  const images = await extractFromZip(blob);
  if (images.length === 0) {
    throw new Error("Nenhum criativo foi gerado. Verifique o backend.");
  }

  return { images, zipBlob: blob };
}

async function readErrorMessage(res: Response): Promise<string> {
  let body = "";
  try {
    body = await res.text();
  } catch {
    /* noop */
  }
  const trimmed = truncate(body.trim(), 500);
  return trimmed
    ? `Erro ${res.status}: ${trimmed}`
    : `Erro ${res.status}: ${res.statusText}`;
}

function truncate(s: string, max: number): string {
  return s.length > max ? `${s.slice(0, max)}…` : s;
}

// ── ZIP extraction ─────────────────────────────────────

async function extractFromZip(blob: Blob): Promise<GeneratedImage[]> {
  const zip = await JSZip.loadAsync(blob);
  const images: GeneratedImage[] = [];
  const entries = Object.entries(zip.files).filter(
    ([name]) =>
      /\.(png|jpe?g|webp)$/i.test(name) && !name.startsWith("__MACOSX")
  );

  for (const [name, file] of entries) {
    const data = await file.async("blob");
    images.push({ name, url: URL.createObjectURL(data) });
  }

  return images.sort((a, b) =>
    a.name.localeCompare(b.name, undefined, { numeric: true })
  );
}

// ── Download helpers ───────────────────────────────────

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export function downloadFromUrl(objectUrl: string, filename: string) {
  const a = document.createElement("a");
  a.href = objectUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

// ── SSE streaming ──────────────────────────────────────

export interface StreamImage {
  n: number;
  total: number;
  name: string;
  dataUrl: string;
}

export interface StreamHandlers {
  onPhase?: (phase: string) => void;
  onImageStart?: (n: number, total: number) => void;
  onImageDone?: (img: StreamImage) => void;
  onImageFailed?: (info: { n: number; total: number; message: string }) => void;
  onDone?: (info: { total: number; delivered: number }) => void;
  onError?: (err: { code: string; message: string }) => void;
}

/** Parse one SSE frame ("event: x\ndata: y") into {event, data}. Exported for tests. */
export function parseSseFrame(
  frame: string
): { event: string; data: string } | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of frame.split(/\r?\n/)) {
    if (line.startsWith(":")) continue; // comment / heartbeat
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).replace(/^ /, ""));
  }
  if (dataLines.length === 0) return null;
  return { event, data: dataLines.join("\n") };
}

/** Split a buffer into complete frames + the trailing partial. Exported for tests. */
export function splitSseFrames(buffer: string): { frames: string[]; rest: string } {
  const parts = buffer.split(/\r?\n\r?\n/);
  const rest = parts.pop() ?? "";
  return { frames: parts.filter((p) => p.trim().length > 0), rest };
}

/**
 * Dispatch one frame. AWAITS the handler so that `onImageDone` (which decodes the
 * data URL into a Blob) fully completes before the next frame — critically, before
 * `done` — so the client-side zip never misses the last image.
 */
async function dispatchFrame(frame: string, h: StreamHandlers): Promise<void> {
  const parsed = parseSseFrame(frame);
  if (!parsed) return;
  let data: Record<string, unknown>;
  try {
    data = JSON.parse(parsed.data);
  } catch {
    return;
  }
  switch (parsed.event) {
    case "phase":
      h.onPhase?.(String(data.phase));
      break;
    case "image_start":
      h.onImageStart?.(Number(data.n), Number(data.total));
      break;
    case "image_done":
      await h.onImageDone?.({
        n: Number(data.n),
        total: Number(data.total),
        name: String(data.name),
        dataUrl: String(data.dataUrl),
      });
      break;
    case "image_failed":
      h.onImageFailed?.({
        n: Number(data.n),
        total: Number(data.total),
        message: String(data.message),
      });
      break;
    case "done":
      await h.onDone?.({ total: Number(data.total), delivered: Number(data.delivered) });
      break;
    case "error":
      h.onError?.({ code: String(data.code), message: String(data.message) });
      break;
  }
}

/**
 * Generate creatives with real-time progress via SSE. Calls the handlers as the
 * backend streams events; the final images arrive inline as data URLs through
 * `onImageDone`. Fatal failures surface through `onError` (not a throw), except
 * network/abort errors which reject so the caller can branch on AbortError.
 */
export async function streamCreatives(
  request: GenerateRequest,
  handlers: StreamHandlers,
  signal?: AbortSignal
): Promise<void> {
  if (!STREAM_URL) throw new Error("Streaming não suportado para esta URL de API.");
  if (!request.objective?.trim()) {
    throw new Error("O contexto/objetivo é obrigatório.");
  }

  const res = await fetch(STREAM_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify(request),
    signal,
  });

  if (!res.ok || !res.body) {
    // Pre-stream failure: backend returned JSON {detail, code} (e.g. 422/502).
    let message = `Erro ${res.status}: ${res.statusText}`;
    let code = "http_error";
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") message = body.detail;
      else if (Array.isArray(body?.detail)) {
        message = body.detail
          .map((d: { msg?: string }) => d?.msg ?? String(d))
          .join("; ");
      }
      if (typeof body?.code === "string") code = body.code;
    } catch {
      /* keep the status-line default */
    }
    handlers.onError?.({ code, message });
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const { frames, rest } = splitSseFrames(buffer);
      buffer = rest;
      for (const frame of frames) await dispatchFrame(frame, handlers);
    }
  } finally {
    reader.releaseLock?.();
  }

  const tail = buffer.trim();
  if (tail) await dispatchFrame(tail, handlers);
}

/** Decode a data: URL into a Blob (for client-side zipping + object URLs). */
export async function dataUrlToBlob(dataUrl: string): Promise<Blob> {
  const res = await fetch(dataUrl);
  return res.blob();
}

/** Build a .zip from named image blobs, client-side. */
export async function buildZip(
  images: { name: string; blob: Blob }[]
): Promise<Blob> {
  const zip = new JSZip();
  for (const img of images) zip.file(img.name, img.blob);
  return zip.generateAsync({ type: "blob" });
}

// ── API key config (managed from the UI) ───────────────────────

export interface KeyStatus {
  configured: boolean;
  masked: string;
  source: "runtime" | "env" | "missing";
}
export interface ConfigStatus {
  openai: KeyStatus;
  gemini: KeyStatus;
}
export interface ConfigUpdate {
  openai_api_key?: string;
  gemini_api_key?: string;
}
export interface KeyTest {
  ok: boolean;
  code: string;
  message: string;
}

export async function getConfig(): Promise<ConfigStatus> {
  const res = await fetch(`${API_ROOT}/config`);
  if (!res.ok) throw new Error(await readErrorMessage(res));
  return res.json();
}

export async function saveConfig(update: ConfigUpdate): Promise<ConfigStatus> {
  const res = await fetch(`${API_ROOT}/config`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(update),
  });
  if (!res.ok) throw new Error(await readErrorMessage(res));
  return res.json();
}

export async function testConfig(
  update: ConfigUpdate = {}
): Promise<{ openai: KeyTest; gemini: KeyTest }> {
  const res = await fetch(`${API_ROOT}/config/test`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(update),
  });
  if (!res.ok) throw new Error(await readErrorMessage(res));
  return res.json();
}
