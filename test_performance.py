"""
test_performance.py
-------------------
Hits the /ask endpoint with a set of queries and prints a response time summary.
Run with: python test_performance.py
"""

import time
import httpx

BASE_URL = "http://localhost:8000"

QUERIES = [
    "How many customers are there?",
    "Top 5 customers by total spending",
    "Total revenue by product category",
    "How many sales were made in 2024?",
    "Average salary per department",
    "Which employees made the most sales?",
    "List all active projects and their budgets",
    "Sales in Q1 2023",
    "Which product sells the most?",
    "Employees hired after 2022",
]

def run():
    results = []
    print(f"\n{'─'*65}")
    print(f"{'Query':<42} {'Status':<10} {'Time (s)'}")
    print(f"{'─'*65}")

    for q in QUERIES:
        start = time.perf_counter()
        try:
            r = httpx.post(f"{BASE_URL}/ask", json={"question": q}, timeout=30)
            elapsed = time.perf_counter() - start
            data = r.json()
            status = "✅ OK" if not data.get("error") else "❌ ERR"
        except Exception as e:
            elapsed = time.perf_counter() - start
            status = "❌ FAIL"

        results.append(elapsed)
        label = q[:40] + ".." if len(q) > 40 else q
        print(f"{label:<42} {status:<10} {elapsed:.2f}s")

    print(f"{'─'*65}")
    print(f"  Total queries : {len(results)}")
    print(f"  Avg response  : {sum(results)/len(results):.2f}s")
    print(f"  Fastest       : {min(results):.2f}s")
    print(f"  Slowest       : {max(results):.2f}s")
    print(f"{'─'*65}\n")

if __name__ == "__main__":
    run()
