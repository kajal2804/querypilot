"""
database/seed_cache.py — Vector Cache Pre-Seeder
-------------------------------------------------
Standalone service that pre-populates ChromaDB with common questions
WITHOUT needing Groq. Runs SQL directly against PostgreSQL and
generates simple answers from the results.

Run once:
    python -m database.seed_cache
"""

import asyncio
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.connection import init_pool, close_pool, execute_query
from agents.vector_store import VectorStore


# ── Hardcoded question → SQL → answer template pairs ─────────────────────────

SEED_QUERIES = [
    {
        "question": "Which employees made the most sales?",
        "tables":   ["employees", "sales"],
        "sql": """
            SELECT e.first_name, e.last_name, e.department,
                   COUNT(s.sale_id) AS sale_count,
                   SUM(s.total_amount) AS total_revenue
            FROM employees e
            JOIN sales s ON e.employee_id = s.employee_id
            GROUP BY e.employee_id, e.first_name, e.last_name, e.department
            ORDER BY sale_count DESC
            LIMIT 5
        """,
        "template": lambda rows: (
            f"The top salesperson is {rows[0][0]} {rows[0][1]} ({rows[0][2]}) "
            f"with {rows[0][3]} sales totalling ${rows[0][4]:,.2f}. "
            f"They are followed by {rows[1][0]} {rows[1][1]} ({rows[1][3]} sales) "
            f"and {rows[2][0]} {rows[2][1]} ({rows[2][3]} sales)."
        ) if len(rows) >= 3 else f"Found {len(rows)} employee(s) with sales data.",
    },
    {
        "question": "Top 5 customers by total spending",
        "tables":   ["customers", "sales"],
        "sql": """
            SELECT c.first_name, c.last_name,
                   SUM(s.total_amount) AS total_spending
            FROM customers c
            JOIN sales s ON c.customer_id = s.customer_id
            GROUP BY c.customer_id, c.first_name, c.last_name
            ORDER BY total_spending DESC
            LIMIT 5
        """,
        "template": lambda rows: (
            f"The top 5 customers by total spending are: "
            + ", ".join(f"{r[0]} {r[1]} (${r[2]:,.2f})" for r in rows) + "."
        ),
    },
    {
        "question": "Total revenue by product category",
        "tables":   ["products", "sales"],
        "sql": """
            SELECT p.category, SUM(s.total_amount) AS total_revenue
            FROM sales s
            JOIN products p ON s.product_id = p.product_id
            GROUP BY p.category
            ORDER BY total_revenue DESC
        """,
        "template": lambda rows: (
            f"Total revenue by category: "
            + ", ".join(f"{r[0]}: ${r[1]:,.2f}" for r in rows) + "."
        ),
    },
    {
        "question": "How many sales were made in 2024?",
        "tables":   ["sales"],
        "sql": """
            SELECT COUNT(*) AS sale_count
            FROM sales
            WHERE EXTRACT(YEAR FROM sale_date) = 2024
        """,
        "template": lambda rows: f"A total of {rows[0][0]} sales were made in 2024.",
    },
    {
        "question": "Average salary per department",
        "tables":   ["employees"],
        "sql": """
            SELECT department, ROUND(AVG(salary)::numeric, 2) AS avg_salary
            FROM employees
            GROUP BY department
            ORDER BY avg_salary DESC
        """,
        "template": lambda rows: (
            f"Average salaries by department: "
            + ", ".join(f"{r[0]}: ${r[1]:,.2f}" for r in rows) + "."
        ),
    },
    {
        "question": "List all active projects and their budgets",
        "tables":   ["projects"],
        "sql": """
            SELECT name, department, budget
            FROM projects
            WHERE status = 'active'
            ORDER BY budget DESC
        """,
        "template": lambda rows: (
            f"There are {len(rows)} active projects. "
            f"The largest by budget is '{rows[0][0]}' ({rows[0][1]}) at ${rows[0][2]:,.2f}."
        ) if rows else "No active projects found.",
    },
    {
        "question": "How many customers are there?",
        "tables":   ["customers"],
        "sql": "SELECT COUNT(*) FROM customers",
        "template": lambda rows: f"There are {rows[0][0]} customers in the database.",
    },
    {
        "question": "What products are available?",
        "tables":   ["products"],
        "sql": """
            SELECT name, category, unit_price
            FROM products
            ORDER BY category, unit_price DESC
        """,
        "template": lambda rows: (
            f"There are {len(rows)} products available across "
            f"{len(set(r[1] for r in rows))} categories. "
            f"The most expensive is '{rows[0][0]}' at ${rows[0][2]:,.2f}."
        ),
    },
    {
        "question": "Sales in Q1 2023",
        "tables":   ["sales"],
        "sql": "SELECT COUNT(*) AS sale_count, SUM(total_amount) AS revenue FROM sales WHERE sale_date BETWEEN '2023-01-01' AND '2023-03-31'",
        "template": lambda rows: f"In Q1 2023, there were {rows[0][0]} sales totalling ${rows[0][1]:,.2f} in revenue.",
    },
    {
        "question": "Sales in Q2 2023",
        "tables":   ["sales"],
        "sql": "SELECT COUNT(*) AS sale_count, SUM(total_amount) AS revenue FROM sales WHERE sale_date BETWEEN '2023-04-01' AND '2023-06-30'",
        "template": lambda rows: f"In Q2 2023, there were {rows[0][0]} sales totalling ${rows[0][1]:,.2f} in revenue.",
    },
    {
        "question": "Sales in Q3 2023",
        "tables":   ["sales"],
        "sql": "SELECT COUNT(*) AS sale_count, SUM(total_amount) AS revenue FROM sales WHERE sale_date BETWEEN '2023-07-01' AND '2023-09-30'",
        "template": lambda rows: f"In Q3 2023, there were {rows[0][0]} sales totalling ${rows[0][1]:,.2f} in revenue.",
    },
    {
        "question": "Sales in Q4 2023",
        "tables":   ["sales"],
        "sql": "SELECT COUNT(*) AS sale_count, SUM(total_amount) AS revenue FROM sales WHERE sale_date BETWEEN '2023-10-01' AND '2023-12-31'",
        "template": lambda rows: f"In Q4 2023, there were {rows[0][0]} sales totalling ${rows[0][1]:,.2f} in revenue.",
    },
    {
        "question": "Sales in Q1 2024",
        "tables":   ["sales"],
        "sql": "SELECT COUNT(*) AS sale_count, SUM(total_amount) AS revenue FROM sales WHERE sale_date BETWEEN '2024-01-01' AND '2024-03-31'",
        "template": lambda rows: f"In Q1 2024, there were {rows[0][0]} sales totalling ${rows[0][1]:,.2f} in revenue.",
    },
    {
        "question": "What is the total budget across all projects?",
        "tables":   ["projects"],
        "sql": "SELECT SUM(budget) AS total_budget FROM projects",
        "template": lambda rows: f"The total budget across all projects is ${rows[0][0]:,.2f}.",
    },
]


# ── seeder ────────────────────────────────────────────────────────────────────

async def seed_cache():
    print("Connecting to database…")
    await init_pool()

    store = VectorStore()
    print(f"Vector cache currently has {store.count()} entries.\n")

    success = 0
    for item in SEED_QUERIES:
        question = item["question"]
        try:
            rows = await execute_query(item["sql"])
            row_list = [list(r.values()) for r in rows]

            # Generate answer from template
            answer = item["template"](row_list)

            # Store in vector cache
            store.store(question, answer, item["sql"].strip(), item["tables"])
            print(f"  ✅ Cached: {question}")
            success += 1

        except Exception as exc:
            print(f"  ❌ Failed: {question} — {exc}")

    await close_pool()
    print(f"\n✅ Done — {success}/{len(SEED_QUERIES)} queries cached.")
    print(f"   Vector cache now has {store.count()} entries.")


if __name__ == "__main__":
    asyncio.run(seed_cache())
