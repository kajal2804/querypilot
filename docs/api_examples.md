# QueryPilot — API Examples

Base URL: `http://localhost:8000`

---

## POST /ask

Runs the 4-agent pipeline and returns a structured answer.

### Direct Lookup

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Show me all customers from New York"}'
```

```json
{
  "question": "Show me all customers from New York",
  "answer": "There are 14 customers from New York. They include Alice Smith (alice.smith3@gmail.com), Bob Johnson (bob.johnson12@yahoo.com), and 12 others who signed up between 2018 and 2024.",
  "sql_query": "SELECT first_name, last_name, email, signup_date FROM customers WHERE city = 'New York' ORDER BY signup_date DESC",
  "columns": ["first_name", "last_name", "email", "signup_date"],
  "rows": [
    ["Alice", "Smith", "alice.smith3@gmail.com", "2024-03-15"],
    ["Bob", "Johnson", "bob.johnson12@yahoo.com", "2023-11-02"]
  ],
  "row_count": 14,
  "relevant_tables": ["customers", "employees", "products", "sales", "projects"],
  "error": null
}
```

---

### Aggregation

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the total revenue per product category?"}'
```

```json
{
  "question": "What is the total revenue per product category?",
  "answer": "Electronics leads all categories with $142,350.50 in total revenue, followed by Furniture at $87,200.00, Software at $54,900.00, and Stationery at $12,300.75.",
  "sql_query": "SELECT p.category, SUM(s.total_amount) AS total_revenue FROM sales s JOIN products p ON s.product_id = p.product_id GROUP BY p.category ORDER BY total_revenue DESC",
  "columns": ["category", "total_revenue"],
  "rows": [
    ["Electronics", 142350.50],
    ["Furniture", 87200.00],
    ["Software", 54900.00],
    ["Stationery", 12300.75]
  ],
  "row_count": 4,
  "relevant_tables": ["customers", "employees", "products", "sales", "projects"],
  "error": null
}
```

---

### Temporal Query

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "How many sales were made in Q1 2023?"}'
```

```json
{
  "question": "How many sales were made in Q1 2023?",
  "answer": "A total of 47 sales were recorded in Q1 2023 (January through March), representing approximately 9.4% of all sales in the dataset.",
  "sql_query": "SELECT COUNT(*) AS sale_count FROM sales WHERE sale_date BETWEEN '2023-01-01' AND '2023-03-31'",
  "columns": ["sale_count"],
  "rows": [[47]],
  "row_count": 1,
  "relevant_tables": ["customers", "employees", "products", "sales", "projects"],
  "error": null
}
```

---

### Join Query

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Which employees made the most sales?"}'
```

```json
{
  "question": "Which employees made the most sales?",
  "answer": "The top salesperson is Sam Taylor from the Sales department with 28 sales totalling $41,200. They are followed by Grace Miller (24 sales) and Noah Brown (21 sales).",
  "sql_query": "SELECT e.first_name, e.last_name, e.department, COUNT(s.sale_id) AS sale_count, SUM(s.total_amount) AS total_revenue FROM employees e JOIN sales s ON e.employee_id = s.employee_id GROUP BY e.employee_id, e.first_name, e.last_name, e.department ORDER BY sale_count DESC LIMIT 10",
  "columns": ["first_name", "last_name", "department", "sale_count", "total_revenue"],
  "rows": [
    ["Sam", "Taylor", "Sales", 28, 41200.00],
    ["Grace", "Miller", "Sales", 24, 35800.50]
  ],
  "row_count": 10,
  "relevant_tables": ["customers", "employees", "products", "sales", "projects"],
  "error": null
}
```

---

### Error Response (no matching records)

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Show sales from March 2099"}'
```

```json
{
  "question": "Show sales from March 2099",
  "answer": "No matching records were found for sales in March 2099. This is likely because the dataset only contains sales data up to 2025.",
  "sql_query": "SELECT * FROM sales WHERE sale_date BETWEEN '2099-03-01' AND '2099-03-31'",
  "columns": [],
  "rows": [],
  "row_count": 0,
  "relevant_tables": ["customers", "employees", "products", "sales", "projects"],
  "error": null
}
```

---

## GET /health

```bash
curl http://localhost:8000/health
```

```json
{
  "status": "ok",
  "tables": ["customers", "employees", "products", "sales", "projects"]
}
```

---

## GET /schema

```bash
curl http://localhost:8000/schema
```

```json
{
  "schema": {
    "customers": {
      "columns": [
        {"name": "customer_id", "type": "integer", "nullable": false, "constraint": "PRIMARY KEY"},
        {"name": "first_name",  "type": "character varying", "nullable": false, "constraint": null}
      ],
      "foreign_keys": []
    },
    "sales": {
      "columns": [...],
      "foreign_keys": [
        "customer_id → customers.customer_id",
        "employee_id → employees.employee_id",
        "product_id → products.product_id"
      ]
    }
  }
}
```

---

## Interactive Docs

FastAPI auto-generates Swagger UI at:

```
http://localhost:8000/docs
```

And ReDoc at:

```
http://localhost:8000/redoc
```
