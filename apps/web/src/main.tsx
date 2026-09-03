import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "./app/App";

// After a deploy, a tab still holding the previous entry file may ask for a
// lazy chunk that no longer exists. Reload once to pick up the current build.
window.addEventListener("vite:preloadError", (event) => {
  const key = "firelens:chunk-reload";
  if (sessionStorage.getItem(key) === location.href) return;
  sessionStorage.setItem(key, location.href);
  event.preventDefault();
  location.reload();
});

const root = document.getElementById("root");
if (!root) throw new Error("FireLens root element is missing");

createRoot(root).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
