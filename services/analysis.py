from collections import defaultdict
import re
from collections import Counter
import pandas as pd
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
except ImportError:
    TfidfVectorizer = None
    cosine_similarity = None
from database import connect, rows

GAP_THRESHOLDS = {"low": 20, "medium": 40}
READINESS_THRESHOLDS = {"highly_ready": 80, "moderately_ready": 60, "developing": 40}


def employee_skills(employee_id):
    return {item["name"]: item["proficiency"] for item in rows("SELECT s.name, es.proficiency FROM employee_skills es JOIN skills s ON s.id = es.skill_id WHERE es.employee_id = ?", (employee_id,))}


def role_skills(role_id):
    return rows("SELECT s.name, rs.required_level FROM role_skills rs JOIN skills s ON s.id = rs.skill_id WHERE rs.role_id = ? ORDER BY rs.required_level DESC", (role_id,))


def gap_status(gap):
    if gap <= 0: return "Ready"
    if gap <= GAP_THRESHOLDS["low"]: return "Low Gap"
    if gap <= GAP_THRESHOLDS["medium"]: return "Medium Gap"
    return "Critical Gap"


def readiness_label(readiness):
    if readiness >= READINESS_THRESHOLDS["highly_ready"]: return "Highly Ready"
    if readiness >= READINESS_THRESHOLDS["moderately_ready"]: return "Moderately Ready"
    if readiness >= READINESS_THRESHOLDS["developing"]: return "Developing"
    return "Needs Development"


def analyze(employee_id, role_id):
    current = employee_skills(employee_id)
    required = role_skills(role_id)
    gaps = []
    for item in required:
        current_level = current.get(item["name"], 0)
        gap = max(0, item["required_level"] - current_level)
        missing = item["name"] not in current
        status = gap_status(gap)
        gaps.append({"skill": item["name"], "current": current_level, "required": item["required_level"], "gap": gap, "status": status, "missing": missing, "category": "Missing Skill" if missing else "Strong Skill" if gap == 0 else status})
    frame = pd.DataFrame(gaps).sort_values(["gap", "required"], ascending=False) if gaps else pd.DataFrame()
    ordered = frame.to_dict("records") if not frame.empty else []
    eligible = [item for item in required if item["required_level"] > 0]
    ratios = [min(current.get(item["name"], 0) / item["required_level"], 1) for item in eligible]
    readiness = round((sum(ratios) / len(ratios)) * 100, 1) if ratios else 0.0
    strong = [item["skill"] for item in ordered if item["gap"] == 0]
    weak = [item["skill"] for item in ordered if item["gap"] > 0 and not item["missing"]]
    missing = [item["skill"] for item in ordered if item["missing"]]
    focus = [f"{item['skill']} is a {item['status'].lower()} because current proficiency is {item['current']} while the role requires {item['required']}." for item in ordered if item["gap"] > 0]
    explanation = f"{', '.join(strong[:3]) or 'No required skills'} are at or above the role requirement. " + (" ".join(focus[:3]) if focus else "All required skills meet the selected role requirements.")
    return {"gaps": ordered, "readiness": readiness, "readiness_label": readiness_label(readiness), "ready": len(strong), "weak": len(weak), "critical": sum(item["status"] == "Critical Gap" for item in ordered), "strong_skills": strong, "weak_skills": weak, "missing_skills": missing, "explanation": explanation}


def match_roles(employee_id):
    employee_rows = rows("SELECT name, profile, current_role, experience FROM employees WHERE id = ?", (employee_id,))
    if not employee_rows: return []
    employee = employee_rows[0]
    skills = employee_skills(employee_id)
    roles = rows("SELECT id, name, description FROM roles ORDER BY name")
    employee_text = f"{employee['name']} {employee['current_role']} {employee['experience']} years {employee['profile']} {' '.join(skills.keys())}"
    documents = [employee_text] + [role["name"] + " " + role["description"] + " " + " ".join(item["name"] for item in role_skills(role["id"])) for role in roles]
    if roles and TfidfVectorizer:
        similarities = cosine_similarity(TfidfVectorizer().fit_transform(documents))[0][1:]
    else:
        base = Counter(documents[0].lower().split())
        similarities = []
        for document in documents[1:]:
            candidate = Counter(document.lower().split())
            overlap = sum(min(base[token], candidate[token]) for token in base)
            denominator = (sum(base.values()) * sum(candidate.values())) ** 0.5 or 1
            similarities.append(overlap / denominator)
    results = []
    for index, role in enumerate(roles):
        details = analyze(employee_id, role["id"])
        matching_skills = [item["skill"] for item in details["gaps"] if item["gap"] == 0]
        weak_skills = [item["skill"] for item in details["gaps"] if item["gap"] > 0]
        similarity = round(float(similarities[index]) * 100, 1)
        results.append({"id": role["id"], "name": role["name"], "readiness": details["readiness"], "similarity": similarity, "critical": details["critical"], "gap_count": len(weak_skills), "matching_skills": matching_skills, "weak_skills": weak_skills, "missing_skills": details["missing_skills"], "explanation": f"Strong match from {', '.join(matching_skills[:3]) or 'limited overlapping skills'}. Match reduced by {', '.join(weak_skills[:3]) or 'no skill gaps'}.", "details": details})
    return sorted(results, key=lambda item: (item["similarity"], item["readiness"]), reverse=True)


def recommendations(employee_id, role_id):
    analysis = analyze(employee_id, role_id)
    recommendations = []
    for gap in analysis["gaps"]:
        if gap["gap"] <= 0: continue
        resources = rows("SELECT lr.*, s.name AS skill FROM learning_resources lr JOIN skills s ON s.id = lr.skill_id WHERE s.name = ? ORDER BY CASE difficulty WHEN 'Beginner' THEN 1 WHEN 'Intermediate' THEN 2 ELSE 3 END", (gap["skill"],))
        priority = "High" if gap["gap"] > 40 else "Medium" if gap["gap"] > 20 else "Low"
        for resource in resources[:2]:
            resource.update({"priority": priority, "current": gap["current"], "required": gap["required"], "gap": gap["gap"], "reason": f"Recommended because {gap['skill']} is a {priority.lower()} priority gap for the selected role; current proficiency is {gap['current']}% versus {gap['required']}% required."})
            recommendations.append(resource)
    return recommendations


def learning_path(employee_id, role_id):
    analysis = analyze(employee_id, role_id)
    ordered = [item for item in analysis["gaps"] if item["gap"] > 0]
    path = []
    for index, item in enumerate(ordered, 1):
        resource = rows("SELECT lr.id, lr.name, lr.duration, lr.type, lr.provider, lr.url, lr.difficulty, lr.description FROM learning_resources lr JOIN skills s ON s.id = lr.skill_id WHERE s.name = ? ORDER BY CASE difficulty WHEN 'Beginner' THEN 1 WHEN 'Intermediate' THEN 2 ELSE 3 END, lr.id LIMIT 1", (item["skill"],))
        priority = "High" if item["gap"] > GAP_THRESHOLDS["medium"] else "Medium" if item["gap"] > GAP_THRESHOLDS["low"] else "Low"
        path.append({"step": index, "skill": item["skill"], "current": item["current"], "required": item["required"], "gap": item["gap"], "priority": priority, "status": item["status"], "reason": f"Recommended because {item['skill']} is required for the selected role and the employee is {item['gap']} points below the target level.", "resource": resource[0] if resource else None})
    return path


def dashboard_metrics():
    employees = rows("SELECT id, department FROM employees")
    role = rows("SELECT id FROM roles ORDER BY id LIMIT 1")
    readiness = [analyze(employee["id"], role[0]["id"])["readiness"] for employee in employees] if role else []
    skill_counts = defaultdict(int)
    department_scores = defaultdict(list)
    critical = 0
    training = 0
    for employee in employees:
        result = analyze(employee["id"], role[0]["id"]) if role else {"gaps": [], "readiness": 0}
        department_scores[employee["department"]].append(result["readiness"])
        if result["readiness"] < 70: training += 1
        for gap in result["gaps"]:
            if gap["status"] == "Critical Gap":
                critical += 1
                skill_counts[gap["skill"]] += 1
    return {"total_employees": len(employees), "average_readiness": round(sum(readiness) / len(readiness)) if readiness else 0, "critical_gaps": critical, "needing_training": training, "common_gaps": sorted([{"skill": key, "count": value} for key, value in skill_counts.items()], key=lambda item: item["count"], reverse=True)[:6], "departments": [{"department": key, "readiness": round(sum(value) / len(value))} for key, value in department_scores.items()]}


def extract_skills(text):
    found = []
    normalized = text.lower()
    for skill in rows("SELECT id, name FROM skills ORDER BY length(name) DESC"):
        if re.search(r"(?<![a-z])" + re.escape(skill["name"].lower()) + r"(?![a-z])", normalized):
            found.append(skill["name"])
    return found
