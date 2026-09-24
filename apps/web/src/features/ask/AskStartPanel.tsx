import { ArrowRight, Backpack, Crosshair, Funnel, MagnifyingGlass, MapPin, MapTrifold, X } from "@phosphor-icons/react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { fetchGuidedQuestions, type GuidedQuestionCategory } from "../../shared/api/api";
import { emitProductEvent } from "../../shared/telemetry";

function expandPlace(question: string, place: string): string {
  const trimmedPlace = place.trim();
  // Do not silently invent a location when the user has not provided one.
  return trimmedPlace ? question.replaceAll("{place}", trimmedPlace) : question;
}

function isGuidedQuestionCatalogue(value: unknown): value is { categories: GuidedQuestionCategory[] } {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as { schema_version?: unknown; catalogue_sha256?: unknown; categories?: unknown };
  if (candidate.schema_version !== "firelens.guided_questions.v1"
    || typeof candidate.catalogue_sha256 !== "string"
    || !/^[a-f0-9]{64}$/.test(candidate.catalogue_sha256)
    || !Array.isArray(candidate.categories)) return false;
  const categories = candidate.categories as unknown[];
  const questionIds: string[] = [];
  const valid = categories.every((category) => {
    if (typeof category !== "object" || category === null) return false;
    const item = category as { id?: unknown; label?: unknown; questions?: unknown };
    const categoryValid = typeof item.id === "string"
      && item.id.trim().length > 0
      && typeof item.label === "string"
      && item.label.trim().length > 0
      && Array.isArray(item.questions)
      && item.questions.every((question) => {
        if (typeof question !== "object" || question === null) return false;
        const entry = question as Record<string, unknown>;
        const questionValid = typeof entry.id === "string"
          && entry.id.trim().length > 0
          && typeof entry.label === "string"
          && entry.label.trim().length > 0
          && typeof entry.question === "string"
          && entry.question.trim().length > 0
            && ["none", "required"].includes(entry.location_mode as string)
          && ["official_live", "reviewed_guidance", "official_quote"].includes(entry.source_lane as string);
        if (questionValid) questionIds.push(entry.id as string);
        return questionValid;
      });
    return categoryValid;
  });
  return valid && questionIds.length === 24 && new Set(questionIds).size === 24;
}

export const PREPAREDNESS_QUESTION = "What belongs in a wildfire grab-and-go bag?";
export const NEARBY_QUESTION = "Show the incident, perimeter, and evacuation records near {place}.";

export function AskStartPanel({
  locationLabel,
  catalogueOnly = false,
  currentState,
  composer,
  onSelectQuestion,
  onPrepareQuestion,
  onOpenMap,
  onLocationChange,
  onUseApproximateLocation,
}: {
  locationLabel: string;
  catalogueOnly?: boolean;
  currentState?: string | undefined;
  composer?: ReactNode;
  onSelectQuestion: (question: string) => void;
  onPrepareQuestion: (question: string) => void;
  onOpenMap: () => void;
  onLocationChange: (value: string) => void;
  onUseApproximateLocation: () => void;
}) {
  const [catalogue, setCatalogue] = useState<GuidedQuestionCategory[]>([]);
  const [catalogueState, setCatalogueState] = useState<"idle" | "loading" | "ready" | "failed">("idle");
  const [open, setOpen] = useState(false);
  const [nearbyOpen, setNearbyOpen] = useState(false);
  const placeRef = useRef<HTMLInputElement>(null);
  const [search, setSearch] = useState("");
  const [categoryId, setCategoryId] = useState("all");
  const [announcement, setAnnouncement] = useState("");
  const [catalogueRequest, setCatalogueRequest] = useState(0);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const retryRef = useRef<HTMLButtonElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const catalogueRequestedRef = useRef(false);

  useEffect(() => {
    if (!open || catalogueRequestedRef.current) return;
    catalogueRequestedRef.current = true;
    setCatalogueState("loading");
    const controller = new AbortController();
    let active = true;
    void fetchGuidedQuestions(controller.signal)
      .then((payload) => {
        if (!active) return;
        if (!isGuidedQuestionCatalogue(payload)) throw new Error("Invalid guided-question catalogue");
        setCatalogue(payload.categories);
        setCatalogueState("ready");
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          catalogueRequestedRef.current = false;
          return;
        }
        if (!active) return;
        setCatalogueState("failed");
        requestAnimationFrame(() => (retryRef.current ?? triggerRef.current)?.focus());
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [catalogueRequest, open]);

  useEffect(() => {
    if (!open) return;
    const frame = requestAnimationFrame(() => searchRef.current?.focus());
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      setOpen(false);
      setSearch("");
      setCategoryId("all");
      requestAnimationFrame(() => triggerRef.current?.focus());
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      cancelAnimationFrame(frame);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const questionCount = catalogue.reduce((count, category) => count + category.questions.length, 0);
  const filteredCategories = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase();
    return catalogue
      .filter((category) => categoryId === "all" || category.id === categoryId)
      .map((category) => ({
        ...category,
        questions: category.questions.filter((item) => (
          !needle
          || `${item.label} ${item.question} ${category.label}`.toLocaleLowerCase().includes(needle)
        )),
      }))
      .filter((category) => category.questions.length > 0);
  }, [catalogue, categoryId, search]);

  useEffect(() => {
    if (open) emitProductEvent("guided_catalog_opened");
  }, [open]);

  function selectQuestion(question: string) {
    emitProductEvent("guided_question_selected");
    const expandedQuestion = expandPlace(question, locationLabel);
    onSelectQuestion(expandedQuestion);
    setAnnouncement(`Asking: ${expandedQuestion}`);
    setOpen(false);
    setSearch("");
    setCategoryId("all");
  }

  function retryCatalogue() {
    catalogueRequestedRef.current = false;
    setCatalogueState("loading");
    setCatalogueRequest((request) => request + 1);
    requestAnimationFrame(() => searchRef.current?.focus());
  }

  return (
    <section className="conversation-intro ask-start-panel">
      <p className="response-announcement" role="status" aria-live="polite" aria-atomic="true">{announcement}</p>
      {!catalogueOnly && <div className="ask-start-panel__intro">
        <p className="ask-start-panel__eyebrow">British Columbia · Independent public beta</p>
        <h1>Know what’s happening.{" "}<br /><span>Know where the information came from.</span></h1>
        <p>Official wildfire records, evacuation information and reviewed preparedness guidance for B.C.</p>
        {composer}
        <div className="home-task-cards" aria-label="Explore FireLens">
          <button type="button" className="home-task-card" aria-label="Near me: check my area" aria-expanded={nearbyOpen} aria-controls="nearby-search" onClick={() => { setNearbyOpen((value) => !value); if (!nearbyOpen) requestAnimationFrame(() => placeRef.current?.focus()); }}>
            <span className="home-task-card__icon"><MapPin size={24} /></span><strong>Near me</strong><span>Nearby official records</span><span className="home-task-card__action" aria-hidden="true"><ArrowRight size={17} /></span>
          </button>
          <button type="button" className="home-task-card" aria-label="Across B.C.: view wildfire activity" onClick={onOpenMap}>
            <span className="home-task-card__icon"><MapTrifold size={24} /></span><strong>Across B.C.</strong><span>Provincial map and coverage</span><span className="home-task-card__action" aria-hidden="true"><ArrowRight size={17} /></span>
          </button>
          <button type="button" className="home-task-card" aria-label="Preparedness: ask about a grab-and-go bag" onClick={() => onPrepareQuestion(PREPAREDNESS_QUESTION)}>
            <span className="home-task-card__icon"><Backpack size={24} /></span><strong>Preparedness</strong><span>Grab-and-go bag guidance</span><span className="home-task-card__action" aria-hidden="true"><ArrowRight size={17} /></span>
          </button>
        </div>
        {currentState && (
          <p className="ask-start-panel__current-state" role="status">{currentState}</p>
        )}
      </div>}
      <div className="ask-start-panel__console">
        {nearbyOpen && <form className="nearby-search" id="nearby-search" onSubmit={(event) => { event.preventDefault(); if (locationLabel.trim()) onSelectQuestion(expandPlace(NEARBY_QUESTION, locationLabel)); }}>
        <h2>Where should I look?</h2>
        <p>Official records within 50 km. Distances are straight-line, not travel routes.</p>
        <label className="ask-start-panel__place">
          <span>Your B.C. community</span>
          <input
            aria-label="BC community for a nearby lookup"
            ref={placeRef}
            value={locationLabel}
            onChange={(event) => onLocationChange(event.target.value)}
            placeholder="For example, Kelowna"
            maxLength={120}
          />
        </label>
        <button type="button" className="ask-start-panel__approx" aria-label="Use approximate location" onClick={onUseApproximateLocation}>
          <Crosshair size={18} aria-hidden="true" />
          <span>Use my approximate location <small>Not stored</small></span>
        </button>
        <button className="nearby-search__submit" type="submit" disabled={!locationLabel.trim()}>Check my area <ArrowRight size={17} /></button>
        </form>}
        <div className="guided-questions">
          {catalogueState !== "failed" ? (
            <>
            <button ref={triggerRef} type="button" className="guided-questions__trigger" aria-expanded={open} aria-controls="guided-questions-panel" aria-busy={catalogueState === "loading"} onClick={() => setOpen((current) => !current)}>
              <MapPin size={20} aria-hidden="true" />
              <span>Explore example questions{catalogueState === "ready" ? ` · ${questionCount}` : ""}</span>
              <ArrowRight size={18} aria-hidden="true" />
            </button>
            {open && (
              <div id="guided-questions-panel" className="guided-questions__panel" role="region" aria-label="Guided questions">
                <div className="guided-questions__tools">
                  <label className="guided-questions__search">
                    <span className="response-announcement">Search guided questions</span>
                    <MagnifyingGlass size={18} aria-hidden="true" />
                    <input ref={searchRef} type="search" aria-label="Search guided questions" placeholder="Search questions" value={search} onChange={(event) => setSearch(event.target.value)} />
                  </label>
                  <label className="guided-questions__filter">
                    <Funnel size={17} aria-hidden="true" />
                    <span className="response-announcement">Filter by category</span>
                    <select aria-label="Filter guided questions by category" value={categoryId} onChange={(event) => setCategoryId(event.target.value)}>
                      <option value="all">All categories</option>
                      {catalogue.map((category) => <option key={category.id} value={category.id}>{category.label}</option>)}
                    </select>
                  </label>
                  <button type="button" className="guided-questions__close" aria-label="Close guided questions" onClick={() => { setOpen(false); requestAnimationFrame(() => triggerRef.current?.focus()); }}>
                    <X size={19} aria-hidden="true" />
                  </button>
                </div>
                {catalogueState !== "ready" ? (
                  <p className="guided-questions__empty" role="status">Loading guided questions…</p>
                ) : filteredCategories.length > 0 ? (
                  <div className="guided-questions__categories">
                    {filteredCategories.map((category) => (
                      <section key={category.id} aria-labelledby={`guided-category-${category.id}`}>
                        <h2 id={`guided-category-${category.id}`}>{category.label}</h2>
                        <ul>
                          {category.questions.map((item) => (
                            <li key={item.id}><button type="button" onClick={() => selectQuestion(item.question)}><strong>{item.label}</strong><span>{expandPlace(item.question, locationLabel)}</span></button></li>
                          ))}
                        </ul>
                      </section>
                    ))}
                  </div>
                ) : (
                  <p className="guided-questions__empty" role="status">No guided questions match that search.</p>
                )}
              </div>
            )}
            </>
          ) : (
            <div className="guided-questions__failure" role="status" aria-label="Guided questions status" aria-live="polite" aria-atomic="true">
              <span>Guided questions are temporarily unavailable.</span>
              <button ref={retryRef} type="button" onClick={retryCatalogue}>Retry guided questions</button>
            </div>
          )}
          </div>
      </div>
    </section>
  );
}
