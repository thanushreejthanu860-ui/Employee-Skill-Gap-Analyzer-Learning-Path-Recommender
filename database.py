import json
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "database" / "skillpath.db"

SKILLS = [
    ("Python", "Programming and automation"), ("SQL", "Data querying and modeling"),
    ("Statistics", "Statistical reasoning"), ("Machine Learning", "Predictive modeling"),
    ("Pandas", "Data manipulation"), ("Data Visualization", "Insight communication"),
    ("Excel", "Spreadsheet analysis"), ("Communication", "Written and verbal communication"),
    ("Power BI", "Business intelligence dashboards"), ("Problem Solving", "Structured problem solving"),
]
ROLES = {
    "Data Analyst": {"Python": 65, "SQL": 80, "Statistics": 60, "Pandas": 70, "Data Visualization": 80, "Excel": 75, "Communication": 70, "Problem Solving": 75},
    "Data Scientist": {"Python": 85, "SQL": 70, "Statistics": 85, "Machine Learning": 85, "Pandas": 85, "Data Visualization": 65, "Problem Solving": 85},
    "Business Analyst": {"SQL": 65, "Statistics": 55, "Excel": 85, "Power BI": 75, "Communication": 90, "Problem Solving": 85, "Data Visualization": 65},
    "ML Engineer": {"Python": 90, "Machine Learning": 90, "SQL": 60, "Statistics": 75, "Pandas": 75, "Problem Solving": 90},
    "Python Developer": {"Python": 90, "SQL": 65, "Problem Solving": 85, "Communication": 60, "Statistics": 45},
}
RESOURCES = [
    ("Python Foundations", "Python", "Beginner", "Course", "6 hours", "Core syntax, functions, and clean coding habits."),
    ("Python for Data Science", "Python", "Intermediate", "Course", "8 hours", "Practical Python workflows for analytics teams."),
    ("SQL Query Lab", "SQL", "Intermediate", "Workshop", "5 hours", "Joins, window functions, and query optimization."),
    ("Statistics Fundamentals", "Statistics", "Beginner", "Course", "7 hours", "Distributions, hypothesis tests, and confidence intervals."),
    ("Applied Statistics with Python", "Statistics", "Advanced", "Project", "10 hours", "Turn statistical concepts into reproducible notebooks."),
    ("Machine Learning Fundamentals", "Machine Learning", "Intermediate", "Course", "12 hours", "Supervised learning, evaluation, and feature engineering."),
    ("ML Model Evaluation Lab", "Machine Learning", "Advanced", "Lab", "8 hours", "Validation strategies and model diagnostics."),
    ("Pandas and NumPy", "Pandas", "Intermediate", "Course", "6 hours", "Reliable tabular transformations and numerical computing."),
    ("Data Cleaning Project", "Pandas", "Intermediate", "Project", "9 hours", "Clean and document a messy business dataset."),
    ("Dashboard Storytelling", "Data Visualization", "Intermediate", "Workshop", "4 hours", "Choose visuals and explain insights with clarity."),
    ("Visual Analytics with Python", "Data Visualization", "Advanced", "Course", "8 hours", "Build decision-ready charts with real datasets."),
    ("Excel for Analysts", "Excel", "Beginner", "Course", "5 hours", "Formulas, pivots, and data validation."),
    ("Advanced Excel Modeling", "Excel", "Advanced", "Workshop", "7 hours", "Scenario models and defensible assumptions."),
    ("Power BI Essentials", "Power BI", "Beginner", "Course", "6 hours", "Semantic models and interactive reports."),
    ("Power BI Executive Dashboards", "Power BI", "Advanced", "Project", "10 hours", "Deliver a polished KPI dashboard."),
    ("Communicating with Data", "Communication", "Beginner", "Workshop", "3 hours", "Present findings for non-technical audiences."),
    ("Executive Storytelling", "Communication", "Advanced", "Workshop", "5 hours", "Structure concise recommendations and narratives."),
    ("Structured Problem Solving", "Problem Solving", "Beginner", "Course", "4 hours", "Frame ambiguous problems and test hypotheses."),
    ("Case Interview Practice", "Problem Solving", "Intermediate", "Lab", "6 hours", "Solve realistic prioritization and root-cause cases."),
    ("Analytics Capstone", "SQL", "Advanced", "Project", "14 hours", "Complete an end-to-end analytics project."),
    ("Predictive Modeling Project", "Machine Learning", "Advanced", "Project", "16 hours", "Ship a documented predictive model."),
    ("Data Team Collaboration", "Communication", "Intermediate", "Workshop", "4 hours", "Feedback, handoffs, and stakeholder alignment."),
]


def connect():
    DB_PATH.parent.mkdir(exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db():
    db = connect()
    db.executescript("""
    CREATE TABLE IF NOT EXISTS employees (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE, department TEXT NOT NULL, experience INTEGER NOT NULL DEFAULT 1, profile TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS skills (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, description TEXT DEFAULT '');
    CREATE TABLE IF NOT EXISTS employee_skills (employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE, skill_id INTEGER NOT NULL REFERENCES skills(id) ON DELETE CASCADE, proficiency INTEGER NOT NULL CHECK(proficiency BETWEEN 0 AND 100), PRIMARY KEY(employee_id, skill_id));
    CREATE TABLE IF NOT EXISTS roles (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, description TEXT DEFAULT '');
    CREATE TABLE IF NOT EXISTS role_skills (role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE, skill_id INTEGER NOT NULL REFERENCES skills(id) ON DELETE CASCADE, required_level INTEGER NOT NULL CHECK(required_level BETWEEN 0 AND 100), PRIMARY KEY(role_id, skill_id));
    CREATE TABLE IF NOT EXISTS learning_resources (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, skill_id INTEGER NOT NULL REFERENCES skills(id) ON DELETE CASCADE, difficulty TEXT NOT NULL, type TEXT NOT NULL, duration TEXT NOT NULL, description TEXT DEFAULT '', url TEXT DEFAULT '#');
    """)
    if db.execute("SELECT COUNT(*) FROM skills").fetchone()[0] == 0:
        db.executemany("INSERT INTO skills(name, description) VALUES (?, ?)", SKILLS)
        for role_name, description in [(name, f"Synthetic requirements for the {name} pathway.") for name in ROLES]:
            db.execute("INSERT INTO roles(name, description) VALUES (?, ?)", (role_name, description))
        skill_ids = {row["name"]: row["id"] for row in db.execute("SELECT id, name FROM skills")}
        role_ids = {row["name"]: row["id"] for row in db.execute("SELECT id, name FROM roles")}
        for role_name, required in ROLES.items():
            db.executemany("INSERT INTO role_skills(role_id, skill_id, required_level) VALUES (?, ?, ?)", [(role_ids[role_name], skill_ids[name], level) for name, level in required.items()])
        db.executemany("INSERT INTO learning_resources(name, skill_id, difficulty, type, duration, description) VALUES (?, ?, ?, ?, ?, ?)", [(name, skill_ids[skill], difficulty, kind, duration, description) for name, skill, difficulty, kind, duration, description in RESOURCES])
        departments = ["Data & Insights", "Engineering", "Operations", "Finance"]
        first_names = ["Aarav", "Maya", "Ishaan", "Nisha", "Rohan", "Anika", "Vikram", "Leah", "Arjun", "Zoya", "Kabir", "Meera", "Dev", "Sara", "Neel", "Tara", "Kian", "Aditi", "Omar", "Riya"]
        skill_names = list(skill_ids)
        for index, first_name in enumerate(first_names):
            department = departments[index % len(departments)]
            profile = f"{first_name} works on analytics projects using {skill_names[index % 4]}, {skill_names[(index + 1) % 10]}, and {skill_names[(index + 5) % 10]}. Interested in data-driven problem solving and stakeholder communication."
            cursor = db.execute("INSERT INTO employees(name, email, department, experience, profile) VALUES (?, ?, ?, ?, ?)", (f"{first_name} Sharma", f"{first_name.lower()}{index + 1}@skillpath.demo", department, (index % 8) + 1, profile))
            employee_id = cursor.lastrowid
            levels = [(employee_id, skill_ids[skill], min(95, 38 + ((index * 13 + offset * 9) % 55))) for offset, skill in enumerate(skill_names) if (offset + index) % 3 != 0]
            db.executemany("INSERT INTO employee_skills(employee_id, skill_id, proficiency) VALUES (?, ?, ?)", levels)
    db.commit()
    db.close()


def rows(query, params=()):
    db = connect()
    result = [dict(row) for row in db.execute(query, params).fetchall()]
    db.close()
    return result


def row(query, params=()):
    db = connect()
    result = db.execute(query, params).fetchone()
    db.close()
    return dict(result) if result else None
