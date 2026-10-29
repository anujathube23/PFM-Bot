"""Flask app: SQLite setup, JSON API, and the dashboard page."""
import os
from collections import defaultdict
from datetime import date

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from ai_engine import AIEngineError, analyze_finances
from database import PERSONAS, Budget, Expense, Income, SavingsGoal, User, db

load_dotenv()
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///finance.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)
with app.app_context():
    db.create_all()


# ---------- helpers ----------
def month_range(month):
    """'2026-09' -> (first day, first day of next month). Defaults to this month."""
    y, m = map(int, (month or date.today().strftime("%Y-%m")).split("-"))
    return date(y, m, 1), (date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1))


def parse_date(value):
    return date.fromisoformat(value) if value else date.today()


def build_snapshot(user, month=None):
    """Aggregate a user's month into the compact structure sent to the AI and dashboard."""
    start, end = month_range(month)
    incomes = [i for i in user.incomes if start <= i.date < end]
    expenses = [e for e in user.expenses if start <= e.date < end]
    total_income = round(sum(i.amount for i in incomes), 2)
    total_expenses = round(sum(e.amount for e in expenses), 2)

    by_cat, by_source = defaultdict(float), defaultdict(float)
    essential = 0.0
    for e in expenses:
        by_cat[e.category] += e.amount
        essential += e.amount if e.is_essential else 0
    for i in incomes:
        by_source[i.source] += i.amount

    overruns = []
    for b in user.budgets:
        spent = by_cat.get(b.category, 0)
        if spent > b.monthly_limit:
            overruns.append({"category": b.category, "limit": b.monthly_limit,
                             "spent": round(spent, 2), "over_by": round(spent - b.monthly_limit, 2)})

    return {
        "user": user.name, "persona": user.persona, "currency": user.currency,
        "month": start.strftime("%Y-%m"),
        "total_income": total_income, "total_expenses": total_expenses,
        "surplus": round(total_income - total_expenses, 2),
        "savings_rate_pct": round((total_income - total_expenses) / total_income * 100, 1) if total_income else None,
        "essential_expenses": round(essential, 2),
        "discretionary_expenses": round(total_expenses - essential, 2),
        "category_breakdown": {k: round(v, 2) for k, v in sorted(by_cat.items(), key=lambda x: -x[1])},
        "income_by_source": {k: round(v, 2) for k, v in by_source.items()},
        "budget_overruns": overruns,
        "savings_goals": [g.to_dict() for g in user.goals],
    }


def get_user(user_id):
    return db.session.get(User, user_id)


# ---------- routes ----------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/users", methods=["GET", "POST"])
def users():
    if request.method == "POST":
        d = request.get_json(force=True)
        if not d.get("name") or d.get("persona") not in PERSONAS:
            return jsonify(error=f"name and persona ({', '.join(PERSONAS)}) are required"), 400
        u = User(name=d["name"].strip(), persona=d["persona"], currency=d.get("currency", "INR"))
        db.session.add(u)
        db.session.commit()
        return jsonify(u.to_dict()), 201
    return jsonify([u.to_dict() for u in User.query.order_by(User.id)])


@app.route("/api/users/<int:user_id>/summary")
def summary(user_id):
    user = get_user(user_id)
    if not user:
        return jsonify(error="User not found"), 404
    snap = build_snapshot(user, request.args.get("month"))
    start, end = month_range(request.args.get("month"))
    snap["recent_expenses"] = [e.to_dict() for e in sorted(
        (e for e in user.expenses if start <= e.date < end), key=lambda e: e.date, reverse=True)[:8]]
    return jsonify(snap)


@app.route("/api/users/<int:user_id>/<kind>", methods=["POST"])
def add_record(user_id, kind):
    """kind: incomes | expenses | goals | budgets"""
    if not get_user(user_id):
        return jsonify(error="User not found"), 404
    d = request.get_json(force=True)
    try:
        if kind == "incomes":
            row = Income(user_id=user_id, source=d["source"], amount=float(d["amount"]), date=parse_date(d.get("date")))
        elif kind == "expenses":
            row = Expense(user_id=user_id, category=d["category"].strip().title(), amount=float(d["amount"]),
                          description=d.get("description", ""), is_essential=bool(d.get("is_essential", True)),
                          date=parse_date(d.get("date")))
        elif kind == "goals":
            row = SavingsGoal(user_id=user_id, name=d["name"], target_amount=float(d["target_amount"]),
                              saved_amount=float(d.get("saved_amount", 0)),
                              deadline=date.fromisoformat(d["deadline"]) if d.get("deadline") else None)
        elif kind == "budgets":
            row = Budget(user_id=user_id, category=d["category"].strip().title(), monthly_limit=float(d["monthly_limit"]))
        else:
            return jsonify(error="Unknown record type"), 404
    except (KeyError, ValueError, TypeError):
        return jsonify(error="Missing or invalid fields"), 400
    if row.__dict__.get("amount", 1) <= 0:
        return jsonify(error="Amount must be positive"), 400
    db.session.add(row)
    db.session.commit()
    return jsonify(ok=True), 201


@app.route("/api/analyze/<int:user_id>")
def analyze(user_id):
    user = get_user(user_id)
    if not user:
        return jsonify(error="User not found"), 404
    snap = build_snapshot(user, request.args.get("month"))
    if not snap["total_income"] and not snap["total_expenses"]:
        return jsonify(error="Add some income or expenses for this month first."), 400
    try:
        return jsonify(analyze_finances(snap))
    except AIEngineError as exc:
        return jsonify(error=str(exc)), 502


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", port=5000)
