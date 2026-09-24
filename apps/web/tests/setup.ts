import "@testing-library/jest-dom/vitest";

// JSDOM lacks native dialog methods. Browser journeys verify focus trapping and Escape.
if (!HTMLDialogElement.prototype.showModal) {
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); this.dispatchEvent(new Event("close")); };
}
