import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { revealAssistantMessage } from "../src/features/ask/ConversationPresentation";

describe("revealAssistantMessage", () => {
  const scrollIntoView = vi.fn();

  beforeEach(() => {
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: scrollIntoView,
    });
  });

  afterEach(() => {
    document.body.innerHTML = "";
    scrollIntoView.mockReset();
  });

  it("keeps the analytical answer and canvas at their first-viewport position", () => {
    const panel = document.createElement("section");
    panel.className = "conversation-panel conversation-panel--analytical";
    const scroller = document.createElement("div");
    scroller.className = "conversation-scroll";
    const assistant = document.createElement("div");
    scroller.append(assistant);
    panel.append(scroller);
    document.body.append(panel);
    scroller.scrollTop = 180;

    revealAssistantMessage(assistant, true);

    expect(scroller.scrollTop).toBe(0);
    expect(scrollIntoView).not.toHaveBeenCalled();
  });

  it("retains auto-follow for ordinary conversational answers", () => {
    const panel = document.createElement("section");
    const scroller = document.createElement("div");
    scroller.className = "conversation-scroll";
    const question = document.createElement("div");
    question.className = "question-block";
    const assistant = document.createElement("div");
    scroller.append(question);
    scroller.append(assistant);
    panel.append(scroller);
    document.body.append(panel);
    vi.spyOn(scroller, "getBoundingClientRect").mockReturnValue({ top: 10 } as DOMRect);
    vi.spyOn(question, "getBoundingClientRect").mockReturnValue({ top: 3 } as DOMRect);
    scroller.scrollTop = 20;

    revealAssistantMessage(assistant, true);

    expect(scrollIntoView).toHaveBeenCalledWith({ block: "start", inline: "nearest" });
    expect(scrollIntoView.mock.instances[0]).toBe(question);
    expect(scroller.scrollTop).toBe(13);
  });
});
