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
import {
  getResponseMode,
  INITIAL_SUGGESTIONS,
  responseText,
  type Claim,
  type ViewState,
} from "./responseModel";

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
  citedMode: boolean;
  suggestions: string[];
  visibleQuestion: string | undefined;
  assistantText: string;
  mapResults: LiveResult[];
  mapLoading: boolean;
  mapMessage: string | undefined;
  mapAggregateFreshness: "fresh" | "stale" | "mixed" | undefined;
  mapUnavailableLayers: string[];
  selectedLiveResultId: string | undefined;
  setSelectedLiveResultId: (resultId: string) => void;
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
  const activeRequest = useRef<AbortController | null>(null);

  const response = view.kind === "answer" || view.kind === "abstention" ? view.response : undefined;
  const mode = response ? getResponseMode(response) : undefined;
  const claims = view.kind === "answer" ? (view.response.claims ?? []) : [];
  const citedMode = mode === "grounded" || mode === "partial" || mode === "mixed" || mode === "conflict";
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

  const mapResults = useMemo(() => {
    const resultById = new Map<string, LiveResult>();
    for (const result of provinceMap.data?.results ?? []) resultById.set(result.result_id, result);
    for (const result of response?.live_results ?? []) resultById.set(result.result_id, result);
    return [...resultById.values()];
  }, [provinceMap.data?.results, response?.live_results]);
  const mapAggregateFreshness =
    response?.aggregate_freshness ?? provinceMap.data?.aggregate_freshness ?? undefined;
  const mapUnavailableLayers = [
    ...new Set([
      ...(provinceMap.data?.unavailable_layers ?? []),
      ...(response?.unavailable_layers ?? []),
    ]),
  ];
  const requiresLocation = response?.required_input?.kind === "location";

  useEffect(() => {
    const selectedFromResponse = response?.selected_live_result_id;
    if (selectedFromResponse) setSelectedLiveResultId(selectedFromResponse);
  }, [response?.selected_live_result_id]);

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
        visible_live_result_ids: mapResults.slice(0, 100).map((result) => result.result_id),
      };
      const contextSelected = selectedResultOverride ?? selectedLiveResultId;
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
      () => setLocationMessage("Location was not shared."),
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
    const question = query;
    setQuery("");
    void submitQuestion(question);
  }

  const visibleQuestion = "question" in view && view.question ? view.question : undefined;
  const assistantText =
    view.kind === "answer" || view.kind === "abstention"
      ? responseText(view.response)
      : view.kind === "loading"
        ? "Searching the reviewed guidance and validating its evidence…"
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
    citedMode,
    suggestions,
    visibleQuestion,
    assistantText,
    mapResults,
    mapLoading: provinceMap.loading,
    mapMessage: provinceMap.message,
    mapAggregateFreshness,
    mapUnavailableLayers,
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
