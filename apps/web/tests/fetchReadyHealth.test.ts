import { describe, expect, it, vi } from "vitest";
import { fetchReadyHealth, FireLensApiError } from "../src/shared/api/api";

describe("fetchReadyHealth", () => {
  it("treats a 503 body with release_version as unavailable, not ready", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            status: "not_ready",
            release_version: "1.6.4",
            problems: ["provider_unavailable"],
          }),
          { status: 503, headers: { "content-type": "application/json" } },
        ),
      ),
    );
    await expect(fetchReadyHealth()).rejects.toBeInstanceOf(FireLensApiError);
    vi.unstubAllGlobals();
  });

  it("returns the payload when the readiness response is 200", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            status: "ready",
            release_version: "1.6.4",
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      ),
    );
    await expect(fetchReadyHealth()).resolves.toMatchObject({
      status: "ready",
      release_version: "1.6.4",
    });
    vi.unstubAllGlobals();
  });
});
