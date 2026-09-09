# SkillPath AI

SkillPath AI is a Flask + SQLite hackathon application for employee skill-gap analysis and explainable learning-path recommendations. It uses synthetic data only.

## Architecture

- `app.py`: Flask pages and REST API endpoints.
- `database.py`: SQLite schema, seed data, and database helpers.
- `services/analysis.py`: Pandas gap ranking, rule-based readiness, TF-IDF/cosine role matching, recommendations, learning paths, and dashboard aggregation.
- `templates/`: Responsive Bootstrap/Jinja pages.
- `static/`: Custom visual system and Chart.js dashboard scripts.
- `requirements.txt`: Python dependencies.

## Run locally

```powershell
python -m pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000. The demo login accepts any credentials and redirects to the HR dashboard.

The first run creates `database/skillpath.db` with 20 synthetic employees, 10 configurable skills, 5 roles, and 22 learning resources. Readiness is calculated from capped achieved proficiency divided by total role requirements. Profile text extraction is intentionally transparent: matching known skill names adds a 45% baseline.

## Demo flow

Dashboard -> Employees -> employee profile -> Skill gap analysis -> Role matching -> Personalized learning path -> Resources / Analytics.

## API

`GET /api/employees`, `GET /api/skills`, `GET /api/roles`, `GET /api/analysis/<employee>/<role>`, `GET /api/matching/<employee>`, `GET /api/recommendations/<employee>/<role>`, `GET /api/learning-path/<employee>/<role>`, `GET /api/resources`, and `GET /api/dashboard`. Skills and roles also expose POST, PUT, and DELETE endpoints for taxonomy administration.
