# path sm64ex/brain/record_trail.py # hector added
""" # hector added
Records a "breadcrumb trail" of coins by watching YOU play. # hector added
# hector added
You drive Mario down the course (for example Peach's Secret Slide) with your own controller # hector added
or keyboard. This script drops a point every --spacing units along Mario's path and saves them to # hector added
brain/fly_trail.txt. From then on, every time that level loads (including fly resets), the game # hector added
places a coin at each point, so the fly can follow the coins along the track. # hector added
# hector added
How to use: # hector added
  1. Start the game and enter the course (e.g. Peach's Secret Slide). # hector added
  2. From sm64ex/brain:   python3 record_trail.py # hector added
     It restarts the course so the trail starts exactly where Mario enters, and runs the game in # hector added
     slow motion (half speed by default) so you can steer. --slow 3 or --slow 4 is even slower, # hector added
     --slow 1 is normal speed. The sound stutters in slow motion; that's expected. # hector added
  3. Drive Mario to the end of the course yourself. # hector added
  4. Press Ctrl+C to save. Then re-enter the course (or let run_fly.py reset it) to see the coins. # hector added
# hector added
Only one trail is kept: recording a new one replaces the old file. # hector added
Messed up the run (fell off, went the wrong way)? Just press Ctrl+C and record again. # hector added
""" # hector added
# hector added
import argparse # hector added
import math # hector added
import mmap # hector added
import os # hector added
import struct # hector added
import time # hector added
# hector added
SHM_PATH = "/dev/shm/mario_brain" # hector added
SHM_SIZE = 72 # hector added
POS_OFFSET = 8                 # x, y, z floats # hector added
OUTPUT_OFFSET = 56             # stick_x, stick_y, button_a ("<ffB") # hector added
RESET_REQUEST_OFFSET = 65 # hector added
RESET_COUNT_OFFSET = 66 # hector added
LEVEL_NUM_OFFSET = 67 # hector added
SLOW_MOTION_OFFSET = 68         # 2 = half speed ... 4 = quarter speed # hector added
TRAIL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fly_trail.txt") # hector added
# hector added
# hector added
def main(): # hector added
    p = argparse.ArgumentParser(description="Record a coin trail by driving Mario yourself.") # hector added
    p.add_argument("--spacing", type=float, default=250.0, help="distance between trail coins") # hector added
    p.add_argument("--no-reset", action="store_true", help="start recording right where Mario is") # hector added
    p.add_argument("--slow", type=int, default=2, choices=[1, 2, 3, 4], # hector added
                   help="slow motion while recording: 2 = half speed (default), 4 = quarter speed, 1 = off") # hector added
    args = p.parse_args() # hector added
# hector added
    fd = os.open(SHM_PATH, os.O_RDWR) # hector added
    try: # hector added
        shm = mmap.mmap(fd, SHM_SIZE) # hector added
    except ValueError: # hector added
        print("The game's shared memory is the old, smaller size. Rebuild the game with make, restart it,") # hector added
        print("and run this again.") # hector added
        os.close(fd) # hector added
        return # hector added
# hector added
    shm[SLOW_MOTION_OFFSET] = args.slow # hector added
    if args.slow > 1: # hector added
        print(f"Slow motion on: the game runs at 1/{args.slow} speed until you press Ctrl+C.") # hector added
# hector added
    points = [] # hector added
    level = None # hector added
    last_frame = None # hector added
    recording = args.no_reset # hector added
    last_reset_count = shm[RESET_COUNT_OFFSET] # hector added
# hector added
    if args.no_reset: # hector added
        print("Recording now. Drive Mario along the course, then press Ctrl+C to save.") # hector added
    else: # hector added
        shm[RESET_REQUEST_OFFSET] = 1 # hector added
        print("Restarting the course so the trail starts at the entrance...") # hector added
# hector added
    try: # hector added
        while True: # hector added
            frame, = struct.unpack_from("<I", shm, 0) # hector added
            if frame == last_frame: # hector added
                time.sleep(0.0005) # hector added
                continue # hector added
# hector added
            x, y, z = struct.unpack_from("<3f", shm, POS_OFFSET) # hector added
# hector added
            # Answer every frame with "no input", so YOUR controller drives Mario # hector added
            struct.pack_into("<ffB", shm, OUTPUT_OFFSET, 0.0, 0.0, 0) # hector added
            struct.pack_into("<I", shm, 4, frame) # hector added
            last_frame = frame # hector added
# hector added
            if not recording: # hector added
                if shm[RESET_COUNT_OFFSET] != last_reset_count: # hector added
                    recording = True # hector added
                    print("Course restarted. Recording now: drive Mario to the end, then press Ctrl+C.") # hector added
                continue # hector added
# hector added
            if level is None: # hector added
                level = shm[LEVEL_NUM_OFFSET] # hector added
# hector added
            if not points or math.dist(points[-1], (x, y, z)) >= args.spacing: # hector added
                points.append((x, y, z)) # hector added
                if len(points) % 10 == 0: # hector added
                    print(f"  {len(points)} trail points so far") # hector added
    except KeyboardInterrupt: # hector added
        pass # hector added
    finally: # hector added
        struct.pack_into("<ffB", shm, OUTPUT_OFFSET, 0.0, 0.0, 0) # hector added
        shm[SLOW_MOTION_OFFSET] = 0  # back to normal speed # hector added
        shm.close() # hector added
        os.close(fd) # hector added
# hector added
    if level is None or len(points) < 2: # hector added
        print("\nNothing recorded, so the old trail file (if any) was left alone.") # hector added
        return # hector added
# hector added
    with open(TRAIL_FILE, "w") as f: # hector added
        f.write(f"level {level}\n") # hector added
        for x, y, z in points: # hector added
            f.write(f"{x:.1f} {y:.1f} {z:.1f}\n") # hector added
    print(f"\nSaved {len(points)} trail points for level {level} to {TRAIL_FILE}") # hector added
    if len(points) > 150: # hector added
        print("Note: the game places at most 150 trail coins. Use a bigger --spacing for a long course.") # hector added
    print("Re-enter the course (or let run_fly.py reset it) to see the coins.") # hector added
# hector added
# hector added
if __name__ == "__main__": # hector added
    main() # hector added
