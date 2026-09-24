import { useCallback, useEffect, useRef, useState } from "react";
import { fetchOfficialMap, FireLensApiError, type LiveMapResponse } from "../../shared/api/api";

export const MAP_REFRESH_MS = 300_000;
const RETRY_MS = [30_000, 60_000, 120_000, MAP_REFRESH_MS];

export type ProvinceMapState = {
  data?: LiveMapResponse;
  loading: boolean;
  message?: string | undefined;
  checkedAt?: number | undefined;
  refresh: () => void;
};

/** One request owner for visible-map polling, manual retry and visibility resume. */
export function useProvinceMap(enabled: boolean, navigationEpoch = 0): ProvinceMapState {
  const [state, setState] = useState<Omit<ProvinceMapState, "refresh">>({ loading: false });
  const invoke = useRef<() => void>(() => {});
  const generation = useRef(0);
  const dueAt = useRef(0);
  const failures = useRef(0);
  const refresh = useCallback(() => invoke.current(), []);

  // A new question or Home/reset may keep the map enabled. Reuse the same
  // cleanup/generation guard so its pending response cannot cross that boundary.
  useEffect(() => {
    if (!enabled) return;
    let controller: AbortController | undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let disposed = false;
    const visible = () => !disposed && document.visibilityState !== "hidden";
    const schedule = () => {
      clearTimeout(timer);
      if (visible()) timer = setTimeout(request, Math.max(0, dueAt.current - Date.now()));
    };
    function request() {
      if (!visible() || controller) return;
      clearTimeout(timer);
      const current = new AbortController();
      controller = current;
      const token = ++generation.current;
      setState((previous) => ({ ...previous, loading: true }));
      void fetchOfficialMap(current.signal).then((data) => {
        if (disposed || current.signal.aborted || token !== generation.current) return;
        failures.current = 0;
        dueAt.current = Date.now() + MAP_REFRESH_MS;
        setState({ data, loading: false, checkedAt: Date.now() });
      }).catch((error: unknown) => {
        if (disposed || current.signal.aborted || token !== generation.current) return;
        dueAt.current = Date.now() + RETRY_MS[Math.min(failures.current++, RETRY_MS.length - 1)]!;
        setState((previous) => ({
          ...previous,
          loading: false,
          message: error instanceof FireLensApiError && typeof error.detail.message === "string" && error.detail.message.trim()
            ? error.detail.message : "Official wildfire layers could not be loaded.",
        }));
      }).finally(() => {
        if (disposed || token !== generation.current) return;
        controller = undefined;
        schedule();
      });
    }
    const pause = () => {
      clearTimeout(timer);
      if (controller) {
        ++generation.current;
        controller.abort();
        controller = undefined;
        dueAt.current = 0;
        setState((previous) => ({ ...previous, loading: false }));
      }
    };
    const visibilityChanged = () => {
      if (!visible()) pause();
      else if (dueAt.current <= Date.now()) request();
      else schedule();
    };
    invoke.current = request;
    visibilityChanged();
    document.addEventListener("visibilitychange", visibilityChanged);
    return () => {
      disposed = true;
      pause();
      invoke.current = () => {};
      document.removeEventListener("visibilitychange", visibilityChanged);
    };
  }, [enabled, navigationEpoch]);
  return { ...state, refresh };
}
