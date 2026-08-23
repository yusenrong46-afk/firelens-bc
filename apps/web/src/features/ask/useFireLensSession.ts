import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  askFireLens,
  type AskResponse,
  type ConversationTurn,
  FireLensApiError,
  type LocationInput,
  type LiveResult,
  type MapContext,
  type ResponseMode,
} from "../../shared/api/api";
import { useProvinceMap } from "../near-me/useProvinceMap";
import { looksLikeCommunityLabel, selectedResultIdForQuestion } from "./askContinuation";
import {
  getResponseMode,
  INITIAL_SUGGESTIONS,
  responseText,
  type Claim,
  type ViewState,
} from "./responseModel";
import { deriveSessionMapView, type MapAggregateFreshness } from "./sessionMap";

export type FireLensSession = {
  query: string;
  setQuery: (query: string) => void;
  selected: number;
  setSelected: (index: number) => void;
  view: ViewState;
  history: ConversationTurn[];
  earlierTurns: ConversationTurn[];
  locationLabel: string;
  setLocationLabel: (label: string) => void;
  locationMessage: string;
  requiresLocation: boolean;
  response: AskResponse | undefined;
  mode: ResponseMode | undefined;
  claims: Claim[];
  suggestions: string[];
  visibleQuestion: string | undefined;
  assistantText: string;
  mapResults: LiveResult[];
  mapMatchingResults: LiveResult[];
  mapProvinceResults: LiveResult[];
  mapLoading: boolean;
  mapMessage: string | undefined;
  mapAggregateFreshness: MapAggregateFreshness;
  mapUnavailableLayers: string[];
  mapFocus: { latitude: number; longitude: number } | undefined;
  mapFocusResults: LiveResult[];
  selectedLiveResultId: string | undefined;
  setSelectedLiveResultId: (resultId: string | undefined) => void;
  askAboutResult: (resultId: string, question: string) => void;
  submitQuestion: (question: string) => Promise<void>;
  clearHistory: () => void;
  useApproximateLocation: () => void;
  submitLocation: (event: FormEvent<HTMLFormElement>) => void;
  submit: (event: FormEvent<HTMLFormElement>) => void;
  clearManualLocation: () => void;
};

export function useFireLensSession(): FireLensSession {
  const provinceMap = useProvinceMap();
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(0);
  const [view, setView] = useState<ViewState>({ kind: "idle" });
  const [history, setHistory] = useState<ConversationTurn[]>([]);
  const [locationLabel, setLocationLabel] = useState("");
  const [locationMessage, setLocationMessage] = useState("");
  const [selectedLiveResultId, setSelectedLiveResultId] = useState<string>();
  const [loadingSeconds, setLoadingSeconds] = useState(0);
  const activeRequest = useRef<AbortController | null>(null);

  useEffect(() => {
    if (view.kind !== "loading") {
      setLoadingSeconds(0);
      return;
    }
    const started = Date.now();
    const timer = window.setInterval(
      () => setLoadingSeconds(Math.floor((Date.now() - started) / 1000)),
      1_000,
    );
    return () => window.clearInterval(timer);
  }, [view]);

  const response = view.kind === "answer" || view.kind === "abstention" ? view.response : undefined;
  const mode = response ? getResponseMode(response) : undefined;
  const claims = view.kind === "answer" ? (view.response.claims ?? []) : [];
  const currentPairIsStored =
    (view.kind === "answer" || view.kind === "abstention") &&
    history.length >= 2 &&
    history.at(-2)?.role === "user" &&
    history.at(-2)?.content === view.question;
  const earlierTurns = currentPairIsStored ? history.slice(0, -2) : history;
  const suggestions = response?.suggested_questions?.length
    ? response.suggested_questions.slice(0, 6)
    : view.kind === "idle"
      ? INITIAL_SUGGESTIONS
      : [];
  const mapView = useMemo(
    () =>
      deriveSessionMapView(
        response,
        provinceMap.data?.results,
        provinceMap.data?.unavailable_layers,
      ),
    [provinceMap.data?.results, provinceMap.data?.unavailable_layers, response],
  );
  const requiresLocation = response?.required_input?.kind === "location";

  useEffect(() => {
    if (view.kind !== "answer" && view.kind !== "abstention") return;
    setSelectedLiveResultId(view.response.selected_live_result_id ?? undefined);
  }, [view]);

  async function submitQuestionWithContext(
    question: string,
    locationOverride?: LocationInput,
    selectedResultOverride?: string,
  ) {
    const normalized = question.trim();
    if (!normalized) return;
    const requestHistory = history.slice(-6);
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    setSelected(0);
    setView({ kind: "loading", question: normalized });
    try {
      const context: MapContext = {
        visible_live_result_ids: mapView.mapResults.slice(0, 100).map((result) => result.result_id),
      };
      const contextSelected = selectedResultIdForQuestion(
        normalized,
        selectedLiveResultId,
        selectedResultOverride,
      );
      if (contextSelected) context.selected_live_result_id = contextSelected;
      const nextResponse = await askFireLens(
        normalized,
        requestHistory,
        locationOverride,
        controller.signal,
        context,
      );
      const nextHistory: ConversationTurn[] = [
        ...requestHistory,
        { role: "user", content: normalized },
        { role: "assistant", content: nextResponse.history_text ?? responseText(nextResponse) },
      ];
      setHistory(nextHistory.slice(-6));
      setView({
        kind: nextResponse.status === "answer" ? "answer" : "abstention",
        question: normalized,
        response: nextResponse,
      });
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      if (error instanceof FireLensApiError) {
        setView({
          kind: error.detail.retryable ? "unavailable" : "error",
          question: normalized,
          message: error.detail.message,
          retryable: error.detail.retryable,
        });
      } else {
        setView({
          kind: "error",
          question: normalized,
          message: "FireLens could not read the local service response.",
        });
      }
    } finally {
      if (activeRequest.current === controller) activeRequest.current = null;
    }
  }

  async function submitQuestion(question: string) {
    await submitQuestionWithContext(question);
  }

  function clearHistory() {
    activeRequest.current?.abort();
    activeRequest.current = null;
    setHistory([]);
    setSelected(0);
    setLocationLabel("");
    setLocationMessage("");
    setSelectedLiveResultId(undefined);
    setView({ kind: "idle" });
  }

  function useApproximateLocation() {
    if (!navigator.geolocation) {
      setLocationMessage("Location is not available in this browser.");
      return;
    }
    setLocationMessage("Requesting permission…");
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        const location: LocationInput = {
          latitude: Math.round(coords.latitude * 100) / 100,
          longitude: Math.round(coords.longitude * 100) / 100,
          radius_km: 50,
        };
        setLocationLabel("");
        setLocationMessage("Approximate location ready for this request.");
        const continuation = response?.required_input?.continuation_question;
        if (continuation) void submitQuestionWithContext(continuation, location);
      },
      () => setLocationMessage("Location was not shared. You can enter a BC community name instead."),
      { enableHighAccuracy: false, maximumAge: 300_000, timeout: 8_000 },
    );
  }

  function submitLocation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const continuation = response?.required_input?.continuation_question;
    const label = locationLabel.trim();
    if (!continuation || !label) return;
    const location: LocationInput = { label, radius_km: 50 };
    setLocationLabel("");
    void submitQuestionWithContext(continuation, location);
  }

  function askAboutResult(resultId: string, question: string) {
    setSelectedLiveResultId(resultId);
    void submitQuestionWithContext(question, undefined, resultId);
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const question = query.trim();
    setQuery("");
    if (!question) return;
    if (requiresLocation) {
      const continuation = response?.required_input?.continuation_question;
      if (continuation && looksLikeCommunityLabel(question)) {
        const location: LocationInput = { label: question, radius_km: 50 };
        void submitQuestionWithContext(continuation, location);
        return;
      }
    }
    void submitQuestion(question);
  }

  const visibleQuestion = "question" in view && view.question ? view.question : undefined;
  const assistantText =
    view.kind === "answer" || view.kind === "abstention"
      ? responseText(view.response)
      : view.kind === "loading"
        ? loadingSeconds >= 20
          ? "Official sources are responding slowly — FireLens is still working on this request…"
          : loadingSeconds >= 6
            ? "Fetching official records and composing a grounded answer — usually a few more seconds…"
            : "Checking official BC wildfire layers and reviewed guidance…"
        : view.kind === "unavailable" || view.kind === "error"
          ? (view.message ?? "FireLens is unavailable.")
          : provinceMap.loading
            ? "Loading official wildfire layers. You can ask anything while the map gets ready."
            : "Ask about a mapped fire, wildfire preparedness, or an everyday question. FireLens labels official sources, reviewed evidence, and general knowledge differently.";

  return {
    query,
    setQuery,
    selected,
    setSelected,
    view,
    history,
    earlierTurns,
    locationLabel,
    setLocationLabel,
    locationMessage,
    requiresLocation,
    response,
    mode,
    claims,
    suggestions,
    visibleQuestion,
    assistantText,
    mapResults: mapView.mapResults,
    mapMatchingResults: mapView.mapMatchingResults,
    mapProvinceResults: mapView.mapProvinceResults,
    mapLoading: provinceMap.loading,
    mapMessage: provinceMap.message,
    mapAggregateFreshness: mapView.mapAggregateFreshness,
    mapUnavailableLayers: mapView.mapUnavailableLayers,
    mapFocus: mapView.mapFocus,
    mapFocusResults: mapView.mapFocusResults,
    selectedLiveResultId,
    setSelectedLiveResultId,
    askAboutResult,
    submitQuestion,
    clearHistory,
    useApproximateLocation,
    submitLocation,
    submit,
    clearManualLocation: () => {
      setLocationMessage("");
    },
  };
}
