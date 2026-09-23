import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useFireLensSession } from "../src/features/ask/useFireLensSession";
import { askFireLens, fetchOfficialMap, type AskResponse, type LiveMapResponse, type LiveResult } from "../src/shared/api/api";

vi.mock("../src/shared/api/api", async original => ({
  ...await original<object>(), askFireLens: vi.fn(), fetchOfficialMap: vi.fn(),
  fetchReadyHealth: vi.fn(() => new Promise(() => {})), fetchLiveSummary: vi.fn(() => new Promise(() => {})),
}));
const NOW = Date.parse("2026-09-16T00:00:00Z");
const record = (id: string): LiveResult => ({ result_id: id, kind: "incident", authority: "BCWS", source_url: "https://example.test", source_updated_at: new Date(NOW).toISOString(), retrieved_at: new Date(NOW).toISOString(), freshness: "fresh", status: "Being Held", geometry: { type: "Point", coordinates: [-119, 49] }, geometry_relation: "unknown", fire_of_note: false });
const snapshot = (id: string): LiveMapResponse => ({ generated_at: new Date(NOW).toISOString(), results: [record(id)], unavailable_layers: [], partial_layers: [], limitations: [] });
const pending = () => { let resolve!: (value: LiveMapResponse) => void; const promise = new Promise<LiveMapResponse>(done => { resolve = done; }); return { promise, resolve }; };
const settle = async () => { await act(async () => {}); };
beforeEach(() => { vi.useFakeTimers(); vi.setSystemTime(NOW); Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" }); });
afterEach(() => { cleanup(); vi.useRealTimers(); vi.resetAllMocks(); });

it("Home reset rejects a late initial map response while map enabled remains true", async () => {
  const old = pending(); const replacement = pending();
  vi.mocked(fetchOfficialMap).mockReturnValueOnce(old.promise).mockReturnValueOnce(replacement.promise);
  const { result } = renderHook(() => useFireLensSession());
  act(() => result.current.setMapVisible(true)); await settle();
  act(() => result.current.clearHistory());
  await act(async () => old.resolve(snapshot("incident:old-request")));
  expect(result.current.mapResults).toEqual([]);
  expect(vi.mocked(fetchOfficialMap).mock.calls[0]![0]!.aborted).toBe(true);
  expect(fetchOfficialMap).toHaveBeenCalledTimes(2);
  expect(result.current.view.kind).toBe("idle");
});

it("reset retains the last success, coalesces replacement requests and rejects old completion", async () => {
  const first = snapshot("incident:retained"); const old = pending(); const replacement = pending();
  vi.mocked(fetchOfficialMap).mockResolvedValueOnce(first).mockReturnValueOnce(old.promise).mockReturnValueOnce(replacement.promise);
  const { result } = renderHook(() => useFireLensSession());
  act(() => result.current.setMapVisible(true)); await settle();
  act(() => result.current.mapSnapshotStatus!.onRefresh!());
  act(() => result.current.clearHistory());
  expect(result.current.mapResults).toEqual(first.results);
  act(() => { result.current.mapSnapshotStatus!.onRefresh!(); result.current.mapSnapshotStatus!.onRefresh!(); });
  expect(fetchOfficialMap).toHaveBeenCalledTimes(3);
  await act(async () => replacement.resolve(snapshot("incident:after-reset")));
  await act(async () => old.resolve(snapshot("incident:late-before-reset")));
  expect(result.current.mapResults.map(item => item.result_id)).toEqual(["incident:after-reset"]);
  expect(first.results[0]!.result_id).toBe("incident:retained");
});

it("a new question rejects a pending prior map request while province context remains enabled", async () => {
  const first = snapshot("incident:retained"); const old = pending(); const replacement = pending();
  vi.mocked(fetchOfficialMap).mockResolvedValueOnce(first).mockReturnValueOnce(old.promise).mockReturnValueOnce(replacement.promise);
  vi.mocked(askFireLens).mockResolvedValue({ status: "answer", response_mode: "general_knowledge", answer: "Fixture answer", claims: [], evidence: [], live_results: [], limitations: [] } as unknown as AskResponse);
  const { result } = renderHook(() => useFireLensSession());
  act(() => { result.current.setMapVisible(true); result.current.setContextLayersEnabled(true); }); await settle();
  act(() => result.current.mapSnapshotStatus!.onRefresh!());
  await act(() => result.current.submitQuestion("New conversation scope"));
  await act(async () => old.resolve(snapshot("incident:late-prior-question")));
  expect(result.current.mapResults).toEqual(first.results);
  expect(vi.mocked(fetchOfficialMap).mock.calls[1]![0]!.aborted).toBe(true);
  expect(fetchOfficialMap).toHaveBeenCalledTimes(3);
  await act(async () => replacement.resolve(snapshot("incident:current-question")));
  expect(result.current.mapResults.map(item => item.result_id)).toEqual(["incident:current-question"]);
  expect(askFireLens).toHaveBeenCalledTimes(1);
});

it("reset keeps an already successful snapshot and its existing refresh schedule", async () => {
  vi.mocked(fetchOfficialMap).mockResolvedValue(snapshot("incident:retained"));
  const { result } = renderHook(() => useFireLensSession());
  act(() => result.current.setMapVisible(true)); await settle();
  act(() => result.current.clearHistory()); await settle();
  expect(fetchOfficialMap).toHaveBeenCalledTimes(1);
  expect(result.current.mapResults[0]!.result_id).toBe("incident:retained");
  await act(async () => { await vi.advanceTimersByTimeAsync(300_000); });
  expect(fetchOfficialMap).toHaveBeenCalledTimes(2);
});
