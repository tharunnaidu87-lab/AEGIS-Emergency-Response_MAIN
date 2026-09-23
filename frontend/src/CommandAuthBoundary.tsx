import {
  useEffect,
  useMemo,
  useState,
} from "react";

import type {
  FormEvent,
  ReactNode,
} from "react";

import {
  clearCommandToken,
  getCommandToken,
  setCommandToken,
} from "./commandAuthFetch";


const API_BASE =
  (
    import.meta.env
      .VITE_API_BASE_URL ||
    "/api"
  )
    .replace(
      /\/$/,
      ""
    );


const COMMAND_PATHS =
  new Set([
    "/command",
    "/simulate",
    "/relocation",
    "/responder",
  ]);


type AuthRole =
  | "AUTHORITY"
  | "RESPONDER";


type AuthPath =
  | "command"
  | "responder";


type LoginResponse = {
  status?: string;

  role:
    AuthRole;

  username:
    string;

  token:
    string;

  expires_at:
    number;
};


type SessionResponse = {
  status?: string;

  role:
    AuthRole;

  username:
    string;

  expires_at:
    number;
};


// ============================================================
// ROUTE TRACKING
// ============================================================

function currentPath() {
  return window
    .location
    .pathname;
}


function installHistoryEvents() {

  const historyAny =
    history as
    History & {
      __aegisPatched?:
        boolean;
    };


  if (
    historyAny
      .__aegisPatched
  ) {
    return;
  }


  historyAny
    .__aegisPatched =
      true;


  const originalPushState =
    history.pushState.bind(
      history
    );


  const originalReplaceState =
    history.replaceState.bind(
      history
    );


  history.pushState =
    (
      data:
        unknown,

      unused:
        string,

      url?:
        string |
        URL |
        null
    ) => {

      originalPushState(
        data,
        unused,
        url
      );


      window.dispatchEvent(
        new Event(
          "aegis-locationchange"
        )
      );
    };


  history.replaceState =
    (
      data:
        unknown,

      unused:
        string,

      url?:
        string |
        URL |
        null
    ) => {

      originalReplaceState(
        data,
        unused,
        url
      );


      window.dispatchEvent(
        new Event(
          "aegis-locationchange"
        )
      );
    };
}


// ============================================================
// AUTH BOUNDARY
// ============================================================

export default function CommandAuthBoundary({
  children,
}: {
  children:
    ReactNode;
}) {

  const [
    path,
    setPath,
  ] =
    useState(
      currentPath()
    );


  const responder =
    path ===
    "/responder";


  const authPath:
    AuthPath =
      responder
        ? "responder"
        : "command";


  const expectedRole:
    AuthRole =
      responder
        ? "RESPONDER"
        : "AUTHORITY";


  const needsAuth =
    useMemo(
      () =>
        COMMAND_PATHS.has(
          path
        ),
      [
        path,
      ]
    );


  const [
    checking,
    setChecking,
  ] =
    useState(
      needsAuth &&
      Boolean(
        getCommandToken()
      )
    );


  const [
    authenticated,
    setAuthenticated,
  ] =
    useState(
      false
    );


  const [
    authenticatedRole,
    setAuthenticatedRole,
  ] =
    useState<
      AuthRole |
      ""
    >("");


  const [
    username,
    setUsername,
  ] =
    useState("");


  const [
    password,
    setPassword,
  ] =
    useState("");


  const [
    error,
    setError,
  ] =
    useState("");


  const [
    submitting,
    setSubmitting,
  ] =
    useState(
      false
    );


  // ==========================================================
  // WATCH ROUTE
  // ==========================================================

  useEffect(
    () => {

      installHistoryEvents();


      const onLocation =
        () =>
          setPath(
            currentPath()
          );


      window.addEventListener(
        "popstate",
        onLocation
      );


      window.addEventListener(
        "aegis-locationchange",
        onLocation
      );


      return () => {

        window.removeEventListener(
          "popstate",
          onLocation
        );


        window.removeEventListener(
          "aegis-locationchange",
          onLocation
        );
      };
    },
    []
  );


  // ==========================================================
  // VERIFY EXISTING SESSION
  // ==========================================================

  useEffect(
    () => {

      if (
        !needsAuth
      ) {

        setAuthenticated(
          false
        );

        setAuthenticatedRole(
          ""
        );

        setChecking(
          false
        );

        return;
      }


      const token =
        getCommandToken();


      if (
        !token
      ) {

        setAuthenticated(
          false
        );

        setAuthenticatedRole(
          ""
        );

        setChecking(
          false
        );

        return;
      }


      const controller =
        new AbortController();


      setChecking(
        true
      );


      setAuthenticated(
        false
      );


      fetch(
        `${API_BASE}/auth/${authPath}/session`,
        {
          signal:
            controller.signal,
        }
      )
        .then(
          response => {

            if (
              !response.ok
            ) {
              throw new Error(
                "Session expired"
              );
            }


            return response.json();
          }
        )
        .then(
          (
            session:
              SessionResponse
          ) => {

            if (
              controller
                .signal
                .aborted
            ) {
              return;
            }


            if (
              session.role !==
              expectedRole
            ) {
              throw new Error(
                "Wrong staff role"
              );
            }


            setAuthenticated(
              true
            );


            setAuthenticatedRole(
              session.role
            );


            if (
              responder
            ) {

              sessionStorage
                .setItem(
                  "aegis_unit",
                  session.username
                );
            }
          }
        )
        .catch(
          () => {

            if (
              controller
                .signal
                .aborted
            ) {
              return;
            }


            clearCommandToken();


            if (
              responder
            ) {

              sessionStorage
                .removeItem(
                  "aegis_unit"
                );
            }


            setAuthenticated(
              false
            );


            setAuthenticatedRole(
              ""
            );
          }
        )
        .finally(
          () => {

            if (
              !controller
                .signal
                .aborted
            ) {

              setChecking(
                false
              );
            }
          }
        );


      return () =>
        controller.abort();

    },
    [
      needsAuth,
      authPath,
      responder,
      expectedRole,
    ]
  );


  // ==========================================================
  // LOGIN
  // ==========================================================

  async function login(
    event:
      FormEvent<HTMLFormElement>
  ) {

    event.preventDefault();


    setError("");


    setSubmitting(
      true
    );


    try {

      const response =
        await fetch(
          `${API_BASE}/auth/${authPath}/login`,
          {
            method:
              "POST",

            headers: {
              "Content-Type":
                "application/json",
            },

            body:
              JSON.stringify({
                username,
                password,
              }),

            signal:
              AbortSignal.timeout(
                60000
              ),
          }
        );


      if (
        !response.ok
      ) {

        let detail =
          responder
            ? "Responder login failed."
            : "Authority login failed.";


        try {

          const body =
            await response.json();


          if (
            typeof body.detail ===
            "string"
          ) {

            detail =
              body.detail;
          }

        } catch {

          // Keep safe fallback.
        }


        throw new Error(
          detail
        );
      }


      const result:
        LoginResponse =
          await response.json();


      if (
        result.role !==
        expectedRole
      ) {

        throw new Error(
          "Incorrect access role."
        );
      }


      setCommandToken(
        result.token
      );


      setPassword("");


      setAuthenticated(
        true
      );


      setAuthenticatedRole(
        result.role
      );


      if (
        responder
      ) {

        sessionStorage
          .setItem(
            "aegis_unit",
            result.username
          );
      }

    } catch (
      loginError
    ) {

      setError(
        loginError instanceof
          Error
          ? loginError.message
          : "Check your sign-in details and connection, then retry."
      );

    } finally {

      setSubmitting(
        false
      );
    }
  }


  // ==========================================================
  // PUBLIC ROUTES
  // ==========================================================

  if (
    !needsAuth
  ) {

    return (
      <>
        {children}
      </>
    );
  }


  // ==========================================================
  // VERIFYING
  // ==========================================================

  if (
    checking
  ) {

    return (
      <main className="center-state">

        <h1>
          {responder
            ? "AEGIS FIELD"
            : "AEGIS COMMAND"}
        </h1>

        <p>
          VERIFYING{" "}
          {responder
            ? "RESPONDER"
            : "AUTHORITY"}{" "}
          SESSION...
        </p>

      </main>
    );
  }


  // ==========================================================
  // LOGIN SCREEN
  // ==========================================================

  if (
    !authenticated ||
    authenticatedRole !==
      expectedRole
  ) {

    return (

      <main
        className="center-state"
        style={{
          minHeight:
            "100vh",
        }}
      >

        <section
          style={{
            width:
              "min(440px, 92vw)",

            border:
              "1px solid #31453d",

            padding:
              28,

            background:
              "#0d1512",
          }}
        >

          <small>

            {responder
              ? "AEGIS // RESPONDER PORTAL"
              : "AEGIS // COMMAND CENTER"}

          </small>


          <h1>

            {responder
              ? "Responder Sign In"
              : "Command Center Sign In"}

          </h1>


          <p>

            {responder
              ? "Use a demonstration responder unit ID assigned in AEGIS."
              : "Access is restricted to authorized AEGIS Command personnel."}

          </p>


          <form
            onSubmit={
              login
            }
            style={{
              display:
                "grid",

              gap:
                14,
            }}
          >

            <label>

              {responder
                ? "Unit ID"
                : "Username"}

              <input
                autoComplete="username"
                value={
                  username
                }
                onChange={
                  event =>
                    setUsername(
                      event
                        .target
                        .value
                    )
                }
                required
              />

            </label>


            <label>

              Password

              <input
                type="password"
                autoComplete="current-password"
                value={
                  password
                }
                onChange={
                  event =>
                    setPassword(
                      event
                        .target
                        .value
                    )
                }
                required
              />

            </label>


            {error && (

              <p
                role="alert"
                style={{
                  color:
                    "#ffb39d",
                }}
              >
                {error}
              </p>

            )}


            <button
              className="intake-primary"
              disabled={
                submitting
              }
              type="submit"
            >

              {submitting
                ? "VERIFYING..."
                : responder
                  ? "OPEN RESPONDER PORTAL"
                  : "OPEN COMMAND CENTER"}

            </button>

          </form>


          <p>

            <a href="/report">
              RETURN TO PUBLIC REPORTING
            </a>

          </p>

        </section>

      </main>
    );
  }


  // ==========================================================
  // AUTHENTICATED
  // ==========================================================

  return (

    <>

      <button

        type="button"

        onClick={
          () => {

            clearCommandToken();


            if (
              responder
            ) {

              sessionStorage
                .removeItem(
                  "aegis_unit"
                );
            }


            setAuthenticated(
              false
            );


            setAuthenticatedRole(
              ""
            );
          }
        }

        style={{
          position:
            "fixed",

          right:
            18,

          bottom:
            18,

          zIndex:
            10000,

          padding:
            "9px 14px",
        }}
      >

        {responder
          ? "RESPONDER SIGN OUT"
          : "COMMAND SIGN OUT"}

      </button>


      {children}

    </>
  );
}
