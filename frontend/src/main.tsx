import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { initLocale } from "./i18n";
import App from "./App";

initLocale();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
