import os
import json
import math
import sqlite3
import threading
import uuid

from datetime import datetime, timezone
from pathlib import Path


# ============================================================
# DATABASE LOCATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = PROJECT_ROOT / "data"

DATA_DIR.mkdir(
    parents=True,
    exist_ok=True
)

DB_PATH = (PROJECT_ROOT / os.getenv("AEGIS_DB_PATH", "data/aegis.db")).resolve()
if not DB_PATH.is_relative_to(PROJECT_ROOT):
    raise ValueError("AEGIS_DB_PATH must stay inside the project directory")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

WRITE_LOCK = threading.RLock()


# ============================================================
# CONNECTION
# ============================================================

class ClosingConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def get_connection():

    connection = sqlite3.connect(
        DB_PATH,
        timeout=30,
        factory=ClosingConnection
    )

    connection.row_factory = sqlite3.Row

    connection.execute(
        "PRAGMA foreign_keys = ON;"
    )

    connection.execute(
        "PRAGMA journal_mode = WAL;"
    )

    return connection


# ============================================================
# BASIC HELPERS
# ============================================================

def now_iso():

    return datetime.now(
        timezone.utc
    ).isoformat()


def generate_report_id():

    timestamp = datetime.now(
        timezone.utc
    ).strftime(
        "%Y%m%d%H%M%S"
    )

    suffix = (
        uuid.uuid4()
        .hex[:6]
        .upper()
    )

    return (
        f"AEGIS-{timestamp}-{suffix}"
    )


def generate_assignment_id():

    return (
        "ASN-"
        +
        uuid.uuid4()
        .hex[:10]
        .upper()
    )


def generate_fusion_id():

    return (
        "FUS-"
        +
        uuid.uuid4()
        .hex[:12]
        .upper()
    )


def generate_event_id():

    return (
        "EVT-"
        +
        uuid.uuid4()
        .hex[:12]
        .upper()
    )


def _table_columns(
    connection,
    table_name
):

    rows = connection.execute(
        f"PRAGMA table_info({table_name});"
    ).fetchall()

    return {
        row["name"]
        for row in rows
    }


def _ensure_column(
    connection,
    table_name,
    column_name,
    definition
):

    if (
        column_name
        not in
        _table_columns(
            connection,
            table_name
        )
    ):

        connection.execute(
            f"""
            ALTER TABLE {table_name}
            ADD COLUMN {column_name}
            {definition};
            """
        )


def _parse_iso(
    value
):

    try:

        parsed = datetime.fromisoformat(
            value
        )

        if (
            parsed.tzinfo is None
        ):

            parsed = parsed.replace(
                tzinfo=timezone.utc
            )

        return parsed.astimezone(
            timezone.utc
        )

    except Exception:

        return None


# ============================================================
# DISTANCE
# ============================================================

def _haversine_km(
    lat1,
    lon1,
    lat2,
    lon2
):

    radius = 6371.0

    first_lat = math.radians(
        float(lat1)
    )

    second_lat = math.radians(
        float(lat2)
    )

    delta_lat = math.radians(
        float(lat2)
        -
        float(lat1)
    )

    delta_lon = math.radians(
        float(lon2)
        -
        float(lon1)
    )

    value = (
        math.sin(
            delta_lat / 2
        ) ** 2
        +
        math.cos(
            first_lat
        )
        *
        math.cos(
            second_lat
        )
        *
        math.sin(
            delta_lon / 2
        ) ** 2
    )

    return (
        radius
        *
        2
        *
        math.atan2(
            math.sqrt(
                value
            ),
            math.sqrt(
                1 - value
            )
        )
    )


# ============================================================
# LOCATION SIMILARITY
# ============================================================

def _location_similarity(
    first,
    second
):

    def tokens(
        value
    ):

        normalized = "".join(
            character.lower()
            if character.isalnum()
            else " "

            for character
            in str(
                value
            )
        )

        return {
            token

            for token
            in normalized.split()

            if len(
                token
            ) >= 3
        }


    first_tokens = tokens(
        first
    )

    second_tokens = tokens(
        second
    )


    if (
        not first_tokens
        or
        not second_tokens
    ):

        return 0.0


    common = len(
        first_tokens
        &
        second_tokens
    )


    return (
        common
        /
        max(
            len(
                first_tokens
            ),
            len(
                second_tokens
            )
        )
    )


# ============================================================
# RESOURCE CAPABILITY
# ============================================================

def _capability_from_type(
    value
):

    text = (
        str(
            value
        )
        .lower()
        .replace(
            "_",
            " "
        )
        .replace(
            "-",
            " "
        )
    )


    if (
        "ambulance"
        in text
        or
        "medical"
        in text
        or
        "ems"
        in text
    ):

        return "AMBULANCE"


    if (
        "police"
        in text
        or
        "security"
        in text
    ):

        return "POLICE"


    if (
        "fire"
        in text
    ):

        return "FIRE"


    if (
        "boat"
        in text
        or
        "marine"
        in text
        or
        "water rescue"
        in text
    ):

        return "BOAT"


    if (
        "rescue"
        in text
    ):

        return "RESCUE"


    if (
        "drone"
        in text
    ):

        return "DRONE"


    return "OTHER"


# ============================================================
# RESOURCE CATALOG
# ============================================================

def _resource_catalog_paths():

    backend_dir = (
        Path(
            __file__
        )
        .resolve()
        .parent
    )


    return [
        (
            backend_dir
            /
            "data"
            /
            "resources.json"
        ),

        (
            DATA_DIR
            /
            "resources.json"
        ),
    ]


def _load_resource_catalog():

    for path in (
        _resource_catalog_paths()
    ):

        if (
            not path.exists()
        ):

            continue


        try:

            payload = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )


            if (
                isinstance(
                    payload,
                    list
                )
            ):

                return payload

        except Exception:

            continue


    return []


# ============================================================
# INITIALIZE DATABASE
# SAFE MIGRATION — EXISTING DATA IS PRESERVED
# ============================================================

def init_db():

    with get_connection() as connection:

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS reports (

                id TEXT PRIMARY KEY,

                fusion_id TEXT,

                source TEXT NOT NULL,

                raw_content TEXT NOT NULL DEFAULT '',

                phone TEXT NOT NULL DEFAULT '',

                incident_type TEXT NOT NULL,

                location TEXT NOT NULL,

                latitude REAL NOT NULL,

                longitude REAL NOT NULL,

                people_affected INTEGER NOT NULL,

                hazard_intensity REAL NOT NULL,

                description TEXT NOT NULL DEFAULT '',

                vulnerable_groups_json
                    TEXT NOT NULL
                    DEFAULT '[]',

                gps_verified INTEGER
                    NOT NULL
                    DEFAULT 0,

                spreading INTEGER
                    NOT NULL
                    DEFAULT 0,

                structural_damage INTEGER
                    NOT NULL
                    DEFAULT 0,

                status TEXT
                    NOT NULL
                    DEFAULT 'REPORTED',

                analysis_json TEXT NOT NULL,

                created_at TEXT NOT NULL,

                updated_at TEXT NOT NULL
            );
            """
        )


        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS assignments (

                id TEXT PRIMARY KEY,

                report_id TEXT NOT NULL,

                resource_id TEXT NOT NULL,

                resource_name TEXT NOT NULL,

                resource_type TEXT NOT NULL,

                start_latitude REAL NOT NULL,

                start_longitude REAL NOT NULL,

                distance_km REAL NOT NULL,

                eta_minutes INTEGER NOT NULL,

                status TEXT
                    NOT NULL
                    DEFAULT 'ASSIGNED',

                replaces_assignment_id TEXT,

                replaced_by_assignment_id TEXT,

                assigned_at TEXT NOT NULL,

                updated_at TEXT NOT NULL,

                FOREIGN KEY(report_id)
                    REFERENCES reports(id)
                    ON DELETE CASCADE,

                UNIQUE(
                    report_id,
                    resource_id
                )
            );
            """
        )


        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_events (

                id TEXT PRIMARY KEY,

                report_id TEXT,

                assignment_id TEXT,

                fusion_id TEXT,

                event_type TEXT NOT NULL,

                actor TEXT NOT NULL,

                message TEXT NOT NULL,

                metadata_json TEXT
                    NOT NULL
                    DEFAULT '{}',

                created_at TEXT NOT NULL,

                FOREIGN KEY(report_id)
                    REFERENCES reports(id)
                    ON DELETE CASCADE
            );
            """
        )


        # --------------------------------------------
        # Upgrade old databases safely.
        # --------------------------------------------

        _ensure_column(
            connection,
            "reports",
            "fusion_id",
            "TEXT"
        )


        _ensure_column(
            connection,
            "assignments",
            "replaces_assignment_id",
            "TEXT"
        )


        _ensure_column(
            connection,
            "assignments",
            "replaced_by_assignment_id",
            "TEXT"
        )


        # --------------------------------------------
        # Indexes
        # --------------------------------------------

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_reports_created_at
            ON reports(created_at);
            """
        )


        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_reports_status
            ON reports(status);
            """
        )


        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_reports_fusion
            ON reports(fusion_id);
            """
        )


        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_assignments_resource
            ON assignments(resource_id);
            """
        )


        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_assignments_report
            ON assignments(report_id);
            """
        )


        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_audit_report
            ON audit_events(report_id);
            """
        )


        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_audit_assignment
            ON audit_events(assignment_id);
            """
        )


        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_audit_fusion
            ON audit_events(fusion_id);
            """
        )


        # --------------------------------------------
        # Give old reports a fusion identity.
        # --------------------------------------------

        legacy_rows = connection.execute(
            """
            SELECT id

            FROM reports

            WHERE
                fusion_id IS NULL
                OR
                TRIM(fusion_id) = '';
            """
        ).fetchall()


        for row in legacy_rows:

            connection.execute(
                """
                UPDATE reports

                SET fusion_id = ?

                WHERE id = ?;
                """,

                (
                    generate_fusion_id(),

                    row[
                        "id"
                    ],
                )
            )

    with get_connection() as connection:
        _ensure_column(connection, "assignments", "departed_at", "TEXT")
        _ensure_column(connection, "reports", "injured", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(connection, "reports", "trapped", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(connection, "reports", "intake_json", "TEXT")


# ============================================================
# REPORT DECODING
# ============================================================

def decode_report(
    row
):

    if (
        row is None
    ):

        return None


    report = dict(
        row
    )
    report["intake"] = json.loads(report.pop("intake_json", None) or "null")


    try:

        report[
            "vulnerable_groups"
        ] = json.loads(
            report.pop(
                "vulnerable_groups_json"
            )
        )

    except Exception:

        report[
            "vulnerable_groups"
        ] = []


    try:

        report[
            "analysis"
        ] = json.loads(
            report.pop(
                "analysis_json"
            )
        )

    except Exception:

        report[
            "analysis"
        ] = {}


    report[
        "gps_verified"
    ] = bool(
        report[
            "gps_verified"
        ]
    )


    report[
        "spreading"
    ] = bool(
        report[
            "spreading"
        ]
    )


    report[
        "structural_damage"
    ] = bool(
        report[
            "structural_damage"
        ]
    )


    return report


# ============================================================
# AUDIT DECODING
# ============================================================

def decode_audit_event(
    row
):

    if (
        row is None
    ):

        return None


    event = dict(
        row
    )


    try:

        event[
            "metadata"
        ] = json.loads(
            event.pop(
                "metadata_json"
            )
        )

    except Exception:

        event[
            "metadata"
        ] = {}


    return event


# ============================================================
# AUDIT INTERNAL
# ============================================================

def _insert_audit_event(
    connection,
    *,
    report_id=None,
    assignment_id=None,
    fusion_id=None,
    event_type,
    actor,
    message,
    metadata=None,
    created_at=None,
):

    event_id = (
        generate_event_id()
    )


    timestamp = (
        created_at
        or
        now_iso()
    )


    connection.execute(
        """
        INSERT INTO audit_events (

            id,

            report_id,

            assignment_id,

            fusion_id,

            event_type,

            actor,

            message,

            metadata_json,

            created_at
        )

        VALUES (
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?
        );
        """,

        (
            event_id,

            report_id,

            assignment_id,

            fusion_id,

            event_type,

            actor,

            message,

            json.dumps(
                metadata
                or
                {}
            ),

            timestamp
        )
    )


    return event_id


# ============================================================
# PUBLIC AUDIT CREATION
# ============================================================

def create_audit_event(
    *,
    report_id=None,
    assignment_id=None,
    fusion_id=None,
    event_type,
    actor="SYSTEM",
    message="",
    metadata=None,
):

    with WRITE_LOCK:

        with get_connection() as connection:

            event_id = (
                _insert_audit_event(
                    connection,

                    report_id=report_id,

                    assignment_id=
                        assignment_id,

                    fusion_id=
                        fusion_id,

                    event_type=
                        event_type,

                    actor=
                        actor,

                    message=
                        message,

                    metadata=
                        metadata,
                )
            )


    with get_connection() as connection:

        row = connection.execute(
            """
            SELECT *

            FROM audit_events

            WHERE id = ?;
            """,

            (
                event_id,
            )
        ).fetchone()


    return decode_audit_event(
        row
    )


# ============================================================
# AUTOMATIC FUSION MATCHING
# ============================================================

def _find_fusion_candidate(
    connection,
    payload,
    timestamp
):

    incident_type = str(
        payload.get(
            "incident_type",
            ""
        )
    ).strip()


    if (
        not incident_type
    ):

        return None


    rows = connection.execute(
        """
        SELECT *

        FROM reports

        WHERE
            incident_type = ?
            AND
            status != 'RESOLVED'

        ORDER BY created_at DESC

        LIMIT 100;
        """,

        (
            incident_type,
        )
    ).fetchall()


    current_time = (
        _parse_iso(
            timestamp
        )
    )


    if (
        current_time is None
    ):

        return None


    latitude = float(
        payload.get(
            "latitude",
            0
        )
    )


    longitude = float(
        payload.get(
            "longitude",
            0
        )
    )


    location = str(
        payload.get(
            "location",
            ""
        )
    )


    source = str(
        payload.get(
            "source",
            "APP"
        )
    )


    gps_verified = bool(
        payload.get(
            "gps_verified",
            False
        )
    )


    best = None


    for row in rows:

        candidate = dict(
            row
        )


        created = _parse_iso(
            candidate[
                "created_at"
            ]
        )


        if (
            created is None
        ):

            continue


        age_minutes = abs(
            (
                current_time
                -
                created
            ).total_seconds()
        ) / 60


        if (
            age_minutes >
            90
        ):

            continue


        distance = _haversine_km(
            latitude,
            longitude,

            candidate[
                "latitude"
            ],

            candidate[
                "longitude"
            ]
        )


        location_score = (
            _location_similarity(
                location,

                candidate[
                    "location"
                ]
            )
        )


        qualifies = (
            distance <=
            3.0

            or

            (
                distance <=
                5.0

                and

                location_score >=
                0.55
            )
        )


        if (
            not qualifies
        ):

            continue


        score = 0.0


        if (
            distance <=
            1.0
        ):

            score += 60

        elif (
            distance <=
            3.0
        ):

            score += 45

        else:

            score += 20


        score += (
            location_score
            *
            25
        )


        if (
            age_minutes <=
            30
        ):

            score += 15

        else:

            score += 8


        if (
            source !=
            candidate[
                "source"
            ]
        ):

            score += 5


        if (
            gps_verified
            or
            bool(
                candidate[
                    "gps_verified"
                ]
            )
        ):

            score += 5


        score = min(
            100,
            round(
                score
            )
        )


        if (
            score <
            45
        ):

            continue


        item = {

            "report_id":
                candidate[
                    "id"
                ],

            "fusion_id":
                candidate[
                    "fusion_id"
                ],

            "score":
                score,

            "distance_km":
                round(
                    distance,
                    3
                ),

            "age_minutes":
                round(
                    age_minutes,
                    1
                ),
        }


        if (
            best is None
            or
            item[
                "score"
            ]
            >
            best[
                "score"
            ]
        ):

            best = item


    return best


# ============================================================
# CREATE REPORT
# ============================================================

def create_report(
    payload,
    analysis
):

    report_id = (
        generate_report_id()
    )


    timestamp = (
        now_iso()
    )


    with WRITE_LOCK:

        with get_connection() as connection:

            fusion_match = (
                _find_fusion_candidate(
                    connection,
                    payload,
                    timestamp
                )
            )


            fusion_id = (
                fusion_match[
                    "fusion_id"
                ]

                if fusion_match

                else

                generate_fusion_id()
            )


            connection.execute(
                """
                INSERT INTO reports (

                    id,

                    fusion_id,

                    source,

                    raw_content,

                    phone,

                    incident_type,

                    location,

                    latitude,

                    longitude,

                    people_affected,

                    hazard_intensity,

                    description,

                    vulnerable_groups_json,

                    gps_verified,

                    spreading,

                    structural_damage,

                    status,

                    analysis_json,

                    created_at,

                    updated_at
                )

                VALUES (
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?
                );
                """,

                (
                    report_id,

                    fusion_id,

                    payload.get(
                        "source",
                        "APP"
                    ),

                    payload.get(
                        "raw_content",
                        ""
                    ),

                    payload.get(
                        "phone",
                        ""
                    ),

                    payload[
                        "incident_type"
                    ],

                    payload[
                        "location"
                    ],

                    payload[
                        "latitude"
                    ],

                    payload[
                        "longitude"
                    ],

                    payload[
                        "people_affected"
                    ],

                    payload[
                        "hazard_intensity"
                    ],

                    payload.get(
                        "description",
                        ""
                    ),

                    json.dumps(
                        payload.get(
                            "vulnerable_groups",
                            []
                        )
                    ),

                    int(
                        payload.get(
                            "gps_verified",
                            False
                        )
                    ),

                    int(
                        payload.get(
                            "spreading",
                            False
                        )
                    ),

                    int(
                        payload.get(
                            "structural_damage",
                            False
                        )
                    ),

                    "REPORTED",

                    json.dumps(
                        analysis
                    ),

                    timestamp,

                    timestamp
                )
            )


            _insert_audit_event(
                connection,

                report_id=
                    report_id,

                fusion_id=
                    fusion_id,

                event_type=
                    "REPORT_CREATED",

                actor=
                    payload.get(
                        "source",
                        "APP"
                    ),

                message=(
                    f"{payload.get('source', 'APP')} "
                    "emergency report received."
                ),

                metadata={

                    "incident_type":
                        payload[
                            "incident_type"
                        ],

                    "location":
                        payload[
                            "location"
                        ],

                    "people_affected":
                        payload[
                            "people_affected"
                        ],

                    "gps_verified":
                        bool(
                            payload.get(
                                "gps_verified",
                                False
                            )
                        ),
                },

                created_at=
                    timestamp,
            )


            if (
                fusion_match
            ):

                _insert_audit_event(
                    connection,

                    report_id=
                        report_id,

                    fusion_id=
                        fusion_id,

                    event_type=
                        "REPORT_FUSED",

                    actor=
                        "FUSION_ENGINE",

                    message=(
                        "Report linked to "
                        "existing incident "
                        f"fusion group {fusion_id}."
                    ),

                    metadata={

                        "matched_report_id":
                            fusion_match[
                                "report_id"
                            ],

                        "match_score":
                            fusion_match[
                                "score"
                            ],

                        "distance_km":
                            fusion_match[
                                "distance_km"
                            ],

                        "age_minutes":
                            fusion_match[
                                "age_minutes"
                            ],
                    },

                    created_at=
                        timestamp,
                )


    return get_report(
        report_id
    )


# ============================================================
# GET REPORT
# ============================================================

def get_report(
    report_id
):

    with get_connection() as connection:

        row = connection.execute(
            """
            SELECT *

            FROM reports

            WHERE id = ?;
            """,

            (
                report_id,
            )
        ).fetchone()


    return decode_report(
        row
    )


# ============================================================
# LIST REPORTS
# ============================================================

def list_reports(
    limit=100
):

    safe_limit = max(
        1,

        min(
            int(
                limit
            ),
            500
        )
    )


    with get_connection() as connection:

        rows = connection.execute(
            """
            SELECT *

            FROM reports

            ORDER BY created_at DESC

            LIMIT ?;
            """,

            (
                safe_limit,
            )
        ).fetchall()


    return [
        decode_report(
            row
        )

        for row
        in rows
    ]


# ============================================================
# LIST REPORTS IN ONE FUSION GROUP
# ============================================================

def list_fusion_reports(
    fusion_id,
    limit=200
):

    safe_limit = max(
        1,

        min(
            int(
                limit
            ),
            500
        )
    )


    with get_connection() as connection:

        rows = connection.execute(
            """
            SELECT *

            FROM reports

            WHERE fusion_id = ?

            ORDER BY created_at ASC

            LIMIT ?;
            """,

            (
                fusion_id,
                safe_limit,
            )
        ).fetchall()


    return [
        decode_report(
            row
        )

        for row
        in rows
    ]


# ============================================================
# UPDATE REPORT STATUS
# ============================================================

def update_report_status(report_id, status, actor="SYSTEM", message=None):
    """Compatibility entrypoint; all incident transitions use the shared validator."""
    from operations import set_report_status
    return set_report_status(report_id, status)


# ============================================================
# CREATE RESOURCE ASSIGNMENTS
# ============================================================

def create_assignments_for_report(report_id, actor="COMMAND"):
    """Compatibility entrypoint using the same atomic dispatch service as the API."""
    from operations import dispatch
    result = dispatch(report_id)
    return result["assignments"] if result else []


# ============================================================
# LIST ASSIGNMENTS
# ============================================================

def list_assignments(
    resource_id=None,
    report_id=None,
    limit=200
):

    safe_limit = max(
        1,

        min(
            int(
                limit
            ),
            500
        )
    )


    conditions = []

    values = []


    if (
        resource_id
    ):

        conditions.append(
            "resource_id = ?"
        )

        values.append(
            resource_id
        )


    if (
        report_id
    ):

        conditions.append(
            "report_id = ?"
        )

        values.append(
            report_id
        )


    where_clause = ""


    if (
        conditions
    ):

        where_clause = (
            "WHERE "
            +
            " AND ".join(
                conditions
            )
        )


    values.append(
        safe_limit
    )


    query = f"""
        SELECT *

        FROM assignments

        {where_clause}

        ORDER BY assigned_at DESC

        LIMIT ?;
    """


    with get_connection() as connection:

        rows = connection.execute(
            query,
            tuple(
                values
            )
        ).fetchall()


    return [
        dict(
            row
        )

        for row
        in rows
    ]


# ============================================================
# GET ASSIGNMENT
# ============================================================

def get_assignment(
    assignment_id
):

    with get_connection() as connection:

        row = connection.execute(
            """
            SELECT *

            FROM assignments

            WHERE id = ?;
            """,

            (
                assignment_id,
            )
        ).fetchone()


    if (
        row is None
    ):

        return None


    return dict(
        row
    )


# ============================================================
# UPDATE ASSIGNMENT STATUS
# ============================================================

def update_assignment_status(assignment_id, status, actor="RESPONDER"):
    """Compatibility entrypoint preserving status/arrival validation."""
    from operations import set_assignment_status
    return set_assignment_status(assignment_id, status)


# ============================================================
# REAL BACKUP / REASSIGNMENT
# ============================================================

def reassign_assignment(
    assignment_id,
    reason="UNIT_ISSUE",
    actor="COMMAND",
):

    timestamp = (
        now_iso()
    )


    with WRITE_LOCK:

        with get_connection() as connection:

            connection.execute("BEGIN IMMEDIATE")

            original_row = (
                connection.execute(
                    """
                    SELECT *

                    FROM assignments

                    WHERE id = ?;
                    """,

                    (
                        assignment_id,
                    )
                )
                .fetchone()
            )


            if (
                original_row is None
            ):

                return None


            original = dict(
                original_row
            )


            if (
                original[
                    "status"
                ]
                !=
                "ISSUE"
            ):

                raise ValueError(
                    "Assignment must be "
                    "in ISSUE state before "
                    "reassignment."
                )


            # ------------------------------------------------
            # Already reassigned?
            # ------------------------------------------------

            if (
                original.get(
                    "replaced_by_assignment_id"
                )
            ):

                replacement_row = (
                    connection.execute(
                        """
                        SELECT *

                        FROM assignments

                        WHERE id = ?;
                        """,

                        (
                            original[
                                "replaced_by_assignment_id"
                            ],
                        )
                    )
                    .fetchone()
                )


                return {

                    "original_assignment":
                        original,

                    "replacement_assignment":
                        (
                            dict(
                                replacement_row
                            )

                            if replacement_row

                            else None
                        ),

                    "already_reassigned":
                        True,

                    "reason":
                        reason,
                }


            # ------------------------------------------------
            # Load incident.
            # ------------------------------------------------

            report_row = (
                connection.execute(
                    """
                    SELECT *

                    FROM reports

                    WHERE id = ?;
                    """,

                    (
                        original[
                            "report_id"
                        ],
                    )
                )
                .fetchone()
            )


            if (
                report_row is None
            ):

                raise RuntimeError(
                    "Incident report "
                    "no longer exists."
                )


            report = decode_report(
                report_row
            )


            required_capability = (
                _capability_from_type(
                    original[
                        "resource_type"
                    ]
                )
            )


            # ------------------------------------------------
            # Resources already active anywhere.
            # ------------------------------------------------

            active_resource_rows = (
                connection.execute(
                    """
                    SELECT DISTINCT
                        resource_id

                    FROM assignments

                    WHERE status != 'RESOLVED';
                    """
                )
                .fetchall()
            )


            busy_resource_ids = {

                row[
                    "resource_id"
                ]

                for row
                in active_resource_rows
            }


            # ------------------------------------------------
            # UNIQUE(report_id, resource_id) means a resource
            # already used on this report cannot be inserted
            # again.
            # ------------------------------------------------

            already_used_rows = (
                connection.execute(
                    """
                    SELECT
                        resource_id

                    FROM assignments

                    WHERE report_id = ?;
                    """,

                    (
                        original[
                            "report_id"
                        ],
                    )
                )
                .fetchall()
            )


            already_used_ids = {

                row[
                    "resource_id"
                ]

                for row
                in already_used_rows
            }


            catalog = (
                _load_resource_catalog()
            )


            candidates = []


            for resource in catalog:

                resource_id = str(
                    resource.get(
                        "id",
                        ""
                    )
                )


                if (
                    not resource_id
                ):

                    continue


                if (
                    resource_id ==
                    original[
                        "resource_id"
                    ]
                ):

                    continue


                if (
                    resource_id
                    in
                    busy_resource_ids
                ):

                    continue


                if (
                    resource_id
                    in
                    already_used_ids
                ):

                    continue


                if (
                    str(
                        resource.get(
                            "status",
                            "AVAILABLE"
                        )
                    ).upper()
                    !=
                    "AVAILABLE"
                ):

                    continue


                if (
                    _capability_from_type(
                        resource.get(
                            "type",
                            ""
                        )
                    )
                    !=
                    required_capability
                ):

                    continue


                try:

                    distance = (
                        _haversine_km(

                            report[
                                "latitude"
                            ],

                            report[
                                "longitude"
                            ],

                            float(
                                resource.get(
                                    "latitude",
                                    0
                                )
                            ),

                            float(
                                resource.get(
                                    "longitude",
                                    0
                                )
                            )
                        )
                    )

                except Exception:

                    continue


                candidates.append({

                    "resource":
                        resource,

                    "distance_km":
                        distance,
                })


            candidates.sort(
                key=lambda item:
                    item[
                        "distance_km"
                    ]
            )


            if (
                not candidates
            ):

                raise RuntimeError(
                    "No compatible AVAILABLE "
                    "backup resource found."
                )


            selected = (
                candidates[0]
            )


            resource = (
                selected[
                    "resource"
                ]
            )


            distance = round(
                float(
                    selected[
                        "distance_km"
                    ]
                ),
                3
            )


            eta_minutes = max(
                1,

                round(
                    distance
                    *
                    2.4
                )
            )


            replacement_id = (
                generate_assignment_id()
            )


            # ------------------------------------------------
            # Create new real assignment.
            # ------------------------------------------------

            connection.execute(
                """
                INSERT INTO assignments (

                    id,

                    report_id,

                    resource_id,

                    resource_name,

                    resource_type,

                    start_latitude,

                    start_longitude,

                    distance_km,

                    eta_minutes,

                    status,

                    replaces_assignment_id,

                    replaced_by_assignment_id,

                    assigned_at,

                    updated_at
                )

                VALUES (
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?
                );
                """,

                (
                    replacement_id,

                    original[
                        "report_id"
                    ],

                    resource[
                        "id"
                    ],

                    resource.get(
                        "name",
                        resource[
                            "id"
                        ]
                    ),

                    resource.get(
                        "type",

                        original[
                            "resource_type"
                        ]
                    ),

                    float(
                        resource.get(
                            "latitude",
                            0
                        )
                    ),

                    float(
                        resource.get(
                            "longitude",
                            0
                        )
                    ),

                    distance,

                    eta_minutes,

                    "ASSIGNED",

                    assignment_id,

                    None,

                    timestamp,

                    timestamp
                )
            )


            # ------------------------------------------------
            # Link original → replacement.
            # ------------------------------------------------

            connection.execute(
                """
                UPDATE assignments

                SET
                    replaced_by_assignment_id = ?,
                    updated_at = ?

                WHERE id = ?;
                """,

                (
                    replacement_id,

                    timestamp,

                    assignment_id,
                )
            )


            # ------------------------------------------------
            # Persistent audit trail.
            # ------------------------------------------------

            _insert_audit_event(
                connection,

                report_id=
                    original[
                        "report_id"
                    ],

                assignment_id=
                    replacement_id,

                fusion_id=
                    report.get(
                        "fusion_id"
                    ),

                event_type=
                    "ASSIGNMENT_REASSIGNED",

                actor=
                    actor,

                message=(
                    f"{original['resource_id']} "
                    f"replaced by {resource['id']} "
                    "after responder issue."
                ),

                metadata={

                    "old_assignment_id":
                        assignment_id,

                    "old_resource_id":
                        original[
                            "resource_id"
                        ],

                    "new_assignment_id":
                        replacement_id,

                    "new_resource_id":
                        resource[
                            "id"
                        ],

                    "resource_type":
                        resource.get(
                            "type",
                            "UNKNOWN"
                        ),

                    "reason":
                        reason,

                    "distance_km":
                        distance,

                    "eta_minutes":
                        eta_minutes,

                    "selection":
                        (
                            "NEAREST_AVAILABLE_"
                            "COMPATIBLE_RESOURCE"
                        ),
                },

                created_at=
                    timestamp,
            )


            replacement_row = (
                connection.execute(
                    """
                    SELECT *

                    FROM assignments

                    WHERE id = ?;
                    """,

                    (
                        replacement_id,
                    )
                )
                .fetchone()
            )


            updated_original_row = (
                connection.execute(
                    """
                    SELECT *

                    FROM assignments

                    WHERE id = ?;
                    """,

                    (
                        assignment_id,
                    )
                )
                .fetchone()
            )


            return {

                "original_assignment":
                    dict(
                        updated_original_row
                    ),

                "replacement_assignment":
                    dict(
                        replacement_row
                    ),

                "already_reassigned":
                    False,

                "reason":
                    reason,
            }


# ============================================================
# LIST AUDIT EVENTS
# ============================================================

def list_audit_events(
    report_id=None,
    assignment_id=None,
    fusion_id=None,
    limit=300
):

    safe_limit = max(
        1,

        min(
            int(
                limit
            ),
            1000
        )
    )


    conditions = []

    values = []


    if (
        report_id
    ):

        conditions.append(
            "report_id = ?"
        )

        values.append(
            report_id
        )


    if (
        assignment_id
    ):

        conditions.append(
            "assignment_id = ?"
        )

        values.append(
            assignment_id
        )


    if (
        fusion_id
    ):

        conditions.append(
            "fusion_id = ?"
        )

        values.append(
            fusion_id
        )


    where_clause = ""


    if (
        conditions
    ):

        where_clause = (
            "WHERE "
            +
            " AND ".join(
                conditions
            )
        )


    values.append(
        safe_limit
    )


    query = f"""
        SELECT *

        FROM audit_events

        {where_clause}

        ORDER BY created_at DESC

        LIMIT ?;
    """


    with get_connection() as connection:

        rows = connection.execute(
            query,
            tuple(
                values
            )
        ).fetchall()


    return [
        decode_audit_event(
            row
        )

        for row
        in rows
    ]


# ============================================================
# CLEAR DEMO
# ============================================================

def clear_reports():

    with WRITE_LOCK:

        with get_connection() as connection:

            connection.execute(
                """
                DELETE FROM audit_events;
                """
            )


            # Assignments are deleted automatically
            # by ON DELETE CASCADE.

            cursor = connection.execute(
                """
                DELETE FROM reports;
                """
            )


            return cursor.rowcount
