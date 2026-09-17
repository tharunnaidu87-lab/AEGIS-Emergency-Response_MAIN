try {
  importScripts("/sw-assets.js");
} catch {
  // sw-assets.js is generated during the production build.
  // The basic offline shell still works if it is unavailable.
}

const BUILD_ID = self.AEGIS_BUILD || "fallback";
const API_BASE = self.AEGIS_API || "/api";

const BUILD_ASSETS = Array.isArray(self.AEGIS_ASSETS)
  ? self.AEGIS_ASSETS
  : [];

const CACHE_NAME = `aegis-shell-${BUILD_ID}`;

const SHELL = [
  ...new Set([
    "/",
    "/index.html",
    "/report",
    "/manifest.webmanifest",
    ...BUILD_ASSETS,
  ]),
];

const OUTBOX_DB = "aegis-outbox";
const OUTBOX_VERSION = 1;
const OUTBOX_STORE = "queue";


function apiUrl(path) {
  return API_BASE.replace(/\/$/, "") + path;
}


function isApiRequest(url) {
  const base = new URL(
    API_BASE,
    self.location.origin
  );

  const basePath =
    base.pathname.replace(/\/$/, "");

  return (
    url.origin === base.origin &&
    (
      url.pathname === basePath ||
      url.pathname.startsWith(basePath + "/")
    )
  );
}


// ============================================================
// INDEXEDDB
// ============================================================

function openOutbox() {
  return new Promise(
    (resolve, reject) => {

      const request =
        indexedDB.open(
          OUTBOX_DB,
          OUTBOX_VERSION
        );

      request.onupgradeneeded = () => {
        const db = request.result;

        if (
          !db.objectStoreNames.contains(
            OUTBOX_STORE
          )
        ) {
          db.createObjectStore(
            OUTBOX_STORE,
            {
              keyPath: "id",
            }
          );
        }

        if (
          !db.objectStoreNames.contains(
            "drafts"
          )
        ) {
          db.createObjectStore(
            "drafts"
          );
        }
      };

      request.onsuccess = () =>
        resolve(request.result);

      request.onerror = () =>
        reject(
          request.error ||
          new Error(
            "IndexedDB unavailable"
          )
        );
    }
  );
}


async function readQueue() {
  const db =
    await openOutbox();

  try {

    return await new Promise(
      (resolve, reject) => {

        const transaction =
          db.transaction(
            OUTBOX_STORE,
            "readonly"
          );

        const request =
          transaction
            .objectStore(
              OUTBOX_STORE
            )
            .getAll();

        request.onsuccess = () =>
          resolve(
            request.result || []
          );

        request.onerror = () =>
          reject(
            request.error ||
            new Error(
              "Queue read failed"
            )
          );
      }
    );

  } finally {
    db.close();
  }
}


async function writeQueueItem(
  item
) {
  const db =
    await openOutbox();

  try {

    await new Promise(
      (resolve, reject) => {

        const transaction =
          db.transaction(
            OUTBOX_STORE,
            "readwrite"
          );

        transaction
          .objectStore(
            OUTBOX_STORE
          )
          .put(item);

        transaction.oncomplete =
          () => resolve();

        transaction.onerror =
          transaction.onabort =
            () =>
              reject(
                transaction.error ||
                new Error(
                  "Queue write failed"
                )
              );
      }
    );

  } finally {
    db.close();
  }
}


// ============================================================
// NOTIFY OPEN AEGIS WINDOWS
// ============================================================

async function notifyClients(
  item
) {
  const clients =
    await self.clients.matchAll({
      type: "window",
      includeUncontrolled: true,
    });

  for (
    const client
    of clients
  ) {
    client.postMessage({
      type:
        "AEGIS_OUTBOX_UPDATED",

      id:
        item.id,

      state:
        item.state,
    });
  }
}


// ============================================================
// BACKGROUND DELIVERY
// ============================================================

async function postQueuedItem(
  item
) {
  const controller =
    new AbortController();

  const timeout =
    setTimeout(
      () =>
        controller.abort(),
      15000
    );

  try {

    const response =
      await fetch(
        apiUrl(
          item.path
        ),
        {
          method:
            "POST",

          headers: {
            "Content-Type":
              "application/json",
          },

          body:
            JSON.stringify(
              item.payload
            ),

          signal:
            controller.signal,
        }
      );


    // Permanent validation error:
    // keep the original report
    // for human review.
    if (
      !response.ok
    ) {

      if (
        [
          400,
          409,
          413,
          415,
          422,
        ].includes(
          response.status
        )
      ) {

        item.state =
          "review";

        item.message =
          "Delivery needs review. Your original report remains saved on this device.";

        await writeQueueItem(
          item
        );

        await notifyClients(
          item
        );

        return false;
      }

      throw new Error(
        `Retryable HTTP ${response.status}`
      );
    }


    const receipt =
      await response.json();


    if (
      !receipt?.tracking_token ||
      !(
        receipt.report?.id ||
        receipt.id
      )
    ) {
      throw new Error(
        "Incomplete receipt"
      );
    }


    item.receipt =
      receipt;

    item.state =
      "sent";

    item.message =
      "Delivery confirmed by AEGIS.";


    await writeQueueItem(
      item
    );

    await notifyClients(
      item
    );


    return false;

  } catch {

    item.attempts =
      Number(
        item.attempts || 0
      ) + 1;


    item.next =
      Date.now() +
      Math.min(
        300000,
        3000 *
          2 **
            Math.min(
              item.attempts,
              7
            )
      );


    item.message =
      "Saved on this device. Delivery is not confirmed yet.";


    await writeQueueItem(
      item
    );

    await notifyClients(
      item
    );


    return true;

  } finally {

    clearTimeout(
      timeout
    );
  }
}


async function syncOutboxInBackground() {

  const items =
    await readQueue();

  let retryNeeded =
    false;


  for (
    const item
    of items
  ) {

    if (
      item.state !==
      "pending"
    ) {
      continue;
    }


    retryNeeded =
      (
        await postQueuedItem(
          item
        )
      ) ||
      retryNeeded;
  }


  // Rejecting the Background Sync
  // promise tells the browser that
  // another retry is still required.
  if (
    retryNeeded
  ) {
    throw new Error(
      "One or more AEGIS reports still need delivery retry."
    );
  }
}


// ============================================================
// INSTALL
// ============================================================

self.addEventListener(
  "install",
  event => {

    event.waitUntil(
      (
        async () => {

          const cache =
            await caches.open(
              CACHE_NAME
            );


          await Promise.allSettled(
            SHELL.map(
              url =>
                cache.add(url)
            )
          );


          await self.skipWaiting();
        }
      )()
    );
  }
);


// ============================================================
// ACTIVATE
// ============================================================

self.addEventListener(
  "activate",
  event => {

    event.waitUntil(
      (
        async () => {

          const keys =
            await caches.keys();


          await Promise.all(
            keys
              .filter(
                key =>
                  key.startsWith(
                    "aegis-shell-"
                  ) &&
                  key !==
                    CACHE_NAME
              )
              .map(
                key =>
                  caches.delete(
                    key
                  )
              )
          );


          await self.clients.claim();
        }
      )()
    );
  }
);


// ============================================================
// FETCH
// ============================================================

self.addEventListener(
  "fetch",
  event => {

    const request =
      event.request;


    if (
      request.method !==
      "GET"
    ) {
      return;
    }


    const url =
      new URL(
        request.url
      );


    // NEVER serve emergency API
    // state from cache.
    if (
      isApiRequest(
        url
      )
    ) {
      return;
    }


    // Navigation:
    // network first,
    // offline shell second.
    if (
      request.mode ===
      "navigate"
    ) {

      event.respondWith(
        (
          async () => {

            try {

              const response =
                await fetch(
                  request
                );


              if (
                response.ok
              ) {

                const cache =
                  await caches.open(
                    CACHE_NAME
                  );


                await cache.put(
                  "/index.html",
                  response.clone()
                );
              }


              return response;

            } catch {

              return (
                await caches.match(
                  "/index.html"
                )
              ) ||
              (
                await caches.match(
                  "/report"
                )
              ) ||
              Response.error();
            }
          }
        )()
      );

      return;
    }


    // Same-origin static resources:
    // cache first + refresh.
    if (
      url.origin ===
      self.location.origin
    ) {

      event.respondWith(
        (
          async () => {

            const cached =
              await caches.match(
                request
              );


            const network =
              fetch(
                request
              )
                .then(
                  async response => {

                    if (
                      response.ok
                    ) {

                      const cache =
                        await caches.open(
                          CACHE_NAME
                        );


                      await cache.put(
                        request,
                        response.clone()
                      );
                    }


                    return response;
                  }
                )
                .catch(
                  () =>
                    undefined
                );


            return (
              cached ||
              (
                await network
              ) ||
              Response.error()
            );
          }
        )()
      );
    }
  }
);


// ============================================================
// TRUE BACKGROUND SYNC
// ============================================================

self.addEventListener(
  "sync",
  event => {

    if (
      event.tag ===
      "aegis-outbox"
    ) {

      event.waitUntil(
        syncOutboxInBackground()
      );
    }
  }
);


// ============================================================
// MANUAL MESSAGE FROM OPEN APP
// ============================================================

self.addEventListener(
  "message",
  event => {

    if (
      event.data?.type ===
      "AEGIS_SYNC_OUTBOX"
    ) {

      event.waitUntil(
        syncOutboxInBackground()
          .catch(
            () => {}
          )
      );
    }


    if (
      event.data?.type ===
      "SKIP_WAITING"
    ) {
      self.skipWaiting();
    }
  }
);