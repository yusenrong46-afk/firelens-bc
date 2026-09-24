import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { useFireLensSession } from "../src/features/ask/useFireLensSession";
import { askFireLens, type AskResponse, type LiveMapResponse, type LiveResult } from "../src/shared/api/api";

const state = vi.hoisted(() => ({ data: undefined as LiveMapResponse | undefined }));
vi.mock("../src/features/near-me/useProvinceMap", () => ({ useProvinceMap: () => ({ data: state.data, loading: false, refresh: vi.fn() }) }));
vi.mock("../src/shared/api/api", async (original) => ({ ...await original<object>(), askFireLens: vi.fn(), fetchReadyHealth: vi.fn(() => new Promise(() => {})), fetchLiveSummary: vi.fn(() => new Promise(() => {})) }));
afterEach(() => { cleanup(); vi.clearAllMocks(); state.data = undefined; });
const record = { result_id: "incident:1", kind: "incident", authority: "BCWS", source_url: "https://example.test", source_updated_at: "2026-09-16T00:00:00Z", retrieved_at: "2026-09-16T00:00:00Z", freshness: "fresh", status: "Being Held", geometry: { type: "Point", coordinates: [-119, 49] }, geometry_relation: "unknown", fire_of_note: false } as LiveResult;
const data = (results: LiveResult[]): LiveMapResponse => ({ generated_at: "2026-09-16T00:05:00Z", results, layer_statuses: [{ kind: "incident", authority: "BCWS", source_url: "https://example.test", available: true, freshness: "fresh", retrieved_at: "2026-09-16T00:05:00Z", source_updated_at: "2026-09-16T00:05:00Z", omitted_geometry_count: 0, omitted_status_count: 0, matching_result_count: results.length }], unavailable_layers: [], partial_layers: [], limitations: [] });

it("announces removal of a selected province record without silently selecting another", () => {
  state.data = data([record]); const { result, rerender } = renderHook(() => useFireLensSession());
  act(() => result.current.setSelectedLiveResultId(record.result_id));
  state.data = data([{ ...record, result_id: "incident:2" }]); rerender();
  expect(result.current.selectedLiveResultId).toBeUndefined();
  expect(result.current.mapSnapshotStatus?.selectionMessage).toMatch(/absent from the latest map/);
});

it("preserves answer, history, roster order and selected historical context through map refresh", async () => {
  const response = { status: "answer", response_mode: "live", trace_id: "original-answer", answer: "Original official answer", claims: [], evidence: [], limitations: [], requested_layers: ["incident"], live_results: [record] } as unknown as AskResponse;
  vi.mocked(askFireLens).mockResolvedValue(response); state.data = data([record]);
  const { result, rerender } = renderHook(() => useFireLensSession());
  act(() => result.current.setContextLayersEnabled(true)); await act(() => result.current.submitQuestion("Nearby records"));
  act(() => result.current.setSelectedLiveResultId(record.result_id)); const history = result.current.history;
  state.data = data([]); rerender();
  expect(result.current.selectedLiveResultId).toBe(record.result_id);
  expect(result.current.mapResults).toEqual([]); expect(result.current.mapHistoricalResults).toEqual([record]);
  expect(result.current.response).toBe(response); expect(result.current.history).toBe(history);
  expect(askFireLens).toHaveBeenCalledTimes(1);
});

it("presents an immutable answer snapshot when province context is off", async () => {
  const response = { status: "answer", response_mode: "live", trace_id: "answer-only", answer: "Official answer", claims: [], evidence: [], limitations: ["Answer coverage limit"], requested_layers: ["incident"], live_results: [record] } as unknown as AskResponse;
  vi.mocked(askFireLens).mockResolvedValue(response); state.data = { ...data([record]), limitations: ["Province coverage limit"] };
  const { result } = renderHook(() => useFireLensSession()); await act(() => result.current.submitQuestion("Nearby records"));
  const status = result.current.mapSnapshotStatus;
  expect(status).toMatchObject({ mode: "answer", refreshing: false, limitations: ["Answer coverage limit"] });
  expect(status?.onRefresh).toBeUndefined(); expect(status?.statuses).toBeUndefined();
  expect(status?.generatedAt).toBeUndefined(); expect(result.current.mapMessage).toBeUndefined();
});
