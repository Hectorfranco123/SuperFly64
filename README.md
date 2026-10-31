# SuperFly64
To download, modify, and mod the [Super Mario 64](https://www.google.com/search?q=super+mario+64&kgmid=/m/0phl8) source code natively on Linux, you will use the community's PC Decompilation project (specifically the enhanced fork, [sm64ex GitHub](https://github.com/sm64pc/sm64ex), or the multiplayer branch [sm64coopdx GitHub](https://github.com/coop-deluxe/sm64coopdx/wiki/Compiling-%28Linux%29)). Because copyright law protects the game's actual art and sound assets, the source code repository is fully legal but text-only. You must supply your own original N64 ROM file to legally extract those assets during compilation. [1, 2, 3, 4, 5] 
## Step 1: Install Build Dependencies
Open your terminal and install the compiler, tools, and graphics libraries required to build the game engine from scratch:

* Ubuntu / Debian / Linux Mint:

sudo apt update
sudo apt install build-essential git python3 libglew-dev libsdl2-dev

* Arch Linux / Steam Deck (Desktop Mode):

sudo pacman -S base-devel python sdl2 glew git

* Fedora:

sudo dnf install make gcc python3 glew-devel SDL2-devel git


## Step 2: Clone the Source Code Repository
Clone the repository using Git. The sm64ex repository is highly recommended for modding as it features toggles for built-in mods (like widescreen and a modern analog camera). [6, 7] 

git clone https://github.com/sm64pc/sm64ex.git
cd sm64ex

## Step 3: Add Your Base ROM

   1. Obtain a legally dumped copy of the Super Mario 64 US N64 ROM (must be .z64 format).
   2. Rename the file to baserom.us.z64.
   3. Move or copy this file directly into the root folder of your cloned sm64ex directory. [2, 7, 8] 

## Step 4: Compile the Game
Compile the game using the make utility. You can pass parameters to bake options directly into your custom build: [9, 10] 

make BETTERCAMERA=1 EXTERNAL_DATA=1 TEXTURE_FIX=1 -j$(nproc)


* BETTERCAMERA=1: Enables a modern, non-clunky 3D camera.
* EXTERNAL_DATA=1: Allows you to drop custom HD texture packs into a user folder later.
* -j$(nproc): Forces Linux to use all your available CPU cores to speed up the compilation process. [7, 9] 

IMPORTANT: every time you rebuild, use the SAME options as above. Running plain "make" without them can build a different version of the game.

Once compilation finishes, your native executable will be waiting for you. Run it with: [1] 

./build/us_pc/sm64.us.f3dex2e

------------------------------
## 🛠️ How to Mess with the Source Code & Mod It
Because you compiled the game natively, you can alter the code directly using a code editor like VS Code or Vim: [2, 11] 

* Change Mario's Physics & Movement: Start in src/game/mario.c (jump heights are set there when Mario enters a jump). Most movement code is split across the src/game/mario_actions_*.c files: mario_actions_moving.c (running/walking speed), mario_actions_airborne.c (jumps, falling, gravity), mario_actions_submerged.c (swimming).
* Modify Text & Dialogues: Navigate to text/us/dialogs.h to change what Bowser, Toad, or Bob-omb Buddies say when you interact with them.
* Alter Level Geometry & Triggers: Level scripts and layouts are stored in the levels/ directory. Look through individual subfolders (like levels/bob/ for Bob-omb Battlefield) to change object placements or coin locations.
* HUD (coins, stars, lives, power meter): src/game/hud.c. Text printing: src/game/print.c.
* Controller input (keyboard, gamepad, and now the fly): src/pc/controller/
* Adding Existing Mods: If you don't want to code from scratch, you can download community patches (.patch files) and apply them locally in your terminal before compiling via:

git apply name_of_patch.patch


Whenever you modify any .c or .h source file, simply open your terminal in the main folder and run the make command again (with the same options!). The compiler will rebuild only the files you changed, updating your game in seconds. [10] 
If you ADD a brand new .c file, you also have to run make again, or the game won't include it.


==============================
## 🪰 FLY BRAIN PROJECT (SuperFly64)
==============================

GOAL: A real fruit fly (*Drosophila melanogaster*) brain wiring map extracted from the **FlyWire FAFB (Full Adult Fly Brain)** connectome dataset controls Mario. Specifically, we extract and simulate 5,586 Mushroom Body neurons (Kenyon Cells, Mushroom Body Output Neurons, and PAM/PPL1 dopaminergic clusters) using Leaky Integrate-and-Fire (LIF) dynamics and neurotransmitter valence constraints (Dale's Principle). In Stages 3–4, the fly LEARNS from rewards (coins -> PAM dopamine cluster) and punishments (damage/wall hazards -> PPL1 dopamine cluster) via three-factor synaptic plasticity.

How it works:
  Game (C) --writes Mario's position, facing, speed, nearest coin vector, coins, health, wall contact--> shared memory (/dev/shm/mario_brain)
  Python fly brain --encodes sensory KCs, steps recurrent sparse matrix, decodes MBON motor outputs--> shared memory --> Game
  The game and the brain take turns every frame ("lockstep"), 30 times a second.

## Progress
[x] Stage 1: bridge between game and Python works (tested: Mario steers toward coins + jumps)
[x] Input display overlay in-game (stick box + button lights)
[x] Stage 2: real FlyWire Mushroom Body connectome (5,586 neurons) drives Mario via LIF dynamics and population motor decoding
[ ] Stage 3: rewards: coins -> PAM dopamine neurons (reward), damage/wall stalls -> PPL1 dopamine neurons (punishment)
[ ] Stage 4: three-factor eligibility trace learning in the mushroom body + save learned weights to a file
[ ] Stage 5: test it: learning fly vs frozen fly, same save state, chart the results
[ ] Extra: Python dashboard showing what the fly is "thinking" (pyqtgraph or Dear PyGui)

## Files changed / added
C Engine & Bridge (every line marked `// hector added` or `// hector changed`):
* src/game/hud.c                              -> input display overlay (render_hud_fly_inputs), called at end of render_hud
* src/pc/controller/controller_fly.c          -> NEW: the fly controller backend & nearest-coin sensor
* src/pc/controller/controller_fly.h          -> NEW: 68-byte shared memory layout (BrainLink)
* src/pc/controller/controller_entry_point.c  -> 2 lines: include + &controller_fly (must stay LAST in the list)
* brain/test_fly_bridge.py                    -> NEW: shared-memory bridge script

Connectome Parser & Neural Simulation:
* brain/fly_data_parser.py                    -> NEW: filters FlyWire CSVs (`consolidated_cell_types.csv`, `neurons.csv`, `connections_princeton.csv`) for Mushroom Body neurons (`KC`, `MBON`, `PAM`, `PPL`) and exports `mushroom_body.graphml`
* brain/fly_brain.py                          -> NEW: `fly_brain` class implementing GraphML loading, Dale's Principle sparse matrix construction, Gaussian/exponential KC sensory encoding, LIF dynamics, and bilateral MBON motor decoding

Search the project for "hector" to find every C/bridge change:
grep -rn "hector" src/ brain/

## How to run it
1. Build:   make BETTERCAMERA=1 EXTERNAL_DATA=1 TEXTURE_FIX=1 NODRAWINGDISTANCE=1 -j$(nproc)
2. Start the game FIRST:   ./build/us_pc/sm64.us.f3dex2e   (it creates the shared memory)
3. Load into a level.
4. In a second terminal:
   cd ~/Desktop/sm64mod/sm64ex/brain
   source .venv/bin/activate
   python3 test_fly_bridge.py
5. Ctrl+C stops the script and Mario goes back to your control.

Rules of the bridge:
* If Python isn't running, the game plays normally (no freezing).
* If Python crashes mid-game, expect one ~1.5 second stutter, then the game carries on.
* Fly buttons ADD to yours. The fly's stick only works while you're NOT touching yours (you can always take over).

## Shared memory layout (68 bytes) - C and Python MUST match
Python struct format: `"<II3fff3fffhhBBxxffBxxx"`
offset 0   game_frame      (uint32)    game bumps this each frame after writing telemetry
offset 4   brain_frame     (uint32)    Python sets = game_frame when its answer is ready (write this LAST)
offset 8   pos x,y,z       (3 floats)  Mario's position
offset 20  face_yaw        (float)     Mario's facing angle in radians
offset 24  fwd_vel         (float)     Mario's forward speed
offset 28  coin_pos x,y,z  (3 floats)  nearest coin position
offset 40  angle_to_coin   (float)     radians (-pi to pi) relative to Mario's heading (0 = ahead, + = left, - = right)
offset 44  dist_to_coin    (float)     3D distance to nearest coin (-1 if no coin found)
offset 48  coins           (int16)     coins collected
offset 50  wedges          (int16)     health as power meter wedges (0 to 8, 8 = full)
offset 52  wall_collision  (uint8)     1 if Mario is touching a wall, else 0
offset 53  coin_found      (uint8)     1 if a coin was found, 0 if none (coin fields invalid)
offset 54  _pad1           (2 bytes)   padding
offset 56  stick_x         (float)     -1.0 to 1.0, Mario-relative (+1.0 = right, -1.0 = left)
offset 60  stick_y         (float)     -1.0 to 1.0, Mario-relative (+1.0 = forward)
offset 64  button_a        (uint8)     1 = hold A (jump), 0 = release (must return to 0 for >=1 frame to jump again)
offset 65  _pad2           (3 bytes)   padding
If you ever change the layout: change controller_fly.h AND the Python format string together. (The C side refuses to compile if the size isn't 68, as a reminder.)

## Lessons learned / gotchas
* FileNotFoundError: /dev/shm/mario_brain  -> I forgot to run make, OR the game isn't running yet. Check with:  ls -l /dev/shm/
* Check the fly code got compiled:  find build -name "controller_fly.o"
* The US HUD font has NO letter Z (and a few others are missing). Missing letters show up as the previous letter (that's why it said "ABB"). Z button is labeled T (trigger).
* print_text Y is measured from the BOTTOM of the screen. Rectangles/textures measure Y from the TOP.
* The HUD font prints minus signs as "M" (so -45 shows "M45"). The overlay uses L/R and U/D instead.
* Overlay hides during cutscenes/menus along with the rest of the HUD.
* If the build ever says "undefined reference to shm_open": add -lrt to the linker flags in the Makefile.

## Git / GitHub rules
NEVER commit: baserom.us.z64 (the ROM), build/ (has extracted game assets), brain/.venv/, brain/data/ (connectome files are gigabytes)
Do commit: my changed/new source files, brain/ scripts, a README
Check before pushing:  git status
Commit after every stage that works, so I can roll back.

## Connectome Pipeline & Architecture (Stage 2–4)
1. In `brain/.venv`: `pip install numpy scipy networkx pandas`
2. Place the FlyWire FAFB CSV files (`consolidated_cell_types.csv`, `neurons.csv`, `connections_princeton.csv`) in the working directory and run `python3 fly_data_parser.py` to generate `mushroom_body.graphml` (5,586 nodes).
3. Neuron compartments modeled in `fly_brain.py`:
   - **Inputs (`kc_idx`):** Kenyon Cells partitioned into 50% Gaussian directional compass tuners (`left_tuners` / `right_tuners`), 25% exponential coin proximity tuners, 15% normalized velocity feedback cells, and 10% wall-collision hazard cells (with 95th-percentile APL-inspired sparsity).
   - **Outputs (`mbon_idx`):** Mushroom Body Output Neurons split by neurotransmitter valence into Cholinergic approach pools (`approach_mbon` -> forward thrust `stick_y`) and GABA/Glutamatergic avoidance pools (`avoidance_mbon` -> braking and latched `button_a` jump reflex).
   - **Modulators (`pam_idx` / `ppl_idx`):** Appetitive (PAM) and aversive (PPL1) dopaminergic clusters triggered by coin collection and health loss/wall stalls to drive synaptic plasticity.

Reminders: an untrained connectome doesn't "know" how to play. It does fly reflexes (turning, darting, escape jumps). The learning comes in Stages 3-5.

------------------------------

[1] [https://linuxconfig.org](https://linuxconfig.org/how-to-build-super-mario-64-natively-on-linux)
[2] [https://forum.hyperion-entertainment.com](https://forum.hyperion-entertainment.com/viewtopic.php?t=4631)
[3] [https://forum.hyperion-entertainment.com](https://forum.hyperion-entertainment.com/viewtopic.php?t=4630)
[4] [https://github.com](https://github.com/coop-deluxe/sm64coopdx/wiki/Compiling-%28Linux%29)
[5] [https://github.com](https://github.com/Erotemic/sm64-port/blob/master/README.md)
[6] [https://www.reddit.com](https://www.reddit.com/r/SteamDeck/comments/wfbgnf/the_linux_port_of_super_mario_64_runs_fantastic/)
[7] [https://gist.github.com](https://gist.github.com/Lucas-mother3/c6d47973e92333bed1ca9fe559791b3e)
[8] [https://github.com](https://github.com/Francesco149/sm64pc_instructions)
[9] [https://github.com](https://github.com/sm64pc/sm64ex/wiki/Compiling-on-Linux)
[10] [https://github.com](https://github.com/sm64-port/sm64-port)
[11] [https://mario64hacks.fandom.com](https://mario64hacks.fandom.com/wiki/Hacking_Resources/Tutorials)



rm ~/.local/share/sm64ex/sm64config.txt // run this to clear saved config


## Citation & Attribution

This project is open for personal, educational, and academic research use. However, **attribution is strictly required** for any derivative work, academic publication, presentation, or public media (including YouTube videos, livestreams, and articles) that utilizes this codebase, graph extraction pipeline, or simulation harness.

### Media, Videos & Presentations
If you feature this project in a video, stream, or article, you must include:
1. Visible and verbal credit to the authors (**Rommel Sanchez Perez** and **Hector Franco**).
2. A direct link to this repository in the video description or article text: `https://github.com/Nietch2/SuperFly64`

### Academic Publications
If you use **Mario Fly Brain** in academic research or coursework, please cite this repository using the GitHub **"Cite this repository"** button in the sidebar (powered by [`CITATION.cff`](CITATION.cff)) or via the following BibTeX entry:

```bibtex
@software{sanchez_perez_mario_fly_brain_2026,
  author       = {Sanchez Perez, Rommel and Franco, Hector},
  title        = {{Mario Fly Brain: Biologically Constrained Drosophila Connectome Reinforcement Learning in Super Mario 64}},
  year         = {2026},
  month        = oct,
  institution  = {Elizabethtown College},
  url          = {[https://github.com/Nietch2/SuperFly64](https://github.com/Nietch2/SuperFly64)},
  version      = {0.1.0}
}
