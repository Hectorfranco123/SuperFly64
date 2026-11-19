# SuperFly64

A real fruit fly (*Drosophila melanogaster*) brain wiring map, the mushroom body from the FlyWire FAFB
connectome (5,586 neurons), controls Mario in Super Mario 64 (sm64ex) and learns Peach's Secret Slide
through dopamine-style reward and punishment. No driving helpers: the fly's neurons do all the steering.

**Current result:** in the latest 20-trial test the fly finished the slide in 11 of the last 13 trials
(8 in a row), with finish times of 23.8–24.2 s. The star time is under 21 s. The first learning brain
plateaued at about 20% finishes and about 32.5 s.

**Target users:** Computational neuroscience students, bio-inspired AI/reinforcement learning researchers, and `sm64ex` modding developers exploring real-time neural-to-game-engine bridges.

---

## Part 1: Building the game (sm64ex on Linux)

To download, modify, and mod the Super Mario 64 source code natively on Linux, use the community's PC
decompilation project (the enhanced fork sm64ex on GitHub). Because copyright law protects the game's
art and sound assets, the source code repository is legal but text-only. You must supply your own
original N64 ROM to extract those assets during compilation.

### Step 1: Install build dependencies

Ubuntu / Debian / Linux Mint:
```
sudo apt update
sudo apt install build-essential git python3 libglew-dev libsdl2-dev
```
Arch Linux / Steam Deck (Desktop Mode):
```
sudo pacman -S base-devel python sdl2 glew git
```
Fedora:
```
sudo dnf install make gcc python3 glew-devel SDL2-devel git
```

### Step 2: Clone the source code
```
git clone https://github.com/sm64pc/sm64ex.git
cd sm64ex
```

### Step 3: Add your base ROM
Get a legally dumped Super Mario 64 US N64 ROM (`.z64` format), rename it `baserom.us.z64`, and put it in
the root of the `sm64ex` folder.

### Step 4: Compile
```
make BETTERCAMERA=1 EXTERNAL_DATA=1 TEXTURE_FIX=1 NODRAWINGDISTANCE=1 -j$(nproc)
```
- `BETTERCAMERA=1`: modern 3D camera.
- `EXTERNAL_DATA=1`: lets you add texture packs later.
- `TEXTURE_FIX=1`: fixes some texture glitches.
- `NODRAWINGDISTANCE=1`: draws objects (like the trail coins) at any distance instead of hiding far ones.
- `-j$(nproc)`: uses all CPU cores.

**Every time you rebuild, use the SAME options.** Plain `make` can build a different version of the game.

Run the game:
```
./build/us_pc/sm64.us.f3dex2e
```

### Where things are in the source
- Mario's physics and movement: `src/game/mario.c` and `src/game/mario_actions_*.c` (sliding is in `mario_actions_moving.c`)
- Text and dialog: `text/us/dialogs.h`
- Levels and objects: `levels/`
- HUD: `src/game/hud.c`. Text printing: `src/game/print.c`
- Controller input (keyboard, gamepad, and the fly): `src/pc/controller/`

After changing any `.c` or `.h` file, run the same `make` command again. Only the changed files are rebuilt.

---

## Part 2: The fly brain

### How it works

```
Game (C)  --Mario's position, facing, speed, target coin, coins, health, walls, falling-->  shared memory
Python fly brain  --senses -> Kenyon cells -> output neurons (MBONs) -> stick + jump-->  shared memory  --> Game
```

The game and the brain take turns every frame ("lockstep"), 30 times a second, through 76 bytes of
shared memory at `/dev/shm/mario_brain`. Start the game first: it creates the shared memory.

**The brain** (`brain/fly_brain.py`), built from the real FlyWire wiring (`mushroom_body.graphml`):
- **Kenyon cells (inputs):** direction to the target coin (Gaussian compass cells), coin distance, speed,
  wall contact, and **situation cells** (40% of KCs) that each fire for one combination of speed and
  turn sharpness, so the fly can learn "slow down here" rather than one overall speed. Sparse coding
  (APL-style inhibition) keeps only a few cells active.
- **Dynamics:** leaky integrate-and-fire style rate updates through the connectome's sparse weight matrix,
  with Dale's principle (each neuron's neurotransmitter decides if it excites or inhibits).
- **Output neurons (MBONs):** cholinergic approach neurons drive push; GABA/glutamatergic avoidance
  neurons brake and jump. Steering is a population vote of the direction cells.
- **Dopamine neurons:** PAM (reward) for coins and finishing the slide (bigger reward for faster finishes);
  PPL1 (punishment) for hitting walls, getting stuck, missing a trail coin, falling off and dying.
- **Learning:** three-factor plasticity on Kenyon cell → MBON connections (cell active + output active +
  dopamine), relative to each synapse's original strength, with slow recovery.
- **Pure fly:** the driving helpers (speed limiter, minimum push, stuck jump) are off.

**The game side** (`src/pc/controller/controller_fly.c`):
- Senses Mario's state and writes it every frame; applies the fly's stick and jump.
- Places a **coin trail** from `brain/fly_trail.txt` (recorded by a human with `record_trail.py`). Trail coins
  are numbered, so the fly follows them in order.
- **Look-ahead:** the fly's direction sense points about 0.2 s (up to 700 units) further along the trail
  instead of at the very next coin, like looking down the road. This stopped the overcorrection that
  killed him at the big corner.
- Detects falling off, the finish line (slide timer), stuck frames and missed trail coins, and resets the course.

### Progress
- [x] Stage 1: bridge between game and Python
- [x] In-game input display overlay (stick box + button lights)
- [x] Stage 2: real FlyWire mushroom body connectome (5,586 neurons) drives Mario
- [x] Stage 3: rewards and punishments through PAM and PPL1 dopamine neurons
- [x] Stage 4: three-factor learning + saving learned weights
- [x] Stage 5: learning runs and analysis (finish rate, finish time, corner analysis)
- [ ] Reach star time (under 21 s)
- [ ] Extra: dashboard of what the fly is "thinking"

### Files changed / added

C (every line marked `// hector added` or `// hector changed`):

| File | Change |
|---|---|
| `src/pc/controller/controller_fly.c` | NEW: the fly controller, sensing, coin trail, look-ahead, resets, finish/fall/miss detection |
| `src/pc/controller/controller_fly.h` | NEW: the 76-byte shared memory layout (`BrainLink`) |
| `src/pc/controller/controller_entry_point.c` | 2 lines: include + `&controller_fly` (must stay LAST in the list) |
| `src/game/level_update.c` | 2 lines: include + `fly_spawn_training_coins();` at the end of `init_level()` |
| `src/game/hud.c` | Input display overlay (`render_hud_fly_inputs`), called at the end of `render_hud` |

Python (`brain/`): see **`brain/README.md`** for every file, the saved brains and the logs. The main ones:

| File | What it does |
|---|---|
| `fly_data_parser.py` | Builds `mushroom_body.graphml` from the FlyWire CSVs |
| `fly_brain.py` | The brain |
| `run_fly.py` | Connects the brain to the game, runs trials, logs results, saves weights |
| `record_trail.py` | Record a coin trail by driving the slide in slow motion |
| `analyze_corner.py` | Compares deaths vs finishes at the big corner |
| `test_steering.py` | Checks the brain's steering without the game |

Find every change: `grep -rn "hector" src/ brain/`

### How to run it

1. Build (Part 1, Step 4) and start the game first:
   ```
   ./build/us_pc/sm64.us.f3dex2e
   ```
   The terminal should print `[fly] shared memory ready ... (76 bytes)`.
2. Go into Peach's Secret Slide.
3. In a second terminal:
   ```
   cd ~/Desktop/sm64mod/sm64ex/brain
   source .venv/bin/activate
   python3 run_fly.py --trial-seconds 120 --trials 20 --log demo.csv --load learned_best_v17.npz --save demo.npz
   ```
   Each trial restarts the slide. The terminal shows each trial's coins, time and whether he finished.
   Ctrl+C stops it, saves the weights, and gives Mario back to you.

Python setup (once): `pip install numpy scipy networkx pandas matplotlib` inside `brain/.venv`.

Rules of the bridge:
- If Python isn't running, the game plays normally (no freezing).
- If Python crashes mid-game, expect one short stutter, then the game carries on.
- The fly's stick only works while you're not touching yours (you can always take over).

### Shared memory layout (76 bytes): C and Python must match

Python struct format: `"<II3fff3fffhhBBBBffBBBBBBHB3x"`

| Offset | Field | Type | Written by | Meaning |
|---|---|---|---|---|
| 0 | game_frame | uint32 | game | bumped each frame after writing everything else |
| 4 | brain_frame | uint32 | Python | set = game_frame when the answer is ready (write LAST) |
| 8 | pos | 3 floats | game | Mario's position x, y, z |
| 20 | face_yaw | float | game | facing angle, radians |
| 24 | fwd_vel | float | game | forward speed |
| 28 | coin_pos | 3 floats | game | target position (with a trail: the look-ahead aim spot) |
| 40 | angle_to_coin | float | game | target direction vs Mario's heading (0 = ahead, + = left, − = right) |
| 44 | dist_to_coin | float | game | distance to the next coin (−1 if none) |
| 48 | coins | int16 | game | coins collected |
| 50 | wedges | int16 | game | health, 0–8 |
| 52 | wall_collision | uint8 | game | 1 = touching a wall |
| 53 | coin_found | uint8 | game | 1 = a target exists |
| 54 | airborne | uint8 | game | 0 ground, 1 air, 2 falling off (death floor below) |
| 55 | stuck_frames | uint8 | game | frames pushing without moving |
| 56 | stick_x | float | Python | −1..1, Mario-relative (+ = right) |
| 60 | stick_y | float | Python | −1..1, Mario-relative (+ = forward) |
| 64 | button_a | uint8 | Python | 1 = hold A (jump) |
| 65 | reset_request | uint8 | Python | 1 = restart the course (the game clears it) |
| 66 | reset_count | uint8 | game | +1 each reset |
| 67 | level_num | uint8 | game | current level |
| 68 | slow_motion | uint8 | Python | 2–4 = slow motion (for recording trails) |
| 69 | training_level | uint8 | game | course the fly trains in (0 = none) |
| 70 | finish_frames | uint16 | game | slide time at the finish line, in frames (0 = not yet) |
| 72 | trail_missed | uint8 | game | trail coins passed without collecting (wraps at 255) |
| 73 | (padding) | 3 bytes | | |

If you change the layout, change `controller_fly.h` AND the Python side together. The C side refuses
to compile if the size isn't 76, as a reminder.

### Lessons learned / gotchas
- `mmap length is greater than file size`: the game wasn't rebuilt or restarted after a layout change. Check with `ls -l /dev/shm/mario_brain` (should be 76).
- `FileNotFoundError: /dev/shm/mario_brain`: the game isn't running yet, or the fly code wasn't compiled (`find build -name "controller_fly.o"`).
- `No module named 'scipy'`: the virtual environment isn't active (`source .venv/bin/activate`).
- SM64's own `atan2f` takes its arguments swapped. The fly code uses its own `fly_atan2`.
- On the slide, turning strength goes with push squared, so a soft push barely turns.
- The same brain plays out the exact same run every time, so frozen (no learning) tests repeat one trial.
- The trail file is only read when the level loads: re-enter the slide after recording a new trail.
- The US HUD font has no letter Z, prints minus signs as "M", and `print_text` measures Y from the bottom.
- `undefined reference to shm_open`: add `-lrt` to the linker flags in the Makefile.
- Clear the saved game config: `rm ~/.local/share/sm64ex/sm64config.txt`

### Git / GitHub rules
NEVER commit: `baserom.us.z64` (the ROM), `build/` (extracted game assets), `brain/.venv/`, the connectome
CSVs (gigabytes). Do commit: changed/new source files, `brain/` scripts, READMEs. Check `git status`
before pushing.

---

## Citation & Attribution
This project is open for personal, educational, and academic research use. However, attribution is
strictly required for any derivative work, academic publication, presentation, or public media
(including YouTube videos, livestreams, and articles) that utilizes this codebase, graph extraction
pipeline, or simulation harness.

### Media, Videos & Presentations
If you feature this project in a video, stream, or article, you must include:
- Visible and verbal credit to the authors (Rommel Sanchez Perez and Hector Franco).
- A direct link to this repository in the video description or article text: https://github.com/Hectorfranco123/SuperFly64

### Academic Publications
If you use Mario Fly Brain in academic research or coursework, please cite this repository using the
GitHub "Cite this repository" button in the sidebar (powered by CITATION.cff) or via the following BibTeX entry:

```
@software{sanchez_perez_mario_fly_brain_2026,
  author       = {Sanchez Perez, Rommel and Franco, Hector},
  title        = {{Mario Fly Brain: Biologically Constrained Drosophila Connectome Reinforcement Learning in Super Mario 64}},
  year         = {2026},
  month        = oct,
  institution  = {Elizabethtown College},
  url          = {https://github.com/Hectorfranco123/SuperFly64},
  version      = {0.1.0}
}
```

### Upstream Dataset Attribution
This project processes connectomic data from the FlyWire FAFB (Full Adult Fly Brain) dataset. Any work
utilizing the extracted subgraphs must also credit the upstream dataset in accordance with FlyWire's
attribution guidelines (Dorkenwald et al., Nature, 2024).
