from collections import Counter, defaultdict

from database import row, rows
from services.analysis import analyze, learning_path


def assessed_employees():
    return rows("""
        SELECT DISTINCT e.id, e.name, e.department, e.current_role, e.experience,
               ep.target_role_id, r.name AS target_role
        FROM employees e
        JOIN assessment_requests ar ON ar.employee_id=e.id
        LEFT JOIN employee_profiles ep ON ep.employee_id=e.id
        LEFT JOIN roles r ON r.id=ep.target_role_id
        WHERE ar.status IN ('Completed', 'Reviewed')
          AND ar.id=(SELECT latest.id FROM assessment_requests latest WHERE latest.employee_id=e.id ORDER BY latest.id DESC LIMIT 1)
        ORDER BY e.name
    "")


def organization_analytics():
    employees = assessed_employees()
    evaluated = []
    skill_gaps = Counter()
    department_values = defaultdict(list)
    role_values = defaultdict(list)
    for employee in employees:
        if not employee["target_role_id"]:
            continue
        result = analyze(employee["id"], employee["target_role_id"])
        employee_result = dict(employee)
        employee_result.update({"readiness": result["readiness"], "readiness_label": result["readiness_label"], "top_gaps": result["gaps"][:3], "learning_count": len(learning_path(employee["id"], employee["target_role_id"]))})
        evaluated.append(employee_result)
        department_values[employee["department"]].append(result["readiness"])
        role_values[employee["target_role"]].append(result["readiness"])
        for gap in result["gaps"]:
            if gap["gap"] > 0:
                skill_gaps[gap["skill"]] += 1
    readiness_distribution = Counter(item["readiness_label"] for item in evaluated)
    avg_readiness = round(sum(item["readiness"] for item in evaluated) / len(evaluated), 1) if evaluated else 0
    departments = [{"department": name, "employees": len(values), "readiness": round(sum(values) / len(values), 1)} for name, values in sorted(department_values.items())]
    role_readiness = [{"role": name, "employees": len(values), "readiness": round(sum(values) / len(values), 1)} for name, values in sorted(role_values.items())]
    return {"employees": evaluated, "total_employees": len(employees), "completed_assessments": sum(1 for item in employees if item["target_role_id"]), "pending_assessments": row("SELECT COUNT(*) AS count FROM assessment_requests WHERE status='Pending'")["count"], "average_readiness": avg_readiness, "needing_development": sum(1 for item in evaluated if item["readiness"] < 60), "top_skill_gap": skill_gaps.most_common(1)[0][0] if skill_gaps else "None", "skill_gaps": [{"skill": name, "employees": count} for name, count in skill_gaps.most_common()], "readiness_distribution": dict(readiness_distribution), "departments": departments, "roles": role_readiness}
