import {
  StrictMode,
} from "react";

import {
  createRoot,
} from "react-dom/client";

import "./index.css";
import "./commandAuthFetch";
import "./resilience.css";

import App
  from "./App";

import {
  OutboxStatus,
} from "./DeliveryUI";

import CommandAuthBoundary
  from "./CommandAuthBoundary";

import ErrorBoundary
  from "./ErrorBoundary";


const root =
  document.getElementById(
    "root"
  );


if (
  !root
) {
  throw new Error(
    "AEGIS root element was not found."
  );
}


createRoot(
  root
).render(

  <StrictMode>

    <ErrorBoundary>

      <OutboxStatus />

      <CommandAuthBoundary>

        <App />

      </CommandAuthBoundary>

    </ErrorBoundary>

  </StrictMode>
);


// ============================================================
// PRODUCTION PWA
// ============================================================

if (
  import.meta.env.PROD &&
  "serviceWorker"
  in navigator
) {

  window.addEventListener(
    "load",
    () => {

      void navigator
        .serviceWorker
        .register(
          "/sw.js"
        )
        .then(
          async registration => {

            // Ask browser for the newest
            // AEGIS service worker.
            void registration.update();


            const ready =
              await navigator
                .serviceWorker
                .ready;


            ready
              .active
              ?.postMessage({
                type:
                  "AEGIS_SYNC_OUTBOX",
              });
          }
        )
        .catch(
          () => {

            // IndexedDB + foreground retry
            // still works even if PWA
            // registration fails.
          }
        );
    }
  );
}