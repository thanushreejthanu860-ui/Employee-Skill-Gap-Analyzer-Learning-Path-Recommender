from io import StringIO
from pathlib import Path
import csv
from flask import Flask, flash, jsonify, make_response, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash, generate_password_hash
from database import connect, init_db, row, rows
from services.analysis import analyze, dashboard_metrics, employee_skills, extract_skills, learning_path, match_roles, recommendations
from services.analytics import organization_analytics

app = Flask(__name__)
app.config["SECRET_KEY"] = "skillpath-demo-secret"
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
app.config["RESUME_UPLOAD_FOLDER"] = Path(__file__).resolve().parent / "uploads" / "resumes"
DEMO_USERNAME = "admin"
DEMO_PASSWORD = "admin123"
EMPLOYEE_DEFAULT_PASSWORD = "employee123"
init_db()


def save_employee(payload, employee_id=None):
    name = payload.get("name", "").strip()
    email = payload.get("email", "").strip()
    department = payload.get("department", "").strip()
    if not name or not email or not department:
        raise ValueError("Name, email, and department are required.")
    db = connect()
    values = (name, email, department, int(payload.get("experience", 1)), payload.get("profile", "").strip())
    if employee_id:
        db.execute("UPDATE employees SET name=?, email=?, department=?, experience=?, profile=? WHERE id=?", values + (employee_id,))
        db.execute("DELETE FROM employee_skills WHERE employee_id=?", (employee_id,))
    else:
        employee_id = db.execute("INSERT INTO employees(name,email,department,experience,profile,password_hash) VALUES (?,?,?,?,?,?)", values + (generate_password_hash(EMPLOYEE_DEFAULT_PASSWORD),)).lastrowid
    skill_map = {item["name"]: item["id"] for item in rows("SELECT id, name FROM skills")}
    skills = payload.get("skills", {})
    for skill_name in extract_skills(values[-1]):
        skills.setdefault(skill_name, 45)
    db.executemany("INSERT OR REPLACE INTO employee_skills(employee_id, skill_id, proficiency) VALUES (?,?,?)", [(employee_id, skill_map[name], max(0, min(100, int(level)))) for name, level in skills.items() if name in skill_map])
    db.commit(); db.close()
    return employee_id


@app.context_processor
def inject_globals():
    return {"nav_employee_count": row("SELECT COUNT(*) AS count FROM employees")["count"], "notifications": notifications_data()}


def create_notification(recipient_id, recipient_role, title, message):
    db = connect()
    db.execute("INSERT INTO notifications(recipient_id, recipient_role, title, message) VALUES (?, ?, ?, ?)", (recipient_id, recipient_role, title, message))
    db.commit()
    db.close()


def assessment_form_data(employee_id):
    profile = row("SELECT * FROM employee_profiles WHERE employee_id=?", (employee_id,)) or {}
    certifications = rows("SELECT * FROM employee_certifications WHERE employee_id=? ORDER BY id", (employee_id,))
    projects = rows("SELECT * FROM employee_projects WHERE employee_id=? ORDER BY id", (employee_id,))
    return profile, certifications, projects


def save_assessment(employee_id, form, files):
    employee = row("SELECT * FROM employees WHERE id=?", (employee_id,))
    if not employee:
        raise ValueError("Employee account could not be found.")
    if form.get("employee_id", "").strip() != str(employee_id):
        raise ValueError("The employee ID does not match the signed-in account.")
    required = {field: form.get(field, "").strip() for field in ("name", "department", "current_role", "target_role_id")}
    if any(not value for value in required.values()):
        raise ValueError("Please complete all required professional information.")
    try:
        experience = float(form.get("experience", ""))
        if experience < 0:
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError("Years of experience must be a non-negative number.")
    target_role = row("SELECT id FROM roles WHERE id=?", (required["target_role_id"],))
    if not target_role:
        raise ValueError("Please select a valid target role.")
    skill_ids = form.getlist("skill_id")
    levels = form.getlist("skill_level")
    descriptions = form.getlist("skill_description")
    if not skill_ids:
        raise ValueError("Add at least one current skill.")
    skill_rows = rows("SELECT id FROM skills WHERE id IN ({})".format(",".join("?" for _ in skill_ids)), skill_ids)
    valid_skill_ids = {str(item["id"]) for item in skill_rows}
    if any(skill_id not in valid_skill_ids for skill_id in skill_ids) or len(skill_ids) != len(levels):
        raise ValueError("Please select valid skills and proficiency levels.")
    skill_values = []
    for index, skill_id in enumerate(skill_ids):
        try:
            level = int(levels[index])
            if level < 0 or level > 100:
                raise ValueError
        except (TypeError, ValueError):
            raise ValueError("Skill proficiency must be between 0 and 100.")
        skill_values.append((employee_id, int(skill_id), level, descriptions[index].strip() if index < len(descriptions) else ""))
    resume = files.get("resume")
    resume_filename = ""
    if resume and resume.filename:
        resume_filename = secure_filename(resume.filename)
        if not resume_filename or "." not in resume_filename or resume_filename.rsplit(".", 1)[1].lower() not in {"pdf", "doc", "docx"}:
            raise ValueError("Resume must be a PDF, DOC, or DOCX file.")
        app.config["RESUME_UPLOAD_FOLDER"].mkdir(parents=True, exist_ok=True)
        resume.save(app.config["RESUME_UPLOAD_FOLDER"] / f"{employee_id}_{resume_filename}")
    db = connect()
    try:
        db.execute("UPDATE employees SET name=?, department=?, current_role=?, experience=?, profile=? WHERE id=?", (required["name"], required["department"], required["current_role"], experience, form.get("resume_summary", "").strip(), employee_id))
        db.execute("INSERT INTO employee_profiles(employee_id, target_role_id, highest_qualification, specialization, institution, resume_summary, resume_filename, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP) ON CONFLICT(employee_id) DO UPDATE SET target_role_id=excluded.target_role_id, highest_qualification=excluded.highest_qualification, specialization=excluded.specialization, institution=excluded.institution, resume_summary=excluded.resume_summary, resume_filename=CASE WHEN excluded.resume_filename='' THEN employee_profiles.resume_filename ELSE excluded.resume_filename END, updated_at=CURRENT_TIMESTAMP", (employee_id, int(required["target_role_id"]), form.get("qualification", "").strip(), form.get("specialization", "").strip(), form.get("institution", "").strip(), form.get("resume_summary", "").strip(), resume_filename))
        db.execute("DELETE FROM employee_skills WHERE employee_id=?", (employee_id,))
        db.executemany("INSERT INTO employee_skills(employee_id, skill_id, proficiency, experience) VALUES (?, ?, ?, ?)", skill_values)
        db.execute("DELETE FROM employee_certifications WHERE employee_id=?", (employee_id,))
        db.executemany("INSERT INTO employee_certifications(employee_id, name, issuer, issued_at) VALUES (?, ?, ?, ?)", [(employee_id, name.strip(), issuer.strip(), year.strip()) for name, issuer, year in zip(form.getlist("cert_name"), form.getlist("cert_issuer"), form.getlist("cert_year")) if name.strip()])
        db.execute("DELETE FROM employee_projects WHERE employee_id=?", (employee_id,))
        db.executemany("INSERT INTO employee_projects(employee_id, name, description, technologies) VALUES (?, ?, ?, ?)", [(employee_id, name.strip(), description.strip(), technologies.strip()) for name, description, technologies in zip(form.getlist("project_name"), form.getlist("project_description"), form.getlist("project_technologies")) if name.strip()])
        assessment_update = db.execute("UPDATE assessment_requests SET status='Completed', completed_at=CURRENT_TIMESTAMP WHERE id=? AND employee_id=? AND status='Pending'", (form.get("assessment_id"), employee_id))
        if assessment_update.rowcount != 1:
            raise ValueError("This assessment request is no longer pending.")
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    create_notification(employee_id, "HR", "Assessment Submitted", f"{required['name']} has submitted the Skill Assessment.")


def employee_from_session():
    if not session.get("employee_authenticated") or not session.get("employee_id"):
        return None
    return row("SELECT id, name, email FROM employees WHERE id=?", (session["employee_id"],))


@app.route("/")
def index(): return redirect(url_for("dashboard")) if session.get("authenticated") else redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("authenticated"):
        return redirect(url_for("dashboard"))
    if session.get("employee_authenticated"):
        return redirect(url_for("employee_dashboard"))
    error = None
    if request.method == "POST":
        role = request.form.get("role", "hr")
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if role == "hr":
            if username == DEMO_USERNAME and password == DEMO_PASSWORD:
                session.clear()
                session["authenticated"] = True
                session["username"] = username
                return redirect(url_for("dashboard"))
            error = "Invalid HR credentials."
        else:
            employee = row("SELECT * FROM employees WHERE lower(email)=?", (username.lower(),))
            if employee and employee.get("password_hash") and check_password_hash(employee["password_hash"], password):
                session.clear()
                session["employee_authenticated"] = True
                session["employee_id"] = employee["id"]
                session["role"] = "Employee"
                return redirect(url_for("employee_dashboard"))
            error = "Invalid employee email or password."
    return render_template("login.html", error=error)

@app.route("/employee/register", methods=["GET", "POST"])
def employee_register():
    if session.get("employee_authenticated"):
        return redirect(url_for("employee_dashboard"))
    error = None
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        department = request.form.get("department", "").strip()
        password = request.form.get("password", "").strip()
        if not name or not email or not department or not password:
            error = "All fields are required."
        elif row("SELECT id FROM employees WHERE lower(email)=?", (email,)):
            error = "An account with that email already exists."
        else:
            db = connect()
            emp_id = db.execute("INSERT INTO employees(name, email, department, experience, profile, current_role, password_hash) VALUES (?,?,?,?,?,?,?)", (name, email, department, 0, "", "", generate_password_hash(password))).lastrowid
            db.commit()
            db.close()
            session.clear()
            session["employee_authenticated"] = True
            session["employee_id"] = emp_id
            session["role"] = "Employee"
            return redirect(url_for("employee_dashboard"))
    return render_template("employee_register.html", error=error, form=request.form)

@app.route("/employee/login", methods=["GET", "POST"])
def employee_login():
    return redirect(url_for("login"))

@app.route("/employee/dashboard")
def employee_dashboard():
    employee = employee_from_session()
    if not employee:
        return redirect(url_for("login", next=request.path))
    employee = row("SELECT id, name, email, department, experience, current_role, profile FROM employees WHERE id=?", (employee["id"],))
    assessment = row("SELECT * FROM assessment_requests WHERE employee_id=? AND status='Pending' ORDER BY created_at DESC, id DESC LIMIT 1", (employee["id"],))
    notifications = rows("SELECT * FROM notifications WHERE recipient_role='Employee' AND recipient_id=? ORDER BY created_at DESC, id DESC LIMIT 10", (employee["id"],))
    completed = row("SELECT id FROM assessment_requests WHERE employee_id=? AND status IN ('Completed','Reviewed') ORDER BY id DESC LIMIT 1", (employee["id"],))
    profile = row("SELECT target_role_id FROM employee_profiles WHERE employee_id=?", (employee["id"],))
    target_role = row("SELECT * FROM roles WHERE id=?", (profile["target_role_id"],)) if profile and profile["target_role_id"] else None
    result = analyze(employee["id"], target_role["id"]) if completed and target_role else None
    employee_path = learning_path(employee["id"], target_role["id"]) if result else []
    return render_template("employee_dashboard.html", employee=employee, skills=employee_skills(employee["id"]), assessment=assessment, employee_notifications=notifications, target_role=target_role, employee_result=result, employee_path=employee_path)


@app.get("/employee/messages")
def employee_messages():
    employee = employee_from_session()
    if not employee:
        return redirect(url_for("login", next=request.path))
    messages = rows("""
        SELECT m.*,
               CASE WHEN m.sender_id = ? THEN
                   CASE WHEN m.receiver_role = 'HR' THEN 'HR Manager' ELSE (SELECT e.name FROM employees e WHERE e.id = m.receiver_id) END
               ELSE
                   CASE WHEN m.sender_role = 'HR' THEN 'HR Manager' ELSE (SELECT e.name FROM employees e WHERE e.id = m.sender_id) END
               END AS contact_name
        FROM messages m
        WHERE (m.sender_id = ? AND m.sender_role = 'Employee')
           OR (m.receiver_id = ? AND m.receiver_role = 'Employee')
        ORDER BY m.created_at DESC, m.id DESC
    """, (employee["id"], employee["id"], employee["id"]))
    assessment = row("SELECT * FROM assessment_requests WHERE employee_id=? AND status='Pending' ORDER BY created_at DESC, id DESC LIMIT 1", (employee["id"],))
    return render_template("employee_messages.html", employee=employee, messages=messages, assessment=assessment)


@app.route("/employee/messages/new", methods=["GET", "POST"])
@app.post("/employee/messages/send")
def employee_new_message():
    employee = employee_from_session()
    if not employee:
        return redirect(url_for("login", next=request.path))
    if request.method == "POST":
        subject = request.form.get("subject", "").strip()
        message = request.form.get("message", "").strip()
        recipient_type = request.form.get("recipient_type", "hr")
        if not subject or not message:
            flash("Subject and message are required.", "danger")
            return render_template("employee_new_message.html", employee=employee, form=request.form)
        if recipient_type == "employee":
            recipient_email = request.form.get("recipient_email", "").strip().lower()
            recipient = row("SELECT id, name FROM employees WHERE lower(email)=? AND id!=?", (recipient_email, employee["id"]))
            if not recipient:
                flash("No employee found with that email address.", "danger")
                return render_template("employee_new_message.html", employee=employee, form=request.form)
            db = connect()
            db.execute("INSERT INTO messages(sender_id, receiver_id, sender_role, receiver_role, subject, message) VALUES (?, ?, 'Employee', 'Employee', ?, ?)", (employee["id"], recipient["id"], subject, message))
            db.commit()
            db.close()
            create_notification(recipient["id"], "Employee", f"New message from {employee['name']}", message[:100])
            flash(f"Message sent to {recipient['name']}.", "success")
        else:
            db = connect()
            db.execute("INSERT INTO messages(sender_id, receiver_id, sender_role, receiver_role, subject, message) VALUES (?, ?, 'Employee', 'HR', ?, ?)", (employee["id"], None, subject, message))
            db.commit()
            db.close()
            create_notification(None, "HR", "New employee message", f"New message from {employee['name']}.")
            flash("Message sent to HR.", "success")
        return redirect(url_for("employee_messages"))
    return render_template("employee_new_message.html", employee=employee, form={})


@app.get("/employee/messages/<int:message_id>")
def employee_message_view(message_id):
    employee = employee_from_session()
    if not employee:
        return redirect(url_for("login", next=request.path))
    message = row("""
        SELECT m.*,
               CASE WHEN m.sender_id = ? THEN 'You'
                    WHEN m.sender_role = 'HR' THEN 'HR Manager'
                    ELSE (SELECT e.name FROM employees e WHERE e.id = m.sender_id) END AS sender_name
        FROM messages m
        WHERE m.id=? AND (
            (m.sender_id=? AND m.sender_role='Employee') OR
            (m.receiver_id=? AND m.receiver_role='Employee')
        )
    """, (employee["id"], message_id, employee["id"], employee["id"]))
    if not message:
        flash("That message could not be found.", "warning")
        return redirect(url_for("employee_messages"))
    if message["receiver_role"] == "Employee" and message["receiver_id"] == employee["id"] and not message["is_read"]:
        db = connect(); db.execute("UPDATE messages SET is_read=1 WHERE id=?", (message_id,)); db.commit(); db.close()
        message["is_read"] = 1
    return render_template("employee_message_view.html", employee=employee, message=message)


@app.get("/hr/messages")
def hr_messages():
    if not session.get("authenticated"):
        return redirect(url_for("login", next=request.path))
    messages = rows("""
        SELECT m.*, e.name AS employee_name, (SELECT ar.status FROM assessment_requests ar WHERE ar.employee_id=e.id ORDER BY ar.id DESC LIMIT 1) AS assessment_status
        FROM messages m JOIN employees e ON e.id=m.sender_id
        WHERE m.sender_role='Employee' AND m.receiver_role='HR'
        ORDER BY m.created_at DESC, m.id DESC
    """)
    return render_template("hr_messages.html", messages=messages)


@app.route("/hr/messages/<int:message_id>", methods=["GET", "POST"])
def hr_message_view(message_id):
    if not session.get("authenticated"):
        return redirect(url_for("login", next=request.path))
    message = row("""
        SELECT m.*, e.name AS employee_name, e.email AS employee_email
        FROM messages m JOIN employees e ON e.id=m.sender_id
        WHERE m.id=? AND m.sender_role='Employee' AND m.receiver_role='HR'
    """, (message_id,))
    if not message:
        flash("That message could not be found.", "warning")
        return redirect(url_for("hr_messages"))
    if not message["is_read"]:
        db = connect(); db.execute("UPDATE messages SET is_read=1 WHERE id=?", (message_id,)); db.commit(); db.close()
        message["is_read"] = 1
    if request.method == "POST":
        reply = request.form.get("message", "").strip()
        if not reply:
            flash("Reply message cannot be empty.", "danger")
        else:
            subject = message["subject"] if message["subject"].lower().startswith("re:") else f"Re: {message['subject']}"
            db = connect()
            db.execute("INSERT INTO messages(sender_id, receiver_id, sender_role, receiver_role, subject, message) VALUES (?, ?, 'HR', 'Employee', ?, ?)", (None, message["sender_id"], subject, reply))
            db.commit(); db.close()
            create_notification(message["sender_id"], "Employee", "HR replied to your message", "HR replied to your message.")
            flash("Reply sent to the employee.", "success")
            return redirect(url_for("hr_message_view", message_id=message_id))
    assessment = row("SELECT * FROM assessment_requests WHERE employee_id=? ORDER BY created_at DESC, id DESC LIMIT 1", (message["sender_id"],))
    return render_template("hr_message_view.html", message=message, assessment=assessment)


@app.post("/hr/assessment/send/<int:employee_id>")
def send_assessment_request(employee_id):
    if not session.get("authenticated"):
        return redirect(url_for("login", next=request.path))
    employee = row("SELECT id, name FROM employees WHERE id=?", (employee_id,))
    if not employee:
        flash("That employee could not be found.", "warning")
        return redirect(url_for("hr_messages"))
    pending = row("SELECT id FROM assessment_requests WHERE employee_id=? AND status='Pending' LIMIT 1", (employee_id,))
    if pending:
        flash("This employee already has a pending assessment request.", "warning")
        return redirect(url_for("hr_messages"))
    db = connect()
    db.execute("INSERT INTO assessment_requests(employee_id, hr_id, status) VALUES (?, ?, 'Pending')", (employee_id, None))
    db.commit()
    db.close()
    create_notification(employee_id, "Employee", "Skill Assessment Requested", "HR Manager has requested you to complete your Skill Assessment Form.")
    flash("Skill Assessment Form sent successfully.", "success")
    return redirect(url_for("hr_messages"))


@app.get("/employee/assessment")
def employee_assessment():
    employee = employee_from_session()
    if not employee:
        return redirect(url_for("login", next=request.path))
    assessment = row("SELECT * FROM assessment_requests WHERE employee_id=? ORDER BY created_at DESC, id DESC LIMIT 1", (employee["id"],))
    if not assessment:
        flash("No pending skill assessment found.", "info")
        return redirect(url_for("employee_dashboard"))
    profile, certifications, projects = assessment_form_data(employee["id"])
    target_role = row("SELECT name FROM roles WHERE id=?", (profile.get("target_role_id"),)) if profile.get("target_role_id") else None
    if assessment["status"] == "Completed":
        return render_template("employee_assessment_submitted.html", employee=employee, assessment=assessment, profile=profile, target_role=target_role, certifications=certifications, projects=projects, skills=employee_skills(employee["id"]))
    return render_template("employee_assessment.html", employee=employee, assessment=assessment, profile=profile, certifications=certifications, projects=projects, skills=rows("SELECT * FROM skills ORDER BY name"), roles=rows("SELECT * FROM roles ORDER BY name"), current_skills=employee_skills(employee["id"]))


@app.post("/employee/assessment")
def submit_employee_assessment():
    employee = employee_from_session()
    if not employee:
        return redirect(url_for("login", next=request.path))
    assessment = row("SELECT * FROM assessment_requests WHERE id=? AND employee_id=? AND status='Pending'", (request.form.get("assessment_id"), employee["id"]))
    if not assessment:
        flash("No pending skill assessment found.", "warning")
        return redirect(url_for("employee_dashboard"))
    try:
        save_assessment(employee["id"], request.form, request.files)
    except ValueError as error:
        profile, certifications, projects = assessment_form_data(employee["id"])
        flash(str(error), "danger")
        return render_template("employee_assessment.html", employee=employee, assessment=assessment, profile=profile, certifications=certifications, projects=projects, skills=rows("SELECT * FROM skills ORDER BY name"), roles=rows("SELECT * FROM roles ORDER BY name"), current_skills=employee_skills(employee["id"])), 400
    flash("Assessment submitted successfully.", "success")
    return redirect(url_for("employee_assessment"))


@app.get("/hr/assessment/<int:employee_id>")
@app.get("/hr/assessments/<int:employee_id>")
def hr_assessment_review(employee_id):
    if not session.get("authenticated"):
        return redirect(url_for("login", next=request.path))
    employee = row("SELECT id, name, email, department, experience, current_role, profile FROM employees WHERE id=?", (employee_id,))
    assessment = row("SELECT * FROM assessment_requests WHERE employee_id=? AND status IN ('Completed', 'Reviewed') ORDER BY completed_at DESC, id DESC LIMIT 1", (employee_id,))
    if not employee or not assessment:
        flash("The submitted assessment could not be found.", "warning")
        return redirect(url_for("hr_assessments"))
    profile, certifications, projects = assessment_form_data(employee_id)
    target_role = row("SELECT name FROM roles WHERE id=?", (profile.get("target_role_id"),)) if profile.get("target_role_id") else None
    return render_template("hr_assessment_review.html", employee=employee, assessment=assessment, profile=profile, target_role=target_role, certifications=certifications, projects=projects, skills=employee_skills(employee_id))


@app.get("/hr/assessments")
def hr_assessments():
    if not session.get("authenticated"):
        return redirect(url_for("login", next=request.path))
    assessments = rows("""
        SELECT ar.*, e.name, e.department, e.current_role, e.experience,
               r.name AS target_role
        FROM assessment_requests ar
        JOIN employees e ON e.id=ar.employee_id
        LEFT JOIN employee_profiles ep ON ep.employee_id=e.id
        LEFT JOIN roles r ON r.id=ep.target_role_id
        WHERE ar.id = (SELECT latest.id FROM assessment_requests latest WHERE latest.employee_id=ar.employee_id ORDER BY latest.id DESC LIMIT 1)
        ORDER BY CASE ar.status WHEN 'Completed' THEN 1 WHEN 'Pending' THEN 2 ELSE 3 END, COALESCE(ar.completed_at, ar.created_at) DESC
    """)
    return render_template("hr_assessments.html", assessments=assessments)


@app.post("/hr/assessments/<int:employee_id>/review")
def mark_assessment_reviewed(employee_id):
    if not session.get("authenticated"):
        return redirect(url_for("login", next=request.path))
    db = connect()
    updated = db.execute("UPDATE assessment_requests SET status='Reviewed' WHERE employee_id=? AND status='Completed'", (employee_id,))
    db.commit()
    db.close()
    if updated.rowcount:
        flash("Assessment marked as reviewed.", "success")
    else:
        flash("No completed assessment is available to review.", "warning")
    return redirect(url_for("hr_assessment_review", employee_id=employee_id))


@app.post("/hr/assessments/<int:employee_id>/action")
def assessment_action(employee_id):
    if not session.get("authenticated"):
        return redirect(url_for("login", next=request.path))
    action = request.form.get("action")
    redirect_to = request.form.get("redirect_to", "assessments")
    if action not in ("accept", "reject"):
        flash("Invalid action.", "danger")
        return redirect(url_for("hr_assessments"))
    new_status = "Reviewed" if action == "accept" else "Rejected"
    db = connect()
    updated = db.execute("UPDATE assessment_requests SET status=? WHERE employee_id=? AND status='Completed'", (new_status, employee_id))
    db.commit()
    db.close()
    employee = row("SELECT name FROM employees WHERE id=?", (employee_id,))
    if updated.rowcount:
        label = "accepted" if action == "accept" else "rejected"
        flash(f"Assessment {label}.", "success")
        create_notification(employee_id, "Employee", f"Assessment {label.capitalize()}", f"HR has {label} your submitted Skill Assessment.")
    else:
        flash("No completed assessment found to action.", "warning")
    if redirect_to == "message":
        message = row("SELECT id FROM messages WHERE sender_id=? AND sender_role='Employee' AND receiver_role='HR' ORDER BY id DESC LIMIT 1", (employee_id,))
        if message:
            return redirect(url_for("hr_message_view", message_id=message["id"]))
    if redirect_to == "review":
        return redirect(url_for("hr_assessments"))
    return redirect(url_for("hr_assessments"))


@app.get("/hr/assessments/<int:employee_id>/resume")
def hr_assessment_resume(employee_id):
    if not session.get("authenticated"):
        return redirect(url_for("login", next=request.path))
    profile = row("SELECT resume_filename FROM employee_profiles WHERE employee_id=?", (employee_id,))
    assessment = row("SELECT id FROM assessment_requests WHERE employee_id=? AND status IN ('Completed', 'Reviewed')", (employee_id,))
    if not profile or not profile["resume_filename"] or not assessment:
        flash("No submitted resume is available.", "warning")
        return redirect(url_for("hr_assessment_review", employee_id=employee_id))
    return send_from_directory(app.config["RESUME_UPLOAD_FOLDER"], f"{employee_id}_{profile['resume_filename']}", as_attachment=False, download_name=profile["resume_filename"])


@app.get("/hr/skill-analysis", defaults={"employee_id": None})
@app.get("/hr/skill-analysis/<int:employee_id>")
def hr_skill_analysis(employee_id):
    if not session.get("authenticated"):
        return redirect(url_for("login", next=request.path))
    employees = rows("SELECT DISTINCT e.* FROM employees e JOIN assessment_requests ar ON ar.employee_id=e.id WHERE ar.status IN ('Completed', 'Reviewed') ORDER BY e.name")
    roles = rows("SELECT * FROM roles ORDER BY name")
    if not employees or not roles:
        flash("A completed employee assessment and at least one role are required.", "info")
        return render_template("hr_skill_analysis.html", employees=employees, roles=roles, employee=None, selected_role=None, result=None)
    requested_employee_id = request.args.get("employee_id")
    employee_id = int(requested_employee_id) if requested_employee_id else int(employee_id or row("SELECT e.id FROM employees e JOIN assessment_requests ar ON ar.employee_id=e.id WHERE ar.status IN ('Completed', 'Reviewed') ORDER BY e.name LIMIT 1")["id"])
    employee = row("SELECT * FROM employees WHERE id=?", (employee_id,))
    if not employee or employee["id"] not in {item["id"] for item in employees}:
        flash("That employee assessment could not be found.", "warning")
        return redirect(url_for("hr_skill_analysis"))
    profile = row("SELECT target_role_id FROM employee_profiles WHERE employee_id=?", (employee_id,))
    role_id = int(request.args.get("role_id", profile["target_role_id"] if profile and profile["target_role_id"] else roles[0]["id"]))
    selected_role = row("SELECT * FROM roles WHERE id=?", (role_id,))
    if not selected_role:
        flash("That target role could not be found.", "warning")
        return redirect(url_for("hr_skill_analysis", employee_id=employee_id))
    result = analyze(employee_id, role_id)
    match = next((item for item in match_roles(employee_id) if item["id"] == role_id), None)
    return render_template("hr_skill_analysis.html", employees=employees, roles=roles, employee=employee, selected_role=selected_role, result=result, match=match)


@app.get("/hr/role-matching/<int:employee_id>")
def hr_role_matching(employee_id):
    if not session.get("authenticated"):
        return redirect(url_for("login", next=request.path))
    employees = rows("SELECT DISTINCT e.* FROM employees e JOIN assessment_requests ar ON ar.employee_id=e.id WHERE ar.status IN ('Completed', 'Reviewed') ORDER BY e.name")
    employee = row("SELECT * FROM employees WHERE id=?", (employee_id,))
    if not employee or employee["id"] not in {item["id"] for item in employees}:
        flash("That employee assessment could not be found.", "warning")
        return redirect(url_for("hr_assessments"))
    return render_template("hr_role_matching.html", employees=employees, employee=employee, matches=match_roles(employee_id))

@app.route("/employee/settings", methods=["GET", "POST"])
def employee_settings():
    employee = employee_from_session()
    if not employee:
        return redirect(url_for("login", next=request.path))
    error, success = None, None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()
        if not email:
            error = "Email is required."
        else:
            existing = row("SELECT id FROM employees WHERE lower(email)=? AND id!=?", (email, employee["id"]))
            if existing:
                error = "That email is already in use by another employee."
            else:
                db = connect()
                db.execute("UPDATE employees SET email=? WHERE id=?", (email, employee["id"]))
                if password:
                    db.execute("UPDATE employees SET password_hash=? WHERE id=?", (generate_password_hash(password), employee["id"]))
                db.commit()
                db.close()
                success = "Your email and password have been updated. Use your new email to log in next time."
    employee = row("SELECT id, name, email FROM employees WHERE id=?", (employee["id"],))
    return render_template("employee_settings.html", employee=employee, error=error, success=success)
@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
def dashboard():
    if not session.get("authenticated"):
        return redirect(url_for("login", next=request.path))
    assessment_summary = row("SELECT COUNT(*) AS total, SUM(CASE WHEN status='Pending' THEN 1 ELSE 0 END) AS pending, SUM(CASE WHEN status IN ('Completed', 'Reviewed') THEN 1 ELSE 0 END) AS completed FROM assessment_requests")
    recent_assessments = rows("SELECT ar.employee_id, ar.status, ar.completed_at, e.name, e.current_role FROM assessment_requests ar JOIN employees e ON e.id=ar.employee_id WHERE ar.status IN ('Completed','Reviewed') ORDER BY ar.completed_at DESC, ar.id DESC LIMIT 5")
    return render_template("dashboard.html", metrics=dashboard_metrics(), people=rows("SELECT * FROM employees ORDER BY name LIMIT 5"), assessment_summary=assessment_summary, recent_assessments=recent_assessments)

@app.route("/employees")
def employees():
    query = request.args.get("q", "").strip()
    department = request.args.get("department", "").strip()
    role = request.args.get("role", "").strip()
    readiness = request.args.get("readiness", "").strip()
    risk = request.args.get("risk", "").strip()
    conditions = ["(e.name LIKE ? OR e.email LIKE ? OR CAST(e.id AS TEXT) LIKE ? OR e.department LIKE ? OR e.current_role LIKE ?)"]
    params = [f"%{query}%"] * 5
    if department: conditions.append("e.department = ?"); params.append(department)
    if role: conditions.append("e.current_role = ?"); params.append(role)
    data = rows(f"SELECT e.* FROM employees e WHERE {' AND '.join(conditions)} ORDER BY e.name", params)
    default_role = row("SELECT id FROM roles ORDER BY id LIMIT 1")
    if default_role:
        evaluated = [(item, analyze(item["id"], default_role["id"])) for item in data]
        if readiness == "ready": evaluated = [(item, result) for item, result in evaluated if result["readiness"] >= 70]
        if readiness == "developing": evaluated = [(item, result) for item, result in evaluated if result["readiness"] < 70]
        if risk == "high": evaluated = [(item, result) for item, result in evaluated if result["critical"] > 0]
        if risk == "low": evaluated = [(item, result) for item, result in evaluated if result["critical"] == 0]
        data = [item for item, _ in evaluated]
    return render_template("employees.html", employees=data, query=query, filters={"department": department, "role": role, "readiness": readiness, "risk": risk}, departments=rows("SELECT DISTINCT department FROM employees ORDER BY department"), roles=rows("SELECT DISTINCT current_role AS name FROM employees WHERE current_role <> '' ORDER BY current_role"))

@app.route("/employees/new", methods=["GET", "POST"])
def add_employee():
    if request.method == "POST":
        try: employee_id = save_employee(request.form.to_dict(flat=True) | {"skills": {key.removeprefix("skill_"): value for key, value in request.form.items() if key.startswith("skill_")}}); return redirect(url_for("employee_profile", employee_id=employee_id))
        except ValueError as error: return render_template("employee_form.html", skills=rows("SELECT * FROM skills"), error=str(error), employee=request.form)
    return render_template("employee_form.html", skills=rows("SELECT * FROM skills"), employee={})

@app.route("/employees/<int:employee_id>/edit", methods=["GET", "POST"])
def edit_employee(employee_id):
    employee = row("SELECT * FROM employees WHERE id=?", (employee_id,))
    if request.method == "POST":
        save_employee(request.form.to_dict(flat=True) | {"skills": {key.removeprefix("skill_"): value for key, value in request.form.items() if key.startswith("skill_")}}, employee_id); return redirect(url_for("employee_profile", employee_id=employee_id))
    employee["skills"] = employee_skills(employee_id)
    return render_template("employee_form.html", skills=rows("SELECT * FROM skills"), employee=employee, edit=True)

@app.post("/employees/<int:employee_id>/delete")
def delete_employee(employee_id):
    db = connect(); db.execute("DELETE FROM employees WHERE id=?", (employee_id,)); db.commit(); db.close(); return redirect(url_for("employees"))

@app.route("/employees/<int:employee_id>")
def employee_profile(employee_id):
    employee = row("SELECT * FROM employees WHERE id=?", (employee_id,)); return render_template("employee_profile.html", employee=employee, skills=employee_skills(employee_id), roles=rows("SELECT * FROM roles ORDER BY name"))

@app.route("/analysis/<int:employee_id>")
def analysis_page(employee_id):
    employee = row("SELECT * FROM employees WHERE id=?", (employee_id,)); roles = rows("SELECT * FROM roles ORDER BY name"); role_id = request.args.get("role_id", roles[0]["id"] if roles else None); result = analyze(employee_id, int(role_id)) if role_id else {}
    selected_role = row("SELECT * FROM roles WHERE id=?", (role_id,)) if role_id else None
    return render_template("analysis.html", employee=employee, roles=roles, selected_role=selected_role, result=result)

@app.route("/matching", defaults={"employee_id": None})
@app.route("/matching/<int:employee_id>")
def matching_page(employee_id):
    employees = rows("SELECT * FROM employees ORDER BY name")
    employee_id = int(request.args.get("employee_id", employee_id or (employees[0]["id"] if employees else 0)))
    selected = row("SELECT * FROM employees WHERE id=?", (employee_id,)) if employee_id else None
    return render_template("matching.html", employees=employees, employee=selected, matches=match_roles(employee_id) if selected else [])

@app.route("/learning-path", defaults={"employee_id": None})
@app.route("/learning-path/<int:employee_id>")
def learning_path_page(employee_id):
    if session.get("employee_authenticated"):
        own_employee_id = session.get("employee_id")
        if employee_id and employee_id != own_employee_id:
            flash("You can only view your own learning path.", "warning")
            return redirect(url_for("employee_learning_path"))
        return redirect(url_for("employee_learning_path"))
    if not session.get("authenticated"):
        return redirect(url_for("login", next=request.path))
    employees = rows("SELECT * FROM employees ORDER BY name")
    roles = rows("SELECT * FROM roles ORDER BY name")
    employee_id = int(request.args.get("employee_id", employee_id or (employees[0]["id"] if employees else 0)))
    role_id = int(request.args.get("role_id", roles[0]["id"])) if roles else None
    selected_employee = row("SELECT * FROM employees WHERE id=?", (employee_id,)) if employee_id else None
    selected_role = row("SELECT * FROM roles WHERE id=?", (role_id,)) if role_id else None
    return render_template("learning_path.html", employees=employees, employee=selected_employee, roles=roles, selected_role=selected_role, result=analyze(employee_id, role_id) if selected_employee and role_id else {}, path=learning_path(employee_id, role_id) if selected_employee and role_id else [], recommendations=recommendations(employee_id, role_id) if selected_employee and role_id else [], is_employee_view=False)


@app.get("/hr/learning-path/<int:employee_id>")
def hr_learning_path(employee_id):
    if not session.get("authenticated"):
        return redirect(url_for("login", next=request.path))
    employee = row("SELECT e.* FROM employees e JOIN assessment_requests ar ON ar.employee_id=e.id WHERE e.id=? AND ar.status IN ('Completed', 'Reviewed')", (employee_id,))
    roles = rows("SELECT * FROM roles ORDER BY name")
    if not employee or not roles:
        flash("A completed assessment and available role are required.", "warning")
        return redirect(url_for("hr_assessments"))
    profile = row("SELECT target_role_id FROM employee_profiles WHERE employee_id=?", (employee_id,))
    requested_role_id = request.args.get("role_id")
    role_id = int(requested_role_id) if requested_role_id else int(profile["target_role_id"] if profile and profile["target_role_id"] else roles[0]["id"])
    selected_role = row("SELECT * FROM roles WHERE id=?", (role_id,))
    if not selected_role:
        flash("That target role could not be found.", "warning")
        return redirect(url_for("hr_learning_path", employee_id=employee_id))
    return render_template("learning_path.html", employees=[employee], employee=employee, roles=roles, selected_role=selected_role, result=analyze(employee_id, role_id), path=learning_path(employee_id, role_id), recommendations=recommendations(employee_id, role_id), is_employee_view=False)


@app.get("/employee/learning-path")
def employee_learning_path():
    employee = employee_from_session()
    if not employee:
        return redirect(url_for("login", next=request.path))
    completed = row("SELECT id FROM assessment_requests WHERE employee_id=? AND status IN ('Completed', 'Reviewed') ORDER BY id DESC LIMIT 1", (employee["id"],))
    profile = row("SELECT target_role_id FROM employee_profiles WHERE employee_id=?", (employee["id"],))
    roles = rows("SELECT * FROM roles ORDER BY name")
    if not completed or not profile or not profile["target_role_id"]:
        flash("Submit an assessment with a target role before viewing a learning path.", "info")
        return redirect(url_for("employee_dashboard"))
    selected_role = row("SELECT * FROM roles WHERE id=?", (profile["target_role_id"],))
    return render_template("learning_path.html", employees=[employee], employee=employee, roles=[selected_role] if selected_role else roles, selected_role=selected_role, result=analyze(employee["id"], profile["target_role_id"]) if selected_role else {}, path=learning_path(employee["id"], profile["target_role_id"]) if selected_role else [], recommendations=recommendations(employee["id"], profile["target_role_id"]) if selected_role else [], is_employee_view=True)

@app.route("/resources")
def resources_page(): return render_template("resources.html", resources=rows("SELECT lr.*, s.name AS skill FROM learning_resources lr JOIN skills s ON s.id=lr.skill_id ORDER BY s.name, lr.name"), skills=rows("SELECT * FROM skills ORDER BY name"))

@app.route("/analytics")
def analytics(): return render_template("analytics.html", metrics=dashboard_metrics())

@app.get("/hr/analytics")
def hr_analytics():
    if not session.get("authenticated"):
        return redirect(url_for("login", next=request.path))
    return render_template("hr_analytics.html", analytics=organization_analytics())


@app.get("/hr/reports")
def hr_reports():
    if not session.get("authenticated"):
        return redirect(url_for("login", next=request.path))
    return render_template("hr_reports.html", analytics=organization_analytics())


@app.get("/hr/reports.csv")
def hr_reports_csv():
    if not session.get("authenticated"):
        return redirect(url_for("login", next=request.path))
    report = organization_analytics()
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Employee", "Employee ID", "Department", "Current Role", "Target Role", "Readiness", "Development Status", "Top Skill Gaps", "Learning Areas"])
    for employee in report["employees"]:
        writer.writerow([employee["name"], employee["id"], employee["department"], employee["current_role"], employee["target_role"], employee["readiness"], employee["readiness_label"], "; ".join(item["skill"] for item in employee["top_gaps"]), employee["learning_count"]])
    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = "attachment; filename=skillpath-hr-report.csv"
    return response

@app.route("/configuration")
def configuration(): return render_template("configuration.html", skills=rows("SELECT * FROM skills ORDER BY name"), roles=rows("SELECT * FROM roles ORDER BY name"), role_skills={role["id"]: rows("SELECT s.name, rs.required_level FROM role_skills rs JOIN skills s ON s.id=rs.skill_id WHERE rs.role_id=?", (role["id"],)) for role in rows("SELECT id FROM roles")})

def notifications_data():
    first_employee = row("SELECT id, name FROM employees ORDER BY id LIMIT 1")
    low_skill_count = row("SELECT COUNT(*) AS count FROM employee_skills WHERE proficiency < 35")
    latest_resource = row("SELECT name FROM learning_resources ORDER BY id DESC LIMIT 1")
    notifications = [
        {"icon": "exclamation-triangle", "title": "Training focus identified", "message": f"{low_skill_count['count']} skill baselines are below 35%.", "time": "Current analysis"},
        {"icon": "signpost-split", "title": "Learning path ready", "message": f"A path is available for {first_employee['name']}." if first_employee else "Add an employee to generate a path.", "time": "Based on current data"},
        {"icon": "collection-play", "title": "Resource library updated", "message": f"Latest resource: {latest_resource['name']}." if latest_resource else "No resources available.", "time": "Resource catalog"},
    ]
    for item in rows("SELECT n.*, e.name AS employee_name FROM notifications n LEFT JOIN employees e ON e.id=n.recipient_id WHERE n.recipient_role='HR' ORDER BY n.created_at DESC, n.id DESC LIMIT 10"):
        item["icon"] = "clipboard-check"
        item["time"] = item["created_at"]
        item["action_url"] = url_for("hr_assessment_review", employee_id=item["recipient_id"]) if item["recipient_id"] else None
        notifications.insert(0, item)
    return notifications[:10]

@app.get("/api/notifications")
def api_notifications(): return jsonify(notifications_data())

@app.post("/configuration/skills")
def create_skill():
    name = request.form.get("name", "").strip()
    if name:
        db = connect(); db.execute("INSERT OR IGNORE INTO skills(name, description) VALUES (?, ?)", (name, request.form.get("description", "").strip())); db.commit(); db.close()
    return redirect(url_for("configuration"))

@app.post("/configuration/roles")
def create_role():
    name = request.form.get("name", "").strip()
    if name:
        db = connect(); cursor = db.execute("INSERT OR IGNORE INTO roles(name, description) VALUES (?, ?)", (name, request.form.get("description", "").strip())); role_id = cursor.lastrowid or row("SELECT id FROM roles WHERE name=?", (name,))["id"]
        levels = [(role_id, int(key.removeprefix("skill_")), max(0, min(100, int(value)))) for key, value in request.form.items() if key.startswith("skill_") and value.isdigit()]
        db.executemany("INSERT OR REPLACE INTO role_skills(role_id, skill_id, required_level) VALUES (?, ?, ?)", levels); db.commit(); db.close()
    return redirect(url_for("configuration"))

@app.post("/configuration/skills/<int:skill_id>/edit")
def edit_skill(skill_id):
    name = request.form.get("name", "").strip()
    if name:
        db = connect(); db.execute("UPDATE skills SET name=?, description=? WHERE id=?", (name, request.form.get("description", "").strip(), skill_id)); db.commit(); db.close()
    return redirect(url_for("configuration"))

@app.post("/configuration/skills/<int:skill_id>/delete")
def delete_skill(skill_id):
    db = connect()
    employee_usage = db.execute("SELECT COUNT(*) FROM employee_skills WHERE skill_id=?", (skill_id,)).fetchone()[0]
    role_usage = db.execute("SELECT COUNT(*) FROM role_skills WHERE skill_id=?", (skill_id,)).fetchone()[0]
    resource_usage = db.execute("SELECT COUNT(*) FROM learning_resources WHERE skill_id=?", (skill_id,)).fetchone()[0]
    if not employee_usage and not role_usage and not resource_usage:
        db.execute("DELETE FROM skills WHERE id=?", (skill_id,)); db.commit()
    db.close()
    return redirect(url_for("configuration"))

@app.post("/configuration/roles/<int:role_id>/delete")
def delete_role(role_id):
    db = connect(); db.execute("DELETE FROM roles WHERE id=?", (role_id,)); db.commit(); db.close(); return redirect(url_for("configuration"))

@app.post("/configuration/resources")
def create_resource():
    payload = request.form
    if payload.get("name") and payload.get("skill_id") and payload.get("url"):
        db = connect(); db.execute("INSERT INTO learning_resources(name, skill_id, provider, difficulty, type, duration, description, url) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (payload["name"].strip(), int(payload["skill_id"]), payload.get("provider", "").strip(), payload.get("difficulty", "Intermediate"), payload.get("type", "Article"), payload.get("duration", "Self-paced"), payload.get("description", "").strip(), payload["url"].strip())); db.commit(); db.close()
    return redirect(url_for("configuration"))

@app.post("/api/employees")
def api_create_employee():
    try: return jsonify({"id": save_employee(request.get_json(force=True))}), 201
    except (ValueError, TypeError) as error: return jsonify({"error": str(error)}), 400

@app.get("/api/employees")
def api_employees(): return jsonify(rows("SELECT * FROM employees ORDER BY name"))
@app.get("/api/employees/<int:employee_id>")
def api_employee(employee_id): return jsonify({"employee": row("SELECT * FROM employees WHERE id=?", (employee_id,)), "skills": employee_skills(employee_id)})
@app.get("/api/skills")
def api_skills(): return jsonify(rows("SELECT * FROM skills ORDER BY name"))
@app.get("/api/roles")
def api_roles(): return jsonify(rows("SELECT * FROM roles ORDER BY name"))
@app.get("/api/analysis/<int:employee_id>/<int:role_id>")
def api_analysis(employee_id, role_id): return jsonify(analyze(employee_id, role_id))
@app.get("/api/matching/<int:employee_id>")
def api_matching(employee_id): return jsonify(match_roles(employee_id))
@app.get("/api/recommendations/<int:employee_id>/<int:role_id>")
def api_recommendations(employee_id, role_id): return jsonify(recommendations(employee_id, role_id))
@app.get("/api/learning-path/<int:employee_id>/<int:role_id>")
def api_learning_path(employee_id, role_id): return jsonify(learning_path(employee_id, role_id))
@app.get("/api/resources")
@app.get("/api/resources")
def api_resources(): return jsonify(rows("SELECT lr.*, s.name AS skill FROM learning_resources lr JOIN skills s ON s.id=lr.skill_id ORDER BY lr.name"))
@app.post("/api/resources")
def api_create_resource():
    payload = request.get_json(force=True); db = connect(); cursor = db.execute("INSERT INTO learning_resources(name, skill_id, difficulty, type, duration, description, url) VALUES (?, ?, ?, ?, ?, ?, ?)", (payload["name"].strip(), payload["skill_id"], payload.get("difficulty", "Intermediate"), payload.get("type", "Course"), payload.get("duration", "Self-paced"), payload.get("description", ""), payload.get("url", "#"))); db.commit(); resource_id = cursor.lastrowid; db.close(); return jsonify({"id": resource_id}), 201
@app.get("/api/dashboard")
def api_dashboard(): return jsonify(dashboard_metrics())

@app.post("/api/skills")
def api_create_skill():
    payload = request.get_json(force=True); db = connect(); cursor = db.execute("INSERT INTO skills(name, description) VALUES (?, ?)", (payload["name"].strip(), payload.get("description", ""))); db.commit(); skill_id = cursor.lastrowid; db.close(); return jsonify({"id": skill_id}), 201

@app.put("/api/skills/<int:skill_id>")
def api_update_skill(skill_id):
    payload = request.get_json(force=True); db = connect(); db.execute("UPDATE skills SET name=?, description=? WHERE id=?", (payload["name"].strip(), payload.get("description", ""), skill_id)); db.commit(); db.close(); return jsonify({"id": skill_id})

@app.delete("/api/skills/<int:skill_id>")
def api_delete_skill(skill_id):
    db = connect()
    usage = sum(db.execute(query, (skill_id,)).fetchone()[0] for query in ("SELECT COUNT(*) FROM employee_skills WHERE skill_id=?", "SELECT COUNT(*) FROM role_skills WHERE skill_id=?", "SELECT COUNT(*) FROM learning_resources WHERE skill_id=?"))
    if usage:
        db.close()
        return jsonify({"error": "Skill is still referenced by employees, roles, or resources."}), 409
    db.execute("DELETE FROM skills WHERE id=?", (skill_id,)); db.commit(); db.close(); return jsonify({"deleted": skill_id})

@app.post("/api/roles")
def api_create_role():
    payload = request.get_json(force=True); db = connect(); cursor = db.execute("INSERT INTO roles(name, description) VALUES (?, ?)", (payload["name"].strip(), payload.get("description", ""))); role_id = cursor.lastrowid; db.executemany("INSERT INTO role_skills(role_id, skill_id, required_level) VALUES (?, ?, ?)", [(role_id, item["skill_id"], max(0, min(100, item["required_level"]))) for item in payload.get("skills", [])]); db.commit(); db.close(); return jsonify({"id": role_id}), 201

@app.put("/api/roles/<int:role_id>")
def api_update_role(role_id):
    payload = request.get_json(force=True); db = connect(); db.execute("UPDATE roles SET name=?, description=? WHERE id=?", (payload["name"].strip(), payload.get("description", ""), role_id)); db.execute("DELETE FROM role_skills WHERE role_id=?", (role_id,)); db.executemany("INSERT INTO role_skills(role_id, skill_id, required_level) VALUES (?, ?, ?)", [(role_id, item["skill_id"], max(0, min(100, item["required_level"]))) for item in payload.get("skills", [])]); db.commit(); db.close(); return jsonify({"id": role_id})

@app.delete("/api/roles/<int:role_id>")
def api_delete_role(role_id):
    db = connect(); db.execute("DELETE FROM roles WHERE id=?", (role_id,)); db.commit(); db.close(); return jsonify({"deleted": role_id})

if __name__ == "__main__": app.run(debug=True, host="127.0.0.1", port=5000)
