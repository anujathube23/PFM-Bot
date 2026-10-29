"""SQLAlchemy models. One User table with a `persona` covers all four scenarios
(salaried, student, freelancer, household) so the schema stays simple."""
from datetime import date
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
PERSONAS = ("salaried", "student", "freelancer", "household")


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    persona = db.Column(db.String(20), nullable=False, default="salaried")
    currency = db.Column(db.String(5), nullable=False, default="INR")
    incomes = db.relationship("Income", backref="user", cascade="all, delete-orphan")
    expenses = db.relationship("Expense", backref="user", cascade="all, delete-orphan")
    goals = db.relationship("SavingsGoal", backref="user", cascade="all, delete-orphan")
    budgets = db.relationship("Budget", backref="user", cascade="all, delete-orphan")

    def to_dict(self):
        return {"id": self.id, "name": self.name, "persona": self.persona, "currency": self.currency}


class Income(db.Model):
    """`source` = employer, allowance, or client name (freelancers earn from many)."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    source = db.Column(db.String(80), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)

    def to_dict(self):
        return {"id": self.id, "source": self.source, "amount": self.amount, "date": self.date.isoformat()}


class Expense(db.Model):
    """`is_essential` separates needs from wants (useful for students)."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    category = db.Column(db.String(50), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(200), default="")
    is_essential = db.Column(db.Boolean, default=True)
    date = db.Column(db.Date, nullable=False, default=date.today)

    def to_dict(self):
        return {"id": self.id, "category": self.category, "amount": self.amount,
                "description": self.description, "is_essential": self.is_essential,
                "date": self.date.isoformat()}


class SavingsGoal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    name = db.Column(db.String(80), nullable=False)
    target_amount = db.Column(db.Float, nullable=False)
    saved_amount = db.Column(db.Float, default=0.0)
    deadline = db.Column(db.Date, nullable=True)

    def to_dict(self):
        return {"id": self.id, "name": self.name, "target_amount": self.target_amount,
                "saved_amount": self.saved_amount,
                "deadline": self.deadline.isoformat() if self.deadline else None}


class Budget(db.Model):
    """Optional monthly limit per category, used to detect household overruns."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    category = db.Column(db.String(50), nullable=False)
    monthly_limit = db.Column(db.Float, nullable=False)
