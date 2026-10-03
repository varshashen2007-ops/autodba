# Experiment Manifest Design

## Purpose

The experiment manifest records all parameters needed to reproduce a research evaluation run.

## Required Fields

### Environment
- `experiment_id`: Unique identifier for the run
- `created_at`: ISO 8601 timestamp
- `database_version`: PostgreSQL version string
- `hypopg_version`: HypoPG version string
- `python_version`: Python interpreter version
- `os`: Operating system information

### Dataset
- `dataset_name`: Name of the dataset (e.g., "ecommerce")
- `tables`: List of table names
- `row_counts`: Row counts per table
- `statistics_freshness`: Timestamp of last ANALYZE

### Configuration
- `benchmark_runs`: Number of measurement runs
- `benchmark_warmup_runs`: Number of discarded warm-up runs
- `similarity_threshold`: Minimum cosine similarity for retrieval
- `retrieval_limit`: Maximum number of cases to retrieve
- `incident_type_filter`: Incident type filter (if any)
- `plan_analysis_thresholds`: Plan analysis thresholds
- `hypopg_min_cost_improvement_percent`: Minimum cost improvement for validation

### Split
- `split_method`: Method used for train/test split
- `train_size`: Number of training cases
- `test_size`: Number of test cases
- `group_by`: Grouping criteria used to prevent leakage
- `seed`: Random seed for reproducibility

### Run Parameters
- `retrieval_method`: Name of the retrieval method
- `reranking_method`: Name of the reranking method
- `metrics`: List of metrics to compute
- `ablation_config`: Configuration for ablation studies

## Example

```json
{
  "experiment_id": "exp-001",
  "created_at": "2026-09-23T12:00:00Z",
  "database_version": "PostgreSQL 17",
  "hypopg_version": "1.4.3",
  "python_version": "3.12",
  "os": "Windows 11",
  "dataset_name": "ecommerce",
  "tables": ["customers", "products", "orders", "order_items"],
  "row_counts": {
    "customers": 500,
    "products": 100,
    "orders": 5000,
    "order_items": 15000
  },
  "statistics_freshness": "2026-09-23T10:00:00Z",
  "benchmark_runs": 10,
  "benchmark_warmup_runs": 2,
  "similarity_threshold": 0.20,
  "retrieval_limit": 5,
  "split_method": "grouped_by_query_template",
  "train_size": 3,
  "test_size": 1,
  "group_by": "query_template",
  "seed": 42,
  "retrieval_method": "current_autodba",
  "reranking_method": "none",
  "metrics": ["precision_at_k", "recall_at_k", "ndcg", "runtime_improvement"],
  "ablation_config": {
    "plan_features": true,
    "workload_context": true,
    "outcomes": true,
    "reranking": false
  }
}
```

## Reproducibility Notes

- All experiments must record the random seed used
- Database configuration and dataset version must be recorded
- Query templates and workload conditions must be grouped to prevent leakage
- Measurement quality must be recorded for each case
