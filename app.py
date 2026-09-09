from pathlib import Path
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from database import connect, init_db, row, rows
from services.analysis import analyze, dashboard_metrics, employee_skills, extract_skills, learning_path, match_roles, recommendations

app = Flask(__name__)
app.config["SECRET_KEY"] = "skillpath-demo-secret"
DEMO_USERNAME = "admin"
DEMO_PASSWORD = "admin123"
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
        employee_id = db.execute("INSERT INTO employees(name,email,department,experience,profile) VALUES (?,?,?,?,?)", values).lastrowid
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


@app.route("/")
def index(): return redirect(url_for("dashboard")) if session.get("authenticated") else redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("authenticated"):
        return redirect(url_for("dashboard"))
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if username == DEMO_USERNAME and password == DEMO_PASSWORD:
            session.clear()
            session["authenticated"] = True
            session["username"] = username
            return redirect(url_for("dashboard"))
        error = "Invalid username or password. Use the demo credentials shown below."
    return render_template("login.html", error=error)

@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
def dashboard():
    if not session.get("authenticated"):
        return redirect(url_for("login", next=request.path))
    return render_template("dashboard.html", metrics=dashboard_metrics(), people=rows("SELECT * FROM employees ORDER BY name LIMIT 5"))

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
    employees = rows("SELECT * FROM employees ORDER BY name")
    roles = rows("SELECT * FROM roles ORDER BY name")
    employee_id = int(request.args.get("employee_id", employee_id or (employees[0]["id"] if employees else 0)))
    role_id = int(request.args.get("role_id", roles[0]["id"])) if roles else None
    selected_employee = row("SELECT * FROM employees WHERE id=?", (employee_id,)) if employee_id else None
    selected_role = row("SELECT * FROM roles WHERE id=?", (role_id,)) if role_id else None
    return render_template("learning_path.html", employees=employees, employee=selected_employee, roles=roles, selected_role=selected_role, path=learning_path(employee_id, role_id) if selected_employee and role_id else [], recommendations=recommendations(employee_id, role_id) if selected_employee and role_id else [])

@app.route("/resources")
def resources_page(): return render_template("resources.html", resources=rows("SELECT lr.*, s.name AS skill FROM learning_resources lr JOIN skills s ON s.id=lr.skill_id ORDER BY s.name, lr.name"), skills=rows("SELECT * FROM skills ORDER BY name"))

@app.route("/analytics")
def analytics(): return render_template("analytics.html", metrics=dashboard_metrics())

@app.route("/configuration")
def configuration(): return render_template("configuration.html", skills=rows("SELECT * FROM skills ORDER BY name"), roles=rows("SELECT * FROM roles ORDER BY name"), role_skills={role["id"]: rows("SELECT s.name, rs.required_level FROM role_skills rs JOIN skills s ON s.id=rs.skill_id WHERE rs.role_id=?", (role["id"],)) for role in rows("SELECT id FROM roles")})

def notifications_data():
    first_employee = row("SELECT id, name FROM employees ORDER BY id LIMIT 1")
    low_skill_count = row("SELECT COUNT(*) AS count FROM employee_skills WHERE proficiency < 35")
    latest_resource = row("SELECT name FROM learning_resources ORDER BY id DESC LIMIT 1")
    return [
        {"icon": "exclamation-triangle", "title": "Training focus identified", "message": f"{low_skill_count['count']} skill baselines are below 35%.", "time": "Current analysis"},
        {"icon": "signpost-split", "title": "Learning path ready", "message": f"A path is available for {first_employee['name']}." if first_employee else "Add an employee to generate a path.", "time": "Based on current data"},
        {"icon": "collection-play", "title": "Resource library updated", "message": f"Latest resource: {latest_resource['name']}." if latest_resource else "No resources available.", "time": "Resource catalog"},
    ]

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
