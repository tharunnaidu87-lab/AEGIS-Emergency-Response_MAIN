import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import "./commandAuthFetch";
import App from "./App";
import CommandAuthBoundary from "./CommandAuthBoundary";
import ErrorBoundary from "./ErrorBoundary";

const root = document.getElementById("root");
if (!root) throw new Error("AEGIS root element was not found.");

createRoot(root).render(
  <StrictMode>
    <ErrorBoundary>
      <CommandAuthBoundary>
        <App />
      </CommandAuthBoundary>
    </ErrorBoundary>
  </StrictMode>,
);
