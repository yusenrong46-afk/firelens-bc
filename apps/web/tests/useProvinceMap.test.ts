import { cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useProvinceMap } from "../src/features/near-me/useProvinceMap";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("province map request failures", () => {
  it.each([
    { message: "Official upstream unavailable", expected: "Official upstream unavailable" },
    { error: "Proxy unavailable", expected: "Official wildfire layers could not be loaded." },
    { message: "", expected: "Official wildfire layers could not be loaded." },
  ])("settles with a visible error rather than indefinite loading: $expected", async ({ expected, ...body }) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(body), {
      status: 503, headers: { "Content-Type": "application/json" },
    })));
    const { result } = renderHook(() => useProvinceMap(true));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.message).toBe(expected);
    expect(result.current.data).toBeUndefined();
  });
});
