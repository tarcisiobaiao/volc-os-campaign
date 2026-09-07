import { describe, it, expect, vi, afterEach } from "vitest";

// Streaming is derived from VITE_API_URL — stub it before importing the module.
vi.stubEnv("VITE_API_URL", "http://localhost:8001/generate");

const { streamCreatives, dataUrlToBlob } = await import("@/lib/api");

function sseResponse(body: string): Response {
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(body));
      controller.close();
    },
  });
  return new Response(stream, {
    status: 200,
    headers: { "content-type": "text/event-stream" },
  });
}

afterEach(() => vi.restoreAllMocks());

describe("streamCreatives ordering", () => {
  it("onDone runs only AFTER a slow onImageDone has registered (no missing image)", async () => {
    // image_done and done arrive in the SAME chunk — the original race window.
    const body =
      'event: image_done\ndata: {"n":1,"total":1,"name":"a.png","dataUrl":"data:image/png;base64,AAAA"}\n\n' +
      'event: done\ndata: {"total":1,"delivered":1}\n\n';

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: unknown) => {
        const url = String(input);
        if (url.startsWith("data:")) {
          return new Response(new Blob([new Uint8Array([1, 2, 3])]));
        }
        return sseResponse(body);
      })
    );

    const collected = new Map<number, Blob>();
    const order: string[] = [];
    let sizeAtDone = -1;

    await streamCreatives(
      {
        aspect_ratio: "1:1",
        dimensions: "1080x1080",
        objective: "teste",
        quantity: 1,
        logo: { variant: "aprova-main", assetLabel: "Aprova", data: "", mimeType: "image/png" },
        content_type: "meta-ads",
      } as never,
      {
        onImageDone: async (img) => {
          const blob = await dataUrlToBlob(img.dataUrl); // the async window
          collected.set(img.n, blob);
          order.push("image_done");
        },
        onDone: () => {
          sizeAtDone = collected.size;
          order.push("done");
        },
      }
    );

    expect(order).toEqual(["image_done", "done"]);
    expect(sizeAtDone).toBe(1); // the image was collected BEFORE the zip would be built
  });
});
