SIMULATION — assumed pass rates, not host data.

### E1 arm selectors (ranked goals, T=0)

| scenario | policy (goal / arm / temperature) | kept (±95%) | kept @60 att. | attempts | kept/GPU-h | dup share | 1st keep (median att.) | top arm share |
|---|---|---|---|---|---|---|---|---|
| low | ranked (live) / thompson (live) / T=0 (live) | 6.61 ± 0.24 | 3.90 | 150 | 4.14 | 0.214 | 5 | 0.51 |
| low | ranked (live) / dTS g=0.98 / T=0 (live) | 6.85 ± 0.25 | 3.84 | 151 | 4.41 | 0.164 | 5 | 0.39 |
| low | ranked (live) / dTS g=0.995 / T=0 (live) | 6.78 ± 0.24 | 3.93 | 150 | 4.30 | 0.198 | 5 | 0.47 |
| low | ranked (live) / SW-TS W=60 / T=0 (live) | 6.60 ± 0.24 | 3.74 | 151 | 4.32 | 0.168 | 5 | 0.42 |
| low | ranked (live) / TS by-via / T=0 (live) | 6.57 ± 0.23 | 3.79 | 151 | 4.34 | 0.178 | 5 | 0.37 |
| low | ranked (live) / hier TS (via|kind) / T=0 (live) | 6.78 ± 0.23 | 3.85 | 150 | 4.48 | 0.156 | 5 | 0.34 |
| low | ranked (live) / LinUCB 7f (bundle) / T=0 (live) | 6.83 ± 0.23 | 3.88 | 150 | 4.61 | 0.128 | 5 | 0.26 |
| low | ranked (live) / LinUCB 9f rich / T=0 (live) | 6.87 ± 0.23 | 3.90 | 151 | 4.65 | 0.121 | 5 | 0.25 |
| low | ranked (live) / uniform / T=0 (live) | 6.55 ± 0.23 | 3.67 | 151 | 4.51 | 0.136 | 5 | 0.24 |
| mid | ranked (live) / thompson (live) / T=0 (live) | 14.87 ± 0.32 | 9.09 | 134 | 10.49 | 0.181 | 2 | 0.46 |
| mid | ranked (live) / dTS g=0.98 / T=0 (live) | 14.79 ± 0.31 | 8.90 | 135 | 10.64 | 0.148 | 2 | 0.37 |
| mid | ranked (live) / dTS g=0.995 / T=0 (live) | 14.90 ± 0.32 | 9.10 | 134 | 10.64 | 0.168 | 2 | 0.43 |
| mid | ranked (live) / SW-TS W=60 / T=0 (live) | 14.72 ± 0.32 | 8.97 | 134 | 10.52 | 0.158 | 2 | 0.41 |
| mid | ranked (live) / TS by-via / T=0 (live) | 14.55 ± 0.31 | 8.83 | 135 | 10.66 | 0.166 | 2 | 0.36 |
| mid | ranked (live) / hier TS (via|kind) / T=0 (live) | 14.78 ± 0.32 | 8.94 | 135 | 10.64 | 0.155 | 2 | 0.37 |
| mid | ranked (live) / LinUCB 7f (bundle) / T=0 (live) | 14.82 ± 0.31 | 8.99 | 134 | 10.98 | 0.126 | 2 | 0.30 |
| mid | ranked (live) / LinUCB 9f rich / T=0 (live) | 15.13 ± 0.30 | 9.18 | 134 | 11.33 | 0.117 | 2 | 0.28 |
| mid | ranked (live) / uniform / T=0 (live) | 14.41 ± 0.30 | 8.65 | 135 | 11.20 | 0.129 | 2 | 0.24 |
| contextual | ranked (live) / thompson (live) / T=0 (live) | 15.30 ± 0.32 | 9.12 | 134 | 10.68 | 0.179 | 2 | 0.46 |
| contextual | ranked (live) / dTS g=0.98 / T=0 (live) | 15.09 ± 0.31 | 9.07 | 134 | 10.85 | 0.149 | 2 | 0.38 |
| contextual | ranked (live) / dTS g=0.995 / T=0 (live) | 15.11 ± 0.33 | 9.23 | 134 | 10.67 | 0.172 | 2 | 0.43 |
| contextual | ranked (live) / SW-TS W=60 / T=0 (live) | 15.13 ± 0.32 | 9.17 | 134 | 10.63 | 0.162 | 3 | 0.43 |
| contextual | ranked (live) / TS by-via / T=0 (live) | 15.28 ± 0.34 | 9.12 | 133 | 11.33 | 0.166 | 2 | 0.36 |
| contextual | ranked (live) / hier TS (via|kind) / T=0 (live) | 15.56 ± 0.32 | 9.24 | 133 | 11.25 | 0.153 | 2 | 0.37 |
| contextual | ranked (live) / LinUCB 7f (bundle) / T=0 (live) | 15.56 ± 0.32 | 9.19 | 133 | 11.62 | 0.128 | 2 | 0.31 |
| contextual | ranked (live) / LinUCB 9f rich / T=0 (live) | 15.44 ± 0.33 | 9.31 | 133 | 11.60 | 0.118 | 2 | 0.29 |
| contextual | ranked (live) / uniform / T=0 (live) | 14.58 ± 0.29 | 8.60 | 134 | 11.40 | 0.126 | 3 | 0.24 |
| drift | ranked (live) / thompson (live) / T=0 (live) | 14.46 ± 0.32 | 9.09 | 135 | 10.24 | 0.179 | 2 | 0.45 |
| drift | ranked (live) / dTS g=0.98 / T=0 (live) | 14.61 ± 0.31 | 8.90 | 135 | 10.53 | 0.148 | 2 | 0.37 |
| drift | ranked (live) / dTS g=0.995 / T=0 (live) | 14.59 ± 0.32 | 9.10 | 134 | 10.46 | 0.169 | 2 | 0.43 |
| drift | ranked (live) / SW-TS W=60 / T=0 (live) | 14.68 ± 0.31 | 8.97 | 135 | 10.57 | 0.155 | 2 | 0.41 |
| drift | ranked (live) / TS by-via / T=0 (live) | 14.29 ± 0.31 | 8.83 | 135 | 10.48 | 0.166 | 2 | 0.36 |
| drift | ranked (live) / hier TS (via|kind) / T=0 (live) | 14.57 ± 0.31 | 8.94 | 135 | 10.51 | 0.155 | 2 | 0.37 |
| drift | ranked (live) / LinUCB 7f (bundle) / T=0 (live) | 14.66 ± 0.30 | 8.99 | 135 | 10.90 | 0.126 | 2 | 0.30 |
| drift | ranked (live) / LinUCB 9f rich / T=0 (live) | 14.85 ± 0.29 | 9.18 | 135 | 11.15 | 0.117 | 2 | 0.28 |
| drift | ranked (live) / uniform / T=0 (live) | 14.21 ± 0.31 | 8.65 | 136 | 11.00 | 0.129 | 2 | 0.24 |

### E2 goal selectors (thompson arms, T=0)

| scenario | policy (goal / arm / temperature) | kept (±95%) | kept @60 att. | attempts | kept/GPU-h | dup share | 1st keep (median att.) | top arm share |
|---|---|---|---|---|---|---|---|---|
| low | ranked (live) / thompson (live) / T=0 (live) | 6.61 ± 0.24 | 3.90 | 150 | 4.14 | 0.214 | 5 | 0.51 |
| low | breadth-first / thompson (live) / T=0 (live) | 6.56 ± 0.25 | 3.31 | 151 | 4.20 | 0.209 | 6 | 0.50 |
| low | goal-TS (hier) / thompson (live) / T=0 (live) | 6.57 ± 0.25 | 3.60 | 150 | 4.19 | 0.224 | 9 | 0.51 |
| low | random / thompson (live) / T=0 (live) | 6.60 ± 0.25 | 2.91 | 151 | 4.17 | 0.226 | 14 | 0.51 |
| mid | ranked (live) / thompson (live) / T=0 (live) | 14.87 ± 0.32 | 9.09 | 134 | 10.49 | 0.181 | 2 | 0.46 |
| mid | breadth-first / thompson (live) / T=0 (live) | 14.59 ± 0.33 | 8.39 | 135 | 10.42 | 0.181 | 2 | 0.46 |
| mid | goal-TS (hier) / thompson (live) / T=0 (live) | 14.76 ± 0.33 | 8.57 | 134 | 10.47 | 0.187 | 4 | 0.45 |
| mid | random / thompson (live) / T=0 (live) | 14.76 ± 0.32 | 7.47 | 135 | 10.33 | 0.199 | 5 | 0.47 |
| contextual | ranked (live) / thompson (live) / T=0 (live) | 15.30 ± 0.32 | 9.12 | 134 | 10.68 | 0.179 | 2 | 0.46 |
| contextual | breadth-first / thompson (live) / T=0 (live) | 15.01 ± 0.34 | 8.57 | 134 | 10.55 | 0.178 | 2 | 0.46 |
| contextual | goal-TS (hier) / thompson (live) / T=0 (live) | 15.22 ± 0.35 | 8.65 | 134 | 10.62 | 0.191 | 4 | 0.47 |
| contextual | random / thompson (live) / T=0 (live) | 14.95 ± 0.32 | 7.51 | 134 | 10.49 | 0.196 | 5 | 0.47 |
| drift | ranked (live) / thompson (live) / T=0 (live) | 14.46 ± 0.32 | 9.09 | 135 | 10.24 | 0.179 | 2 | 0.45 |
| drift | breadth-first / thompson (live) / T=0 (live) | 14.24 ± 0.32 | 8.39 | 135 | 10.20 | 0.180 | 2 | 0.46 |
| drift | goal-TS (hier) / thompson (live) / T=0 (live) | 14.27 ± 0.34 | 8.57 | 135 | 10.16 | 0.189 | 4 | 0.45 |
| drift | random / thompson (live) / T=0 (live) | 14.33 ± 0.33 | 7.47 | 135 | 10.03 | 0.199 | 5 | 0.47 |

### E3 sampling temperature (ranked, thompson)

| scenario | policy (goal / arm / temperature) | kept (±95%) | kept @60 att. | attempts | kept/GPU-h | dup share | 1st keep (median att.) | top arm share |
|---|---|---|---|---|---|---|---|---|
| low | ranked (live) / thompson (live) / T=0 (live) | 6.61 ± 0.24 | 3.90 | 150 | 4.14 | 0.214 | 5 | 0.51 |
| low | ranked (live) / thompson (live) / T=0.7 always | 7.18 ± 0.24 | 3.75 | 151 | 4.50 | 0.000 | 5 | 0.51 |
| low | ranked (live) / thompson (live) / schedule 0 then 0.7 | 7.52 ± 0.24 | 3.95 | 150 | 4.74 | 0.000 | 5 | 0.52 |
| low | ranked (live) / thompson (live) / temp bandit {0,.4,.8} | 7.37 ± 0.23 | 3.92 | 150 | 4.68 | 0.034 | 5 | 0.51 |
| mid | ranked (live) / thompson (live) / T=0 (live) | 14.87 ± 0.32 | 9.09 | 134 | 10.49 | 0.181 | 2 | 0.46 |
| mid | ranked (live) / thompson (live) / T=0.7 always | 15.94 ± 0.33 | 8.84 | 134 | 11.10 | 0.000 | 2 | 0.46 |
| mid | ranked (live) / thompson (live) / schedule 0 then 0.7 | 16.15 ± 0.33 | 9.29 | 133 | 11.41 | 0.000 | 2 | 0.47 |
| mid | ranked (live) / thompson (live) / temp bandit {0,.4,.8} | 16.06 ± 0.32 | 9.11 | 134 | 11.32 | 0.026 | 2 | 0.46 |
| contextual | ranked (live) / thompson (live) / T=0 (live) | 15.30 ± 0.32 | 9.12 | 134 | 10.68 | 0.179 | 2 | 0.46 |
| contextual | ranked (live) / thompson (live) / T=0.7 always | 16.14 ± 0.33 | 8.87 | 134 | 11.08 | 0.000 | 3 | 0.47 |
| contextual | ranked (live) / thompson (live) / schedule 0 then 0.7 | 16.45 ± 0.33 | 9.43 | 133 | 11.53 | 0.000 | 2 | 0.48 |
| contextual | ranked (live) / thompson (live) / temp bandit {0,.4,.8} | 16.50 ± 0.34 | 9.34 | 133 | 11.47 | 0.028 | 2 | 0.48 |
| drift | ranked (live) / thompson (live) / T=0 (live) | 14.46 ± 0.32 | 9.09 | 135 | 10.24 | 0.179 | 2 | 0.45 |
| drift | ranked (live) / thompson (live) / T=0.7 always | 15.53 ± 0.32 | 8.84 | 135 | 10.78 | 0.000 | 2 | 0.46 |
| drift | ranked (live) / thompson (live) / schedule 0 then 0.7 | 15.70 ± 0.32 | 9.29 | 134 | 11.16 | 0.000 | 2 | 0.46 |
| drift | ranked (live) / thompson (live) / temp bandit {0,.4,.8} | 15.55 ± 0.31 | 9.11 | 134 | 10.95 | 0.024 | 2 | 0.45 |
| low_dup03 | ranked (live) / thompson (live) / T=0 (live) | 7.45 ± 0.25 | 3.98 | 150 | 4.74 | 0.082 | 5 | 0.51 |
| low_dup03 | ranked (live) / thompson (live) / T=0.7 always | 7.18 ± 0.24 | 3.75 | 151 | 4.50 | 0.000 | 5 | 0.51 |
| low_dup03 | ranked (live) / thompson (live) / schedule 0 then 0.7 | 7.52 ± 0.24 | 3.95 | 150 | 4.74 | 0.000 | 5 | 0.52 |
| low_dup03 | ranked (live) / thompson (live) / temp bandit {0,.4,.8} | 7.53 ± 0.24 | 3.92 | 150 | 4.79 | 0.012 | 5 | 0.51 |
| mid_dup03 | ranked (live) / thompson (live) / T=0 (live) | 15.91 ± 0.33 | 9.24 | 134 | 11.36 | 0.068 | 2 | 0.46 |
| mid_dup03 | ranked (live) / thompson (live) / T=0.7 always | 15.94 ± 0.33 | 8.84 | 134 | 11.10 | 0.000 | 2 | 0.46 |
| mid_dup03 | ranked (live) / thompson (live) / schedule 0 then 0.7 | 16.15 ± 0.33 | 9.29 | 133 | 11.41 | 0.000 | 2 | 0.47 |
| mid_dup03 | ranked (live) / thompson (live) / temp bandit {0,.4,.8} | 16.13 ± 0.32 | 9.11 | 134 | 11.40 | 0.011 | 2 | 0.46 |

### E4 combined

| scenario | policy (goal / arm / temperature) | kept (±95%) | kept @60 att. | attempts | kept/GPU-h | dup share | 1st keep (median att.) | top arm share |
|---|---|---|---|---|---|---|---|---|
| low | ranked (live) / thompson (live) / T=0 (live) | 6.61 ± 0.24 | 3.90 | 150 | 4.14 | 0.214 | 5 | 0.51 |
| low | goal-TS (hier) / thompson (live) / schedule 0 then 0.7 | 7.30 ± 0.25 | 3.45 | 150 | 4.59 | 0.000 | 9 | 0.51 |
| low | breadth-first / thompson (live) / schedule 0 then 0.7 | 7.46 ± 0.24 | 3.48 | 150 | 4.76 | 0.000 | 6 | 0.51 |
| low | goal-TS (hier) / hier TS (via|kind) / schedule 0 then 0.7 | 7.16 ± 0.25 | 3.56 | 150 | 4.69 | 0.000 | 9 | 0.35 |
| mid | ranked (live) / thompson (live) / T=0 (live) | 14.87 ± 0.32 | 9.09 | 134 | 10.49 | 0.181 | 2 | 0.46 |
| mid | goal-TS (hier) / thompson (live) / schedule 0 then 0.7 | 16.04 ± 0.33 | 8.74 | 134 | 11.37 | 0.000 | 4 | 0.48 |
| mid | breadth-first / thompson (live) / schedule 0 then 0.7 | 16.05 ± 0.32 | 8.49 | 134 | 11.56 | 0.000 | 2 | 0.47 |
| mid | goal-TS (hier) / hier TS (via|kind) / schedule 0 then 0.7 | 15.78 ± 0.32 | 8.63 | 134 | 11.38 | 0.000 | 4 | 0.37 |
| contextual | ranked (live) / thompson (live) / T=0 (live) | 15.30 ± 0.32 | 9.12 | 134 | 10.68 | 0.179 | 2 | 0.46 |
| contextual | goal-TS (hier) / thompson (live) / schedule 0 then 0.7 | 16.21 ± 0.34 | 8.69 | 133 | 11.30 | 0.000 | 4 | 0.48 |
| contextual | breadth-first / thompson (live) / schedule 0 then 0.7 | 16.36 ± 0.34 | 8.79 | 133 | 11.78 | 0.000 | 2 | 0.47 |
| contextual | goal-TS (hier) / hier TS (via|kind) / schedule 0 then 0.7 | 16.47 ± 0.34 | 8.91 | 133 | 12.04 | 0.000 | 4 | 0.38 |
| drift | ranked (live) / thompson (live) / T=0 (live) | 14.46 ± 0.32 | 9.09 | 135 | 10.24 | 0.179 | 2 | 0.45 |
| drift | goal-TS (hier) / thompson (live) / schedule 0 then 0.7 | 15.71 ± 0.33 | 8.74 | 134 | 11.21 | 0.000 | 4 | 0.47 |
| drift | breadth-first / thompson (live) / schedule 0 then 0.7 | 15.56 ± 0.31 | 8.49 | 134 | 11.25 | 0.000 | 2 | 0.46 |
| drift | goal-TS (hier) / hier TS (via|kind) / schedule 0 then 0.7 | 15.46 ± 0.32 | 8.63 | 135 | 11.17 | 0.000 | 4 | 0.37 |
| low_dup03 | ranked (live) / thompson (live) / T=0 (live) | 7.45 ± 0.25 | 3.98 | 150 | 4.74 | 0.082 | 5 | 0.51 |
| low_dup03 | goal-TS (hier) / thompson (live) / schedule 0 then 0.7 | 7.30 ± 0.25 | 3.45 | 150 | 4.59 | 0.000 | 9 | 0.51 |
| low_dup03 | breadth-first / thompson (live) / schedule 0 then 0.7 | 7.46 ± 0.24 | 3.48 | 150 | 4.76 | 0.000 | 6 | 0.51 |
| low_dup03 | goal-TS (hier) / hier TS (via|kind) / schedule 0 then 0.7 | 7.16 ± 0.25 | 3.56 | 150 | 4.69 | 0.000 | 9 | 0.35 |
| mid_dup03 | ranked (live) / thompson (live) / T=0 (live) | 15.91 ± 0.33 | 9.24 | 134 | 11.36 | 0.068 | 2 | 0.46 |
| mid_dup03 | goal-TS (hier) / thompson (live) / schedule 0 then 0.7 | 16.04 ± 0.33 | 8.74 | 134 | 11.37 | 0.000 | 4 | 0.48 |
| mid_dup03 | breadth-first / thompson (live) / schedule 0 then 0.7 | 16.05 ± 0.32 | 8.49 | 134 | 11.56 | 0.000 | 2 | 0.47 |
| mid_dup03 | goal-TS (hier) / hier TS (via|kind) / schedule 0 then 0.7 | 15.78 ± 0.32 | 8.63 | 134 | 11.38 | 0.000 | 4 | 0.37 |
