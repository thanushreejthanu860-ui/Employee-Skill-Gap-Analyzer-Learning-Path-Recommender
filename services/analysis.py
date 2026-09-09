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


def employee_skills(employee_id):
    return {item["name"]: item["proficiency"] for item in rows("SELECT s.name, es.proficiency FROM employee_skills es JOIN skills s ON s.id = es.skill_id WHERE es.employee_id = ?", (employee_id,))}


def role_skills(role_id):
    return rows("SELECT s.name, rs.required_level FROM role_skills rs JOIN skills s ON s.id = rs.skill_id WHERE rs.role_id = ? ORDER BY rs.required_level DESC", (role_id,))


def gap_status(gap):
    if gap <= 0: return "Ready"
    if gap <= 20: return "Low Gap"
    if gap <= 40: return "Medium Gap"
    return "Critical Gap"


def analyze(employee_id, role_id):
    current = employee_skills(employee_id)
    required = role_skills(role_id)
    gaps = []
    for item in required:
        current_level = current.get(item["name"], 0)
        gap = max(0, item["required_level"] - current_level)
        gaps.append({"skill": item["name"], "current": current_level, "required": item["required_level"], "gap": gap, "status": gap_status(gap)})
    frame = pd.DataFrame(gaps).sort_values(["gap", "required"], ascending=False) if gaps else pd.DataFrame()
    ordered = frame.to_dict("records") if not frame.empty else []
    required_total = sum(item["required_level"] for item in required) or 1
    achieved = sum(min(current.get(item["name"], 0), item["required_level"]) for item in required)
    readiness = round((achieved / required_total) * 100)
    return {"gaps": ordered, "readiness": readiness, "ready": sum(item["status"] == "Ready" for item in ordered), "weak": sum(item["status"] in ("Low Gap", "Medium Gap") for item in ordered), "critical": sum(item["status"] == "Critical Gap" for item in ordered), "explanation": f"Readiness is the achieved proficiency capped at each role requirement ({achieved}/{required_total}). Missing skills count as 0; gaps are ranked largest first."}


def match_roles(employee_id):
    employee = rows("SELECT name, profile FROM employees WHERE id = ?", (employee_id,))[0]
    skills = employee_skills(employee_id)
    roles = rows("SELECT id, name, description FROM roles ORDER BY name")
    documents = [employee["profile"] + " " + " ".join(skills.keys())] + [role["name"] + " " + role["description"] + " " + " ".join(item["name"] for item in role_skills(role["id"])) for role in roles]
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
        results.append({"id": role["id"], "name": role["name"], "readiness": details["readiness"], "similarity": round(float(similarities[index]) * 100), "critical": details["critical"], "gap_count": len(weak_skills), "matching_skills": matching_skills, "weak_skills": weak_skills, "explanation": f"{employee['name']} matches {len(matching_skills)} required skills and needs development in {len(weak_skills)} skills for {role['name']}."})
    return sorted(results, key=lambda item: (item["readiness"], item["similarity"]), reverse=True)


def recommendations(employee_id, role_id):
    analysis = analyze(employee_id, role_id)
    recommendations = []
    for gap in analysis["gaps"]:
        if gap["gap"] <= 0: continue
        resources = rows("SELECT lr.*, s.name AS skill FROM learning_resources lr JOIN skills s ON s.id = lr.skill_id WHERE s.name = ? ORDER BY CASE difficulty WHEN 'Beginner' THEN 1 WHEN 'Intermediate' THEN 2 ELSE 3 END", (gap["skill"],))
        priority = "High" if gap["gap"] > 40 else "Medium" if gap["gap"] > 20 else "Low"
        for resource in resources[:2]:
            resource.update({"priority": priority, "current": gap["current"], "required": gap["required"], "gap": gap["gap"], "reason": f"{gap['skill']} is the {'largest' if gap is analysis['gaps'][0] else 'next'} skill gap for the selected role."})
            recommendations.append(resource)
    return recommendations


def learning_path(employee_id, role_id):
    analysis = analyze(employee_id, role_id)
    ordered = [item for item in analysis["gaps"] if item["gap"] > 0]
    path = []
    for index, item in enumerate(ordered, 1):
        resource = rows("SELECT lr.name, lr.duration, lr.type FROM learning_resources lr JOIN skills s ON s.id = lr.skill_id WHERE s.name = ? ORDER BY CASE difficulty WHEN 'Beginner' THEN 1 WHEN 'Intermediate' THEN 2 ELSE 3 END LIMIT 1", (item["skill"],))
        path.append({"step": index, "skill": item["skill"], "current": item["current"], "required": item["required"], "gap": item["gap"], "priority": "High" if item["gap"] > 40 else "Medium" if item["gap"] > 20 else "Low", "status": item["status"], "reason": f"{item['skill']} is a {item['status'].lower()} for this role, so it is prioritized from the employee's measured gap.", "resource": resource[0] if resource else {"name": f"Build {item['skill']} capability", "duration": "Self-paced", "type": "Practice"}})
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
