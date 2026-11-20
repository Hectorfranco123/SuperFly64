# path sm64ex/brain/record_trail.py 
# made by hector
""" 
Records a "breadcrumb trail" of coins by watching YOU play. 

You drive Mario down the course (for example Peach's Secret Slide) with your own controller 
or keyboard. This script drops a point every --spacing units along Mario's path and saves them to 
brain/fly_trail.txt. From then on, every time that level loads (including fly resets), the game 
places a coin at each point, so the fly can follow the coins along the track. 

How to use: 
  1. Start the game and enter the course (e.g. Peach's Secret Slide). 
  2. From sm64ex/brain:   python3 record_trail.py 
     It restarts the course so the trail starts exactly where Mario enters, and runs the game in 
     slow motion (half speed by default) so you can steer. --slow 3 or --slow 4 is even slower, 
     --slow 1 is normal speed. The sound stutters in slow motion; that's expected. 
  3. Drive Mario to the end of the course yourself. 
  4. Press Ctrl+C to save. Then re-enter the course (or let run_fly.py reset it) to see the coins. 

Only one trail is kept: recording a new one replaces the old file. 
Messed up the run (fell off, went the wrong way)? Just press Ctrl+C and record again. 
""" 

import argparse 
import math 
import mmap 
import os 
import struct 
import time 

SHM_PATH = "/dev/shm/mario_brain" 
SHM_SIZE = 72 
POS_OFFSET = 8                 # x, y, z floats 
OUTPUT_OFFSET = 56             # stick_x, stick_y, button_a ("<ffB") 
RESET_REQUEST_OFFSET = 65 
RESET_COUNT_OFFSET = 66 
LEVEL_NUM_OFFSET = 67 
SLOW_MOTION_OFFSET = 68         # 2 = half speed ... 4 = quarter speed 
TRAIL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fly_trail.txt") 


def main(): 
    p = argparse.ArgumentParser(description="Record a coin trail by driving Mario yourself.") 
    p.add_argument("--spacing", type=float, default=250.0, help="distance between trail coins") 
    p.add_argument("--no-reset", action="store_true", help="start recording right where Mario is") 
    p.add_argument("--slow", type=int, default=2, choices=[1, 2, 3, 4], 
                   help="slow motion while recording: 2 = half speed (default), 4 = quarter speed, 1 = off") 
    args = p.parse_args() 

    fd = os.open(SHM_PATH, os.O_RDWR) 
    try: 
        shm = mmap.mmap(fd, SHM_SIZE) 
    except ValueError: 
        print("The game's shared memory is the old, smaller size. Rebuild the game with make, restart it,") 
        print("and run this again.") 
        os.close(fd) 
        return 

    shm[SLOW_MOTION_OFFSET] = args.slow 
    if args.slow > 1: 
        print(f"Slow motion on: the game runs at 1/{args.slow} speed until you press Ctrl+C.") 

    points = [] 
    level = None 
    last_frame = None 
    recording = args.no_reset 
    last_reset_count = shm[RESET_COUNT_OFFSET] 

    if args.no_reset: 
        print("Recording now. Drive Mario along the course, then press Ctrl+C to save.") 
    else: 
        shm[RESET_REQUEST_OFFSET] = 1 
        print("Restarting the course so the trail starts at the entrance...") 

    try: 
        while True: 
            frame, = struct.unpack_from("<I", shm, 0) 
            if frame == last_frame: 
                time.sleep(0.0005) 
                continue 

            x, y, z = struct.unpack_from("<3f", shm, POS_OFFSET) 

            # Answer every frame with "no input", so YOUR controller drives Mario 
            struct.pack_into("<ffB", shm, OUTPUT_OFFSET, 0.0, 0.0, 0) 
            struct.pack_into("<I", shm, 4, frame) 
            last_frame = frame 

            if not recording: 
                if shm[RESET_COUNT_OFFSET] != last_reset_count: 
                    recording = True 
                    print("Course restarted. Recording now: drive Mario to the end, then press Ctrl+C.") 
                    print("sleeping 3 seconds to let the game settle...")
                    time.sleep(3)  
                continue 

            if level is None: 
                level = shm[LEVEL_NUM_OFFSET] 

            if not points or math.dist(points[-1], (x, y, z)) >= args.spacing: 
                points.append((x, y, z)) 
                if len(points) % 10 == 0: 
                    print(f"  {len(points)} trail points so far") 
    except KeyboardInterrupt: 
        pass 
    finally: 
        struct.pack_into("<ffB", shm, OUTPUT_OFFSET, 0.0, 0.0, 0) 
        shm[SLOW_MOTION_OFFSET] = 0  # back to normal speed 
        shm.close() 
        os.close(fd) 

    if level is None or len(points) < 2: 
        print("\nNothing recorded, so the old trail file (if any) was left alone.") 
        return 

    with open(TRAIL_FILE, "w") as f: 
        f.write(f"level {level}\n") 
        for x, y, z in points: 
            f.write(f"{x:.1f} {y:.1f} {z:.1f}\n") 
    print(f"\nSaved {len(points)} trail points for level {level} to {TRAIL_FILE}") 
    if len(points) > 150: 
        print("Note: the game places at most 150 trail coins. Use a bigger --spacing for a long course.") 
    print("Re-enter the course (or let run_fly.py reset it) to see the coins.") 


if __name__ == "__main__": 
    main() 