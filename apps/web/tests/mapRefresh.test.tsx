import { act, cleanup, render, renderHook, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useProvinceMap } from "../src/features/near-me/useProvinceMap";
import { deriveSessionMapView } from "../src/features/ask/sessionMap";
import { liveDataTone } from "../src/app/LiveDataStatus";
import type { LiveMapResponse, LiveResult } from "../src/shared/api/api";
import { MapRefreshStatus, mapSnapshotAge } from "../src/features/near-me/MapRefreshStatus";

const NOW = Date.parse("2026-09-16T00:00:00Z");
const record = (id: string, retrieved = NOW): LiveResult => ({ result_id: id, kind: "incident", authority: "BCWS", source_url: "https://example.test", source_updated_at: new Date(retrieved).toISOString(), retrieved_at: new Date(retrieved).toISOString(), freshness: "fresh", status: "Being Held", geometry: { type: "Point", coordinates: [-119, 49] }, geometry_relation: "unknown", fire_of_note: false });
const payload = (results: LiveResult[] = [record("incident:1")]): LiveMapResponse => ({ generated_at: new Date().toISOString(), results, unavailable_layers: [], partial_layers: [], limitations: [], layer_statuses: [{ kind: "incident", authority: "BCWS", source_url: "https://example.test", available: true, freshness: "fresh", retrieved_at: new Date().toISOString(), source_updated_at: new Date().toISOString(), matching_result_count: results.length, omitted_geometry_count: 0, omitted_status_count: 0 }] });
const ok = (data = payload()) => new Response(JSON.stringify(data), { headers: { "content-type": "application/json" } });
async function settle() { await act(async () => { await vi.advanceTimersByTimeAsync(0); }); }
async function advance(ms: number) { await act(async () => { await vi.advanceTimersByTimeAsync(ms); }); }
async function visibility(value: "hidden" | "visible") { await act(async () => { Object.defineProperty(document, "visibilityState", { configurable: true, value }); document.dispatchEvent(new Event("visibilitychange")); }); await settle(); }

beforeEach(() => { vi.useFakeTimers(); vi.setSystemTime(NOW); Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" }); });
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe("map refresh ownership", () => {
  it("refreshes after five minutes without dropping the first snapshot", async () => {
    const fetch = vi.fn().mockImplementation(() => Promise.resolve(ok())); vi.stubGlobal("fetch", fetch);
    const { result } = renderHook(() => useProvinceMap(true)); await settle();
    expect(result.current.data?.results).toHaveLength(1);
    await advance(299_999); expect(fetch).toHaveBeenCalledTimes(1);
    await advance(1); expect(fetch).toHaveBeenCalledTimes(2);
  });
  it("pauses while hidden and refreshes once on an overdue return", async () => {
    const fetch = vi.fn().mockImplementation(() => Promise.resolve(ok())); vi.stubGlobal("fetch", fetch);
    renderHook(() => useProvinceMap(true)); await settle(); await visibility("hidden");
    await advance(900_000); expect(fetch).toHaveBeenCalledTimes(1);
    await visibility("visible"); expect(fetch).toHaveBeenCalledTimes(2);
    await visibility("visible"); expect(fetch).toHaveBeenCalledTimes(2);
  });
  it("waits until due after a short visibility pause and a disabled interval", async () => {
    const fetch = vi.fn().mockImplementation(() => Promise.resolve(ok())); vi.stubGlobal("fetch", fetch);
    const { rerender } = renderHook(({ enabled }) => useProvinceMap(enabled), { initialProps: { enabled: true } }); await settle();
    await advance(30_000); await visibility("hidden"); await advance(30_000); await visibility("visible"); expect(fetch).toHaveBeenCalledTimes(1);
    rerender({ enabled: false }); await advance(300_000); expect(fetch).toHaveBeenCalledTimes(1);
    rerender({ enabled: true }); await settle(); expect(fetch).toHaveBeenCalledTimes(2);
  });
  it("coalesces pending manual and visibility refreshes and retains data while refreshing", async () => {
    let resolve!: (response: Response) => void;
    const fetch = vi.fn().mockResolvedValueOnce(ok()).mockImplementation(() => new Promise<Response>((done) => { resolve = done; })); vi.stubGlobal("fetch", fetch);
    const { result } = renderHook(() => useProvinceMap(true)); await settle(); const first = result.current.data;
    act(() => { result.current.refresh(); result.current.refresh(); }); await visibility("visible");
    expect(fetch).toHaveBeenCalledTimes(2); expect(result.current.loading).toBe(true); expect(result.current.data).toBe(first);
    await act(async () => resolve(ok(payload([record("incident:2")])))); await settle();
    expect(result.current.data?.results[0]?.result_id).toBe("incident:2");
  });
  it("retries at 30, 60, 120 and 300 seconds, retaining the last success until recovery", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(ok()).mockImplementation(() => Promise.reject(new TypeError("offline"))); vi.stubGlobal("fetch", fetch);
    const { result } = renderHook(() => useProvinceMap(true)); await settle(); const first = result.current.data;
    act(() => result.current.refresh()); await settle();
    expect(result.current.message).toBeTruthy(); expect(result.current.data).toBe(first);
    for (const delay of [30_000, 60_000, 120_000, 300_000]) {
      const attempts = fetch.mock.calls.length; await advance(delay - 1); expect(fetch).toHaveBeenCalledTimes(attempts);
      await advance(1); expect(fetch).toHaveBeenCalledTimes(attempts + 1);
    }
    fetch.mockImplementation(() => Promise.resolve(ok(payload([])))); act(() => result.current.refresh()); await settle();
    expect(result.current.message).toBeUndefined(); expect(result.current.data?.results).toEqual([]);
    const recovered = fetch.mock.calls.length; await advance(299_999); expect(fetch).toHaveBeenCalledTimes(recovered); await advance(1); expect(fetch).toHaveBeenCalledTimes(recovered + 1);
    expect(fetch.mock.calls.every(([url]) => String(url).startsWith("/api/v1/live/map?"))).toBe(true);
  });
  it("aborts on hide and rejects late responses from a transport that ignores abort", async () => {
    const resolve: ((response: Response) => void)[] = [];
    const fetch = vi.fn().mockImplementation(() => new Promise<Response>((done) => resolve.push(done))); vi.stubGlobal("fetch", fetch);
    const { result, unmount } = renderHook(() => useProvinceMap(true)); await settle();
    const firstSignal = fetch.mock.calls[0]![1].signal as AbortSignal;
    await visibility("hidden"); expect(firstSignal.aborted).toBe(true); await visibility("visible");
    await act(async () => resolve[1]!(ok(payload([record("incident:new")])))); await settle();
    await act(async () => resolve[0]!(ok(payload([record("incident:old")])))); await settle();
    expect(result.current.data?.results[0]?.result_id).toBe("incident:new");
    act(() => result.current.refresh()); const lastSignal = fetch.mock.calls.at(-1)![1].signal as AbortSignal;
    unmount(); expect(lastSignal.aborted).toBe(true); await advance(900_000); expect(fetch).toHaveBeenCalledTimes(3);
  });
});

describe("map observations", () => {
  it("uses a newer map observation without mutating the answer roster", () => {
    const answer = record("incident:1", NOW - 300_000); const fresh = record("incident:1", NOW);
    const roster = { results: [answer], focus: undefined, unavailableLayers: [] };
    const view = deriveSessionMapView(roster, [fresh], [], true);
    expect(view.mapResults[0]).toBe(fresh); expect(roster.results[0]).toBe(answer);
  });
  it("shows stale freshness for an available zero-result layer", () => {
    const data = payload([]); data.layer_statuses![0]!.freshness = "stale";
    expect(deriveSessionMapView(undefined, [], [], true, data.layer_statuses).mapAggregateFreshness).toBe("stale");
  });
  it("keeps answer observations on equal or invalid map timestamps", () => {
    const answer = record("incident:1"); const roster = { results: [answer], focus: undefined, unavailableLayers: [] };
    expect(deriveSessionMapView(roster, [{ ...answer, name: "Changed" }], [], true).mapResults[0]).toBe(answer);
    expect(deriveSessionMapView(roster, [{ ...answer, retrieved_at: "unknown" }], [], true).mapResults[0]).toBe(answer);
  });
  it("excludes absent answer snapshots from current counts, preserving answer order", () => {
    const first = record("incident:1"); const second = record("incident:2"); const roster = { results: [second, first], focus: undefined, unavailableLayers: [] };
    const statuses = payload().layer_statuses!; statuses[0]!.retrieved_at = new Date(NOW + 1000).toISOString();
    const view = deriveSessionMapView(roster, [record("incident:1", NOW + 1000), record("incident:3")], [], true, statuses);
    expect(view.mapResults.map((r) => r.result_id)).toEqual(["incident:1", "incident:3"]);
    expect(view.mapHistoricalResults).toEqual([second]); expect(roster.results).toEqual([second, first]);
  });
  it.each(["older", "equal", "missing", "unavailable", "partial geometry", "partial status", "stale"])("keeps absent answer records when map observation is %s", (condition) => {
    const answer = record("incident:1"); const statuses = payload([]).layer_statuses!;
    statuses[0]!.retrieved_at = new Date(NOW + 1000).toISOString();
    if (condition === "older") statuses[0]!.retrieved_at = new Date(NOW - 1000).toISOString();
    if (condition === "equal") statuses[0]!.retrieved_at = new Date(NOW).toISOString();
    if (condition === "missing") statuses[0]!.retrieved_at = null;
    if (condition === "unavailable") statuses[0]!.available = false;
    if (condition === "partial geometry") statuses[0]!.omitted_geometry_count = 1;
    if (condition === "partial status") statuses[0]!.omitted_status_count = 1;
    if (condition === "stale") statuses[0]!.freshness = "stale";
    const view = deriveSessionMapView({ results: [answer], focus: undefined, unavailableLayers: [] }, [], [], true, statuses);
    expect(view.mapResults).toEqual([answer]); expect(view.mapHistoricalResults).toEqual([]);
  });
  it("uses the oldest layer retrieval and exposes source clock limitations without inventing failure", () => {
    const data = payload([]); data.layer_statuses![0]!.retrieved_at = new Date(NOW - 600_000).toISOString();
    const status = { now: NOW, checkedAt: NOW, refreshing: false, statuses: data.layer_statuses, generatedAt: data.generated_at, limitations: ["An official source timestamp was later than retrieval and is not treated as current."], onRefresh: vi.fn() };
    expect(mapSnapshotAge(status, []).overdue).toBe(true);
    render(<MapRefreshStatus status={status} results={[]} />);
    expect(screen.getByText(/snapshot is due for refresh/)).toBeVisible();
    expect(screen.getByText(/source timestamp was later/)).toBeVisible();
    expect(screen.queryByText(/Refresh failed/)).not.toBeInTheDocument();
    expect(screen.getByText(/Oldest retrieval/)).toHaveTextContent(/Sep 15/);
  });
  it("does not label working official feeds unavailable when AI is disabled", () => {
    expect(liveDataTone({ incident_record_count: 1, evacuation_record_count: 0, source_status: "fresh", freshness: "fresh", retrieved_at: new Date(NOW).toISOString(), limitation: "Returned records only" }, "not_ready")).toBe("live");
  });
  it.each(["partial", "unavailable"])("ages retained answer records independently of a newer %s layer", (condition) => {
    const retained = record("incident:old", NOW - 900_000);
    const statuses = payload([]).layer_statuses!;
    if (condition === "partial") statuses[0]!.omitted_geometry_count = 1;
    else { statuses[0]!.available = false; statuses[0]!.retrieved_at = null; }
    const status = { now: NOW, checkedAt: NOW, refreshing: false, statuses, onRefresh: vi.fn() };
    expect(mapSnapshotAge(status, [retained])).toMatchObject({ oldest: NOW - 900_000, overdue: true });
    render(<MapRefreshStatus status={status} results={[retained]} />);
    expect(screen.getByText(/snapshot is due for refresh/)).toBeVisible();
  });
  it("keeps unknown record times visible despite known layer times", () => {
    const status = { now: NOW, checkedAt: NOW, refreshing: false, statuses: payload().layer_statuses, onRefresh: vi.fn() };
    expect(mapSnapshotAge(status, [{ ...record("incident:unknown"), retrieved_at: "unknown" }]).unknown).toBe(true);
  });
  it("retains answer coverage warnings until a strictly newer complete layer observation", () => {
    const statuses = payload([]).layer_statuses!;
    const answer = { results: [], focus: undefined, unavailableLayers: ["incident"], partialLayers: ["incident"], observedAt: new Date(NOW).toISOString() };
    expect(deriveSessionMapView(answer, [], [], true, statuses).mapUnavailableLayers).toEqual(["incident"]);
    expect(deriveSessionMapView(answer, [], [], true, statuses).mapPartialLayers).toEqual(["incident"]);
    statuses[0]!.retrieved_at = new Date(NOW + 300_000).toISOString();
    expect(deriveSessionMapView(answer, [], [], true, statuses).mapUnavailableLayers).toEqual([]);
    expect(deriveSessionMapView(answer, [], [], true, statuses).mapPartialLayers).toEqual([]);
  });
  it.each(["older", "missing", "partial geometry", "partial status", "unavailable", "stale"])("does not clear answer coverage using a %s layer observation", (condition) => {
    const statuses = payload([]).layer_statuses!;
    statuses[0]!.retrieved_at = new Date(NOW + 300_000).toISOString();
    if (condition === "older") statuses[0]!.retrieved_at = new Date(NOW - 1000).toISOString();
    if (condition === "missing") statuses[0]!.retrieved_at = null;
    if (condition === "partial geometry") statuses[0]!.omitted_geometry_count = 1;
    if (condition === "partial status") statuses[0]!.omitted_status_count = 1;
    if (condition === "unavailable") statuses[0]!.available = false;
    if (condition === "stale") statuses[0]!.freshness = "stale";
    const answer = { results: [], focus: undefined, unavailableLayers: ["incident"], partialLayers: ["incident"], observedAt: new Date(NOW).toISOString() };
    const view = deriveSessionMapView(answer, [], [], true, statuses);
    expect(view.mapUnavailableLayers).toEqual(["incident"]); expect(view.mapPartialLayers).toEqual(["incident"]);
  });
  it("labels an answer snapshot and keeps source times without offering a no-op refresh", () => {
    const status = { mode: "answer" as const, now: NOW, refreshing: false, onRefresh: vi.fn() };
    render(<MapRefreshStatus status={status} results={[record("incident:1")]} />);
    expect(screen.getByText("Answer snapshot")).toBeVisible();
    expect(screen.queryByRole("button", { name: /Refresh map|Retry map/ })).not.toBeInTheDocument();
    expect(screen.getByText(/fresh at retrieval/)).toBeInTheDocument();
    expect(screen.queryByText(/Response generated/)).not.toBeInTheDocument();
  });
  it("does not replace an unknown layer retrieval with a known displayed-record time", () => {
    const statuses = payload([]).layer_statuses!; statuses[0]!.retrieved_at = null;
    expect(mapSnapshotAge({ now: NOW, refreshing: false, statuses }, [record("incident:1")])).toMatchObject({ unknown: true, oldest: NOW });
  });
});
