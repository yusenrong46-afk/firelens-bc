import { useEffect, useState } from "react";
import {
  fetchOfficialMap,
  FireLensApiError,
  type LiveMapResponse,
} from "../../shared/api/api";

type ProvinceMapState = {
  data?: LiveMapResponse;
  loading: boolean;
  message?: string;
};

export function useProvinceMap(enabled: boolean): ProvinceMapState {
  const [state, setState] = useState<ProvinceMapState>({ loading: false });

  useEffect(() => {
    if (!enabled) {
      setState((current) => current.loading ? { ...current, loading: false } : current);
      return;
    }
    if (state.data) return;

    const controller = new AbortController();
    setState({ loading: true });
    void fetchOfficialMap(controller.signal)
      .then((data) => setState({ data, loading: false }))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setState({
          loading: false,
          message:
            error instanceof FireLensApiError
              ? error.detail.message
              : "Official wildfire layers could not be loaded.",
        });
      });
    return () => controller.abort();
  }, [enabled, state.data]);

  return state;
}
