# SuperFly64: the `brain/` folder

A real fruit-fly mushroom-body connectome (FlyWire data, about 5,586 neurons) controls Mario in
sm64ex and learns Peach's Secret Slide through dopamine-style reward and punishment.
This folder holds the Python side: the brain, the program that connects it to the game,
the tools, and the results of every training run.

The game side lives in `../src/pc/controller/controller_fly.c` and `controller_fly.h`. The game and
the brain talk through 76 bytes of shared memory (`/dev/shm/mario_brain`), one handshake per
frame. Start the game first, then run the brain.

## Current best setup

| What | File |
|---|---|
| Brain code | `fly_brain.py` (situation-cell brain, `turn_effort` 1.5, death punishment 1.5, finish range 21–28 s) |
| Learned weights | `learned_best_v17.npz` (11 of the last 13 trials finished, 23.8–24.2 s) |
| Coin trail | `fly_trail.txt` / `fly_trail_best.txt` (centered line, `--spacing 480`) |
| Game setting | `controller_fly.c` look-ahead: `FLY_AIM_FRAMES 6`, `FLY_AIM_MAX 700` |

The full history of what we tried and why is in the "SuperFly64 Learning Notes" doc.

## Code

| File | What it does |
|---|---|
| `fly_brain.py` | **The brain.** Builds the network from `mushroom_body.graphml`. Kenyon cells sense coin direction, coin distance, speed, walls and "situations" (speed × turn sharpness). Approach and avoidance output neurons (MBONs) decide steering and push. Dopamine neurons give reward (PAM: coins, finishing) and punishment (PPL1: walls, getting stuck, missed coins, falling, dying). Learning changes Kenyon cell -> MBON connections (three-factor rule). Pure fly: no driving helpers. |
| `fly_brain_before_v15.py` | Backup of the brain before the v15 reward changes (death punishment 3.0, finish range 21–40 s). |
| `run_fly.py` | **Runs everything.** Connects to the game, feeds Mario's senses to the brain every frame, sends the stick back, runs trials (resets, deaths, finishes, missed coins) and saves weights and logs. Main options: `--load`, `--save`, `--trials`, `--trial-seconds`, `--log`, `--trace`, `--frozen`, `--autosave`. |
| `record_trail.py` | You drive Mario down the slide in slow motion (`--slow 4`), and it drops a trail point every `--spacing` units into `fly_trail.txt`. The game turns those points into coins, numbered in order. |
| `analyze_corner.py` | Compares runs that died at the big corner with runs that finished: speed, facing, push, turn and side-to-side position 3, 2, 1 and 0.5 s before the corner. Draws `corner_paths.png`. Usage: `python3 analyze_corner.py <log.csv> <trace.csv>` |
| `fly_data_parser.py` | Builds `mushroom_body.graphml` from the FlyWire CSV files: keeps the KC, MBON, PAM and PPL neurons and the connections between them. Only needs to run once. |
| `test_steering.py` | Checks the brain's steering without the game: shows it a coin at fixed angles and prints which way it would go. Learning is off, so saved weights never change. |
| `test_fly_bridge.py` | An early test of the game - Python handshake. **Outdated:** it uses the old 68-byte layout and doesn't match the current game. |
| `inspect_learning.py` | Prints statistics about a weights file (expects `learned.npz`; edit the name to inspect another). |

## Connectome data

| File | What it is |
|---|---|
| `neurons.csv`, `consolidated_cell_types.csv`, `connections_princeton.csv` | Raw FlyWire downloads: neurons, cell types, synaptic connections. Inputs to `fly_data_parser.py`. |
| `mushroom_body.graphml` | The mushroom-body network the brain is built from (output of `fly_data_parser.py`). |

## Coin trails

| File | What it is |
|---|---|
| `fly_trail.txt` | The trail the game uses now (it's read when the level loads). First line `level 27`, then one `x y z` point per line. |
| `fly_trail_best.txt` | Backup of the current best trail (centered line). |
| `fly_trail_old.txt` | The previous trail (before the centered re-record). |

## Learned weights (`.npz`)

Every `.npz` is a saved brain: the learned connection strengths. Load one with `--load`.

| File | What it is |
|---|---|
| **`learned_best_v17.npz`** | **Current best**: look-ahead + centered trail (same as `trail_v17.npz`). |
| `learned_best_lookahead.npz` | Best with look-ahead on the old trail (same as `lookahead_v16b.npz`, 10 of 20 finished, 23.5–23.9 s). |
| `learned_best_67pct.npz` | Backup of `learned_v13.npz` (6 of 9 finished; its real rate turned out to be about 40%). The starting brain for all the corner tests. |
| `trail_v17.npz` | Saved from the `corner3` test (centered trail). |
| `lookahead_v16b.npz` | Saved from the `corner2b` test (look-ahead 0.2 s). |
| `lookahead_v16.npz` | Saved from the `corner2` test (look-ahead 0.5 s, 0 of 17). Don't use. |
| `corner_scratch.npz` | Saved from the first corner test. Throwaway. |
| `learned_v15.npz` | v15 run (818 trials, about 38% finished). |
| `learned_v14.npz` | v14 run (slump, stopped early). |
| `learned_v13.npz` | First run with `turn_effort` (6 of 9 finished). |
| `learned_v9.npz` – `learned_v11.npz` | Situation-cell brain, early runs (v10 had 1,500+ trials). |
| `learned_v4.npz` – `learned_v7.npz` | Original brain (before situation cells). v6 is the ~20% result kept for the presentation. |
| `speed_test.npz` | From an early speed test. |

## Logs (`.csv`)

**Learning logs** (`learning_vN.csv`, one row per trial). Columns: `mode, trial, seconds, frames, coins,
min_wedges, wall_frames, max_stuck_frames, left_course (died), finished, finish_seconds, missed`.

| File | What it is |
|---|---|
| `learning_v4.csv` – `learning_v8.csv` | Original brain runs (v6: about 20% over 500 trials). |
| `learning_v9.csv` – `learning_v11.csv` | Situation-cell brain, early runs. |
| `learning_v13.csv` | `turn_effort` added: 6 of 9 finished. |
| `learning_v14.csv` | Continued from v13: good start, then a slump. |
| `learning_v15.csv` | Death punishment 1.5 and finish range 21–28 s: 818 trials, about 38%. Contains 6 "ghost finish" rows (0.5 s), a bug fixed afterwards. |
| `frozen.csv`, `frozen_v6.csv`, `frozen_v7.csv`, `frozen_v12.csv` | Runs with learning switched off (`--frozen`). Note: the same brain plays out the same run every time, so a frozen run mostly repeats one trial. |
| `speed_test.csv` | Early speed test. |

**Corner tests** (each one has a log plus a per-frame trace from `--trace`; the trace has position, facing, speed, stick, jump, falling, coins, coin angle and distance, and walls for every frame).

| Files | Test | Result |
|---|---|---|
| `corner.csv`, `corner_trace.csv` | Old aiming (next coin), old trail | 11 of 40. Found the overcorrection wobble before the corner. |
| `corner2.csv`, `corner2_trace.csv` | Look-ahead 0.5 s | 0 of 17: aimed too far ahead. |
| `corner2b.csv`, `corner2b_trace.csv` | Look-ahead 0.2 s | 10 of 20, 23.5–23.9 s. |
| `corner3.csv`, `corner3_trace.csv` | Look-ahead 0.2 s + centered trail | 12 of 20 (11 of the last 13), 23.8–24.2 s. |
| `corner_paths.png` | Top-down picture from `analyze_corner.py` (from the last analysis run). Note: drawn with z pointing up, so it's a mirror image of the game. |

## Typical commands

```
# train (continue from the best brain)
python3 run_fly.py --trial-seconds 120 --trials 200 --log learning_v18.csv --load learned_best_v17.npz --save learned_v18.npz

# record a new coin trail (back up fly_trail.txt first)
python3 record_trail.py --slow 4 --spacing 480

# corner test with per-frame trace, then analyze it
python3 run_fly.py --trial-seconds 120 --trials 20 --log corner4.csv --trace corner4_trace.csv --load learned_best_v17.npz --save corner4.npz
python3 analyze_corner.py corner4.csv corner4_trace.csv

# to just see test brain as a demo but not do any learning
python3 run_fly.py --frozen --load learned_best_v17.npz --trial-seconds 120 --trials 20
```