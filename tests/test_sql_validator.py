from agents.sql_validator import validate_sql


def test_valid_select_query():
    sql = "SELECT * FROM employees;"

    valid, error = validate_sql(sql)

    assert valid is True
    assert error is None


def test_valid_with_query():
    sql = """
    WITH employee_data AS (
        SELECT id, name FROM employees
    )
    SELECT * FROM employee_data;
    """

    valid, error = validate_sql(sql)

    assert valid is True
    assert error is None


def test_reject_update():
    sql = "UPDATE employees SET salary = 100000;"

    valid, error = validate_sql(sql)

    assert valid is False
    assert "UPDATE" in error


def test_reject_delete():
    sql = "DELETE FROM employees;"

    valid, error = validate_sql(sql)

    assert valid is False
    assert "DELETE" in error


def test_reject_drop():
    sql = "DROP TABLE employees;"

    valid, error = validate_sql(sql)

    assert valid is False
    assert "DROP" in error


def test_reject_multiple_statements():
    sql = "SELECT * FROM employees; DROP TABLE employees;"

    valid, error = validate_sql(sql)

    assert valid is False
    assert "Multiple SQL statements" in error


def test_reject_dangerous_operation_inside_with():
    sql = """
    WITH deleted AS (
        DELETE FROM employees
        RETURNING *
    )
    SELECT * FROM deleted;
    """

    valid, error = validate_sql(sql)

    assert valid is False
    assert "DELETE" in error


def test_allow_keyword_inside_string():
    sql = "SELECT 'DROP TABLE employees;' AS message;"

    valid, error = validate_sql(sql)

    assert valid is True
    assert error is None


def test_reject_empty_sql():
    valid, error = validate_sql("")

    assert valid is False
    assert "empty" in error.lower()