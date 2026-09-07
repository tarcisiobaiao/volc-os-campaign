import { describe, it, expect } from "vitest";
import { parseSseFrame, splitSseFrames } from "@/lib/api";

describe("parseSseFrame", () => {
  it("parses event + data", () => {
    const frame = 'event: image_done\ndata: {"n":1,"total":3}';
    expect(parseSseFrame(frame)).toEqual({
      event: "image_done",
      data: '{"n":1,"total":3}',
    });
  });

  it("defaults event to 'message' when only data is present", () => {
    expect(parseSseFrame("data: hello")).toEqual({ event: "message", data: "hello" });
  });

  it("ignores comment/heartbeat lines and returns null without data", () => {
    expect(parseSseFrame(": keep-alive")).toBeNull();
    expect(parseSseFrame("event: phase")).toBeNull();
  });

  it("strips exactly one leading space after data:", () => {
    expect(parseSseFrame("data:  two-spaces")?.data).toBe(" two-spaces");
  });
});

describe("splitSseFrames", () => {
  it("returns complete frames and keeps the trailing partial as rest", () => {
    const buffer = "event: phase\ndata: {}\n\nevent: done\ndata: {}\n\nevent: partial";
    const { frames, rest } = splitSseFrames(buffer);
    expect(frames).toHaveLength(2);
    expect(rest).toBe("event: partial");
  });

  it("reassembles a frame split across chunk boundaries", () => {
    // Chunk 1 ends mid-frame; chunk 2 completes it.
    let buffer = "event: image_done\ndata: {\"n\":1,";
    let out = splitSseFrames(buffer);
    expect(out.frames).toHaveLength(0);
    buffer = out.rest + '"total":3}\n\n';
    out = splitSseFrames(buffer);
    expect(out.frames).toHaveLength(1);
    expect(parseSseFrame(out.frames[0])).toEqual({
      event: "image_done",
      data: '{"n":1,"total":3}',
    });
  });
});
