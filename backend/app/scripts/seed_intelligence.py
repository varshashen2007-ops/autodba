from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.services.memory_service import MemoryService
from app.schemas.optimization import OptimizationOutcome


SEED_CASES = [
    {
        "incident_type": "missing_index",
        "query_text": "SELECT * FROM orders WHERE customer_id = 42",
        "diagnosis": {
            "finding_type": "missing_index",
            "node_type": "Seq Scan",
            "relation": "orders",
            "estimated_cost": 107.50,
        },
        "recommendation": {
            "action": "create_index",
            "table": "orders",
            "columns": ["customer_id"],
            "sql_preview": "CREATE INDEX ON orders (customer_id);",
        },
        "validation": {
            "hypopg_validated": True,
            "estimated_cost_before": 107.50,
            "estimated_cost_after": 28.16,
            "cost_improvement_percent": 73.80,
        },
        "benchmark": {
            "runtime_improvement_percent": 87.90,
            "validated": True,
        },
        "outcome": OptimizationOutcome.SUCCESS,
        "outcome_summary": "Index reduced planner cost substantially and improved measured runtime.",
    },
    {
        "incident_type": "expensive_sort",
        "query_text": "SELECT * FROM orders ORDER BY order_date DESC",
        "diagnosis": {
            "finding_type": "expensive_sort",
            "node_type": "Sort",
            "relation": "orders",
            "estimated_cost": 850.0,
        },
        "recommendation": {
            "action": "create_index",
            "table": "orders",
            "columns": ["order_date"],
            "sql_preview": "CREATE INDEX ON orders (order_date);",
        },
        "validation": {
            "hypopg_validated": True,
            "cost_improvement_percent": 61.20,
        },
        "benchmark": {
            "runtime_improvement_percent": 54.30,
            "validated": True,
        },
        "outcome": OptimizationOutcome.SUCCESS,
        "outcome_summary": "Ordering workload benefited from an index aligned with the ORDER BY column.",
    },
    {
        "incident_type": "expensive_nested_loop",
        "query_text": "SELECT * FROM orders o JOIN customers c ON o.customer_id = c.id WHERE c.id = 42",
        "diagnosis": {
            "finding_type": "expensive_nested_loop",
            "node_type": "Nested Loop",
            "estimated_cost": 1250.0,
        },
        "recommendation": {
            "action": "investigate_index",
            "table": "orders",
            "columns": ["customer_id"],
        },
        "validation": {
            "hypopg_validated": True,
            "cost_improvement_percent": 48.50,
        },
        "benchmark": {
            "runtime_improvement_percent": 42.10,
            "validated": True,
        },
        "outcome": OptimizationOutcome.SUCCESS,
        "outcome_summary": "Supporting the join predicate with an index reduced nested-loop work.",
    },
    {
        "incident_type": "large_row_estimate",
        "query_text": "SELECT * FROM order_items WHERE product_id = 17",
        "diagnosis": {
            "finding_type": "large_row_estimate",
            "node_type": "Seq Scan",
            "relation": "order_items",
            "estimated_rows": 15000,
        },
        "recommendation": {
            "action": "analyze_table",
            "table": "order_items",
        },
        "validation": {
            "hypopg_validated": False,
            "cost_improvement_percent": 0.0,
        },
        "benchmark": {
            "runtime_improvement_percent": 18.40,
            "validated": True,
        },
        "outcome": OptimizationOutcome.SUCCESS,
        "outcome_summary": "Refreshing table statistics improved planner estimates for the workload.",
    },
]


def main() -> None:
    db: Session = SessionLocal()
    try:
        service = MemoryService(db)

        for case in SEED_CASES:
            service.create_memory(**case)

        print(f"Seeded {len(SEED_CASES)} historical optimization memories.")
    finally:
        db.close()


if __name__ == "__main__":
    main()

