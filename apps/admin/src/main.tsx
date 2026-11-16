import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import "@safra/design-tokens/fonts.css";
import "@safra/design-tokens/tokens.css";
import "./admin.css";

createRoot(document.getElementById("root") as HTMLElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
