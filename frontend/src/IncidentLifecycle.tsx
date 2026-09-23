import type {
  Assignment,
  SharedReport,
} from "./api";


type Props = {
  report: SharedReport;
  assignments: Assignment[];
  audience?: "COMMAND" | "RESPONDER";
  compact?: boolean;
};


const STEPS = [
  "REPORT RECEIVED",
  "ANALYSIS COMPLETE",
  "AWAITING APPROVAL",
  "DISPATCHED",
  "EN ROUTE",
  "ON SCENE",
  "RESOLVED",
] as const;


function getLifecycleIndex(
  report: SharedReport,
  assignments: Assignment[]
): number {

  const activeAssignments =
    assignments.filter(
      assignment =>
        !assignment.replaced_by_assignment_id
    );


  if (
    report.status === "RESOLVED" ||
    (
      activeAssignments.length > 0 &&
      activeAssignments.every(
        assignment =>
          assignment.status === "RESOLVED"
      )
    )
  ) {
    return 6;
  }


  if (
    report.status === "ON_SCENE" ||
    activeAssignments.some(
      assignment =>
        assignment.status === "ON_SCENE" ||
        assignment.status === "RESOLVED"
    )
  ) {
    return 5;
  }


  if (
    report.status === "EN_ROUTE" ||
    activeAssignments.some(
      assignment =>
        assignment.status === "EN_ROUTE"
    )
  ) {
    return 4;
  }


  if (
    report.status === "DISPATCHED" ||
    activeAssignments.length > 0
  ) {
    return 3;
  }


  /*
   * Stored reports already contain
   * completed AEGIS analysis.
   *
   * Therefore REPORTED means:
   *
   * REPORT RECEIVED
   *      ↓
   * ANALYSIS COMPLETE
   *      ↓
   * AWAITING AUTHORITY APPROVAL
   */

  return 2;
}


function displayReportStatus(
  report: SharedReport
): string {

  if (
    report.status === "REPORTED" ||
    report.status === "ACKNOWLEDGED"
  ) {
    return "AWAITING AUTHORITY APPROVAL";
  }


  return report.status.replaceAll(
    "_",
    " "
  );
}


export default function IncidentLifecycle({
  report,
  assignments,
  audience = "COMMAND",
  compact = false,
}: Props) {

  const activeAssignments =
    assignments.filter(
      assignment =>
        !assignment.replaced_by_assignment_id
    );


  const currentIndex =
    getLifecycleIndex(
      report,
      activeAssignments
    );


  const assignedCount =
    activeAssignments.filter(
      assignment =>
        assignment.status === "ASSIGNED"
    ).length;


  const acceptedCount =
    activeAssignments.filter(
      assignment =>
        assignment.status === "ACCEPTED"
    ).length;


  const enRouteCount =
    activeAssignments.filter(
      assignment =>
        assignment.status === "EN_ROUTE"
    ).length;


  const onSceneCount =
    activeAssignments.filter(
      assignment =>
        assignment.status === "ON_SCENE"
    ).length;


  const resolvedCount =
    activeAssignments.filter(
      assignment =>
        assignment.status === "RESOLVED"
    ).length;


  const issueCount =
    activeAssignments.filter(
      assignment =>
        assignment.status === "ISSUE"
    ).length;


  return (

    <section
      className={
        compact
          ? "incident-lifecycle compact"
          : "incident-lifecycle"
      }
      aria-label="Incident response lifecycle"
    >

      <div className="lifecycle-heading">

        <div>

          <small>

            {audience === "COMMAND"
              ? "INCIDENT RESPONSE LIFECYCLE"
              : "FIELD RESPONSE LIFECYCLE"}

          </small>


          <strong>

            {STEPS[currentIndex]}

          </strong>

        </div>


        <div className="lifecycle-badges">

          {report.fusion_id && (

            <span className="lifecycle-fusion">

              FUSION{" "}

              {report.fusion_id}

            </span>

          )}


          <span
            className={
              report.status === "RESOLVED"
                ? "lifecycle-state resolved"
                : "lifecycle-state active"
            }
          >

            {displayReportStatus(
              report
            )}

          </span>

        </div>

      </div>


      <div className="lifecycle-track">

        {STEPS.map(
          (
            step,
            index
          ) => {

            const stepState =
              index < currentIndex
                ? "done"
                : index === currentIndex
                  ? "current"
                  : "future";


            return (

              <div
                key={step}
                className={
                  `lifecycle-step ${stepState}`
                }
              >

                <span className="lifecycle-node">

                  {index < currentIndex
                    ? "✓"
                    : index + 1}

                </span>


                <span className="lifecycle-label">

                  {step}

                </span>

              </div>

            );
          }
        )}

      </div>


      {activeAssignments.length > 0 && (

        <div className="lifecycle-unit-summary">

          <div>

            <small>
              ASSIGNED
            </small>

            <strong>
              {assignedCount}
            </strong>

          </div>


          <div>

            <small>
              ACCEPTED
            </small>

            <strong>
              {acceptedCount}
            </strong>

          </div>


          <div>

            <small>
              EN ROUTE
            </small>

            <strong>
              {enRouteCount}
            </strong>

          </div>


          <div>

            <small>
              ON SCENE
            </small>

            <strong>
              {onSceneCount}
            </strong>

          </div>


          <div>

            <small>
              RESOLVED
            </small>

            <strong>
              {resolvedCount}
            </strong>

          </div>


          <div
            className={
              issueCount > 0
                ? "issue"
                : ""
            }
          >

            <small>
              ISSUE
            </small>

            <strong>
              {issueCount}
            </strong>

          </div>

        </div>

      )}

    </section>
  );
}
