"""
database/seed.py
----------------
Generates synthetic data for all 5 tables.
Run once after the database is created:

    python -m database.seed          # from querypilot/ root
"""

import asyncio
import random
import sys, os
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from database.connection import init_pool, close_pool, get_pool, _create_schema

random.seed(42)

# ── lookup data ───────────────────────────────────────────────────────────────

FIRST_NAMES = [
    "Alice","Bob","Carol","David","Eva","Frank","Grace","Henry",
    "Isla","Jack","Karen","Leo","Mia","Noah","Olivia","Paul",
    "Quinn","Rachel","Sam","Tina","Uma","Victor","Wendy","Xander",
    "Yara","Zoe","Aaron","Beth","Chris","Diana",
]
LAST_NAMES = [
    "Smith","Johnson","Williams","Brown","Jones","Garcia","Miller",
    "Davis","Wilson","Martinez","Anderson","Taylor","Thomas","Jackson",
    "White","Harris","Martin","Thompson","Moore","Young",
]
CITIES    = ["New York","Los Angeles","Chicago","Houston","Phoenix",
             "Philadelphia","San Diego","Dallas","London","Paris",
             "Berlin","Sydney","Toronto","Tokyo","Singapore"]
COUNTRIES = ["USA","USA","USA","USA","USA","UK","France","Germany",
             "Australia","Canada","Japan","Singapore","India"]

DEPARTMENTS = ["Sales","Engineering","Marketing","HR","Finance","Support","Operations"]
JOB_TITLES = {
    "Sales":       ["Sales Rep","Senior Sales Rep","Account Executive","Sales Manager"],
    "Engineering": ["Junior Engineer","Software Engineer","Senior Engineer","Tech Lead"],
    "Marketing":   ["Marketing Analyst","Content Strategist","Growth Manager","CMO"],
    "HR":          ["HR Coordinator","HR Specialist","HR Manager","CHRO"],
    "Finance":     ["Analyst","Senior Analyst","Controller","CFO"],
    "Support":     ["Support Agent","Senior Support Agent","Support Lead","Support Manager"],
    "Operations":  ["Ops Analyst","Operations Manager","COO","Logistics Coordinator"],
}

PRODUCTS = [
    ("Laptop Pro 15",            "Electronics",  1299.99),
    ("Wireless Mouse",           "Electronics",    29.99),
    ("USB-C Hub",                "Electronics",    49.99),
    ("Standing Desk",            "Furniture",     399.99),
    ("Ergonomic Chair",          "Furniture",     549.99),
    ('Monitor 27"',              "Electronics",   349.99),
    ("Mechanical Keyboard",      "Electronics",   119.99),
    ("Noise-Cancelling Headphones","Electronics", 249.99),
    ("Webcam HD",                "Electronics",    79.99),
    ("Desk Lamp",                "Furniture",      39.99),
    ("Cloud Storage 1yr",        "Software",       99.99),
    ("VPN License 1yr",          "Software",       59.99),
    ("Antivirus Suite",          "Software",       49.99),
    ("Project Mgmt Tool",        "Software",      149.99),
    ("Notebook Set",             "Stationery",     14.99),
    ("Ballpoint Pens x20",       "Stationery",      9.99),
    ("Whiteboard",               "Furniture",     129.99),
    ("Printer Ink Set",          "Stationery",     34.99),
    ("External SSD 1TB",         "Electronics",   109.99),
    ("Smart Speaker",            "Electronics",    89.99),
]

PROJECT_NAMES = [
    "CRM Overhaul","Data Warehouse Migration","Mobile App v2","AI Chatbot Launch",
    "ERP Integration","Website Redesign","Sales Dashboard","HR Portal",
    "Cloud Cost Optimisation","Customer Loyalty Programme","Supply Chain Analytics",
    "Security Audit 2024","API Gateway Upgrade","Marketing Automation","BI Platform",
]
PROJECT_STATUSES = ["active","completed","on_hold","cancelled"]


def rand_date(start_year=2020, end_year=2025) -> date:
    start = date(start_year, 1, 1)
    end   = date(end_year, 12, 31)
    return start + timedelta(days=random.randint(0, (end - start).days))


def rand_email(first: str, last: str, idx: int) -> str:
    domains = ["gmail.com","yahoo.com","outlook.com","company.io","mail.com"]
    return f"{first.lower()}.{last.lower()}{idx}@{random.choice(domains)}"


# ── seed ──────────────────────────────────────────────────────────────────────

async def seed() -> None:
    await init_pool()
    pool = get_pool()

    async with pool.acquire() as conn:
        # ── customers (200) ───────────────────────────────────────────────────
        print("Seeding customers…")
        customer_ids = []
        for i in range(200):
            fn, ln = random.choice(FIRST_NAMES), random.choice(LAST_NAMES)
            row = await conn.fetchrow(
                """INSERT INTO customers (first_name,last_name,email,city,country,signup_date)
                   VALUES ($1,$2,$3,$4,$5,$6) RETURNING customer_id""",
                fn, ln, rand_email(fn, ln, i),
                random.choice(CITIES), random.choice(COUNTRIES),
                rand_date(2018, 2024),
            )
            customer_ids.append(row["customer_id"])

        # ── employees (50) ────────────────────────────────────────────────────
        print("Seeding employees…")
        employee_ids = []
        for _ in range(50):
            fn, ln = random.choice(FIRST_NAMES), random.choice(LAST_NAMES)
            dept  = random.choice(DEPARTMENTS)
            title = random.choice(JOB_TITLES[dept])
            row = await conn.fetchrow(
                """INSERT INTO employees (first_name,last_name,department,job_title,hire_date,salary)
                   VALUES ($1,$2,$3,$4,$5,$6) RETURNING employee_id""",
                fn, ln, dept, title,
                rand_date(2015, 2024),
                round(random.uniform(40_000, 150_000), 2),
            )
            employee_ids.append(row["employee_id"])

        # ── products (20) ─────────────────────────────────────────────────────
        print("Seeding products…")
        product_ids    = []
        product_prices = {}
        for name, cat, price in PRODUCTS:
            row = await conn.fetchrow(
                """INSERT INTO products (name,category,unit_price,stock_qty)
                   VALUES ($1,$2,$3,$4) RETURNING product_id""",
                name, cat, price, random.randint(10, 500),
            )
            product_ids.append(row["product_id"])
            product_prices[row["product_id"]] = price

        # ── sales (500) ───────────────────────────────────────────────────────
        print("Seeding sales…")
        for _ in range(500):
            pid = random.choice(product_ids)
            qty = random.randint(1, 10)
            await conn.execute(
                """INSERT INTO sales (customer_id,employee_id,product_id,quantity,total_amount,sale_date)
                   VALUES ($1,$2,$3,$4,$5,$6)""",
                random.choice(customer_ids),
                random.choice(employee_ids),
                pid, qty,
                round(product_prices[pid] * qty, 2),
                rand_date(2020, 2025),
            )

        # ── projects (15) ─────────────────────────────────────────────────────
        print("Seeding projects…")
        for pname in PROJECT_NAMES:
            dept   = random.choice(DEPARTMENTS)
            lead   = random.choice(employee_ids)
            status = random.choice(PROJECT_STATUSES)
            start  = rand_date(2021, 2024)
            end    = (start + timedelta(days=random.randint(90, 540))
                      if status == "completed" else None)
            await conn.execute(
                """INSERT INTO projects (name,department,lead_employee_id,status,budget,start_date,end_date)
                   VALUES ($1,$2,$3,$4,$5,$6,$7)""",
                pname, dept, lead, status,
                round(random.uniform(10_000, 500_000), 2),
                start, end,
            )

    await close_pool()
    print("✅ Database seeded — 200 customers, 50 employees, 20 products, 500 sales, 15 projects.")


if __name__ == "__main__":
    asyncio.run(seed())
