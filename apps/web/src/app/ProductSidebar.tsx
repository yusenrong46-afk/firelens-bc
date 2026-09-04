import { ArrowSquareOut, House, Info, MapTrifold, Trash } from "@phosphor-icons/react";
import { BCWS_MAP_URL } from "../shared/officialLinks";

export type RecentQuestion = {
  text: string;
  current?: boolean;
};

export function ProductSidebar({
  homeActive,
  onHome,
  onHowItWorks,
  onClear,
  onSelectQuestion,
  howItWorksOpen,
  recentQuestions,
}: {
  homeActive: boolean;
  onHome: () => void;
  onHowItWorks: () => void;
  onClear: () => void;
  onSelectQuestion: (question: string) => void;
  howItWorksOpen: boolean;
  recentQuestions: RecentQuestion[];
}) {
  return (
    <aside className="product-sidebar" aria-label="Product navigation">
      <div className="product-sidebar__brand">
        <a
          className="product-sidebar__lockup"
          href="/"
          aria-label="FireLens home"
          onClick={(event) => {
            event.preventDefault();
            onHome();
          }}
        >
          <img src="/assets/firelens-mark.png" alt="" width={40} height={40} />
          <span>
            <strong className="product-sidebar__name">FireLens</strong>
            <small className="product-sidebar__subtitle">B.C. wildfire intelligence</small>
          </span>
        </a>
      </div>

      <nav className="product-sidebar__nav" aria-label="Primary">
        <button
          type="button"
          className={homeActive ? "product-nav product-nav--active" : "product-nav"}
          onClick={onHome}
          aria-current={homeActive ? "page" : undefined}
        >
          <House size={18} /> Home
        </button>
        <button
          type="button"
          className="product-nav"
          aria-expanded={howItWorksOpen}
          aria-controls="how-firelens-works"
          onClick={onHowItWorks}
        >
          <Info size={18} /> How it works
        </button>
        <a
          className="product-nav"
          href={BCWS_MAP_URL}
          target="_blank"
          rel="noreferrer"
        >
          <MapTrifold size={18} /> Official map
          <ArrowSquareOut size={14} aria-hidden="true" className="product-nav__external" />
          <span className="response-announcement">Opens in a new tab</span>
        </a>
      </nav>

      {recentQuestions.length > 0 && (
        <div className="product-sidebar__recent">
          <h2 className="product-sidebar__recent-heading">Recent questions</h2>
          <ul>
            {recentQuestions.map((item) => (
              <li key={item.text}>
                <button
                  type="button"
                  className={item.current ? "recent-question recent-question--current" : "recent-question"}
                  onClick={() => onSelectQuestion(item.text)}
                >
                  {item.text}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="product-sidebar__footer">
        <div className="product-sidebar__landscape" aria-hidden="true">
          <img src="/assets/pacific-landscape.svg" alt="" loading="lazy" />
        </div>
        <button type="button" className="product-sidebar__clear" onClick={onClear}>
          <Trash size={16} /> Clear conversation
        </button>
      </div>
    </aside>
  );
}

/** Up to four unique user questions from session history + visible question. */
export function deriveRecentQuestions(
  history: { role: string; content: string }[],
  visibleQuestion: string | undefined,
): RecentQuestion[] {
  const texts: string[] = [];
  for (const turn of history) {
    if (turn.role !== "user") continue;
    const text = turn.content.trim();
    if (!text) continue;
    if (!texts.some((existing) => existing.localeCompare(text, undefined, { sensitivity: "accent" }) === 0)) {
      texts.push(text);
    }
  }
  if (visibleQuestion?.trim()) {
    const current = visibleQuestion.trim();
    const without = texts.filter(
      (text) => text.localeCompare(current, undefined, { sensitivity: "accent" }) !== 0,
    );
    return [{ text: current, current: true }, ...without.map((text) => ({ text }))].slice(0, 4);
  }
  return texts.slice(-4).reverse().map((text) => ({ text }));
}
