import { FormEvent, useRef, useState } from "react";
import {
  askFireLens,
  type AskResponse,
  type ConversationTurn,
  FireLensApiError,
  type LocationInput,
  type ResponseMode,
} from "../../shared/api/api";
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
  response: AskResponse | undefined;
  mode: ResponseMode | undefined;
  claims: Claim[];
  citedMode: boolean;
  suggestions: string[];
  visibleQuestion: string | undefined;
  assistantText: string;
  submitQuestion: (question: string) => Promise<void>;
  clearHistory: () => void;
  useApproximateLocation: () => void;
  submit: (event: FormEvent<HTMLFormElement>) => void;
  clearManualLocation: () => void;
};

export function useFireLensSession(): FireLensSession {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(0);
  const [view, setView] = useState<ViewState>({ kind: "idle" });
  const [history, setHistory] = useState<ConversationTurn[]>([]);
  const [locationLabel, setLocationLabel] = useState("");
  const [coarseLocation, setCoarseLocation] = useState<LocationInput | undefined>();
  const [locationMessage, setLocationMessage] = useState("");
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

  async function submitQuestion(question: string) {
    const normalized = question.trim();
    if (!normalized) return;
    const requestHistory = history.slice(-6);
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    setSelected(0);
    setView({ kind: "loading", question: normalized });
    try {
      const requestLocation = locationLabel.trim()
        ? { label: locationLabel.trim(), radius_km: 50 }
        : coarseLocation;
      const nextResponse = await askFireLens(
        normalized,
        requestHistory,
        requestLocation,
        controller.signal,
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

  function clearHistory() {
    activeRequest.current?.abort();
    activeRequest.current = null;
    setHistory([]);
    setSelected(0);
    setLocationLabel("");
    setCoarseLocation(undefined);
    setLocationMessage("");
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
        setLocationLabel("");
        setCoarseLocation({
          latitude: Math.round(coords.latitude * 100) / 100,
          longitude: Math.round(coords.longitude * 100) / 100,
          radius_km: 50,
        });
        setLocationMessage("Approximate location ready for this session.");
      },
      () => setLocationMessage("Location was not shared."),
      { enableHighAccuracy: false, maximumAge: 300_000, timeout: 8_000 },
    );
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
          : "Ask about stable BC wildfire preparedness guidance. FireLens will either return locally cited evidence or explain why it cannot answer.";

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
    response,
    mode,
    claims,
    citedMode,
    suggestions,
    visibleQuestion,
    assistantText,
    submitQuestion,
    clearHistory,
    useApproximateLocation,
    submit,
    clearManualLocation: () => {
      setCoarseLocation(undefined);
      setLocationMessage("");
    },
  };
}
