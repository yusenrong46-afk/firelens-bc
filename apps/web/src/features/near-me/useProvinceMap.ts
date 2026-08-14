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

export function useProvinceMap(): ProvinceMapState {
  const [state, setState] = useState<ProvinceMapState>({ loading: true });

  useEffect(() => {
    const controller = new AbortController();
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
  }, []);

  return state;
}
