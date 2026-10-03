# AutoDBA Research Evaluation Harness

This directory contains the research evaluation framework for comparing AutoDBA's current case retrieval with improved retrieval methods.

## Overview

The evaluation tests whether retrieved historical optimization cases help choose better database recommendations on unseen queries and workloads.

## Components

### 1. Case Schema (`metrics.py`)

Defines the structure for optimization cases including:
- Query, plan, schema/statistics
- Workload context
- Recommended action
- HypoPG validation
- Measured outcome
- Measurement quality

### 2. Evaluation Framework (`evaluation_framework.py`)

Core evaluation engine that:
- Runs queries through the AutoDBA pipeline
- Retrieves similar historical cases
- Generates recommendations
- Simulates benchmarking
- Compares predicted vs actual outcomes

### 3. Research Harness (`harness.py`)

Main orchestration layer that:
- Runs full evaluation cycles
- Compares AutoDBA recommendations vs manual interventions
- Calculates improvement gaps
- Generates human-readable reports

## Running Evaluations

```python
from research.harness import ResearchHarness

harness = ResearchHarness()

# Single evaluation
result = harness.run_evaluation(
    query="SELECT * FROM orders WHERE customer_id = 42",
    incident_type="missing_index"
)

# Side-by-side comparison
comparison = harness.run_comparison(
    query="SELECT * FROM orders WHERE customer_id = 42",
    incident_type="missing_index"
)

# Generate report
report = harness.generate_report(result)
print(report)
```

## Data Flow

```
Query + Incident Type
       │
       ▼
┌──────────────────┐
│ Identify Bottleneck │
└──────────────────┘
       │
       ▼
┌──────────────────┐
│ Retrieve Similar Cases │◄── Memory Store (optimization_memories)
└──────────────────┘
       │
       ▼
┌──────────────────┐
│ Generate Recommendation │
└──────────────────┘
       │
       ▼
┌──────────────────┐
│ Simulate Benchmark   │
└──────────────────┘
       │
       ▼
┌──────────────────┐
│ Determine Outcome    │
└──────────────────┘
```

## Evaluation Metrics

- **Retrieval Quality**: Precision@K, Recall@K, NDCG for similar case retrieval
- **Recommendation Quality**: Accuracy of recommendation type, index selection
- **Tuning Time**: End-to-end latency from query to recommendation
- **Workload Runtime**: Measured before/after execution time
- **P95 Latency**: Tail latency improvements
- **Index Storage/Write Overhead**: Index size, write amplification

## Ablation Studies

The framework supports isolating the value of:
- Plan features (execution plan structure, cost estimates)
- Workload context (query patterns, frequency)
- Outcomes (historical success/failure rates)
- Reranking (outcome-aware reranking)

## Experiment Manifest

Each run records:
- Database version (PostgreSQL 17 + HypoPG)
- Dataset (E-commerce: customers, products, orders, order_items)
- Configuration (thresholds, similarity parameters)
- Random seed
- Run parameters

## Data Sources

- **Simulated/Seeded Cases**: Pre-loaded from `seed_intelligence.py` (4 cases)
- **Real Measured Cases**: Generated through closed-loop benchmarking

## Train/Test Split

Leakage-resistant splitting groups related query templates and workload conditions to prevent data leakage between training and test sets.

## Requirements

```
psycopg2-binary>=2.9
sqlalchemy>=2.0
pydantic>=2.0
pytest>=8.0
```

## Notes

- This is research scaffolding - does not modify existing AutoDBA code
- All evaluation logic is contained in `research/` directory
- Does not claim performance improvement or novelty