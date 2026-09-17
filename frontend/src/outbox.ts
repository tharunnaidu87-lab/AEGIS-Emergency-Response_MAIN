import {
  API_BASE,
  type CreateReportRequest,
  type SharedReport,
} from "./api";


export type Receipt = {
  report?: SharedReport;

  tracking_token:
    string;

  id?: string;

  status:
    string;
};


export type Queued = {
  id: string;

  path:
    | "/reports"
    | "/distress";

  payload:
    Record<string, unknown>;

  created:
    string;

  state:
    | "pending"
    | "sent"
    | "review";

  attempts:
    number;

  next:
    number;

  receipt?:
    Receipt;

  message?:
    string;
};


const changed = () =>
  window.dispatchEvent(
    new Event(
      "aegis-outbox"
    )
  );


// ============================================================
// DATABASE
// ============================================================

export function openStore():
Promise<IDBDatabase> {

  return new Promise(
    (
      resolve,
      reject
    ) => {

      const request =
        indexedDB.open(
          "aegis-outbox",
          1
        );


      request.onupgradeneeded =
        () => {

          const db =
            request.result;


          if (
            !db
              .objectStoreNames
              .contains(
                "queue"
              )
          ) {

            db.createObjectStore(
              "queue",
              {
                keyPath:
                  "id",
              }
            );
          }


          if (
            !db
              .objectStoreNames
              .contains(
                "drafts"
              )
          ) {

            db.createObjectStore(
              "drafts"
            );
          }
        };


      request.onsuccess =
        () =>
          resolve(
            request.result
          );


      request.onerror =
        () =>
          reject(
            new Error(
              "This browser could not save the report. Keep this page open and try again."
            )
          );
    }
  );
}


export async function store<T>(
  name: string,

  mode:
    IDBTransactionMode,

  action:
    (
      store:
        IDBObjectStore
    ) => IDBRequest<T>
): Promise<T> {

  const db =
    await openStore();


  return new Promise(
    (
      resolve,
      reject
    ) => {

      const transaction =
        db.transaction(
          name,
          mode
        );


      const request =
        action(
          transaction
            .objectStore(
              name
            )
        );


      transaction.oncomplete =
        () => {

          db.close();

          resolve(
            request.result
          );
        };


      transaction.onerror =
        transaction.onabort =
          () => {

            db.close();

            reject(
              new Error(
                "Saving failed. Keep this page open and retry."
              )
            );
          };
    }
  );
}


export const listOutbox =
  () =>
    store<Queued[]>(
      "queue",
      "readonly",
      store =>
        store.getAll()
    );


// ============================================================
// RECEIPTS
// ============================================================

export function rememberReceipt(
  receipt:
    Receipt
) {

  const id =
    receipt.report?.id ||
    receipt.id;


  if (
    !id ||
    !receipt.tracking_token
  ) {
    return;
  }


  try {

    localStorage.setItem(
      "aegis-receipt-" +
      id,

      receipt.tracking_token
    );

  } catch {

    // IndexedDB receipt still exists.
    // Public tracking can recover
    // when storage becomes available.
  }
}


// ============================================================
// BACKGROUND SYNC REGISTRATION
// ============================================================

async function requestBackgroundSync() {

  if (
    !(
      "serviceWorker"
      in navigator
    )
  ) {
    return;
  }


  try {

    const registration =
      await navigator
        .serviceWorker
        .ready;


    const sync =
      (
        registration as
        ServiceWorkerRegistration & {
          sync?: {
            register(
              tag: string
            ):
            Promise<void>;
          };
        }
      ).sync;


    if (
      sync
    ) {

      await sync.register(
        "aegis-outbox"
      );

    } else {

      registration
        .active
        ?.postMessage({
          type:
            "AEGIS_SYNC_OUTBOX",
        });
    }

  } catch {

    // Foreground retry remains active.
  }
}


// ============================================================
// FOREGROUND DELIVERY
// ============================================================

let running:
Promise<void> |
undefined;


export function syncOutbox(
  force = false
):
Promise<void> {

  if (
    running
  ) {
    return running;
  }


  running =
    (
      async () => {

        if (
          !navigator.onLine
        ) {

          await requestBackgroundSync();

          return;
        }


        const items =
          await listOutbox();


        let pendingRemains =
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


          if (
            !force &&
            item.next >
              Date.now()
          ) {

            pendingRemains =
              true;

            continue;
          }


          try {

            const response =
              await fetch(
                API_BASE +
                item.path,
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
                    AbortSignal.timeout(
                      15000
                    ),
                }
              );


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
                  "Delivery needs review. Your original report remains saved here.";

              } else {

                throw new Error(
                  "retry"
                );
              }

            } else {

              const receipt:
                Receipt =
                  await response.json();


              if (
                !receipt
                  .tracking_token ||
                !(
                  receipt.report?.id ||
                  receipt.id
                )
              ) {

                throw new Error(
                  "receipt"
                );
              }


              item.receipt =
                receipt;

              item.state =
                "sent";

              item.message =
                "Delivery confirmed by AEGIS.";


              rememberReceipt(
                receipt
              );
            }

          } catch {

            item.attempts++;


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


            pendingRemains =
              true;
          }


          await store(
            "queue",
            "readwrite",
            store =>
              store.put(
                item
              )
          );


          changed();
        }


        if (
          pendingRemains
        ) {

          await requestBackgroundSync();
        }

      }
    )()
      .finally(
        () => {

          running =
            undefined;
        }
      );


  return running;
}


// ============================================================
// QUEUE
// ============================================================

export async function enqueue(
  path:
    Queued["path"],

  payload:
    Record<string, unknown>,

  id =
    crypto.randomUUID()
) {

  const item:
    Queued = {

      id,

      path,

      payload: {
        ...payload,

        client_request_id:
          id,
      },

      created:
        new Date()
          .toISOString(),

      state:
        "pending",

      attempts:
        0,

      next:
        0,
  };


  await store(
    "queue",
    "readwrite",
    store =>
      store.put(
        item
      )
  );


  changed();


  if (
    navigator.storage?.persist
  ) {

    void navigator
      .storage
      .persist()
      .catch(
        () =>
          false
      );
  }


  await requestBackgroundSync();


  // Do not make the citizen wait
  // for a slow network response.
  void syncOutbox();


  return id;
}


// ============================================================
// NORMAL REPORT
// ============================================================

export const queueReport =
  (
    report:
      CreateReportRequest
  ) =>
    enqueue(
      "/reports",
      {
        ...report,
      }
    );


// ============================================================
// VOICE DRAFT
// ============================================================

export async function saveVoiceDraft(
  audio:
    Blob
) {

  await store(
    "drafts",
    "readwrite",
    store =>
      store.put(
        audio,
        "voice"
      )
  );
}


export const loadVoiceDraft =
  () =>
    store<
      Blob |
      undefined
    >(
      "drafts",
      "readonly",
      store =>
        store.get(
          "voice"
        )
    );


// ============================================================
// BLOB → BASE64
// ============================================================

export async function encodeBlob(
  blob:
    Blob
):
Promise<string> {

  return new Promise(
    (
      resolve,
      reject
    ) => {

      const reader =
        new FileReader();


      reader.onload =
        () => {

          resolve(
            String(
              reader.result
            )
              .split(",")[1]
          );
        };


      reader.onerror =
        reject;


      reader.readAsDataURL(
        blob
      );
    }
  );
}