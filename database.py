import sqlite3


DATABASE = "campusclub.db"


# =========================================================
# DATABASE CONNECTION
# =========================================================

def get_db_connection():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


# =========================================================
# INITIALIZE DATABASE
# =========================================================

def init_db():

    connection = get_db_connection()

    # =====================================================
    # USERS
    # =====================================================

    connection.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            role TEXT NOT NULL,
            ra_number TEXT,
            status TEXT NOT NULL DEFAULT 'ACTIVE'
        )
    """)

    # =====================================================
    # CLUBS
    # =====================================================

    connection.execute("""
        CREATE TABLE IF NOT EXISTS clubs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            coordinator_name TEXT,
            status TEXT NOT NULL DEFAULT 'ACTIVE'
        )
    """)

    # =====================================================
    # EVENTS
    # =====================================================

    connection.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            category TEXT NOT NULL,
            event_date TEXT NOT NULL,
            event_time TEXT NOT NULL,
            event_end_time TEXT NOT NULL DEFAULT '23:59',
            venue TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING'
        )
    """)

    # =====================================================
    # EVENT REGISTRATIONS
    # =====================================================

    connection.execute("""
        CREATE TABLE IF NOT EXISTS event_registrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            registered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            status TEXT NOT NULL DEFAULT 'REGISTERED',

            FOREIGN KEY (event_id)
                REFERENCES events(id)
                ON DELETE CASCADE,

            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE,

            UNIQUE(event_id, user_id)
        )
    """)

    # =====================================================
    # OD REQUESTS
    # =====================================================

    connection.execute("""
        CREATE TABLE IF NOT EXISTS od_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            reason TEXT NOT NULL,
            request_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE
        )
    """)

    # =====================================================
    # NOTIFICATIONS
    # =====================================================

    connection.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            notification_type TEXT NOT NULL DEFAULT 'INFO',
            is_read INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE
        )
    """)

    # =====================================================
    # ATTENDANCE
    # =====================================================

    connection.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            attended_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (event_id)
                REFERENCES events(id)
                ON DELETE CASCADE,

            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE,

            UNIQUE(event_id, user_id)
        )
    """)

    # =====================================================
    # OLD TIMETABLE TABLE
    # Kept for compatibility with older project code.
    # =====================================================

    connection.execute("""
        CREATE TABLE IF NOT EXISTS timetable (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day TEXT,
            period TEXT,
            subject TEXT,
            start_time TEXT,
            end_time TEXT
        )
    """)

    # =====================================================
    # TIMETABLE STRUCTURES
    # =====================================================

    connection.execute("""
        CREATE TABLE IF NOT EXISTS timetable_structures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            scope TEXT,
            working_days TEXT NOT NULL,
            effective_from TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 0
        )
    """)

    # =====================================================
    # TIMETABLE PERIODS
    # =====================================================

    connection.execute("""
        CREATE TABLE IF NOT EXISTS timetable_periods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            structure_id INTEGER NOT NULL,
            period_number INTEGER NOT NULL,
            label TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            period_type TEXT NOT NULL DEFAULT 'CLASS',

            FOREIGN KEY (structure_id)
                REFERENCES timetable_structures(id)
                ON DELETE CASCADE
        )
    """)

    # =====================================================
    # CERTIFICATES
    # =====================================================

    connection.execute("""
        CREATE TABLE IF NOT EXISTS certificates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            event_id INTEGER,
            certificate_number TEXT NOT NULL UNIQUE,
            certificate_type TEXT NOT NULL DEFAULT 'PARTICIPATION',
            issued_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE,

            FOREIGN KEY (event_id)
                REFERENCES events(id)
                ON DELETE SET NULL
        )
    """)

    # =====================================================
    # BADGES
    # =====================================================

    connection.execute("""
        CREATE TABLE IF NOT EXISTS badges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            criteria TEXT
        )
    """)

    # =====================================================
    # STUDENT BADGES
    # =====================================================

    connection.execute("""
        CREATE TABLE IF NOT EXISTS student_badges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            badge_id INTEGER NOT NULL,
            awarded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE,

            FOREIGN KEY (badge_id)
                REFERENCES badges(id)
                ON DELETE CASCADE,

            UNIQUE(user_id, badge_id)
        )
    """)

    # =====================================================
    # CLUB MEMBERS
    # =====================================================

    connection.execute("""
        CREATE TABLE IF NOT EXISTS club_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            club_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            club_role TEXT NOT NULL DEFAULT 'MEMBER',
            joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (club_id)
                REFERENCES clubs(id)
                ON DELETE CASCADE,

            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE,

            UNIQUE(club_id, user_id)
        )
    """)

    # =====================================================
    # AUDIT LOGS
    # =====================================================

    connection.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT NOT NULL,
            entity TEXT NOT NULL,
            entity_id INTEGER,
            details TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE SET NULL
        )
    """)

    # =====================================================
    # MIGRATION: EVENT END TIME
    # =====================================================

    event_columns = connection.execute(
        "PRAGMA table_info(events)"
    ).fetchall()

    event_column_names = [
        column["name"]
        for column in event_columns
    ]

    if "event_end_time" not in event_column_names:

        connection.execute("""
            ALTER TABLE events
            ADD COLUMN event_end_time TEXT
            NOT NULL DEFAULT '23:59'
        """)

    # =====================================================
    # MIGRATION: USER RA NUMBER
    # =====================================================

    user_columns = connection.execute(
        "PRAGMA table_info(users)"
    ).fetchall()

    user_column_names = [
        column["name"]
        for column in user_columns
    ]

    if "ra_number" not in user_column_names:

        connection.execute("""
            ALTER TABLE users
            ADD COLUMN ra_number TEXT
        """)

    # =====================================================
    # MIGRATION: USER STATUS
    # =====================================================

    if "status" not in user_column_names:

        connection.execute("""
            ALTER TABLE users
            ADD COLUMN status TEXT
            NOT NULL DEFAULT 'ACTIVE'
        """)

    connection.commit()

    # =========================================================
    # MIGRATION: EVENT CLUB ID
    # =========================================================

    event_columns = connection.execute(
        "PRAGMA table_info(events)"
    ).fetchall()

    event_column_names = [
    column["name"]
    for column in event_columns
    ]

    if "club_id" not in event_column_names:

        connection.execute("""
        ALTER TABLE events
        ADD COLUMN club_id INTEGER
    """)

    # =========================================================
    # MIGRATION: EVENT REJECTION REASON
    # =========================================================

    event_columns = connection.execute(
        "PRAGMA table_info(events)"
    ).fetchall()

    event_column_names = [
        column["name"]
        for column in event_columns
    ]

    if "rejection_reason" not in event_column_names:

        connection.execute("""
            ALTER TABLE events
            ADD COLUMN rejection_reason TEXT
        """)
    # =========================================================
    # MIGRATION: OD REJECTION REASON
    # =========================================================

    od_columns = connection.execute(
        "PRAGMA table_info(od_requests)"
    ).fetchall()

    od_column_names = [
        column["name"]
        for column in od_columns
    ]

    if "rejection_reason" not in od_column_names:

        connection.execute("""
            ALTER TABLE od_requests
            ADD COLUMN rejection_reason TEXT
        """)

        # =========================================================
        # MIGRATION: CERTIFICATE VERIFICATION FIELDS
        # =========================================================

        certificate_columns = connection.execute(
            "PRAGMA table_info(certificates)"
        ).fetchall()

        certificate_column_names = [
            column["name"]
            for column in certificate_columns
        ]

        if "certificate_code" not in certificate_column_names:

            connection.execute("""
                ALTER TABLE certificates
                ADD COLUMN certificate_code TEXT
            """)

        if "issued_at" not in certificate_column_names:

            connection.execute("""
            ALTER TABLE certificates
            ADD COLUMN issued_at TEXT
            """)

        if "event_id" not in certificate_column_names:

            connection.execute("""
            ALTER TABLE certificates
            ADD COLUMN event_id INTEGER
            """)
    # =====================================================
    # DEMO USERS
    # =====================================================

    create_demo_users(connection)

    # =====================================================
    # DEMO CLUBS
    # =====================================================

    create_demo_clubs(connection)

    # =====================================================
    # DEMO BADGES
    # =====================================================

    create_demo_badges(connection)

    connection.commit()
    connection.close()


# =========================================================
# DEMO USERS
# =========================================================

def create_demo_users(connection):

    demo_users = [

        (
            "Test Student",
            "dg7048@srmist.edu.in",
            "123456",
            "Student",
            "RA2411003050397"
        ),

        (
            "Campus Admin",
            "admin@srmist.edu.in",
            "admin123",
            "Admin",
            None
        ),

        (
            "Campus Super Admin",
            "superadmin@srmist.edu.in",
            "superadmin123",
            "Super Admin",
            None
        ),

        (
            "Campus Club Admin",
            "clubadmin@srmist.edu.in",
            "clubadmin123",
            "Club Admin",
            None
        ),

        (
            "Campus Faculty",
            "faculty@srmist.edu.in",
            "faculty123",
            "Faculty",
            None
        )
    ]

    for user in demo_users:

        existing = connection.execute("""
            SELECT id
            FROM users
            WHERE LOWER(email) = LOWER(?)
        """, (user[1],)).fetchone()

        if existing is None:

            connection.execute("""
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
            """, user)


# =========================================================
# DEMO CLUBS
# =========================================================

def create_demo_clubs(connection):

    clubs = [
        (
            "CodeCraft Club",
            "Programming, coding and software development community.",
            "Campus Faculty",
            "ACTIVE"
        ),
        (
            "AI Innovators Club",
            "Artificial intelligence and machine learning community.",
            "Campus Faculty",
            "ACTIVE"
        ),
        (
            "Cultural Fusion Club",
            "Cultural, arts and creative activities.",
            "Campus Faculty",
            "ACTIVE"
        )
    ]

    for club in clubs:

        existing = connection.execute("""
            SELECT id
            FROM clubs
            WHERE name = ?
        """, (club[0],)).fetchone()

        if existing is None:

            connection.execute("""
                INSERT INTO clubs
                (
                    name,
                    description,
                    coordinator_name,
                    status
                )
                VALUES (?, ?, ?, ?)
            """, club)


# =========================================================
# DEMO BADGES
# =========================================================

def create_demo_badges(connection):

    badges = [
        (
            "Event Explorer",
            "Awarded for participating in campus events.",
            "Participate in 3 events"
        ),
        (
            "Club Contributor",
            "Awarded for active club participation.",
            "Participate in club activities"
        ),
        (
            "Campus Achiever",
            "Awarded for consistent campus engagement.",
            "Complete multiple campus activities"
        )
    ]

    for badge in badges:

        existing = connection.execute("""
            SELECT id
            FROM badges
            WHERE name = ?
        """, (badge[0],)).fetchone()

        if existing is None:

            connection.execute("""
                INSERT INTO badges
                (
                    name,
                    description,
                    criteria
                )
                VALUES (?, ?, ?)
            """, badge)


# =========================================================
# RUN INITIALIZATION
# =========================================================

if __name__ == "__main__":
    init_db()
    print("CampusClub database initialized successfully.")