import { act, renderHook } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { useFireLensSession } from "../src/features/ask/useFireLensSession";
import { askFireLens, type AskResponse } from "../src/shared/api/api";

vi.mock("../src/shared/api/api", async (original) => ({
  ...await original<object>(),
  askFireLens: vi.fn(),
  fetchReadyHealth: vi.fn(() => new Promise(() => {})),
  fetchLiveSummary: vi.fn(() => new Promise(() => {})),
}));
vi.mock("../src/features/near-me/useProvinceMap", () => ({
  useProvinceMap: () => ({ data: undefined, loading: false }),
}));
afterEach(() => { vi.clearAllMocks(); vi.unstubAllGlobals(); });
const response = { status: "answer", response_mode: "background", trace_id: "test", answer: "Old answer", claims: [], evidence: [], limitations: [], live_results: [] } as unknown as AskResponse;

test("Home resets the private draft and optional map layers", () => {
  const { result } = renderHook(() => useFireLensSession());
  act(() => { result.current.setQuery("private draft"); result.current.setContextLayersEnabled(true); });
  act(() => result.current.clearHistory());
  expect(result.current.query).toBe("");
  expect(result.current.contextLayersEnabled).toBe(false);
});

test.each(["resolve", "reject"])("late %s after Home cannot replace idle state, even if transport ignores abort", async (outcome) => {
  let resolve!: (value: AskResponse) => void;
  let reject!: (error: Error) => void;
  vi.mocked(askFireLens).mockImplementation(() => new Promise((yes, no) => { resolve = yes; reject = no; }));
  const { result } = renderHook(() => useFireLensSession());
  let pending!: Promise<void>;
  act(() => { pending = result.current.submitQuestion("old question"); });
  act(() => result.current.clearHistory());
  await act(async () => { if (outcome === "resolve") resolve(response); else reject(new Error("late failure")); await pending; });
  expect(result.current.view.kind).toBe("idle");
  expect(result.current.history).toEqual([]);
});

test("a superseded response cannot replace the newer answer", async () => {
  let finishOld!: (value: AskResponse) => void;
  vi.mocked(askFireLens).mockImplementationOnce(() => new Promise((resolve) => { finishOld = resolve; }))
    .mockResolvedValueOnce({ ...response, answer: "New answer" });
  const { result } = renderHook(() => useFireLensSession());
  let old!: Promise<void>;
  act(() => { old = result.current.submitQuestion("old question"); });
  await act(() => result.current.submitQuestion("new question"));
  await act(async () => { finishOld(response); await old; });
  expect(result.current.assistantText).toBe("New answer");
  expect(result.current.visibleQuestion).toBe("new question");
});

test.each(["home", "new-question", "unmount"])("pending geolocation is invalidated by %s", async (action) => {
  let success!: PositionCallback;
  let failure!: PositionErrorCallback;
  vi.stubGlobal("navigator", { geolocation: { getCurrentPosition: (yes: PositionCallback, no: PositionErrorCallback) => { success = yes; failure = no; } } });
  vi.mocked(askFireLens).mockResolvedValue(response);
  const { result, unmount } = renderHook(() => useFireLensSession());
  act(() => result.current.useApproximateLocation());
  if (action === "home") act(() => result.current.clearHistory());
  if (action === "unmount") unmount();
  if (action === "new-question") await act(() => result.current.submitQuestion("new question"));
  const calls = vi.mocked(askFireLens).mock.calls.length;
  await act(async () => { success({ coords: { latitude: 49.899, longitude: -119.499 } } as GeolocationPosition); failure({} as GeolocationPositionError); });
  expect(askFireLens).toHaveBeenCalledTimes(calls);
  if (action !== "unmount") expect(result.current.activeLocation).toBeUndefined();
});
