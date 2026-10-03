# Research Data

## Data Provenance

This directory contains sample cases used for the research evaluation harness.
All cases are clearly labeled by provenance type.

### Provenance Types

- **seeded**: Cases from `seed_intelligence.py` in the main application (4 cases)
- **simulated**: Synthetically generated cases for evaluation purposes
- **real_measured**: Cases from actual closed-loop benchmarking (requires running AutoDBA)

### File Structure

- `sample_cases.json`: Seeded and simulated cases for testing the harness
- Real measured cases are generated at runtime when AutoDBA's closed-loop service runs

### Synthetic Case Generation

Synthetic cases (simulated) are generated using:
- Query templates from the existing seed cases
- Random parameterization of WHERE clauses, JOIN conditions, and ORDER BY columns
- Plausible but fictional benchmark outcomes (runtime improvements, planner costs)
- Varying measurement quality levels (high/medium/low)

IMPORTANT: Synthetic cases are clearly labeled and should never be used to claim
performance improvements or novelty in the AutoDBA system.

### Data Quality Notes

- Seeded cases have high confidence (real HypoPG validation results)
- Simulated cases have medium confidence (plausible but unverified outcomes)
- Real measured cases require actual database benchmarking infrastructure
- All synthetic data is clearly marked with "provenance": "simulated" in JSON