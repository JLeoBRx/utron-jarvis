import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "@safra/design-tokens/fonts.css";
import "@safra/design-tokens/tokens.css";
import "@safra/ui/styles.css";
import symbolUrl from "@safra/design-tokens/symbol.svg";

import { App } from "./App";
import "./app.css";

const icon = document.createElement("link");
icon.rel = "icon";
icon.type = "image/svg+xml";
icon.href = symbolUrl;
document.head.append(icon);

createRoot(document.getElementById("raiz") as HTMLElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
