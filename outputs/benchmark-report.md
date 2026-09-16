# Sharing & survival

Experiment `18a37e7fe1f14dd0` · engine 1.0.0
Status: complete. Completed 300/300 runs in 37.25 seconds.

| Condition / policy | Seeds | Mean survival | Hungry inhabitant-days | Spoilage | Recovered | Recovery days (recovered only) |
|---|---:|---:|---:|---:|---:|---:|
| drought / pool | 50 | 1.000 | 0.0 | 9082.9 | 50 | 0.0 |
| drought / private | 50 | 0.783 | 81.3 | 8652.1 | 50 | 0.0 |
| drought / surplus / reserve 3 | 50 | 1.000 | 0.4 | 9083.0 | 50 | 0.0 |
| individual / pool | 50 | 1.000 | 0.0 | 5952.2 | 0 | N/A |
| individual / private | 50 | 0.999 | 212.6 | 6064.4 | 0 | N/A |
| individual / surplus / reserve 3 | 50 | 1.000 | 0.0 | 5952.2 | 0 | N/A |

## Paired differences (B minus A)

| A | B | Metric | Paired seeds | Difference | 95% bootstrap interval |
|---|---|---|---:|---:|---|
| drought / pool | drought / private | survival | 50 | -0.2170 | -0.2360 to -0.1985 |
| drought / pool | drought / private | hungry_days | 50 | 81.3000 | 76.9795 to 86.1005 |
| drought / pool | drought / private | spoiled | 50 | -430.7935 | -476.2925 to -388.6861 |
| drought / pool | drought / surplus / reserve 3 | survival | 50 | 0.0000 | 0.0000 to 0.0000 |
| drought / pool | drought / surplus / reserve 3 | hungry_days | 50 | 0.4400 | 0.0000 to 1.3200 |
| drought / pool | drought / surplus / reserve 3 | spoiled | 50 | 0.0461 | -0.0000 to 0.1844 |
| drought / private | drought / surplus / reserve 3 | survival | 50 | 0.2170 | 0.1970 to 0.2355 |
| drought / private | drought / surplus / reserve 3 | hungry_days | 50 | -80.8600 | -85.4805 to -76.3185 |
| drought / private | drought / surplus / reserve 3 | spoiled | 50 | 430.8396 | 389.8376 to 480.2539 |
| individual / pool | individual / private | survival | 50 | -0.0010 | -0.0025 to 0.0000 |
| individual / pool | individual / private | hungry_days | 50 | 212.5800 | 191.9510 to 232.2830 |
| individual / pool | individual / private | spoiled | 50 | 112.2297 | 101.1975 to 123.2677 |
| individual / pool | individual / surplus / reserve 3 | survival | 50 | 0.0000 | 0.0000 to 0.0000 |
| individual / pool | individual / surplus / reserve 3 | hungry_days | 50 | 0.0000 | 0.0000 to 0.0000 |
| individual / pool | individual / surplus / reserve 3 | spoiled | 50 | 0.0000 | -0.0000 to 0.0000 |
| individual / private | individual / surplus / reserve 3 | survival | 50 | 0.0010 | 0.0000 to 0.0025 |
| individual / private | individual / surplus / reserve 3 | hungry_days | 50 | -212.5800 | -233.2415 to -192.0570 |
| individual / private | individual / surplus / reserve 3 | spoiled | 50 | -112.2297 | -122.3744 to -101.2972 |

## Assumptions

Results describe this version of the simulated world. Paired intervals are descriptive, not adjusted for multiple comparisons. Recovery averages include recovered colonies only.
Sharing is instantaneous at the settlement. Rules and gathering behavior are explicit; inhabitants do not use AI. No causal claim about real societies is established.

## Configuration

```json
{
  "name": "Sharing & survival",
  "base": {
    "version": "1",
    "seed": 42,
    "population": 40,
    "duration": 365,
    "policy": "surplus",
    "reserve": 3,
    "ration": 1,
    "initial_food": 4,
    "daily_yield": 2.4,
    "patch_regrowth": 13,
    "spoilage": 0.035,
    "starvation_days": 7,
    "failure_chance": 0.2,
    "drought_start": 90,
    "drought_length": 20,
    "drought_severity": 0.7,
    "condition": "individual"
  },
  "policies": [
    "private",
    "pool",
    "surplus"
  ],
  "conditions": [
    "individual",
    "drought"
  ],
  "reserves": [
    3
  ],
  "seeds": 50,
  "seed_start": 1000
}
```