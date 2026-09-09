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
    ("Python Foundations", "Python", "OpenLearn", "Beginner", "Course", "6 hours", "Core syntax, functions, and clean coding habits.", "https://www.open.edu/openlearn/science-maths-technology/computing-ict/introduction-programming-python/content-section-overview"),
    ("Python for Data Science", "Python", "freeCodeCamp", "Intermediate", "Video", "8 hours", "Practical Python workflows for analytics teams.", "https://www.youtube.com/watch?v=LHBE6Q9XlzI"),
    ("SQL Query Lab", "SQL", "freeCodeCamp", "Intermediate", "Video", "4 hours", "Joins, window functions, and query optimization.", "https://www.youtube.com/watch?v=HXV3zeQKqGY"),
    ("Statistics Fundamentals", "Statistics", "Khan Academy", "Beginner", "Course", "7 hours", "Distributions, hypothesis tests, and confidence intervals.", "https://www.khanacademy.org/math/statistics-probability"),
    ("Applied Statistics with Python", "Statistics", "SciPy", "Advanced", "Article", "3 hours", "Turn statistical concepts into reproducible notebooks.", "https://docs.scipy.org/doc/scipy/tutorial/stats.html"),
    ("Machine Learning Fundamentals", "Machine Learning", "Google", "Intermediate", "Course", "15 hours", "Supervised learning, evaluation, and feature engineering.", "https://developers.google.com/machine-learning/crash-course"),
    ("ML Model Evaluation Lab", "Machine Learning", "scikit-learn", "Advanced", "Article", "2 hours", "Validation strategies and model diagnostics.", "https://scikit-learn.org/stable/modules/model_evaluation.html"),
    ("Pandas and NumPy", "Pandas", "Data School", "Intermediate", "Video", "6 hours", "Reliable tabular transformations and numerical computing.", "https://www.youtube.com/watch?v=vmEHCJofslg"),
    ("Data Cleaning Project", "Pandas", "Kaggle", "Intermediate", "Course", "9 hours", "Clean and document a messy business dataset.", "https://www.kaggle.com/learn/pandas"),
    ("Dashboard Storytelling", "Data Visualization", "Tableau", "Intermediate", "Article", "2 hours", "Choose visuals and explain insights with clarity.", "https://www.tableau.com/learn/articles/data-storytelling"),
    ("Visual Analytics with Python", "Data Visualization", "Matplotlib", "Advanced", "Article", "4 hours", "Build decision-ready charts with real datasets.", "https://matplotlib.org/stable/tutorials/pyplot.html"),
    ("Excel for Analysts", "Excel", "Microsoft", "Beginner", "Course", "5 hours", "Formulas, pivots, and data validation.", "https://support.microsoft.com/en-us/excel"),
    ("Advanced Excel Modeling", "Excel", "Microsoft", "Advanced", "Article", "7 hours", "Scenario models and defensible assumptions.", "https://support.microsoft.com/en-us/office/overview-of-formulas-in-excel-ecfdc708-9162-49e8-b993-c311f47ca173"),
    ("Power BI Essentials", "Power BI", "Microsoft Learn", "Beginner", "Course", "6 hours", "Semantic models and interactive reports.", "https://learn.microsoft.com/en-us/training/powerplatform/power-bi"),
    ("Power BI Executive Dashboards", "Power BI", "Microsoft Learn", "Advanced", "Course", "10 hours", "Deliver a polished KPI dashboard.", "https://learn.microsoft.com/en-us/power-bi/guidance/power-bi-adoption-roadmap-overview"),
    ("Communicating with Data", "Communication", "Google", "Beginner", "Article", "3 hours", "Present findings for non-technical audiences.", "https://developers.google.com/machine-learning/guides/text-classification"),
    ("Executive Storytelling", "Communication", "Harvard Business Review", "Advanced", "Article", "2 hours", "Structure concise recommendations and narratives.", "https://hbr.org/topic/communication"),
    ("Structured Problem Solving", "Problem Solving", "McKinsey", "Beginner", "Article", "4 hours", "Frame ambiguous problems and test hypotheses.", "https://www.mckinsey.com/capabilities/people-and-organizational-performance/our-insights"),
    ("Case Interview Practice", "Problem Solving", "Khan Academy", "Intermediate", "Course", "6 hours", "Solve realistic prioritization and root-cause cases.", "https://www.khanacademy.org/economics-finance-domain"),
    ("Analytics Capstone", "SQL", "Mode", "Advanced", "Course", "14 hours", "Complete an end-to-end analytics project.", "https://mode.com/sql-tutorial/"),
    ("Predictive Modeling Project", "Machine Learning", "Kaggle", "Advanced", "Project", "16 hours", "Ship a documented predictive model.", "https://www.kaggle.com/learn/intro-to-machine-learning"),
    ("Data Team Collaboration", "Communication", "Atlassian", "Intermediate", "Article", "4 hours", "Feedback, handoffs, and stakeholder alignment.", "https://www.atlassian.com/team-playbook"),
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
    CREATE TABLE IF NOT EXISTS employees (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE, department TEXT NOT NULL, experience INTEGER NOT NULL DEFAULT 1, profile TEXT DEFAULT '', current_role TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS skills (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, description TEXT DEFAULT '');
    CREATE TABLE IF NOT EXISTS employee_skills (employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE, skill_id INTEGER NOT NULL REFERENCES skills(id) ON DELETE CASCADE, proficiency INTEGER NOT NULL CHECK(proficiency BETWEEN 0 AND 100), PRIMARY KEY(employee_id, skill_id));
    CREATE TABLE IF NOT EXISTS roles (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, description TEXT DEFAULT '');
    CREATE TABLE IF NOT EXISTS role_skills (role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE, skill_id INTEGER NOT NULL REFERENCES skills(id) ON DELETE CASCADE, required_level INTEGER NOT NULL CHECK(required_level BETWEEN 0 AND 100), PRIMARY KEY(role_id, skill_id));
    CREATE TABLE IF NOT EXISTS learning_resources (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, skill_id INTEGER NOT NULL REFERENCES skills(id) ON DELETE CASCADE, provider TEXT DEFAULT '', difficulty TEXT NOT NULL, type TEXT NOT NULL, duration TEXT NOT NULL, description TEXT DEFAULT '', url TEXT DEFAULT '#');
    """)
    employee_columns = {item[1] for item in db.execute("PRAGMA table_info(employees)").fetchall()}
    resource_columns = {item[1] for item in db.execute("PRAGMA table_info(learning_resources)").fetchall()}
    if "current_role" not in employee_columns:
        db.execute("ALTER TABLE employees ADD COLUMN current_role TEXT DEFAULT ''")
    if "provider" not in resource_columns:
        db.execute("ALTER TABLE learning_resources ADD COLUMN provider TEXT DEFAULT ''")
    if db.execute("SELECT COUNT(*) FROM skills").fetchone()[0] == 0:
        db.executemany("INSERT INTO skills(name, description) VALUES (?, ?)", SKILLS)
        for role_name, description in [(name, f"Synthetic requirements for the {name} pathway.") for name in ROLES]:
            db.execute("INSERT INTO roles(name, description) VALUES (?, ?)", (role_name, description))
        skill_ids = {row["name"]: row["id"] for row in db.execute("SELECT id, name FROM skills")}
        role_ids = {row["name"]: row["id"] for row in db.execute("SELECT id, name FROM roles")}
        for role_name, required in ROLES.items():
            db.executemany("INSERT INTO role_skills(role_id, skill_id, required_level) VALUES (?, ?, ?)", [(role_ids[role_name], skill_ids[name], level) for name, level in required.items()])
        db.executemany("INSERT INTO learning_resources(name, skill_id, provider, difficulty, type, duration, description, url) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [(name, skill_ids[skill], provider, difficulty, kind, duration, description, url) for name, skill, provider, difficulty, kind, duration, description, url in RESOURCES])
        departments = ["Data & Insights", "Engineering", "Operations", "Finance"]
        first_names = ["Aarav", "Maya", "Ishaan", "Nisha", "Rohan", "Anika", "Vikram", "Leah", "Arjun", "Zoya", "Kabir", "Meera", "Dev", "Sara", "Neel", "Tara", "Kian", "Aditi", "Omar", "Riya"]
        skill_names = list(skill_ids)
        for index, first_name in enumerate(first_names):
            department = departments[index % len(departments)]
            profile = f"{first_name} works on analytics projects using {skill_names[index % 4]}, {skill_names[(index + 1) % 10]}, and {skill_names[(index + 5) % 10]}. Interested in data-driven problem solving and stakeholder communication."
            current_role = ["Data Analyst", "Python Developer", "Business Analyst", "Data Scientist"][index % 4]
            cursor = db.execute("INSERT INTO employees(name, email, department, experience, profile, current_role) VALUES (?, ?, ?, ?, ?, ?)", (f"{first_name} Sharma", f"{first_name.lower()}{index + 1}@skillpath.demo", department, (index % 8) + 1, profile, current_role))
            employee_id = cursor.lastrowid
            levels = [(employee_id, skill_ids[skill], min(95, 38 + ((index * 13 + offset * 9) % 55))) for offset, skill in enumerate(skill_names) if (offset + index) % 3 != 0]
            db.executemany("INSERT INTO employee_skills(employee_id, skill_id, proficiency) VALUES (?, ?, ?)", levels)
    db.execute("UPDATE learning_resources SET provider = CASE (SELECT name FROM skills WHERE id=learning_resources.skill_id) WHEN 'Python' THEN 'Python.org' WHEN 'SQL' THEN 'freeCodeCamp' WHEN 'Pandas' THEN 'Pandas' WHEN 'Statistics' THEN 'Khan Academy' WHEN 'Machine Learning' THEN 'Google' WHEN 'Power BI' THEN 'Microsoft Learn' WHEN 'Excel' THEN 'Microsoft' WHEN 'Data Visualization' THEN 'Matplotlib' WHEN 'Communication' THEN 'Atlassian' WHEN 'Problem Solving' THEN 'McKinsey' ELSE 'Open Learning' END WHERE provider IS NULL OR provider = ''")
    db.execute("UPDATE learning_resources SET url = CASE (SELECT name FROM skills WHERE id=learning_resources.skill_id) WHEN 'Python' THEN 'https://www.python.org/about/gettingstarted/' WHEN 'SQL' THEN 'https://www.w3schools.com/sql/' WHEN 'Pandas' THEN 'https://pandas.pydata.org/docs/getting_started/intro_tutorials/' WHEN 'Statistics' THEN 'https://www.khanacademy.org/math/statistics-probability' WHEN 'Machine Learning' THEN 'https://developers.google.com/machine-learning/crash-course' WHEN 'Power BI' THEN 'https://learn.microsoft.com/en-us/training/powerplatform/power-bi' WHEN 'Excel' THEN 'https://support.microsoft.com/en-us/excel' WHEN 'Data Visualization' THEN 'https://matplotlib.org/stable/tutorials/pyplot.html' WHEN 'Communication' THEN 'https://www.atlassian.com/team-playbook' WHEN 'Problem Solving' THEN 'https://www.mckinsey.com/capabilities/people-and-organizational-performance/our-insights' ELSE 'https://www.khanacademy.org/' END WHERE url IS NULL OR url = '#'")
    db.execute("UPDATE learning_resources SET type = CASE WHEN type IN ('Workshop', 'Lab') THEN 'Video' WHEN type = 'Project' THEN 'Course' ELSE type END WHERE type NOT IN ('Video', 'Course', 'Article')")
    db.execute("UPDATE employees SET current_role = CASE (id % 4) WHEN 1 THEN 'Data Analyst' WHEN 2 THEN 'Python Developer' WHEN 3 THEN 'Business Analyst' ELSE 'Data Scientist' END WHERE current_role IS NULL OR current_role = ''")
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
