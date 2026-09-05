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

  it("reveals the page header for analytical answers without nested scrolling", () => {
    const panel = document.createElement("section");
    panel.className = "pc-main";
    const scroller = document.createElement("div");
    scroller.className = "conversation-scroll";
    const assistant = document.createElement("div");
    scroller.append(assistant);
    panel.append(scroller);
    document.body.append(panel);
    scroller.scrollTop = 180;

    revealAssistantMessage(assistant, true);

    expect(scroller.scrollTop).toBe(180);
    expect(scrollIntoView.mock.instances[0]).toBe(panel);
  });

  it("reveals the same header for ordinary answers without scroll compensation", () => {
    const panel = document.createElement("section");
    panel.className = "pc-main";
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
    expect(scrollIntoView.mock.instances[0]).toBe(panel);
    expect(scroller.scrollTop).toBe(20);
  });
});
