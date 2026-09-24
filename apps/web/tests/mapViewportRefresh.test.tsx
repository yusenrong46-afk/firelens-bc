import { cleanup, render } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { FitResults } from "../src/features/near-me/MapViewport";
import type { LiveResult } from "../src/shared/api/api";

const map = vi.hoisted(() => ({ fitBounds: vi.fn(), setView: vi.fn(), invalidateSize: vi.fn(), getContainer: vi.fn() }));
vi.mock("react-leaflet", () => ({ useMap: () => map }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });
const record = { result_id: "incident:1", kind: "incident", authority: "BCWS", source_url: "https://example.test", source_updated_at: "2026-09-16T00:00:00Z", retrieved_at: "2026-09-16T00:00:00Z", freshness: "fresh", status: "Being Held", geometry: { type: "Point", coordinates: [-119, 49] }, geometry_relation: "unknown", fire_of_note: false } as LiveResult;

it("fits initial records and explicit selection or scope, retaining viewport through refresh and selection removal", () => {
  const { rerender } = render(<FitResults results={[]} focusResults={[]} scopeKey="province" />);
  expect(map.fitBounds).toHaveBeenCalledTimes(1);
  rerender(<FitResults results={[record]} focusResults={[]} scopeKey="province" />);
  expect(map.fitBounds).toHaveBeenCalledTimes(2);
  const updated = { ...record, retrieved_at: "2026-09-16T00:05:00Z", geometry: { type: "Point", coordinates: [-118, 49] } };
  rerender(<FitResults results={[updated, { ...record, result_id: "incident:2" }]} focusResults={[]} scopeKey="province" />);
  expect(map.fitBounds).toHaveBeenCalledTimes(2);
  rerender(<FitResults results={[updated]} focusResults={[]} scopeKey="province" selectedResultId="incident:1" />);
  expect(map.fitBounds).toHaveBeenCalledTimes(3);
  rerender(<FitResults results={[]} focusResults={[]} scopeKey="province" />);
  expect(map.fitBounds).toHaveBeenCalledTimes(3);
  rerender(<FitResults results={[updated]} focusResults={[updated]} scopeKey="new-question" focus={{ latitude: 49, longitude: -119 }} />);
  expect(map.fitBounds).toHaveBeenCalledTimes(4);
});

it("retains the viewport on unchanged hide and return", () => {
  const result = render(<FitResults results={[record]} focusResults={[record]} scopeKey="answer" />);
  map.fitBounds.mockClear();
  result.rerender(<FitResults active={false} results={[record]} focusResults={[record]} scopeKey="answer" />);
  result.rerender(<FitResults active results={[record]} focusResults={[record]} scopeKey="answer" />);
  expect(map.fitBounds).not.toHaveBeenCalled();
});

it("applies a pending location once when the hidden map returns", () => {
  const result = render(<FitResults results={[]} focusResults={[]} scopeKey="province" />);
  const focus = { latitude: 53.91, longitude: -122.75 };
  result.rerender(<FitResults active={false} results={[]} focusResults={[]} scopeKey="PG" focus={focus} />);
  expect(map.setView).not.toHaveBeenCalled();
  result.rerender(<FitResults active results={[]} focusResults={[]} scopeKey="PG" focus={focus} />);
  expect(map.setView).toHaveBeenCalledExactlyOnceWith([53.91, -122.75], 10, { animate: false });
});

it("applies pending record selection on return without fitting while hidden", () => {
  const result = render(<FitResults results={[record]} focusResults={[]} scopeKey="province" />);
  map.fitBounds.mockClear();
  result.rerender(<FitResults active={false} results={[record]} focusResults={[]} scopeKey="province" selectedResultId={record.result_id} />);
  expect(map.fitBounds).not.toHaveBeenCalled();
  result.rerender(<FitResults active results={[record]} focusResults={[]} scopeKey="province" selectedResultId={record.result_id} />);
  expect(map.fitBounds).toHaveBeenCalledExactlyOnceWith([[49, -119]], { padding: [40, 40], maxZoom: 12, animate: false });
});
