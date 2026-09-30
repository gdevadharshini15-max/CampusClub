from flask import Flask, render_template, request, redirect, url_for, session
from database import init_db, get_db_connection
from datetime import datetime
import re


app = Flask(__name__)

app.secret_key = "campusclub-secret-key"

init_db()


def ensure_extended_schema():
    """Add hackathon-specific schema without destroying existing data."""
    c = get_db_connection()
    def cols(table):
        return {r[1] for r in c.execute(f"PRAGMA table_info({table})").fetchall()}
    def addcol(table, name, definition):
        if name not in cols(table):
            c.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
    addcol("clubs", "faculty_coordinator_id", "INTEGER")
    addcol("users", "mentor_id", "INTEGER")
    addcol("club_members", "dynamic_role_id", "INTEGER")
    addcol("events", "completed_at", "TEXT")
    addcol("certificates", "participation_role", "TEXT")
    addcol("certificates", "qr_token", "TEXT")
    addcol("badges", "club_id", "INTEGER")
    addcol("badges", "criteria", "TEXT")
    c.execute("""CREATE TABLE IF NOT EXISTS club_roles (
        id INTEGER PRIMARY KEY AUTOINCREMENT, club_id INTEGER NOT NULL,
        name TEXT NOT NULL, permissions TEXT NOT NULL DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(club_id,name))""")
    c.execute("""CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT, sender_id INTEGER NOT NULL,
        recipient_id INTEGER NOT NULL, club_id INTEGER, event_id INTEGER, od_request_id INTEGER,
        body TEXT NOT NULL, is_read INTEGER DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    c.commit(); c.close()


ensure_extended_schema()


# =========================================================
# NOTIFICATION HELPER
# =========================================================

def create_notification(
    user_id,
    title,
    message,
    notification_type="INFO"
):

    connection = get_db_connection()

    connection.execute(
        """
        INSERT INTO notifications
        (
            user_id,
            title,
            message,
            notification_type
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            user_id,
            title,
            message,
            notification_type
        )
    )

    connection.commit()
    connection.close()


# =========================================================
# AUDIT LOG HELPER
# =========================================================

def create_audit_log(
    user_id,
    action,
    entity,
    entity_id=None,
    details=""
):

    connection = get_db_connection()

    connection.execute(
        """
        INSERT INTO audit_logs
        (
            user_id,
            action,
            entity,
            entity_id,
            details
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            user_id,
            action,
            entity,
            entity_id,
            details
        )
    )

    connection.commit()
    connection.close()


# =========================================================
# TIME CONVERSION HELPER
# =========================================================

def time_to_minutes(time_value):

    if not time_value:
        return 0

    time_value = str(time_value).strip()

    formats = [
        "%H:%M",
        "%I:%M %p",
        "%I:%M%p"
    ]

    for fmt in formats:

        try:

            parsed_time = datetime.strptime(
                time_value,
                fmt
            )

            return (
                parsed_time.hour * 60
                + parsed_time.minute
            )

        except ValueError:
            continue

    raise ValueError(
        f"Unsupported time format: {time_value}"
    )


# =========================================================
# TIMETABLE IMPACT HELPER
# =========================================================

def get_affected_timetable_periods(
    event_start,
    event_end,
    event_date=None
):

    try:

        event_start_minutes = time_to_minutes(
            event_start
        )

        event_end_minutes = time_to_minutes(
            event_end
        )

    except ValueError:

        return []


    connection = get_db_connection()

    periods = connection.execute(
        """
        SELECT
            timetable_periods.*,
            timetable_structures.name AS structure_name,
            timetable_structures.working_days,
            timetable_structures.effective_from
        FROM timetable_periods
        JOIN timetable_structures
        ON timetable_periods.structure_id =
           timetable_structures.id
        WHERE timetable_structures.is_active = 1
        ORDER BY timetable_periods.period_number
        """
    ).fetchall()

    connection.close()


    affected_periods = []


    # ---------------------------------------------------------
    # CHECK WORKING DAY IF EVENT DATE IS AVAILABLE
    # ---------------------------------------------------------

    event_weekday = None

    if event_date:

        try:

            parsed_date = datetime.strptime(
                event_date,
                "%Y-%m-%d"
            )

            event_weekday = parsed_date.strftime(
                "%A"
            )

        except ValueError:

            event_weekday = None


    for period in periods:

        # -----------------------------------------------------
        # WORKING DAY CHECK
        # -----------------------------------------------------

        if event_weekday:

            working_days = (
                period["working_days"] or ""
            )

            working_day_list = [
                day.strip().lower()
                for day in working_days.split(",")
            ]

            if (
                working_day_list
                and event_weekday.lower()
                not in working_day_list
            ):
                continue


        # -----------------------------------------------------
        # EFFECTIVE DATE CHECK
        # -----------------------------------------------------

        if event_date and period["effective_from"]:

            if event_date < period["effective_from"]:
                continue


        # -----------------------------------------------------
        # TIME OVERLAP
        # -----------------------------------------------------

        try:

            period_start = time_to_minutes(
                period["start_time"]
            )

            period_end = time_to_minutes(
                period["end_time"]
            )

        except ValueError:

            continue


        if (
            event_start_minutes < period_end
            and event_end_minutes > period_start
        ):

            affected_periods.append(period)


    return affected_periods


# =========================================================
# HOME
# =========================================================

@app.route("/")
def index():

    return render_template(
        "index.html"
    )


# =========================================================
# LOGIN
# =========================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if request.method == "POST":

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )


        connection = get_db_connection()


        user = connection.execute(
            """
            SELECT *
            FROM users
            WHERE LOWER(email) = ?
            AND status = 'ACTIVE'
            """,
            (email,)
        ).fetchone()


        connection.close()


        if user is None:

            return render_template(
                "login.html",
                error="Account not found or account is inactive."
            )


        if user["password"] != password:

            return render_template(
                "login.html",
                error="Incorrect password."
            )


        session["user_id"] = user["id"]

        session["user_name"] = user["name"]

        session["user_role"] = user["role"]


        return redirect(
            url_for("dashboard")
        )


    return render_template(
        "login.html"
    )


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("login")
    )


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect(url_for("login"))

    role = session.get("user_role")
    user_id = session["user_id"]

    connection = get_db_connection()

    stats = {
        "events": 0,
        "registrations": 0,
        "clubs": 0,
        "pending_events": 0,
        "pending_od": 0,
        "certificates": 0,
        "badges": 0,
        "notifications": 0
    }

    if role == "Student":
        stats["events"] = connection.execute("""
            SELECT COUNT(*)
            FROM events
            WHERE status = 'APPROVED'
        """).fetchone()[0]

        stats["registrations"] = connection.execute("""
            SELECT COUNT(*)
            FROM event_registrations
            WHERE user_id = ?
            AND status = 'REGISTERED'
        """, (user_id,)).fetchone()[0]

        stats["clubs"] = connection.execute("""
            SELECT COUNT(*)
            FROM club_members
            WHERE user_id = ?
            AND club_role = 'MEMBER'
        """, (user_id,)).fetchone()[0]

        stats["certificates"] = connection.execute("""
            SELECT COUNT(*)
            FROM certificates
            WHERE student_id = ?
        """, (user_id,)).fetchone()[0]

        stats["badges"] = connection.execute("""
            SELECT COUNT(*)
            FROM student_badges
            WHERE student_id = ?
        """, (user_id,)).fetchone()[0]

    elif role in ["Super Admin", "Admin", "Faculty"]:
        stats["events"] = connection.execute("""
            SELECT COUNT(*)
            FROM events
            WHERE status = 'APPROVED'
        """).fetchone()[0]

        stats["pending_events"] = connection.execute("""
            SELECT COUNT(*)
            FROM events
            WHERE status = 'PENDING'
        """).fetchone()[0]

        stats["pending_od"] = connection.execute("""
            SELECT COUNT(*)
            FROM od_requests
            WHERE status = 'PENDING'
        """).fetchone()[0]

        stats["clubs"] = connection.execute("""
            SELECT COUNT(*)
            FROM clubs
            WHERE status = 'ACTIVE'
        """).fetchone()[0]

    elif role == "Club Admin":
        club = connection.execute("""
            SELECT club_id
            FROM club_members
            WHERE user_id = ?
            AND club_role = 'ADMIN'
            ORDER BY id ASC
            LIMIT 1
        """, (user_id,)).fetchone()

        if club:
            club_id = club["club_id"]

            stats["events"] = connection.execute("""
                SELECT COUNT(*)
                FROM events
                WHERE club_id = ?
            """, (club_id,)).fetchone()[0]

            stats["pending_events"] = connection.execute("""
                SELECT COUNT(*)
                FROM events
                WHERE club_id = ?
                AND status = 'PENDING'
            """, (club_id,)).fetchone()[0]

            stats["clubs"] = 1

    stats["notifications"] = connection.execute("""
        SELECT COUNT(*)
        FROM notifications
        WHERE user_id = ?
    """, (user_id,)).fetchone()[0]

    connection.close()

    return render_template(
        "dashboard.html",
        role=role,
        stats=stats
    )

# =========================================================
# SUPER ADMIN - USER MANAGEMENT
# =========================================================

@app.route("/admin/users")
def manage_users():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )


    if session.get("user_role") != "Super Admin":

        return render_template(
            "access_denied.html"
        ), 403


    connection = get_db_connection()


    users = connection.execute(
        """
        SELECT
            id,
            name,
            email,
            role,
            ra_number,
            status
        FROM users
        ORDER BY id ASC
        """
    ).fetchall()


    connection.close()


    return render_template(
        "users.html",
        users=users
    )


# =========================================================
# CREATE USER
# =========================================================

@app.route(
    "/admin/users/create",
    methods=["POST"]
)
def create_user():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )


    if session.get("user_role") != "Super Admin":

        return render_template(
            "access_denied.html"
        ), 403


    name = request.form.get(
        "name",
        ""
    ).strip()


    email = request.form.get(
        "email",
        ""
    ).strip().lower()


    password = request.form.get(
        "password",
        ""
    ).strip()


    role = request.form.get(
        "role",
        ""
    ).strip()


    ra_number = request.form.get(
        "ra_number",
        ""
    ).strip()


    allowed_roles = [
        "Super Admin",
        "Admin",
        "Club Admin",
        "Faculty",
        "Student"
    ]


    # ---------------------------------------------------------
    # BASIC VALIDATION
    # ---------------------------------------------------------

    if (
        not name
        or not email
        or not password
        or role not in allowed_roles
    ):

        return redirect(
            url_for("manage_users")
        )


    # ---------------------------------------------------------
    # EMAIL VALIDATION
    # ---------------------------------------------------------

    if not email.endswith(
        "@srmist.edu.in"
    ):

        return redirect(
            url_for("manage_users")
        )


    if len(password) < 6:

        return redirect(
            url_for("manage_users")
        )


    connection = get_db_connection()


    # ---------------------------------------------------------
    # DUPLICATE EMAIL
    # ---------------------------------------------------------

    existing_email = connection.execute(
        """
        SELECT id
        FROM users
        WHERE LOWER(email) = ?
        """,
        (email,)
    ).fetchone()


    if existing_email:

        connection.close()

        return redirect(
            url_for("manage_users")
        )


    # ---------------------------------------------------------
    # STUDENT RA NUMBER
    # ---------------------------------------------------------

    if role == "Student":

        # RA Number must be exactly 15 alphanumeric characters.
        if not re.fullmatch(r"[A-Za-z0-9]{15}", ra_number):

            connection.close()

            return redirect(
                url_for("manage_users")
            )


        existing_ra = connection.execute(
            """
            SELECT id
            FROM users
            WHERE ra_number = ?
            """,
            (ra_number,)
        ).fetchone()


        if existing_ra:

            connection.close()

            return redirect(
                url_for("manage_users")
            )


    else:

        ra_number = None


    # ---------------------------------------------------------
    # CREATE USER
    # ---------------------------------------------------------

    cursor = connection.execute(
        """
        INSERT INTO users
        (
            name,
            email,
            password,
            role,
            ra_number,
            status
        )
        VALUES (?, ?, ?, ?, ?, 'ACTIVE')
        """,
        (
            name,
            email,
            password,
            role,
            ra_number
        )
    )


    new_user_id = cursor.lastrowid


    # ---------------------------------------------------------
    # AUDIT LOG
    # ---------------------------------------------------------

    connection.execute(
        """
        INSERT INTO audit_logs
        (
            user_id,
            action,
            entity,
            entity_id,
            details
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            session["user_id"],
            "CREATE",
            "USER",
            new_user_id,
            f"Created user {email} with role {role}"
        )
    )


    connection.commit()
    connection.close()


    return redirect(
        url_for("manage_users")
    )


# =========================================================
# ACTIVATE / DEACTIVATE USER
# =========================================================

@app.route(
    "/admin/users/<int:user_id>/toggle",
    methods=["POST"]
)
def toggle_user_status(user_id):

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )


    if session.get("user_role") != "Super Admin":

        return render_template(
            "access_denied.html"
        ), 403


    # ---------------------------------------------------------
    # PREVENT SELF DEACTIVATION
    # ---------------------------------------------------------

    if user_id == session["user_id"]:

        return redirect(
            url_for("manage_users")
        )


    connection = get_db_connection()


    user = connection.execute(
        """
        SELECT
            id,
            name,
            email,
            role,
            status
        FROM users
        WHERE id = ?
        """,
        (user_id,)
    ).fetchone()


    if user is None:

        connection.close()

        return redirect(
            url_for("manage_users")
        )


    if user["status"] == "ACTIVE":

        new_status = "INACTIVE"

    else:

        new_status = "ACTIVE"


    connection.execute(
        """
        UPDATE users
        SET status = ?
        WHERE id = ?
        """,
        (
            new_status,
            user_id
        )
    )


    # ---------------------------------------------------------
    # AUDIT
    # ---------------------------------------------------------

    connection.execute(
        """
        INSERT INTO audit_logs
        (
            user_id,
            action,
            entity,
            entity_id,
            details
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            session["user_id"],
            "STATUS_CHANGE",
            "USER",
            user_id,
            f"Changed {user['email']} status to {new_status}"
        )
    )


    connection.commit()
    connection.close()


    return redirect(
        url_for("manage_users")
    )

# =========================================================
# FACULTY EVENT APPROVAL
# =========================================================

@app.route("/faculty/events")
def faculty_events():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("user_role") != "Faculty":
        return render_template(
            "access_denied.html"
        ), 403

    connection = get_db_connection()

    events = connection.execute("""
        SELECT
            events.*,
            clubs.name AS club_name
        FROM events

        LEFT JOIN clubs
        ON events.club_id = clubs.id

        WHERE clubs.faculty_coordinator_id = ?

        ORDER BY
            CASE
                WHEN events.status = 'PENDING' THEN 0
                ELSE 1
            END,
            events.event_date ASC
    """, (session["user_id"],)).fetchall()

    connection.close()

    return render_template(
        "faculty_events.html",
        events=events
    )


# =========================================================
# FACULTY APPROVE EVENT
# =========================================================

@app.route(
    "/faculty/events/<int:event_id>/approve",
    methods=["POST"]
)
def faculty_approve_event(event_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("user_role") != "Faculty":
        return render_template(
            "access_denied.html"
        ), 403

    connection = get_db_connection()

    event = connection.execute("""
        SELECT
            events.*,
            clubs.name AS club_name
        FROM events

        LEFT JOIN clubs
        ON events.club_id = clubs.id

        WHERE events.id = ?
          AND clubs.faculty_coordinator_id = ?
    """, (
        event_id, session["user_id"],
    )).fetchone()

    if event is None:

        connection.close()

        return "Event not found", 404

    if event["status"] != "PENDING":

        connection.close()

        return redirect(
            url_for("faculty_events")
        )

    # ---------------------------------------------
    # APPROVE
    # ---------------------------------------------

    connection.execute("""
        UPDATE events

        SET
            status = 'APPROVED',
            rejection_reason = NULL

        WHERE id = ?
    """, (
        event_id,
    ))

    # ---------------------------------------------
    # AUDIT LOG
    # ---------------------------------------------

    connection.execute("""
        INSERT INTO audit_logs
        (
            user_id,
            action,
            entity,
            entity_id,
            details
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        session["user_id"],
        "APPROVE",
        "EVENT",
        event_id,
        f"Faculty approved event: {event['title']}"
    ))

    connection.commit()

    connection.close()

    # ---------------------------------------------
    # NOTIFY CLUB ADMIN
    # ---------------------------------------------

    if event["club_id"]:

        connection = get_db_connection()

        club_admin = connection.execute("""
            SELECT user_id
            FROM club_members
            WHERE club_id = ?
            AND club_role = 'ADMIN'
        """, (
            event["club_id"],
        )).fetchone()

        connection.close()

        if club_admin:

            create_notification(
                club_admin["user_id"],
                "Event Approved",
                f"Your event '{event['title']}' has been approved.",
                "EVENT"
            )

    return redirect(
        url_for("faculty_events")
    )


# =========================================================
# FACULTY REJECT EVENT
# =========================================================

@app.route(
    "/faculty/events/<int:event_id>/reject",
    methods=["POST"]
)
def faculty_reject_event(event_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("user_role") != "Faculty":
        return render_template(
            "access_denied.html"
        ), 403

    rejection_reason = request.form.get(
        "rejection_reason",
        ""
    ).strip()

    if not rejection_reason:

        return redirect(
            url_for("faculty_events")
        )

    connection = get_db_connection()

    event = connection.execute("""
        SELECT
            events.*,
            clubs.name AS club_name
        FROM events

        LEFT JOIN clubs
        ON events.club_id = clubs.id

        WHERE events.id = ?
          AND clubs.faculty_coordinator_id = ?
    """, (
        event_id, session["user_id"],
    )).fetchone()

    if event is None:

        connection.close()

        return "Event not found", 404

    if event["status"] != "PENDING":

        connection.close()

        return redirect(
            url_for("faculty_events")
        )

    # ---------------------------------------------
    # REJECT
    # ---------------------------------------------

    connection.execute("""
        UPDATE events

        SET
            status = 'REJECTED',
            rejection_reason = ?

        WHERE id = ?
    """, (
        rejection_reason,
        event_id
    ))

    # ---------------------------------------------
    # AUDIT LOG
    # ---------------------------------------------

    connection.execute("""
        INSERT INTO audit_logs
        (
            user_id,
            action,
            entity,
            entity_id,
            details
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        session["user_id"],
        "REJECT",
        "EVENT",
        event_id,
        f"Faculty rejected event: {event['title']}. Reason: {rejection_reason}"
    ))

    connection.commit()

    connection.close()

    # ---------------------------------------------
    # NOTIFY CLUB ADMIN
    # ---------------------------------------------

    if event["club_id"]:

        connection = get_db_connection()

        club_admin = connection.execute("""
            SELECT user_id
            FROM club_members
            WHERE club_id = ?
            AND club_role = 'ADMIN'
        """, (
            event["club_id"],
        )).fetchone()

        connection.close()

        if club_admin:

            create_notification(
                club_admin["user_id"],
                "Event Rejected",
                f"Your event '{event['title']}' was rejected. Reason: {rejection_reason}",
                "EVENT"
            )

    return redirect(
        url_for("faculty_events")
    )

# =========================================================
# EVENTS - STUDENT
# =========================================================

@app.route("/events")
def events():

    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = get_db_connection()

    events = connection.execute("""
        SELECT
            events.*,
            clubs.name AS club_name
        FROM events

        LEFT JOIN clubs
        ON events.club_id = clubs.id

        WHERE events.status = 'APPROVED'

        ORDER BY events.event_date ASC
    """).fetchall()

    connection.close()

    return render_template(
        "events.html",
        events=events
    )

# =========================================================
# CLUB MANAGEMENT
# =========================================================


# =========================================================
# CLUB MANAGEMENT PAGE
# =========================================================

@app.route("/admin/clubs")
def manage_clubs():

    if "user_id" not in session:
        return redirect(url_for("login"))

    role = session.get("user_role")

    if role not in [
        "Super Admin",
        "Admin",
        "Club Admin"
    ]:
        return render_template(
            "access_denied.html"
        ), 403

    connection = get_db_connection()

    # -----------------------------------------------------
    # SUPER ADMIN / ADMIN
    # -----------------------------------------------------

    if role in [
        "Super Admin",
        "Admin"
    ]:

        clubs = connection.execute("""
            SELECT
                clubs.*,
                users.name AS club_admin_name,
                users.email AS club_admin_email
            FROM clubs

            LEFT JOIN club_members
            ON clubs.id = club_members.club_id
            AND club_members.club_role = 'ADMIN'

            LEFT JOIN users
            ON club_members.user_id = users.id

            ORDER BY clubs.id ASC
        """).fetchall()

    # -----------------------------------------------------
    # CLUB ADMIN
    # -----------------------------------------------------

    else:

        clubs = connection.execute("""
            SELECT
                clubs.*,
                users.name AS club_admin_name,
                users.email AS club_admin_email
            FROM clubs

            JOIN club_members
            ON clubs.id = club_members.club_id

            JOIN users
            ON club_members.user_id = users.id

            WHERE club_members.user_id = ?
            AND club_members.club_role = 'ADMIN'

            ORDER BY clubs.id ASC
        """, (
            session["user_id"],
        )).fetchall()

    connection.close()

    return render_template(
        "manage_clubs.html",
        clubs=clubs
    )


# =========================================================
# CREATE CLUB
# =========================================================

@app.route(
    "/admin/clubs/create",
    methods=["POST"]
)
def create_club():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("user_role") not in [
        "Super Admin",
        "Admin"
    ]:
        return render_template(
            "access_denied.html"
        ), 403

    name = request.form.get(
        "name",
        ""
    ).strip()

    description = request.form.get(
        "description",
        ""
    ).strip()

    coordinator_name = request.form.get(
        "coordinator_name",
        ""
    ).strip()

    if not name:
        return redirect(
            url_for("manage_clubs")
        )

    connection = get_db_connection()

    existing = connection.execute("""
        SELECT id
        FROM clubs
        WHERE LOWER(name) = LOWER(?)
    """, (
        name,
    )).fetchone()

    if existing:

        connection.close()

        return redirect(
            url_for("manage_clubs")
        )

    cursor = connection.execute("""
        INSERT INTO clubs
        (
            name,
            description,
            coordinator_name,
            status
        )
        VALUES (?, ?, ?, 'ACTIVE')
    """, (
        name,
        description,
        coordinator_name
    ))

    club_id = cursor.lastrowid

    connection.execute("""
        INSERT INTO audit_logs
        (
            user_id,
            action,
            entity,
            entity_id,
            details
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        session["user_id"],
        "CREATE",
        "CLUB",
        club_id,
        f"Created club: {name}"
    ))

    connection.commit()
    connection.close()

    return redirect(
        url_for("manage_clubs")
    )


# =========================================================
# ACTIVATE / DEACTIVATE CLUB
# =========================================================

@app.route(
    "/admin/clubs/<int:club_id>/toggle",
    methods=["POST"]
)
def toggle_club_status(club_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("user_role") not in [
        "Super Admin",
        "Admin"
    ]:
        return render_template(
            "access_denied.html"
        ), 403

    connection = get_db_connection()

    club = connection.execute("""
        SELECT
            id,
            name,
            status
        FROM clubs
        WHERE id = ?
    """, (
        club_id,
    )).fetchone()

    if club is None:

        connection.close()

        return redirect(
            url_for("manage_clubs")
        )

    if club["status"] == "ACTIVE":

        new_status = "INACTIVE"

    else:

        new_status = "ACTIVE"

    connection.execute("""
        UPDATE clubs
        SET status = ?
        WHERE id = ?
    """, (
        new_status,
        club_id
    ))

    connection.execute("""
        INSERT INTO audit_logs
        (
            user_id,
            action,
            entity,
            entity_id,
            details
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        session["user_id"],
        "STATUS_CHANGE",
        "CLUB",
        club_id,
        f"Changed club {club['name']} status to {new_status}"
    ))

    connection.commit()
    connection.close()

    return redirect(
        url_for("manage_clubs")
    )


# =========================================================
# ASSIGN CLUB ADMIN
# =========================================================

@app.route(
    "/admin/clubs/<int:club_id>/assign-admin",
    methods=["POST"]
)
def assign_club_admin(club_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("user_role") not in [
        "Super Admin",
        "Admin"
    ]:
        return render_template(
            "access_denied.html"
        ), 403

    user_id = request.form.get(
        "user_id",
        ""
    ).strip()

    if not user_id:
        return redirect(
            url_for("manage_clubs")
        )

    connection = get_db_connection()

    # -----------------------------------------------------
    # VERIFY CLUB
    # -----------------------------------------------------

    club = connection.execute("""
        SELECT *
        FROM clubs
        WHERE id = ?
    """, (
        club_id,
    )).fetchone()

    if club is None:

        connection.close()

        return redirect(
            url_for("manage_clubs")
        )

    # -----------------------------------------------------
    # VERIFY USER
    # -----------------------------------------------------

    user = connection.execute("""
        SELECT
            id,
            name,
            email,
            role,
            status
        FROM users
        WHERE id = ?
    """, (
        user_id,
    )).fetchone()

    if user is None:

        connection.close()

        return redirect(
            url_for("manage_clubs")
        )

    # Only Club Admin accounts can be assigned
    if user["role"] != "Club Admin":

        connection.close()

        return redirect(
            url_for("manage_clubs")
        )

    if user["status"] != "ACTIVE":

        connection.close()

        return redirect(
            url_for("manage_clubs")
        )

    # -----------------------------------------------------
    # REMOVE EXISTING ADMIN FOR THIS CLUB
    # -----------------------------------------------------

    connection.execute("""
        DELETE FROM club_members
        WHERE club_id = ?
        AND club_role = 'ADMIN'
    """, (
        club_id,
    ))

    # -----------------------------------------------------
    # REMOVE THIS USER AS ADMIN FROM OTHER CLUBS
    # -----------------------------------------------------

    connection.execute("""
        DELETE FROM club_members
        WHERE user_id = ?
        AND club_role = 'ADMIN'
    """, (
        user_id,
    ))

    # -----------------------------------------------------
    # ASSIGN USER
    # -----------------------------------------------------

    connection.execute("""
        INSERT INTO club_members
        (
            club_id,
            user_id,
            club_role
        )
        VALUES (?, ?, 'ADMIN')
    """, (
        club_id,
        user_id
    ))

    connection.execute("""
        INSERT INTO audit_logs
        (
            user_id,
            action,
            entity,
            entity_id,
            details
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        session["user_id"],
        "ASSIGN",
        "CLUB_ADMIN",
        club_id,
        f"Assigned {user['email']} as Club Admin"
    ))

    connection.commit()
    connection.close()

    create_notification(
        user["id"],
        "Club Admin Assignment",
        f"You have been assigned as Club Admin for {club['name']}.",
        "CLUB"
    )

    return redirect(
        url_for("manage_clubs")
    )


# =========================================================
# VIEW CLUB MEMBERS
# =========================================================

@app.route(
    "/admin/clubs/<int:club_id>/members"
)
def club_members(club_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    role = session.get("user_role")

    if role not in [
        "Super Admin",
        "Admin",
        "Club Admin"
    ]:
        return render_template(
            "access_denied.html"
        ), 403

    connection = get_db_connection()

    club = connection.execute("""
        SELECT *
        FROM clubs
        WHERE id = ?
    """, (
        club_id,
    )).fetchone()

    if club is None:

        connection.close()

        return "Club not found", 404

    # -----------------------------------------------------
    # CLUB ADMIN OWNERSHIP CHECK
    # -----------------------------------------------------

    if role == "Club Admin":

        assigned = connection.execute("""
            SELECT id
            FROM club_members
            WHERE club_id = ?
            AND user_id = ?
            AND club_role = 'ADMIN'
        """, (
            club_id,
            session["user_id"]
        )).fetchone()

        if assigned is None:

            connection.close()

            return render_template(
                "access_denied.html"
            ), 403

    # -----------------------------------------------------
    # GET MEMBERS
    # -----------------------------------------------------

    members = connection.execute("""
        SELECT
            club_members.id,
            club_members.club_role,
            club_members.joined_at,
            users.id AS user_id,
            users.name,
            users.email,
            users.ra_number,
            users.status
        FROM club_members

        JOIN users
        ON club_members.user_id = users.id

        WHERE club_members.club_id = ?

        ORDER BY
            club_members.club_role ASC,
            users.name ASC
    """, (
        club_id,
    )).fetchall()

    connection.close()

    return render_template(
        "club_members.html",
        club=club,
        members=members
    )


# =========================================================
# STUDENT JOIN CLUB
# =========================================================

@app.route(
    "/clubs/<int:club_id>/join",
    methods=["POST"]
)
def join_club(club_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    # Only students can join
    if session.get("user_role") != "Student":

        return render_template(
            "access_denied.html"
        ), 403

    connection = get_db_connection()

    club = connection.execute("""
        SELECT *
        FROM clubs
        WHERE id = ?
        AND status = 'ACTIVE'
    """, (
        club_id,
    )).fetchone()

    if club is None:

        connection.close()

        return redirect(
            url_for("clubs")
        )

    # -----------------------------------------------------
    # CHECK EXISTING MEMBERSHIP
    # -----------------------------------------------------

    existing = connection.execute("""
        SELECT id
        FROM club_members
        WHERE club_id = ?
        AND user_id = ?
    """, (
        club_id,
        session["user_id"]
    )).fetchone()

    if existing:

        connection.close()

        return redirect(
            url_for("clubs")
        )

    # -----------------------------------------------------
    # JOIN CLUB
    # -----------------------------------------------------

    connection.execute("""
        INSERT INTO club_members
        (
            club_id,
            user_id,
            club_role
        )
        VALUES (?, ?, 'MEMBER')
    """, (
        club_id,
        session["user_id"]
    ))

    connection.execute("""
        INSERT INTO audit_logs
        (
            user_id,
            action,
            entity,
            entity_id,
            details
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        session["user_id"],
        "JOIN",
        "CLUB",
        club_id,
        f"Joined club: {club['name']}"
    ))

    connection.commit()
    connection.close()

    # Notify Club Admin
    connection = get_db_connection()

    admins = connection.execute("""
        SELECT user_id
        FROM club_members
        WHERE club_id = ?
        AND club_role = 'ADMIN'
    """, (
        club_id,
    )).fetchall()

    connection.close()

    for admin in admins:

        create_notification(
            admin["user_id"],
            "New Club Member",
            f"{session['user_name']} joined {club['name']}.",
            "CLUB"
        )

    return redirect(
        url_for("clubs")
    )


# =========================================================
# CLUB ADMIN - REMOVE MEMBER
# =========================================================

@app.route(
    "/admin/clubs/<int:club_id>/members/<int:user_id>/remove",
    methods=["POST"]
)
def remove_club_member(
    club_id,
    user_id
):

    if "user_id" not in session:
        return redirect(url_for("login"))

    role = session.get("user_role")

    if role not in [
        "Super Admin",
        "Admin",
        "Club Admin"
    ]:
        return render_template(
            "access_denied.html"
        ), 403

    connection = get_db_connection()

    # -----------------------------------------------------
    # CLUB ADMIN OWNERSHIP CHECK
    # -----------------------------------------------------

    if role == "Club Admin":

        assigned = connection.execute("""
            SELECT id
            FROM club_members
            WHERE club_id = ?
            AND user_id = ?
            AND club_role = 'ADMIN'
        """, (
            club_id,
            session["user_id"]
        )).fetchone()

        if assigned is None:

            connection.close()

            return render_template(
                "access_denied.html"
            ), 403

    # -----------------------------------------------------
    # DO NOT REMOVE CLUB ADMIN
    # -----------------------------------------------------

    target = connection.execute("""
        SELECT club_role
        FROM club_members
        WHERE club_id = ?
        AND user_id = ?
    """, (
        club_id,
        user_id
    )).fetchone()

    if target is None:

        connection.close()

        return redirect(
            url_for(
                "club_members",
                club_id=club_id
            )
        )

    if target["club_role"] == "ADMIN":

        connection.close()

        return redirect(
            url_for(
                "club_members",
                club_id=club_id
            )
        )

    # -----------------------------------------------------
    # REMOVE
    # -----------------------------------------------------

    connection.execute("""
        DELETE FROM club_members
        WHERE club_id = ?
        AND user_id = ?
    """, (
        club_id,
        user_id
    ))

    connection.execute("""
        INSERT INTO audit_logs
        (
            user_id,
            action,
            entity,
            entity_id,
            details
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        session["user_id"],
        "REMOVE",
        "CLUB_MEMBER",
        user_id,
        f"Removed user {user_id} from club {club_id}"
    ))

    connection.commit()
    connection.close()

    return redirect(
        url_for(
            "club_members",
            club_id=club_id
        )
    )


# =========================================================
# CLUB ADMIN - CREATE EVENT
# =========================================================

@app.route(
    "/club-admin/clubs/<int:club_id>/events/create",
    methods=["GET", "POST"]
)
def club_admin_create_event(club_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    # Global Club Admin or a dynamically assigned club role with create_event permission.
    if session.get("user_role") != "Club Admin" and not _role_has(club_id, session["user_id"], "create_event"):
        return render_template("access_denied.html"), 403

    connection = get_db_connection()

    # -----------------------------------------------------
    # VERIFY CLUB OWNERSHIP
    # -----------------------------------------------------

    club = connection.execute("""
        SELECT *
        FROM clubs
        WHERE id = ?
        AND status = 'ACTIVE'
    """, (
        club_id,
    )).fetchone()

    if club is None:

        connection.close()

        return "Club not found", 404

    assigned = connection.execute("SELECT id FROM club_members WHERE club_id=? AND user_id=?", (club_id, session["user_id"])).fetchone()

    if assigned is None:

        connection.close()

        return render_template(
            "access_denied.html"
        ), 403

    connection.close()

    # -----------------------------------------------------
    # CREATE EVENT
    # -----------------------------------------------------

    if request.method == "POST":

        title = request.form.get(
            "title",
            ""
        ).strip()

        description = request.form.get(
            "description",
            ""
        ).strip()

        category = request.form.get(
            "category",
            ""
        ).strip()

        event_date = request.form.get(
            "event_date",
            ""
        ).strip()

        event_time = request.form.get(
            "event_time",
            ""
        ).strip()

        event_end_time = request.form.get(
            "event_end_time",
            ""
        ).strip()

        venue = request.form.get(
            "venue",
            ""
        ).strip()

        if not (
            title
            and category
            and event_date
            and event_time
            and event_end_time
            and venue
        ):

            return render_template(
                "club_create_event.html",
                club=club,
                error="Please fill in all required fields."
            )

        try:

            start_minutes = time_to_minutes(
                event_time
            )

            end_minutes = time_to_minutes(
                event_end_time
            )

        except ValueError:

            return render_template(
                "club_create_event.html",
                club=club,
                error="Invalid event time."
            )

        if end_minutes <= start_minutes:

            return render_template(
                "club_create_event.html",
                club=club,
                error="End time must be after start time."
            )

        connection = get_db_connection()

        cursor = connection.execute("""
            INSERT INTO events
            (
                club_id,
                title,
                description,
                category,
                event_date,
                event_time,
                event_end_time,
                venue,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')
        """, (
            club_id,
            title,
            description,
            category,
            event_date,
            event_time,
            event_end_time,
            venue
        ))

        event_id = cursor.lastrowid

        connection.execute("""
            INSERT INTO audit_logs
            (
                user_id,
                action,
                entity,
                entity_id,
                details
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            session["user_id"],
            "CREATE",
            "EVENT",
            event_id,
            f"Club Admin created event '{title}' for {club['name']}"
        ))

        # Notify assigned Faculty Coordinator + Admins
        recipients = connection.execute("""
            SELECT id FROM users WHERE status='ACTIVE' AND role IN ('Admin','Super Admin')
            UNION
            SELECT faculty_coordinator_id FROM clubs WHERE id=? AND faculty_coordinator_id IS NOT NULL
        """, (club_id,)).fetchall()

        connection.commit()
        connection.close()

        for admin in recipients:

            create_notification(
                admin["id"],
                "New Event Approval Required",
                f"{club['name']} submitted '{title}' for approval.",
                "EVENT"
            )

        return redirect(
            url_for(
                "club_admin_events",
                club_id=club_id
            )
        )

    return render_template(
        "club_create_event.html",
        club=club
    )


# =========================================================
# CLUB ADMIN - VIEW OWN EVENTS
# =========================================================

@app.route(
    "/club-admin/clubs/<int:club_id>/events"
)
def club_admin_events(club_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("user_role") != "Club Admin":

        return render_template(
            "access_denied.html"
        ), 403

    connection = get_db_connection()

    # -----------------------------------------------------
    # OWNERSHIP CHECK
    # -----------------------------------------------------

    assigned = connection.execute("""
        SELECT id
        FROM club_members
        WHERE club_id = ?
        AND user_id = ?
        AND club_role = 'ADMIN'
    """, (
        club_id,
        session["user_id"]
    )).fetchone()

    if assigned is None:

        connection.close()

        return render_template(
            "access_denied.html"
        ), 403

    club = connection.execute("""
        SELECT *
        FROM clubs
        WHERE id = ?
    """, (
        club_id,
    )).fetchone()

    events = connection.execute("""
        SELECT *
        FROM events
        WHERE club_id = ?
        ORDER BY event_date ASC
    """, (
        club_id,
    )).fetchall()

    connection.close()

    return render_template(
        "club_admin_events.html",
        club=club,
        events=events
    )


# =========================================================
# EVENT REGISTRATION
# =========================================================

@app.route(
    "/register-event/<int:event_id>",
    methods=["POST"]
)
def register_event(event_id):

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )


    connection = get_db_connection()


    # ---------------------------------------------------------
    # VERIFY EVENT
    # ---------------------------------------------------------

    event = connection.execute(
        """
        SELECT *
        FROM events
        WHERE id = ?
        AND status = 'APPROVED'
        """,
        (event_id,)
    ).fetchone()


    if event is None:

        connection.close()

        return redirect(
            url_for("events")
        )


    try:

        connection.execute(
            """
            INSERT INTO event_registrations
            (
                event_id,
                user_id,
                registered_at,
                status
            )
            VALUES (?, ?, CURRENT_TIMESTAMP, 'REGISTERED')
            """,
            (
                event_id,
                session["user_id"]
            )
        )


        connection.commit()

        connection.close()


        create_notification(
            session["user_id"],
            "Event Registration Successful",
            f"You have successfully registered for {event['title']}.",
            "EVENT"
        )


    except Exception as e:

        print(
            "REGISTRATION ERROR:",
            e
        )

        connection.close()


    return redirect(
        url_for("events")
    )


# =========================================================
# MY REGISTRATIONS
# =========================================================

@app.route("/my-registrations")
def my_registrations():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )


    connection = get_db_connection()


    registrations = connection.execute(
        """
        SELECT
            event_registrations.id,
            event_registrations.status,
            event_registrations.registered_at,
            events.title,
            events.description,
            events.category,
            events.event_date,
            events.event_time,
            events.event_end_time,
            events.venue
        FROM event_registrations
        JOIN events
        ON event_registrations.event_id =
           events.id
        WHERE event_registrations.user_id = ?
        ORDER BY events.event_date ASC
        """,
        (
            session["user_id"],
        )
    ).fetchall()


    connection.close()


    return render_template(
        "my_registrations.html",
        registrations=registrations
    )


# =========================================================
# CLUBS - STUDENT VIEW
# =========================================================

@app.route("/clubs")
def clubs():

    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = get_db_connection()

    clubs = connection.execute("""
        SELECT
            clubs.*,
            (
                SELECT COUNT(*)
                FROM club_members
                WHERE club_members.club_id = clubs.id
                AND club_members.club_role = 'MEMBER'
            ) AS member_count,

            EXISTS (
                SELECT 1
                FROM club_members
                WHERE club_members.club_id = clubs.id
                AND club_members.user_id = ?
            ) AS joined

        FROM clubs

        WHERE clubs.status = 'ACTIVE'

        ORDER BY clubs.name ASC
    """, (
        session["user_id"],
    )).fetchall()

    connection.close()

    return render_template(
        "clubs.html",
        clubs=clubs
    )


# =========================================================
# STUDENT OD REQUESTS
# =========================================================

@app.route(
    "/od-requests",
    methods=["GET", "POST"]
)
def od_requests():
    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("user_role") != "Student":
        return render_template("access_denied.html"), 403
    c=get_db_connection(); uid=session["user_id"]; error=None
    if request.method == "POST":
        event_id=request.form.get("event_id","").strip()
        reason=request.form.get("reason","").strip()
        request_date=request.form.get("request_date","").strip()
        event=c.execute("SELECT * FROM events WHERE id=? AND status='APPROVED'",(event_id,)).fetchone() if event_id else None
        registered=c.execute("SELECT id FROM event_registrations WHERE event_id=? AND user_id=? AND status='REGISTERED'",(event_id,uid)).fetchone() if event_id else None
        mentor=c.execute("SELECT mentor_id FROM users WHERE id=?",(uid,)).fetchone()
        if not event: error="Select an approved event."
        elif not registered: error="You must register for the event before applying for OD."
        elif not reason or not request_date: error="Event, reason and request date are required."
        elif request_date != event["event_date"]: error="OD date must match the event date."
        elif not mentor or not mentor["mentor_id"]: error="No Class Mentor is assigned to your account yet."
        else:
            periods=get_affected_timetable_periods(event["event_time"],event["event_end_time"],event["event_date"])
            existing=c.execute("SELECT id FROM od_requests WHERE user_id=? AND event_id=? AND status='PENDING'",(uid,event_id)).fetchone()
            if existing: error="A pending OD request already exists for this event."
            else:
                c.execute("INSERT INTO od_requests (user_id,student_id,event_id,reason,request_date,status) VALUES (?,?,?,?,?,'PENDING')",(uid,uid,event_id,reason,request_date))
                c.commit(); oid=c.execute("SELECT last_insert_rowid()").fetchone()[0]
                create_notification(mentor["mentor_id"],"New OD Request",f"{session['user_name']} submitted an OD request for {event['title']}.","OD")
                create_audit_log(uid,"CREATE","OD_REQUEST",oid,f"OD for {event['title']}; affected periods: {len(periods)}")
                c.close(); return redirect(url_for("od_requests"))
    events=c.execute("""SELECT e.* FROM events e JOIN event_registrations r ON r.event_id=e.id AND r.user_id=? AND r.status='REGISTERED' WHERE e.status='APPROVED' ORDER BY e.event_date DESC""",(uid,)).fetchall()
    requests=c.execute("""SELECT o.*,e.title AS event_title,e.event_date,e.event_time,e.event_end_time FROM od_requests o LEFT JOIN events e ON o.event_id=e.id WHERE o.user_id=? ORDER BY o.created_at DESC""",(uid,)).fetchall()
    c.close(); return render_template("od_requests.html",requests=requests,events=events,error=error)


# =========================================================
# ADMIN - OD REQUESTS
# =========================================================

@app.route("/admin/od-requests")
def admin_od_requests():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )


    if session.get("user_role") not in [
        "Admin",
        "Super Admin"
    ]:

        return render_template(
            "access_denied.html"
        ), 403


    connection = get_db_connection()


    requests = connection.execute(
        """
        SELECT
            od_requests.id,
            od_requests.reason,
            od_requests.request_date,
            od_requests.status,
            od_requests.created_at,
            users.name,
            users.email
        FROM od_requests
        JOIN users
        ON od_requests.user_id =
           users.id
        ORDER BY od_requests.created_at DESC
        """
    ).fetchall()


    connection.close()


    return render_template(
        "admin_od_requests.html",
        requests=requests
    )

# =========================================================
# FACULTY OD APPROVAL
# =========================================================

@app.route("/faculty/od-requests")
def faculty_od_requests():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("user_role") != "Faculty":
        return render_template(
            "access_denied.html"
        ), 403

    connection = get_db_connection()

    requests = connection.execute("""
        SELECT
            od_requests.*,
            users.name AS student_name,
            users.email AS student_email,
            users.ra_number,
            events.title AS event_title,
            events.event_date,
            events.event_time,
            events.event_end_time,
            clubs.name AS club_name

        FROM od_requests

        JOIN users
        ON od_requests.student_id = users.id

        LEFT JOIN events
        ON od_requests.event_id = events.id

        LEFT JOIN clubs
        ON events.club_id = clubs.id

        WHERE users.mentor_id = ?

        ORDER BY
            CASE
                WHEN od_requests.status = 'PENDING' THEN 0
                ELSE 1
            END,
            od_requests.id DESC
    """, (session["user_id"],)).fetchall()

    connection.close()

    return render_template(
        "faculty_od_requests.html",
        requests=requests
    )


# =========================================================
# FACULTY APPROVE OD
# =========================================================

@app.route(
    "/faculty/od-requests/<int:request_id>/approve",
    methods=["POST"]
)
def faculty_approve_od(request_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("user_role") != "Faculty":
        return render_template(
            "access_denied.html"
        ), 403

    connection = get_db_connection()

    od_request = connection.execute("""
        SELECT
            od_requests.*,
            users.name AS student_name,
            events.title AS event_title

        FROM od_requests

        JOIN users
        ON od_requests.student_id = users.id

        LEFT JOIN events
        ON od_requests.event_id = events.id

        WHERE od_requests.id = ?
          AND users.mentor_id = ?
    """, (
        request_id, session["user_id"],
    )).fetchone()

    if od_request is None:

        connection.close()

        return "OD request not found", 404

    if od_request["status"] != "PENDING":

        connection.close()

        return redirect(
            url_for("faculty_od_requests")
        )

    # ---------------------------------------------
    # APPROVE OD
    # ---------------------------------------------

    connection.execute("""
        UPDATE od_requests

        SET
            status = 'APPROVED',
            rejection_reason = NULL

        WHERE id = ?
    """, (
        request_id,
    ))

    # ---------------------------------------------
    # AUDIT LOG
    # ---------------------------------------------

    connection.execute("""
        INSERT INTO audit_logs
        (
            user_id,
            action,
            entity,
            entity_id,
            details
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        session["user_id"],
        "APPROVE",
        "OD_REQUEST",
        request_id,
        f"Faculty approved OD request for {od_request['student_name']}"
    ))

    connection.commit()

    student_id = od_request["student_id"]

    connection.close()

    # ---------------------------------------------
    # NOTIFICATION
    # ---------------------------------------------

    create_notification(
        student_id,
        "OD Request Approved",
        f"Your OD request for '{od_request['event_title'] or 'the event'}' has been approved.",
        "OD"
    )

    return redirect(
        url_for("faculty_od_requests")
    )


# =========================================================
# FACULTY REJECT OD
# =========================================================

@app.route(
    "/faculty/od-requests/<int:request_id>/reject",
    methods=["POST"]
)
def faculty_reject_od(request_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("user_role") != "Faculty":
        return render_template(
            "access_denied.html"
        ), 403

    rejection_reason = request.form.get(
        "rejection_reason",
        ""
    ).strip()

    if not rejection_reason:

        return redirect(
            url_for("faculty_od_requests")
        )

    connection = get_db_connection()

    od_request = connection.execute("""
        SELECT
            od_requests.*,
            users.name AS student_name,
            events.title AS event_title

        FROM od_requests

        JOIN users
        ON od_requests.student_id = users.id

        LEFT JOIN events
        ON od_requests.event_id = events.id

        WHERE od_requests.id = ?
          AND users.mentor_id = ?
    """, (
        request_id, session["user_id"],
    )).fetchone()

    if od_request is None:

        connection.close()

        return "OD request not found", 404

    if od_request["status"] != "PENDING":

        connection.close()

        return redirect(
            url_for("faculty_od_requests")
        )

    # ---------------------------------------------
    # REJECT OD
    # ---------------------------------------------

    connection.execute("""
        UPDATE od_requests

        SET
            status = 'REJECTED',
            rejection_reason = ?

        WHERE id = ?
    """, (
        rejection_reason,
        request_id
    ))

    # ---------------------------------------------
    # AUDIT LOG
    # ---------------------------------------------

    connection.execute("""
        INSERT INTO audit_logs
        (
            user_id,
            action,
            entity,
            entity_id,
            details
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        session["user_id"],
        "REJECT",
        "OD_REQUEST",
        request_id,
        f"Faculty rejected OD request for {od_request['student_name']}. Reason: {rejection_reason}"
    ))

    connection.commit()

    student_id = od_request["student_id"]

    connection.close()

    # ---------------------------------------------
    # NOTIFICATION
    # ---------------------------------------------

    create_notification(
        student_id,
        "OD Request Rejected",
        f"Your OD request for '{od_request['event_title'] or 'the event'}' was rejected. Reason: {rejection_reason}",
        "OD"
    )

    return redirect(
        url_for("faculty_od_requests")
    )
# =========================================================
# APPROVE OD
# =========================================================

@app.route(
    "/admin/od-requests/<int:request_id>/approve",
    methods=["POST"]
)
def approve_od_request(request_id):

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )


    if session.get("user_role") not in [
        "Admin",
        "Super Admin"
    ]:

        return render_template(
            "access_denied.html"
        ), 403


    connection = get_db_connection()


    od_request = connection.execute(
        """
        SELECT
            user_id,
            request_date
        FROM od_requests
        WHERE id = ?
        """,
        (
            request_id,
        )
    ).fetchone()


    if od_request:

        connection.execute(
            """
            UPDATE od_requests
            SET status = 'APPROVED'
            WHERE id = ?
            """,
            (
                request_id,
            )
        )


        connection.commit()
        connection.close()


        create_notification(
            od_request["user_id"],
            "OD Request Approved",
            f"Your OD request for {od_request['request_date']} has been approved.",
            "APPROVAL"
        )


    else:

        connection.close()


    return redirect(
        url_for("admin_od_requests")
    )


# =========================================================
# REJECT OD
# =========================================================

@app.route(
    "/admin/od-requests/<int:request_id>/reject",
    methods=["POST"]
)
def reject_od_request(request_id):

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )


    if session.get("user_role") not in [
        "Admin",
        "Super Admin"
    ]:

        return render_template(
            "access_denied.html"
        ), 403


    connection = get_db_connection()


    od_request = connection.execute(
        """
        SELECT
            user_id,
            request_date
        FROM od_requests
        WHERE id = ?
        """,
        (
            request_id,
        )
    ).fetchone()


    if od_request:

        connection.execute(
            """
            UPDATE od_requests
            SET status = 'REJECTED'
            WHERE id = ?
            """,
            (
                request_id,
            )
        )


        connection.commit()
        connection.close()


        create_notification(
            od_request["user_id"],
            "OD Request Rejected",
            f"Your OD request for {od_request['request_date']} has been rejected.",
            "REJECTION"
        )


    else:

        connection.close()


    return redirect(
        url_for("admin_od_requests")
    )


# =========================================================
# ADMIN - CREATE EVENT
# =========================================================

@app.route(
    "/admin/events/create",
    methods=["GET", "POST"]
)
def create_event():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )


    if session.get("user_role") not in [
        "Admin",
        "Super Admin"
    ]:

        return render_template(
            "access_denied.html"
        ), 403


    if request.method == "POST":

        title = request.form.get(
            "title",
            ""
        ).strip()


        description = request.form.get(
            "description",
            ""
        ).strip()


        category = request.form.get(
            "category",
            ""
        ).strip()


        event_date = request.form.get(
            "event_date",
            ""
        ).strip()


        event_time = request.form.get(
            "event_time",
            ""
        ).strip()


        event_end_time = request.form.get(
            "event_end_time",
            ""
        ).strip()


        venue = request.form.get(
            "venue",
            ""
        ).strip()


        if not (
            title
            and category
            and event_date
            and event_time
            and event_end_time
            and venue
        ):

            return render_template(
                "create_event.html",
                error="Please fill in all required fields."
            )


        try:

            start_minutes = time_to_minutes(
                event_time
            )

            end_minutes = time_to_minutes(
                event_end_time
            )

        except ValueError:

            return render_template(
                "create_event.html",
                error="Invalid event time."
            )


        if end_minutes <= start_minutes:

            return render_template(
                "create_event.html",
                error="Event end time must be after the start time."
            )


        connection = get_db_connection()


        cursor = connection.execute(
            """
            INSERT INTO events
            (
                title,
                description,
                category,
                event_date,
                event_time,
                event_end_time,
                venue,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING')
            """,
            (
                title,
                description,
                category,
                event_date,
                event_time,
                event_end_time,
                venue
            )
        )


        event_id = cursor.lastrowid


        # -----------------------------------------------------
        # AUDIT LOG
        # -----------------------------------------------------

        connection.execute(
            """
            INSERT INTO audit_logs
            (
                user_id,
                action,
                entity,
                entity_id,
                details
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                session["user_id"],
                "CREATE",
                "EVENT",
                event_id,
                f"Created event: {title}"
            )
        )


        connection.commit()
        connection.close()


        return redirect(
            url_for("admin_events")
        )


    return render_template(
        "create_event.html"
    )


# =========================================================
# ADMIN - MANAGE EVENTS
# =========================================================

@app.route("/admin/events")
def admin_events():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )


    if session.get("user_role") not in [
        "Admin",
        "Super Admin"
    ]:

        return render_template(
            "access_denied.html"
        ), 403


    connection = get_db_connection()


    events = connection.execute(
        """
        SELECT *
        FROM events
        ORDER BY event_date ASC
        """
    ).fetchall()


    connection.close()


    event_data = []


    for event in events:

        affected_periods = get_affected_timetable_periods(
            event["event_time"],
            event["event_end_time"],
            event["event_date"]
        )


        event_data.append(
            {
                "event": event,
                "affected_periods": affected_periods
            }
        )


    return render_template(
        "admin_events.html",
        events=event_data
    )


# =========================================================
# APPROVE EVENT
# =========================================================

@app.route(
    "/admin/events/<int:event_id>/approve",
    methods=["POST"]
)
def approve_event(event_id):

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )


    if session.get("user_role") not in [
        "Admin",
        "Super Admin"
    ]:

        return render_template(
            "access_denied.html"
        ), 403


    connection = get_db_connection()


    event = connection.execute(
        """
        SELECT
            title
        FROM events
        WHERE id = ?
        """,
        (
            event_id,
        )
    ).fetchone()


    connection.execute(
        """
        UPDATE events
        SET status = 'APPROVED'
        WHERE id = ?
        """,
        (
            event_id,
        )
    )


    connection.commit()
    connection.close()


    if event:

        create_audit_log(
            session["user_id"],
            "APPROVE",
            "EVENT",
            event_id,
            f"Approved event: {event['title']}"
        )


    return redirect(
        url_for("admin_events")
    )


# =========================================================
# REJECT EVENT
# =========================================================

@app.route(
    "/admin/events/<int:event_id>/reject",
    methods=["POST"]
)
def reject_event(event_id):

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )


    if session.get("user_role") not in [
        "Admin",
        "Super Admin"
    ]:

        return render_template(
            "access_denied.html"
        ), 403


    connection = get_db_connection()


    event = connection.execute(
        """
        SELECT
            title
        FROM events
        WHERE id = ?
        """,
        (
            event_id,
        )
    ).fetchone()


    connection.execute(
        """
        UPDATE events
        SET status = 'REJECTED'
        WHERE id = ?
        """,
        (
            event_id,
        )
    )


    connection.commit()
    connection.close()


    if event:

        create_audit_log(
            session["user_id"],
            "REJECT",
            "EVENT",
            event_id,
            f"Rejected event: {event['title']}"
        )


    return redirect(
        url_for("admin_events")
    )


# =========================================================
# NOTIFICATIONS
# =========================================================

@app.route("/notifications")
def notifications():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )


    connection = get_db_connection()


    notifications = connection.execute(
        """
        SELECT *
        FROM notifications
        WHERE user_id = ?
        ORDER BY created_at DESC
        """,
        (
            session["user_id"],
        )
    ).fetchall()


    connection.close()


    return render_template(
        "notifications.html",
        notifications=notifications
    )


# =========================================================
# MARK NOTIFICATION READ
# =========================================================

@app.route(
    "/notifications/<int:notification_id>/read",
    methods=["POST"]
)
def mark_notification_read(
    notification_id
):

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )


    connection = get_db_connection()


    connection.execute(
        """
        UPDATE notifications
        SET is_read = 1
        WHERE id = ?
        AND user_id = ?
        """,
        (
            notification_id,
            session["user_id"]
        )
    )


    connection.commit()
    connection.close()


    return redirect(
        url_for("notifications")
    )


# =========================================================
# QR ATTENDANCE - ADMIN
# =========================================================

@app.route(
    "/admin/events/<int:event_id>/attendance"
)
def event_attendance(event_id):

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )


    if session.get("user_role") not in [
        "Admin",
        "Super Admin"
    ]:

        return render_template(
            "access_denied.html"
        ), 403


    connection = get_db_connection()


    event = connection.execute(
        """
        SELECT *
        FROM events
        WHERE id = ?
        """,
        (
            event_id,
        )
    ).fetchone()


    attendance = connection.execute(
        """
        SELECT
            attendance.attended_at,
            users.name,
            users.email
        FROM attendance
        JOIN users
        ON attendance.user_id =
           users.id
        WHERE attendance.event_id = ?
        ORDER BY attendance.attended_at DESC
        """,
        (
            event_id,
        )
    ).fetchall()


    connection.close()


    if event is None:

        return "Event not found", 404


    attendance_url = url_for(
        "mark_attendance",
        event_id=event_id,
        _external=True
    )


    return render_template(
        "attendance.html",
        event=event,
        attendance=attendance,
        attendance_url=attendance_url
    )


# =========================================================
# QR ATTENDANCE - STUDENT
# =========================================================

@app.route(
    "/attendance/<int:event_id>"
)
def mark_attendance(event_id):

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )


    connection = get_db_connection()


    event = connection.execute(
        """
        SELECT *
        FROM events
        WHERE id = ?
        AND status = 'APPROVED'
        """,
        (
            event_id,
        )
    ).fetchone()


    if event is None:

        connection.close()

        return "Event not found", 404


    try:

        connection.execute(
            """
            INSERT INTO attendance
            (
                event_id,
                user_id
            )
            VALUES (?, ?)
            """,
            (
                event_id,
                session["user_id"]
            )
        )


        connection.commit()

        already_attended = False


    except Exception:

        already_attended = True


    connection.close()


    if already_attended:

        return render_template(
            "attendance_success.html",
            event=event,
            already_attended=True
        )


    create_notification(
        session["user_id"],
        "Attendance Recorded",
        f"Your attendance for {event['title']} has been recorded successfully.",
        "ATTENDANCE"
    )


    return render_template(
        "attendance_success.html",
        event=event,
        already_attended=False
    )


# =========================================================
# STUDENT TIMETABLE
# =========================================================

@app.route(
    "/timetable",
    methods=["GET"]
)
def timetable():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )


    connection = get_db_connection()


    structures = connection.execute(
        """
        SELECT *
        FROM timetable_structures
        ORDER BY effective_from DESC, id DESC
        """
    ).fetchall()


    structure_data = []


    for structure in structures:

        periods = connection.execute(
            """
            SELECT *
            FROM timetable_periods
            WHERE structure_id = ?
            ORDER BY period_number
            """,
            (
                structure["id"],
            )
        ).fetchall()


        structure_data.append(
            {
                "structure": structure,
                "periods": periods
            }
        )


    connection.close()


    return render_template(
        "timetable.html",
        structures=structure_data
    )


# =========================================================
# SUPER ADMIN - CREATE TIMETABLE STRUCTURE
# =========================================================

@app.route(
    "/admin/timetable/create",
    methods=["POST"]
)
def create_timetable_structure():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )


    if session.get("user_role") != "Super Admin":

        return render_template(
            "access_denied.html"
        ), 403


    name = request.form.get(
        "name",
        ""
    ).strip()


    scope = request.form.get(
        "scope",
        ""
    ).strip()


    working_days = request.form.get(
        "working_days",
        ""
    ).strip()


    effective_from = request.form.get(
        "effective_from",
        ""
    ).strip()


    if not (
        name
        and working_days
        and effective_from
    ):

        return redirect(
            url_for("timetable")
        )


    connection = get_db_connection()


    cursor = connection.execute(
        """
        INSERT INTO timetable_structures
        (
            name,
            scope,
            working_days,
            effective_from,
            is_active
        )
        VALUES (?, ?, ?, ?, 0)
        """,
        (
            name,
            scope,
            working_days,
            effective_from
        )
    )


    structure_id = cursor.lastrowid


    connection.commit()
    connection.close()


    create_audit_log(
        session["user_id"],
        "CREATE",
        "TIMETABLE_STRUCTURE",
        structure_id,
        f"Created timetable structure: {name}"
    )


    return redirect(
        url_for("timetable")
    )


# =========================================================
# SUPER ADMIN - ADD TIMETABLE PERIOD
# =========================================================

@app.route(
    "/admin/timetable/<int:structure_id>/add-period",
    methods=["POST"]
)
def add_timetable_period(structure_id):

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )


    if session.get("user_role") != "Super Admin":

        return render_template(
            "access_denied.html"
        ), 403


    period_number = request.form.get(
        "period_number",
        ""
    ).strip()


    label = request.form.get(
        "label",
        ""
    ).strip()


    start_time = request.form.get(
        "start_time",
        ""
    ).strip()


    end_time = request.form.get(
        "end_time",
        ""
    ).strip()


    period_type = request.form.get(
        "period_type",
        "CLASS"
    ).strip()


    if not (
        period_number
        and label
        and start_time
        and end_time
    ):

        return redirect(
            url_for("timetable")
        )


    try:

        period_number = int(
            period_number
        )

        start_minutes = time_to_minutes(
            start_time
        )

        end_minutes = time_to_minutes(
            end_time
        )

    except ValueError:

        return "Invalid period details", 400


    connection = get_db_connection()


    # ---------------------------------------------------------
    # CHECK STRUCTURE
    # ---------------------------------------------------------

    structure = connection.execute(
        """
        SELECT *
        FROM timetable_structures
        WHERE id = ?
        """,
        (
            structure_id,
        )
    ).fetchone()


    if structure is None:

        connection.close()

        return "Timetable structure not found", 404


    # ---------------------------------------------------------
    # TIME VALIDATION
    # ---------------------------------------------------------

    if end_minutes <= start_minutes:

        connection.close()

        return "End time must be after start time", 400


    # ---------------------------------------------------------
    # CHECK OVERLAP
    # ---------------------------------------------------------

    existing_periods = connection.execute(
        """
        SELECT *
        FROM timetable_periods
        WHERE structure_id = ?
        """,
        (
            structure_id,
        )
    ).fetchall()


    for existing in existing_periods:

        try:

            existing_start = time_to_minutes(
                existing["start_time"]
            )

            existing_end = time_to_minutes(
                existing["end_time"]
            )

        except ValueError:

            continue


        if (
            start_minutes < existing_end
            and end_minutes > existing_start
        ):

            connection.close()

            return (
                "Period overlaps with an existing period",
                400
            )


    # ---------------------------------------------------------
    # INSERT PERIOD
    # ---------------------------------------------------------

    connection.execute(
        """
        INSERT INTO timetable_periods
        (
            structure_id,
            period_number,
            label,
            start_time,
            end_time,
            period_type
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            structure_id,
            period_number,
            label,
            start_time,
            end_time,
            period_type
        )
    )


    connection.commit()
    connection.close()


    create_audit_log(
        session["user_id"],
        "CREATE",
        "TIMETABLE_PERIOD",
        structure_id,
        f"Added period {label}: {start_time} - {end_time}"
    )


    return redirect(
        url_for("timetable")
    )


# =========================================================
# SUPER ADMIN - ACTIVATE TIMETABLE
# =========================================================

@app.route(
    "/admin/timetable/<int:structure_id>/activate",
    methods=["POST"]
)
def activate_timetable_structure(
    structure_id
):

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )


    if session.get("user_role") != "Super Admin":

        return render_template(
            "access_denied.html"
        ), 403


    connection = get_db_connection()


    structure = connection.execute(
        """
        SELECT *
        FROM timetable_structures
        WHERE id = ?
        """,
        (
            structure_id,
        )
    ).fetchone()


    if structure is None:

        connection.close()

        return "Timetable structure not found", 404


    periods = connection.execute(
        """
        SELECT *
        FROM timetable_periods
        WHERE structure_id = ?
        ORDER BY period_number
        """,
        (
            structure_id,
        )
    ).fetchall()


    if not periods:

        connection.close()

        return (
            "Add at least one period before activating",
            400
        )


    # ---------------------------------------------------------
    # DEACTIVATE ALL OTHER STRUCTURES
    # ---------------------------------------------------------

    connection.execute(
        """
        UPDATE timetable_structures
        SET is_active = 0
        """
    )


    # ---------------------------------------------------------
    # ACTIVATE SELECTED STRUCTURE
    # ---------------------------------------------------------

    connection.execute(
        """
        UPDATE timetable_structures
        SET is_active = 1
        WHERE id = ?
        """,
        (
            structure_id,
        )
    )


    connection.commit()
    connection.close()


    create_audit_log(
        session["user_id"],
        "ACTIVATE",
        "TIMETABLE_STRUCTURE",
        structure_id,
        f"Activated timetable structure: {structure['name']}"
    )


    return redirect(
        url_for("timetable")
    )


# =========================================================
# CERTIFICATES
# =========================================================

import uuid
from datetime import datetime


# =========================================================
# ISSUE CERTIFICATE PAGE
# =========================================================

@app.route(
    "/certificates/issue",
    methods=["GET", "POST"]
)
def issue_certificate():

    if "user_id" not in session:
        return redirect(url_for("login"))

    role=session.get("user_role")
    if role not in ["Super Admin", "Admin", "Faculty", "Club Admin"]:
        return render_template("access_denied.html"), 403

    connection = get_db_connection()

    # -----------------------------------------------------
    # GET STUDENTS
    # -----------------------------------------------------

    students = connection.execute("""
        SELECT
            id,
            name,
            email,
            ra_number
        FROM users
        WHERE role = 'Student'
        AND status = 'ACTIVE'
        ORDER BY name ASC
    """).fetchall()

    # -----------------------------------------------------
    # GET APPROVED EVENTS
    # -----------------------------------------------------

    events = connection.execute("""
        SELECT
            events.id,
            events.title,
            events.event_date,
            clubs.name AS club_name
        FROM events

        LEFT JOIN clubs
        ON events.club_id = clubs.id

        WHERE events.status = 'COMPLETED'

        ORDER BY events.event_date DESC
    """).fetchall()

    connection.close()

    # -----------------------------------------------------
    # ISSUE CERTIFICATE
    # -----------------------------------------------------

    if request.method == "POST":

        student_id = request.form.get(
            "student_id",
            ""
        ).strip()

        event_id = request.form.get(
            "event_id",
            ""
        ).strip()

        certificate_type = request.form.get(
            "certificate_type",
            "Participation"
        ).strip()

        title = request.form.get(
            "title",
            ""
        ).strip()

        if not student_id or not title:

            return render_template(
                "issue_certificate.html",
                students=students,
                events=events,
                error="Student and certificate title are required."
            )

        # -------------------------------------------------
        # VALIDATE STUDENT
        # -------------------------------------------------

        connection = get_db_connection()

        student = connection.execute("""
            SELECT
                id,
                name,
                email,
                ra_number
            FROM users
            WHERE id = ?
            AND role = 'Student'
            AND status = 'ACTIVE'
        """, (
            student_id,
        )).fetchone()

        if student is None:

            connection.close()

            return render_template(
                "issue_certificate.html",
                students=students,
                events=events,
                error="Invalid student."
            )

        # -------------------------------------------------
        # VALIDATE EVENT
        # -------------------------------------------------

        event = None

        if event_id:

            event = connection.execute("""
                SELECT
                    id,
                    title,
                    status
                FROM events
                WHERE id = ?
            """, (
                event_id,
            )).fetchone()

            if event is None:

                connection.close()

                return render_template(
                    "issue_certificate.html",
                    students=students,
                    events=events,
                    error="Invalid event."
                )

            if role == "Club Admin":
                own=connection.execute("SELECT 1 FROM club_members WHERE club_id=(SELECT club_id FROM events WHERE id=?) AND user_id=? AND club_role='ADMIN'",(event_id,session["user_id"])).fetchone()
                if not own:
                    connection.close(); return render_template("access_denied.html"),403

            if event["status"] != "COMPLETED":

                connection.close()

                return render_template(
                    "issue_certificate.html",
                    students=students,
                    events=events,
                    error="Certificates can only be issued for completed events."
                )

        # -------------------------------------------------
        # GENERATE UNIQUE CERTIFICATE CODE
        # -------------------------------------------------

        if not event_id:
            connection.close()
            return render_template("issue_certificate.html", students=students, events=events, error="A completed event is required.")

        attended = connection.execute("SELECT id FROM attendance WHERE event_id=? AND user_id=?", (event_id, student_id)).fetchone()
        if not attended:
            connection.close()
            return render_template("issue_certificate.html", students=students, events=events, error="Student attendance must be confirmed before issuing a certificate.")

        participation_role = request.form.get("participation_role", "Participant").strip() or "Participant"
        qr_token = uuid.uuid4().hex

        certificate_code = (
            "CC-"
            + datetime.now().strftime("%Y%m%d")
            + "-"
            + uuid.uuid4().hex[:8].upper()
        )

        issued_at = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        # -------------------------------------------------
        # INSERT
        # -------------------------------------------------

        cursor = connection.execute("""
            INSERT INTO certificates
            (
                student_id,
                event_id,
                certificate_code,
                issued_at,
                certificate_type,
                title,
                participation_role,
                qr_token
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            student_id,
            event_id if event_id else None,
            certificate_code,
            issued_at,
            certificate_type,
            title,
            participation_role,
            qr_token
        ))

        certificate_id = cursor.lastrowid

        # -------------------------------------------------
        # AUDIT LOG
        # -------------------------------------------------

        connection.execute("""
            INSERT INTO audit_logs
            (
                user_id,
                action,
                entity,
                entity_id,
                details
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            session["user_id"],
            "CREATE",
            "CERTIFICATE",
            certificate_id,
            f"Issued certificate {certificate_code} to {student['name']}"
        ))

        connection.commit()

        connection.close()

        # -------------------------------------------------
        # NOTIFY STUDENT
        # -------------------------------------------------

        create_notification(
            student["id"],
            "Certificate Issued",
            f"A certificate has been issued to you: {title}. Certificate ID: {certificate_code}",
            "CERTIFICATE"
        )

        return redirect(
            url_for("view_certificate",
                    certificate_id=certificate_id)
        )

    return render_template(
        "issue_certificate.html",
        students=students,
        events=events
    )


# =========================================================
# STUDENT CERTIFICATES
# =========================================================

@app.route("/certificates")
def certificates():

    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = get_db_connection()

    if session.get("user_role") == "Student":

        certificates = connection.execute("""
            SELECT
                certificates.*,
                events.title AS event_title,
                events.event_date,
                clubs.name AS club_name

            FROM certificates

            LEFT JOIN events
            ON certificates.event_id = events.id

            LEFT JOIN clubs
            ON events.club_id = clubs.id

            WHERE certificates.student_id = ?

            ORDER BY certificates.issued_at DESC
        """, (
            session["user_id"],
        )).fetchall()

    elif session.get("user_role") in [
        "Super Admin",
        "Admin",
        "Faculty"
    ]:

        certificates = connection.execute("""
            SELECT
                certificates.*,
                users.name AS student_name,
                users.ra_number,
                events.title AS event_title,
                events.event_date,
                clubs.name AS club_name

            FROM certificates

            JOIN users
            ON certificates.student_id = users.id

            LEFT JOIN events
            ON certificates.event_id = events.id

            LEFT JOIN clubs
            ON events.club_id = clubs.id

            ORDER BY certificates.issued_at DESC
        """).fetchall()

    else:

        connection.close()

        return render_template(
            "access_denied.html"
        ), 403

    connection.close()

    return render_template(
        "certificates.html",
        certificates=certificates
    )


# =========================================================
# VIEW CERTIFICATE
# =========================================================

@app.route(
    "/certificates/<int:certificate_id>"
)
def view_certificate(certificate_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = get_db_connection()

    certificate = connection.execute("""
        SELECT
            certificates.*,

            users.name AS student_name,
            users.email AS student_email,
            users.ra_number,

            events.title AS event_title,
            events.event_date,
            events.venue,

            clubs.name AS club_name

        FROM certificates

        JOIN users
        ON certificates.student_id = users.id

        LEFT JOIN events
        ON certificates.event_id = events.id

        LEFT JOIN clubs
        ON events.club_id = clubs.id

        WHERE certificates.id = ?
    """, (
        certificate_id,
    )).fetchone()

    connection.close()

    if certificate is None:
        return "Certificate not found", 404

    # -----------------------------------------------------
    # STUDENT OWNERSHIP
    # -----------------------------------------------------

    if session.get("user_role") == "Student":

        if certificate["student_id"] != session["user_id"]:

            return render_template(
                "access_denied.html"
            ), 403

    elif session.get("user_role") not in [
        "Super Admin",
        "Admin",
        "Faculty"
    ]:

        return render_template(
            "access_denied.html"
        ), 403

    return render_template(
        "certificate_view.html",
        certificate=certificate
    )


# =========================================================
# PUBLIC CERTIFICATE VERIFICATION
# =========================================================

@app.route("/verify-certificate", methods=["GET", "POST"])
def verify_certificate():

    certificate = None

    code = request.args.get("code") or request.form.get("code")

    if code:
        connection = get_db_connection()

        certificate = connection.execute("""
            SELECT
                c.*,
                u.name AS student_name,
                u.ra_number,
                e.title AS event_title,
                e.event_date,
                e.venue,
                cl.name AS club_name
            FROM certificates c
            JOIN users u ON c.student_id = u.id
            LEFT JOIN events e ON c.event_id = e.id
            LEFT JOIN clubs cl ON e.club_id = cl.id
            WHERE c.certificate_code = ?
        """, (code,)).fetchone()

        connection.close()

    return render_template(
        "verify_certificate.html",
        certificate=certificate
    )


# ============================================================
# BADGE MANAGEMENT
# ============================================================

@app.route("/badges")
def badges():

    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = get_db_connection()

    user_id = session["user_id"]

    # All available badges
    all_badges = connection.execute("""
        SELECT *
        FROM badges
        ORDER BY id ASC
    """).fetchall()

    # Badges earned by current student
    earned_badges = connection.execute("""
        SELECT
            b.*,
            sb.awarded_at
        FROM student_badges sb
        JOIN badges b ON sb.badge_id = b.id
        WHERE sb.student_id = ?
        ORDER BY sb.awarded_at DESC
    """, (user_id,)).fetchall()

    earned_ids = {badge["id"] for badge in earned_badges}

    connection.close()

    return render_template(
        "badges.html",
        all_badges=all_badges,
        earned_badges=earned_badges,
        earned_ids=earned_ids
    )


@app.route("/admin/badges")
def admin_badges():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("user_role") not in ["Super Admin", "Admin"]:
        return redirect(url_for("access_denied"))

    connection = get_db_connection()

    badges = connection.execute("""
        SELECT *
        FROM badges
        ORDER BY id ASC
    """).fetchall()

    students = connection.execute("""
        SELECT
            id,
            name,
            email,
            ra_number
        FROM users
        WHERE role = 'Student'
        AND status = 'ACTIVE'
        ORDER BY name ASC
    """).fetchall()

    connection.close()

    return render_template(
        "admin_badges.html",
        badges=badges,
        students=students
    )


@app.route("/admin/badges/award", methods=["POST"])
def award_badge():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("user_role") not in ["Super Admin", "Admin"]:
        return redirect(url_for("access_denied"))

    student_id = request.form.get("student_id")
    badge_id = request.form.get("badge_id")

    if not student_id or not badge_id:
        return redirect(url_for("admin_badges"))

    connection = get_db_connection()

    # Prevent duplicate badge award
    existing = connection.execute("""
        SELECT id
        FROM student_badges
        WHERE student_id = ?
        AND badge_id = ?
    """, (student_id, badge_id)).fetchone()

    if existing:
        connection.close()
        return redirect(url_for("admin_badges"))

    connection.execute("""
        INSERT INTO student_badges
        (student_id, badge_id, awarded_at)
        VALUES (?, ?, datetime('now'))
    """, (student_id, badge_id))

    connection.commit()

    badge = connection.execute("""
        SELECT name
        FROM badges
        WHERE id = ?
    """, (badge_id,)).fetchone()

    student = connection.execute("""
        SELECT name
        FROM users
        WHERE id = ?
    """, (student_id,)).fetchone()

    # Notification
    if student and badge:
        create_notification(
            student_id,
            "New Badge Earned 🏅",
            f"Congratulations! You earned the '{badge['name']}' badge.",
            "BADGE"
        )

    # Audit log
    create_audit_log(
        session["user_id"],
        "AWARD",
        "BADGE",
        badge_id,
        f"Badge ID {badge_id} awarded to student {student_id}"
    )

    connection.commit()
    connection.close()

    return redirect(url_for("admin_badges"))


# =========================================================
# AUDIT LOGS
# =========================================================

@app.route("/admin/audit-logs")
def audit_logs():
    if "user_id" not in session:
        return redirect(url_for("login"))

    # Full audit history is restricted to Super Admin.
    if session.get("user_role") != "Super Admin":
        return render_template("access_denied.html"), 403

    connection = get_db_connection()

    logs = connection.execute("""
        SELECT
            audit_logs.id,
            audit_logs.action,
            audit_logs.entity,
            audit_logs.entity_id,
            audit_logs.details,
            audit_logs.created_at,
            users.name AS user_name,
            users.email AS user_email,
            users.role AS user_role
        FROM audit_logs
        LEFT JOIN users
            ON audit_logs.user_id = users.id
        ORDER BY audit_logs.created_at DESC, audit_logs.id DESC
        LIMIT 500
    """).fetchall()

    connection.close()

    return render_template(
        "audit_logs.html",
        logs=logs
    )


# =========================================================
# STUDENT ENGAGEMENT PASSPORT
# =========================================================

@app.route("/student/passport")
def student_passport():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("user_role") != "Student":
        return render_template("access_denied.html"), 403

    connection = get_db_connection()
    student_id = session["user_id"]

    clubs = connection.execute("""
        SELECT
            clubs.name,
            club_members.club_role,
            club_members.joined_at
        FROM club_members
        JOIN clubs ON club_members.club_id = clubs.id
        WHERE club_members.user_id = ?
        ORDER BY club_members.joined_at DESC
    """, (student_id,)).fetchall()

    registrations = connection.execute("""
        SELECT
            events.title,
            events.category,
            events.event_date,
            events.event_time,
            events.venue,
            event_registrations.status,
            event_registrations.registered_at
        FROM event_registrations
        JOIN events ON event_registrations.event_id = events.id
        WHERE event_registrations.user_id = ?
        ORDER BY events.event_date DESC, event_registrations.id DESC
    """, (student_id,)).fetchall()

    certificates = connection.execute("""
        SELECT
            certificates.certificate_code,
            certificates.title,
            certificates.certificate_type,
            certificates.issued_at,
            events.title AS event_title,
            events.event_date,
            clubs.name AS club_name
        FROM certificates
        LEFT JOIN events ON certificates.event_id = events.id
        LEFT JOIN clubs ON events.club_id = clubs.id
        WHERE certificates.student_id = ?
        ORDER BY certificates.issued_at DESC
    """, (student_id,)).fetchall()

    badges = connection.execute("""
        SELECT
            badges.name,
            badges.description,
            student_badges.awarded_at
        FROM student_badges
        JOIN badges ON student_badges.badge_id = badges.id
        WHERE student_badges.student_id = ?
        ORDER BY student_badges.awarded_at DESC
    """, (student_id,)).fetchall()

    od_requests = connection.execute("""
        SELECT
            od_requests.request_date,
            od_requests.reason,
            od_requests.status,
            od_requests.created_at,
            events.title AS event_title,
            events.event_time,
            events.event_end_time
        FROM od_requests
        LEFT JOIN events ON od_requests.event_id = events.id
        WHERE od_requests.user_id = ?
        ORDER BY od_requests.created_at DESC
    """, (student_id,)).fetchall()

    timeline = connection.execute("""
        SELECT *
        FROM (
            SELECT
                'CLUB' AS activity_type,
                'Joined ' || clubs.name AS activity,
                club_members.joined_at AS activity_date
            FROM club_members
            JOIN clubs ON club_members.club_id = clubs.id
            WHERE club_members.user_id = ?

            UNION ALL

            SELECT
                'EVENT' AS activity_type,
                'Registered for ' || events.title AS activity,
                event_registrations.registered_at AS activity_date
            FROM event_registrations
            JOIN events ON event_registrations.event_id = events.id
            WHERE event_registrations.user_id = ?

            UNION ALL

            SELECT
                'CERTIFICATE' AS activity_type,
                'Earned certificate: ' || certificates.title AS activity,
                certificates.issued_at AS activity_date
            FROM certificates
            WHERE certificates.student_id = ?

            UNION ALL

            SELECT
                'BADGE' AS activity_type,
                'Earned badge: ' || badges.name AS activity,
                student_badges.awarded_at AS activity_date
            FROM student_badges
            JOIN badges ON student_badges.badge_id = badges.id
            WHERE student_badges.student_id = ?

            UNION ALL

            SELECT
                'OD' AS activity_type,
                'OD request for ' || COALESCE(events.title, 'campus activity') AS activity,
                od_requests.created_at AS activity_date
            FROM od_requests
            LEFT JOIN events ON od_requests.event_id = events.id
            WHERE od_requests.user_id = ?
        )
        ORDER BY activity_date DESC
        LIMIT 30
    """, (
        student_id,
        student_id,
        student_id,
        student_id,
        student_id
    )).fetchall()

    connection.close()

    total_clubs = len(clubs)
    total_events = sum(
        1 for r in registrations
        if r["status"] == "REGISTERED"
    )
    total_certificates = len(certificates)
    total_badges = len(badges)
    approved_od = sum(
        1 for r in od_requests
        if r["status"] == "APPROVED"
    )

    # Simple transparent engagement score for the demo.
    engagement_points = (
        total_clubs * 10
        + total_events * 5
        + total_certificates * 15
        + total_badges * 20
        + approved_od * 3
    )

    return render_template(
        "student_passport.html",
        clubs=clubs,
        registrations=registrations,
        certificates=certificates,
        badges=badges,
        od_requests=od_requests,
        timeline=timeline,
        total_clubs=total_clubs,
        total_events=total_events,
        total_certificates=total_certificates,
        total_badges=total_badges,
        approved_od=approved_od,
        engagement_points=engagement_points
    )

# =========================================================
# ANALYTICS DASHBOARD
# =========================================================

@app.route("/analytics")
def analytics():
    if "user_id" not in session:
        return redirect(url_for("login"))

    role = session.get("user_role")
    allowed_roles = [
        "Super Admin",
        "Admin",
        "Club Admin",
        "Faculty",
        "Student"
    ]

    if role not in allowed_roles:
        return render_template("access_denied.html"), 403

    connection = get_db_connection()
    user_id = session["user_id"]
    club_name = None

    # -----------------------------------------------------
    # GLOBAL ANALYTICS
    # Super Admin / Admin / Faculty
    # -----------------------------------------------------
    if role in ["Super Admin", "Admin", "Faculty"]:

        total_users = connection.execute("""
            SELECT COUNT(*)
            FROM users
            WHERE status = 'ACTIVE'
        """).fetchone()[0]

        total_students = connection.execute("""
            SELECT COUNT(*)
            FROM users
            WHERE role = 'Student'
            AND status = 'ACTIVE'
        """).fetchone()[0]

        total_clubs = connection.execute("""
            SELECT COUNT(*)
            FROM clubs
            WHERE status = 'ACTIVE'
        """).fetchone()[0]

        total_events = connection.execute("""
            SELECT COUNT(*)
            FROM events
            WHERE status = 'APPROVED'
        """).fetchone()[0]

        pending_events = connection.execute("""
            SELECT COUNT(*)
            FROM events
            WHERE status = 'PENDING'
        """).fetchone()[0]

        total_registrations = connection.execute("""
            SELECT COUNT(*)
            FROM event_registrations
            WHERE status = 'REGISTERED'
        """).fetchone()[0]

        total_od = connection.execute("""
            SELECT COUNT(*)
            FROM od_requests
        """).fetchone()[0]

        pending_od = connection.execute("""
            SELECT COUNT(*)
            FROM od_requests
            WHERE status = 'PENDING'
        """).fetchone()[0]

        total_certificates = connection.execute("""
            SELECT COUNT(*)
            FROM certificates
        """).fetchone()[0]

        total_badges = connection.execute("""
            SELECT COUNT(*)
            FROM student_badges
        """).fetchone()[0]

        top_events = connection.execute("""
            SELECT
                events.title,
                COUNT(event_registrations.id) AS registration_count
            FROM events
            LEFT JOIN event_registrations
                ON events.id = event_registrations.event_id
                AND event_registrations.status = 'REGISTERED'
            WHERE events.status = 'APPROVED'
            GROUP BY events.id
            ORDER BY registration_count DESC, events.event_date ASC
            LIMIT 5
        """).fetchall()

        club_stats = connection.execute("""
            SELECT
                clubs.name,
                COUNT(DISTINCT club_members.user_id) AS members,
                COUNT(DISTINCT events.id) AS events
            FROM clubs
            LEFT JOIN club_members
                ON clubs.id = club_members.club_id
                AND club_members.club_role = 'MEMBER'
            LEFT JOIN events
                ON clubs.id = events.club_id
            WHERE clubs.status = 'ACTIVE'
            GROUP BY clubs.id
            ORDER BY members DESC, events DESC
            LIMIT 8
        """).fetchall()

    # -----------------------------------------------------
    # CLUB ADMIN ANALYTICS - OWN CLUB ONLY
    # -----------------------------------------------------
    elif role == "Club Admin":

        club = connection.execute("""
            SELECT
                clubs.id,
                clubs.name
            FROM clubs
            JOIN club_members
                ON clubs.id = club_members.club_id
            WHERE club_members.user_id = ?
            AND club_members.club_role = 'ADMIN'
            LIMIT 1
        """, (user_id,)).fetchone()

        if club is None:
            connection.close()
            return render_template(
                "analytics.html",
                role=role,
                club_name="No club assigned",
                total_users=0,
                total_students=0,
                total_clubs=0,
                total_events=0,
                pending_events=0,
                total_registrations=0,
                total_od=0,
                pending_od=0,
                total_certificates=0,
                total_badges=0,
                top_events=[],
                club_stats=[]
            )

        club_id = club["id"]
        club_name = club["name"]

        total_users = connection.execute("""
            SELECT COUNT(DISTINCT club_members.user_id)
            FROM club_members
            WHERE club_members.club_id = ?
            AND club_members.club_role = 'MEMBER'
        """, (club_id,)).fetchone()[0]

        total_students = total_users
        total_clubs = 1

        total_events = connection.execute("""
            SELECT COUNT(*)
            FROM events
            WHERE club_id = ?
            AND status = 'APPROVED'
        """, (club_id,)).fetchone()[0]

        pending_events = connection.execute("""
            SELECT COUNT(*)
            FROM events
            WHERE club_id = ?
            AND status = 'PENDING'
        """, (club_id,)).fetchone()[0]

        total_registrations = connection.execute("""
            SELECT COUNT(*)
            FROM event_registrations
            JOIN events
                ON event_registrations.event_id = events.id
            WHERE events.club_id = ?
            AND event_registrations.status = 'REGISTERED'
        """, (club_id,)).fetchone()[0]

        total_od = connection.execute("""
            SELECT COUNT(*)
            FROM od_requests
            JOIN events
                ON od_requests.event_id = events.id
            WHERE events.club_id = ?
        """, (club_id,)).fetchone()[0]

        pending_od = connection.execute("""
            SELECT COUNT(*)
            FROM od_requests
            JOIN events
                ON od_requests.event_id = events.id
            WHERE events.club_id = ?
            AND od_requests.status = 'PENDING'
        """, (club_id,)).fetchone()[0]

        total_certificates = connection.execute("""
            SELECT COUNT(*)
            FROM certificates
            JOIN events
                ON certificates.event_id = events.id
            WHERE events.club_id = ?
        """, (club_id,)).fetchone()[0]

        total_badges = connection.execute("""
            SELECT COUNT(*)
            FROM student_badges
            JOIN users
                ON student_badges.student_id = users.id
            JOIN club_members
                ON club_members.user_id = users.id
            WHERE club_members.club_id = ?
            AND club_members.club_role = 'MEMBER'
        """, (club_id,)).fetchone()[0]

        top_events = connection.execute("""
            SELECT
                events.title,
                COUNT(event_registrations.id) AS registration_count
            FROM events
            LEFT JOIN event_registrations
                ON events.id = event_registrations.event_id
                AND event_registrations.status = 'REGISTERED'
            WHERE events.club_id = ?
            AND events.status = 'APPROVED'
            GROUP BY events.id
            ORDER BY registration_count DESC, events.event_date ASC
            LIMIT 5
        """, (club_id,)).fetchall()

        club_stats = connection.execute("""
            SELECT
                clubs.name,
                COUNT(DISTINCT club_members.user_id) AS members,
                COUNT(DISTINCT events.id) AS events
            FROM clubs
            LEFT JOIN club_members
                ON clubs.id = club_members.club_id
                AND club_members.club_role = 'MEMBER'
            LEFT JOIN events
                ON clubs.id = events.club_id
            WHERE clubs.id = ?
            GROUP BY clubs.id
        """, (club_id,)).fetchall()

    # -----------------------------------------------------
    # STUDENT PERSONAL ANALYTICS
    # -----------------------------------------------------
    else:

        total_users = 1
        total_students = 1
        total_clubs = connection.execute("""
            SELECT COUNT(*)
            FROM club_members
            WHERE user_id = ?
            AND club_role = 'MEMBER'
        """, (user_id,)).fetchone()[0]

        total_events = connection.execute("""
            SELECT COUNT(*)
            FROM event_registrations
            WHERE user_id = ?
            AND status = 'REGISTERED'
        """, (user_id,)).fetchone()[0]

        pending_events = 0

        total_registrations = total_events

        total_od = connection.execute("""
            SELECT COUNT(*)
            FROM od_requests
            WHERE user_id = ?
        """, (user_id,)).fetchone()[0]

        pending_od = connection.execute("""
            SELECT COUNT(*)
            FROM od_requests
            WHERE user_id = ?
            AND status = 'PENDING'
        """, (user_id,)).fetchone()[0]

        total_certificates = connection.execute("""
            SELECT COUNT(*)
            FROM certificates
            WHERE student_id = ?
        """, (user_id,)).fetchone()[0]

        total_badges = connection.execute("""
            SELECT COUNT(*)
            FROM student_badges
            WHERE student_id = ?
        """, (user_id,)).fetchone()[0]

        top_events = connection.execute("""
            SELECT
                events.title,
                1 AS registration_count
            FROM event_registrations
            JOIN events
                ON event_registrations.event_id = events.id
            WHERE event_registrations.user_id = ?
            ORDER BY events.event_date DESC
            LIMIT 5
        """, (user_id,)).fetchall()

        club_stats = connection.execute("""
            SELECT
                clubs.name,
                1 AS members,
                (
                    SELECT COUNT(*)
                    FROM events
                    WHERE events.club_id = clubs.id
                    AND events.status = 'APPROVED'
                ) AS events
            FROM clubs
            JOIN club_members
                ON clubs.id = club_members.club_id
            WHERE club_members.user_id = ?
            AND club_members.club_role = 'MEMBER'
        """, (user_id,)).fetchall()

    connection.close()

    return render_template(
        "analytics.html",
        role=role,
        club_name=club_name,
        total_users=total_users,
        total_students=total_students,
        total_clubs=total_clubs,
        total_events=total_events,
        pending_events=pending_events,
        total_registrations=total_registrations,
        total_od=total_od,
        pending_od=pending_od,
        total_certificates=total_certificates,
        total_badges=total_badges,
        top_events=top_events,
        club_stats=club_stats
    )


# =========================================================
# HACKATHON EXTENSIONS
# =========================================================

def _role_has(club_id, user_id, permission):
    c = get_db_connection()

    row = c.execute("""
        SELECT club_role, dynamic_role_id
        FROM club_members
        WHERE club_id = ?
        AND user_id = ?
    """, (club_id, user_id)).fetchone()

    if not row:
        c.close()
        return False

    # A Club Admin assigned to the club has full club permissions.
    if str(row["club_role"]).strip().upper() == "ADMIN":
        c.close()
        return True

    # Dynamically assigned roles use their selected permissions.
    dynamic_role_id = row["dynamic_role_id"]

    if not dynamic_role_id:
        c.close()
        return False

    role = c.execute("""
        SELECT permissions
        FROM club_roles
        WHERE id = ?
        AND club_id = ?
    """, (dynamic_role_id, club_id)).fetchone()

    c.close()

    if not role:
        return False

    permissions = [
        p.strip()
        for p in (role["permissions"] or "").split(",")
        if p.strip()
    ]

    return permission in permissions

@app.route("/admin/events/<int:event_id>/complete", methods=["POST"])
def complete_event(event_id):
    role=session.get("user_role")
    if role not in ["Admin","Super Admin","Club Admin"]: return render_template("access_denied.html"),403
    c=get_db_connection(); e=c.execute("SELECT * FROM events WHERE id=? AND status='APPROVED'",(event_id,)).fetchone()
    if not e: c.close(); return "Only approved events can be completed",400
    if role=="Club Admin":
        own=c.execute("SELECT 1 FROM club_members WHERE club_id=? AND user_id=? AND club_role='ADMIN'",(e["club_id"],session["user_id"])).fetchone()
        if not own: c.close(); return render_template("access_denied.html"),403
    c.execute("UPDATE events SET status='COMPLETED', completed_at=datetime('now') WHERE id=?",(event_id,)); c.commit(); c.close()
    create_audit_log(session["user_id"],"COMPLETE","EVENT",event_id,f"Completed event: {e['title']}")
    return redirect(url_for("admin_events"))

@app.route("/admin/assignments", methods=["GET","POST"])
def assignments():
    if session.get("user_role") not in ["Super Admin","Admin"]: return render_template("access_denied.html"),403
    c=get_db_connection(); error=None
    if request.method=="POST":
        faculty_id=request.form.get("faculty_id"); club_id=request.form.get("club_id"); mentor_student_id=request.form.get("mentor_student_id"); mentor_id=request.form.get("mentor_id")
        if faculty_id and club_id:
            c.execute("UPDATE clubs SET faculty_coordinator_id=? WHERE id=?",(faculty_id,club_id))
        if mentor_student_id and mentor_id:
            c.execute("UPDATE users SET mentor_id=? WHERE id=? AND role='Student'",(mentor_id,mentor_student_id))
        c.commit(); create_audit_log(session["user_id"],"UPDATE","ASSIGNMENT",None,"Faculty coordinator / class mentor assignment")
    faculty=c.execute("SELECT id,name,email FROM users WHERE role='Faculty' AND status='ACTIVE' ORDER BY name").fetchall(); clubs=c.execute("SELECT id,name,faculty_coordinator_id FROM clubs ORDER BY name").fetchall(); students=c.execute("SELECT u.id,u.name,u.email,u.mentor_id, m.name AS mentor_name FROM users u LEFT JOIN users m ON u.mentor_id=m.id WHERE u.role='Student' ORDER BY u.name").fetchall()
    c.close(); return render_template("assignments.html",faculty=faculty,clubs=clubs,students=students)

@app.route("/club-admin/clubs/<int:club_id>/roles", methods=["GET","POST"])
def club_roles(club_id):
    if session.get("user_role")!="Club Admin": return render_template("access_denied.html"),403
    if not _role_has(club_id,session["user_id"],"manage_roles"): return render_template("access_denied.html"),403
    c=get_db_connection()
    if request.method=="POST":
        name=request.form.get("name","").strip(); perms=",".join(request.form.getlist("permissions"))
        if name: c.execute("INSERT OR REPLACE INTO club_roles(club_id,name,permissions) VALUES (?,?,?)",(club_id,name,perms)); c.commit()
    roles=c.execute("SELECT * FROM club_roles WHERE club_id=? ORDER BY name",(club_id,)).fetchall(); members=c.execute("SELECT cm.id,u.name,u.email,cm.dynamic_role_id,cr.name AS dynamic_role FROM club_members cm JOIN users u ON u.id=cm.user_id LEFT JOIN club_roles cr ON cr.id=cm.dynamic_role_id WHERE cm.club_id=?",(club_id,)).fetchall(); c.close(); return render_template("club_roles.html",club_id=club_id,roles=roles,members=members)

@app.route("/club-admin/clubs/<int:club_id>/roles/assign", methods=["POST"])
def assign_dynamic_role(club_id):
    if session.get("user_role")!="Club Admin" or not _role_has(club_id,session["user_id"],"manage_roles"): return render_template("access_denied.html"),403
    c=get_db_connection(); c.execute("UPDATE club_members SET dynamic_role_id=? WHERE id=? AND club_id=?",(request.form.get("role_id"),request.form.get("member_id"),club_id)); c.commit(); c.close(); return redirect(url_for("club_roles",club_id=club_id))

@app.route("/club-admin/clubs/<int:club_id>/badges/create", methods=["POST"])
def create_club_badge(club_id):
    if session.get("user_role")!="Club Admin" or not _role_has(club_id,session["user_id"],"award_badges"): return render_template("access_denied.html"),403
    c=get_db_connection(); name=request.form.get("name","").strip(); desc=request.form.get("description","").strip(); criteria=request.form.get("criteria","").strip();
    if name: c.execute("INSERT INTO badges(name,description,club_id,criteria) VALUES(?,?,?,?)",(name,desc,club_id,criteria)); c.commit()
    c.close(); return redirect(url_for("club_roles",club_id=club_id))

@app.route("/messages", methods=["GET","POST"])
def messages():
    if "user_id" not in session: return redirect(url_for("login"))
    if session.get("user_role") not in ["Faculty","Club Admin"]: return render_template("access_denied.html"),403
    c=get_db_connection()
    if request.method=="POST":
        rid=request.form.get("recipient_id"); body=request.form.get("body","").strip(); event_id=request.form.get("event_id") or None; od_id=request.form.get("od_request_id") or None
        if rid and body: c.execute("INSERT INTO messages(sender_id,recipient_id,event_id,od_request_id,body) VALUES(?,?,?,?,?)",(session["user_id"],rid,event_id,od_id,body)); c.commit(); create_notification(int(rid),"New Message",f"New message from {session['user_name']}","MESSAGE")
    inbox=c.execute("SELECT m.*,u.name AS sender_name FROM messages m JOIN users u ON u.id=m.sender_id WHERE m.recipient_id=? ORDER BY m.created_at DESC",(session["user_id"],)).fetchall(); faculty=c.execute("SELECT id,name FROM users WHERE role='Faculty' AND status='ACTIVE' AND id!=?",(session["user_id"],)).fetchall(); club_admins=c.execute("SELECT DISTINCT u.id,u.name FROM users u JOIN club_members cm ON cm.user_id=u.id WHERE cm.club_role='ADMIN' AND u.id!=?",(session["user_id"],)).fetchall(); c.close(); return render_template("messages.html",inbox=inbox,recipients=faculty+club_admins)

@app.route("/certificates/<int:certificate_id>/download")
def download_certificate(certificate_id):
    from flask import send_file
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    import io
    c=get_db_connection(); cert=c.execute("SELECT certificates.*,u.name AS student_name,u.ra_number,e.title AS event_title,e.event_date,e.venue,cl.name AS club_name FROM certificates JOIN users u ON u.id=certificates.student_id LEFT JOIN events e ON e.id=certificates.event_id LEFT JOIN clubs cl ON cl.id=e.club_id WHERE certificates.id=?",(certificate_id,)).fetchone(); c.close()
    if not cert: return "Certificate not found",404
    if session.get("user_role")=="Student" and cert["student_id"]!=session["user_id"]: return render_template("access_denied.html"),403
    buf=io.BytesIO(); pdf=canvas.Canvas(buf,pagesize=A4); w,h=A4; pdf.setFont("Helvetica-Bold",24); pdf.drawCentredString(w/2,h-130,"CampusClub Certificate"); pdf.setFont("Helvetica",14); pdf.drawCentredString(w/2,h-180,"This certifies that"); pdf.setFont("Helvetica-Bold",20); pdf.drawCentredString(w/2,h-220,cert["student_name"]); pdf.setFont("Helvetica",12); pdf.drawCentredString(w/2,h-260,f"RA Number: {cert['ra_number'] or '-'}"); pdf.drawCentredString(w/2,h-290,f"participated in {cert['event_title'] or cert['title']}"); pdf.drawCentredString(w/2,h-320,f"Club: {cert['club_name'] or '-'}   Date: {cert['event_date'] or '-'}"); pdf.drawCentredString(w/2,h-350,f"Role: {cert['participation_role'] or 'Participant'}"); pdf.drawCentredString(w/2,h-400,f"Certificate ID: {cert['certificate_code']}"); pdf.save(); buf.seek(0); return send_file(buf,as_attachment=True,download_name=f"{cert['certificate_code']}.pdf",mimetype="application/pdf")

@app.route("/certificates/<int:certificate_id>/qr")
def certificate_qr(certificate_id):
    from flask import send_file
    import io,qrcode
    c=get_db_connection(); cert=c.execute("SELECT certificate_code,qr_token FROM certificates WHERE id=?",(certificate_id,)).fetchone(); c.close()
    if not cert: return "Certificate not found",404
    img=qrcode.make(url_for("verify_certificate",code=cert["certificate_code"],_external=True)); buf=io.BytesIO(); img.save(buf,format="PNG"); buf.seek(0); return send_file(buf,mimetype="image/png",download_name=f"{cert['certificate_code']}-qr.png")

@app.route("/certificates/bulk-issue", methods=["POST"])
def bulk_issue_certificates():
    if session.get("user_role") not in ["Super Admin","Admin","Faculty","Club Admin"]: return render_template("access_denied.html"),403
    eid=request.form.get("event_id"); role=request.form.get("participation_role","Participant"); c=get_db_connection(); event=c.execute("SELECT * FROM events WHERE id=? AND status='COMPLETED'",(eid,)).fetchone()
    if not event: c.close(); return "Event must be COMPLETED",400
    rows=c.execute("SELECT DISTINCT r.user_id FROM event_registrations r JOIN attendance a ON a.event_id=r.event_id AND a.user_id=r.user_id WHERE r.event_id=? AND r.status='REGISTERED'",(eid,)).fetchall(); count=0
    for row in rows:
        exists=c.execute("SELECT id FROM certificates WHERE event_id=? AND student_id=?",(eid,row["user_id"])).fetchone()
        if exists: continue
        code="CC-"+datetime.now().strftime("%Y%m%d")+"-"+uuid.uuid4().hex[:8].upper(); token=uuid.uuid4().hex
        c.execute("INSERT INTO certificates(student_id,event_id,certificate_code,issued_at,certificate_type,title,participation_role,qr_token) VALUES(?,?,?,?,?,?,?,?)",(row["user_id"],eid,code,datetime.now().strftime("%Y-%m-%d %H:%M:%S"),"Participation",event["title"],role,token)); count+=1; create_notification(row["user_id"],"Certificate Issued",f"Your certificate for {event['title']} is ready: {code}","CERTIFICATE")
    c.commit(); c.close(); return f"{count} certificates issued successfully."

# GOOGLE SIGN-IN (OAuth 2.0; configure GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET)
@app.route("/auth/google")
def google_login():
    import os, urllib.parse
    cid=os.getenv("GOOGLE_CLIENT_ID"); secret=os.getenv("GOOGLE_CLIENT_SECRET")
    if not cid or not secret: return "Google Sign-In is ready but GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are not configured.",503
    params={"client_id":cid,"redirect_uri":url_for("google_callback",_external=True),"response_type":"code","scope":"openid email profile","access_type":"offline","prompt":"select_account"}
    return redirect("https://accounts.google.com/o/oauth2/v2/auth?"+urllib.parse.urlencode(params))

@app.route("/auth/google/callback")
def google_callback():
    import os, requests
    code=request.args.get("code"); cid=os.getenv("GOOGLE_CLIENT_ID"); secret=os.getenv("GOOGLE_CLIENT_SECRET")
    if not code or not cid or not secret: return redirect(url_for("login"))
    token=requests.post("https://oauth2.googleapis.com/token",data={"code":code,"client_id":cid,"client_secret":secret,"redirect_uri":url_for("google_callback",_external=True),"grant_type":"authorization_code"},timeout=10).json()
    access=token.get("access_token")
    if not access: return "Google authentication failed",401
    info=requests.get("https://www.googleapis.com/oauth2/v3/userinfo",headers={"Authorization":f"Bearer {access}"},timeout=10).json(); email=(info.get("email") or "").lower()
    if not email.endswith("@srmist.edu.in"): return "Only @srmist.edu.in Google accounts are allowed.",403
    c=get_db_connection(); user=c.execute("SELECT * FROM users WHERE email=?",(email,)).fetchone();
    if not user: c.close(); return "Your SRM Google account is not registered. Ask the Super Admin to create your account first.",403
    session["user_id"]=user["id"]; session["user_name"]=user["name"]; session["user_role"]=user["role"]; c.close(); return redirect(url_for("dashboard"))

@app.route("/analytics/detailed")
def detailed_analytics():
    if "user_id" not in session: return redirect(url_for("login"))
    role=session.get("user_role"); c=get_db_connection(); uid=session["user_id"]
    if role=="Student":
        attended=c.execute("SELECT COUNT(*) FROM attendance WHERE user_id=?",(uid,)).fetchone()[0]; od_total=c.execute("SELECT COUNT(*) FROM od_requests WHERE student_id=?",(uid,)).fetchone()[0]; od_ok=c.execute("SELECT COUNT(*) FROM od_requests WHERE student_id=? AND status='APPROVED'",(uid,)).fetchone()[0]
    else:
        attended=c.execute("SELECT COUNT(*) FROM attendance").fetchone()[0]; od_total=c.execute("SELECT COUNT(*) FROM od_requests").fetchone()[0]; od_ok=c.execute("SELECT COUNT(*) FROM od_requests WHERE status='APPROVED'").fetchone()[0]
    avg=c.execute("SELECT ROUND(CAST(COUNT(*) AS REAL)/NULLIF(COUNT(DISTINCT event_id),0),2) FROM attendance").fetchone()[0] or 0
    clubs=c.execute("SELECT clubs.name,COUNT(DISTINCT CASE WHEN cm.club_role='MEMBER' THEN cm.user_id END) members,COUNT(DISTINCT events.id) events,COUNT(DISTINCT attendance.id) attendance FROM clubs LEFT JOIN club_members cm ON cm.club_id=clubs.id LEFT JOIN events ON events.club_id=clubs.id LEFT JOIN attendance ON attendance.event_id=events.id GROUP BY clubs.id ORDER BY members DESC,events DESC").fetchall()
    pe=c.execute("SELECT COUNT(*) FROM events WHERE status='PENDING'").fetchone()[0]; po=c.execute("SELECT COUNT(*) FROM od_requests WHERE status='PENDING'").fetchone()[0]; c.close(); return render_template("analytics_detailed.html",attended=attended,od_rate=round(od_ok*100/od_total,1) if od_total else 0,club_count=len(clubs),avg_attendance=avg,clubs=clubs,pending_events=pe,pending_od=po)

# =========================================================
# RUN APPLICATION
# =========================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )