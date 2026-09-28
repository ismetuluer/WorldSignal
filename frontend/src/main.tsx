import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { initToken, setToken } from "./api/client";
import { App } from "./App";
import "./styles/app.css";

// Apply the OS theme before React renders to avoid a light flash in dark mode.
document.documentElement.dataset.theme = window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";

const token = initToken();
setToken(token);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App hasToken={token !== null} />
  </StrictMode>,
);
