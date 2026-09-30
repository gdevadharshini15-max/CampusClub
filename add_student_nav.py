from pathlib import Path

BASE = Path(__file__).parent / "templates"

NAVBAR = r'''
<nav style="
    background:#111827;
    border:1px solid #273244;
    border-radius:16px;
    padding:12px 16px;
    margin-bottom:24px;
    display:flex;
    flex-wrap:wrap;
    align-items:center;
    gap:8px;
">

    <a href="{{ url_for('dashboard') }}"
       style="color:white;text-decoration:none;font-weight:700;margin-right:12px;">
        CampusClub
    </a>

    <a href="{{ url_for('dashboard') }}" class="nav-link-custom">Dashboard</a>
    <a href="{{ url_for('events') }}" class="nav-link-custom">Events</a>
    <a href="{{ url_for('my_registrations') }}" class="nav-link-custom">My Registrations</a>
    <a href="{{ url_for('clubs') }}" class="nav-link-custom">Clubs</a>
    <a href="{{ url_for('od_requests') }}" class="nav-link-custom">OD Requests</a>
    <a href="{{ url_for('timetable') }}" class="nav-link-custom">Timetable</a>
    <a href="{{ url_for('notifications') }}" class="nav-link-custom">Notifications</a>
    <a href="{{ url_for('badges') }}" class="nav-link-custom">Badges</a>
    <a href="{{ url_for('certificates') }}" class="nav-link-custom">Certificates</a>
    <a href="{{ url_for('student_passport') }}" class="nav-link-custom">Passport</a>
    <a href="{{ url_for('analytics') }}" class="nav-link-custom">Analytics</a>

    <a href="{{ url_for('logout') }}"
       style="
       color:#ff9b9b;
       text-decoration:none;
       margin-left:auto;
       ">
        Logout
    </a>
</nav>

<style>
.nav-link-custom {
    color:#cbd5e1;
    text-decoration:none;
    padding:7px 10px;
    border-radius:8px;
}

.nav-link-custom:hover {
    background:#1f2937;
    color:white;
}
</style>
'''

pages = [
    "events.html",
    "my_registrations.html",
    "clubs.html",
    "od_requests.html",
    "timetable.html",
    "notifications.html",
    "badges.html",
    "certificates.html",
    "student_passport.html",
    "analytics.html"
]

for filename in pages:

    path = BASE / filename

    if not path.exists():
        print("SKIPPED:", filename)
        continue

    text = path.read_text(encoding="utf-8")

    # Remove previous navbar include if we added one
    text = text.replace("{% include 'navbar.html' %}", "")

    # Remove only if this script was accidentally run twice
    marker = "<!-- CAMPUSCLUB GLOBAL NAV -->"
    if marker in text:
        print("ALREADY DONE:", filename)
        continue

    navbar_block = (
        marker +
        "\n" +
        NAVBAR +
        "\n<!-- END CAMPUSCLUB GLOBAL NAV -->\n"
    )

    if "<body>" in text:
        text = text.replace(
            "<body>",
            "<body>\n" + navbar_block,
            1
        )

    elif "<body " in text:
        start = text.find("<body")
        end = text.find(">", start)

        if end != -1:
            text = (
                text[:end + 1]
                + "\n"
                + navbar_block
                + text[end + 1:]
            )
        else:
            print("BODY NOT FOUND:", filename)
            continue

    else:
        print("BODY NOT FOUND:", filename)
        continue

    path.write_text(text, encoding="utf-8")

    print("UPDATED:", filename)

print("\nGLOBAL STUDENT NAVIGATION ADDED.")