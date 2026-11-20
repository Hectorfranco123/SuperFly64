#made by gemini - Hector
#edits were made by hector

import mmap 
import math 
import os 
import struct 
import time 

# path sm64ex/brain/test_fly_bridge.py
# ==================== NOTES FOR THE PYTHON SIDE (from Hector) ==================== 
# 
# HOW THE HANDSHAKE WORKS 
#   1. Start the game FIRST. It creates the shared memory /dev/shm/mario_brain. 
#   2. Every frame the game writes Mario's info, then bumps game_frame. 
#   3. Python reads the info, writes stick_x / stick_y / button_a, 
#      then writes brain_frame = game_frame LAST. That tells the game "outputs ready". 
#   4. The game waits up to 50 ms for that answer. If Python isn't running, 
#      the game just plays normally (no freezing). 
#   Python struct format for the whole 72-byte block: "<II3fff3fffhhBBBBffBBBBBxxx" # hector changed
# 
# INPUTS (written by the game) 
#   pos, face_yaw, fwd_vel  Mario's position, facing (radians), forward speed 
#   coin_pos                nearest coin's x, y, z (use y vs Mario's y to see if it's up high) 
#   angle_to_coin           radians, -pi to pi, relative to where MARIO is facing: 
#                             0 = straight ahead, positive = coin on Mario's LEFT, 
#                             negative = coin on Mario's RIGHT, +/-pi = behind him 
#   dist_to_coin            3D distance to the nearest coin 
#   coin_found              1 = a coin was found. 0 = no coin: then dist_to_coin = -1 
#                           and coin_pos / angle_to_coin mean nothing, so CHECK THIS FIRST 
#   coins                   coins collected 
#   wedges                  health, 0 to 8 (8 = full) 
#   wall_collision          1 = Mario is touching a wall right now 
#   airborne                1 = Mario is in the air (jumping, falling, flying), 0 = on the ground 
#   stuck_frames            how many frames in a row the fly has pushed the stick (at least 0.3) 
#                           but Mario barely moved: catches trees, slopes, objects, corners that 
#                           wall_collision misses. 0 = moving fine. Counts up to 255 (about 8.5 s). 
#   reset_count             goes up by 1 every time the game performs a level reset 
#                           (watch for it changing to know a new trial has started) 
#   level_num               the game's internal number for the current level (offset 67) 
#   slow_motion             (offset 68, written by Python) 2 = game runs at half speed, 3 = a third, 
#                           4 = a quarter (the most). 0 or 1 = normal. Only works while Python is 
#                           answering; record_trail.py uses it so a human can keep up on the slide. 
#                           Sound stutters in slow motion; that's expected. 
# 
# OUTPUTS (written by Python) 
#   stick_x, stick_y        -1 to 1, MARIO-RELATIVE (not camera-relative like a normal player): 
#                             stick_y =  1 -> go forward (the way Mario faces) 
#                             stick_x =  1 -> go to Mario's right, -1 -> his left 
#                           Holding stick_x steady makes Mario keep turning, like a fly steering. 
#                           The C code converts this for the camera, so the camera can be anywhere. 
#                           To head straight at the coin: 
#                             stick_x = -sin(angle_to_coin) 
#                             stick_y =  cos(angle_to_coin) 
#                           Values outside -1..1 get clamped, NaN is treated as 0. 
#   button_a                1 = hold A (jump), 0 = release. 
#                           To jump AGAIN, button_a must go back to 0 for at least one frame, 
#                           just like a real controller (holding A only jumps once). 
#   reset_request           write 1 to restart the current course from its start, for a fresh 
#                           trial (Stage 5). Don't write 0 afterwards: the GAME clears it back to 0 
#                           when the reset happens, then bumps reset_count. The reset reloads every 
#                           object (collected coins come back), sets coins to 0 and health to full, 
#                           and skips the star select screen (same star/act as before). 
#                           Works inside the 15 main courses and Peach's Secret Slide; anywhere else 
#                           (castle, paused, mid-warp) the request waits until it's possible. 
# 
# THINGS TO KNOW 
#   - If Hector touches his own stick, his stick wins (so he can rescue Mario). 
#     Buttons combine: A from either one counts. 
#   - Coin rings/lines more than 2000 units away don't exist in the game yet 
#     (the game only creates them when Mario gets close). Build with 
#     NODRAWINGDISTANCE=1 to make every coin exist so the fly can "smell" all of them. 
#   - Want camera-relative steering instead? Set FLY_BODY_RELATIVE to 0 in controller_fly.c. 
#   - If this layout ever changes, the Python format string must change too. 
#     (The C side refuses to compile unless the block is exactly 72 bytes, as a reminder.) # hector changed
# ================================================================================= 

# Bridge test: steers Mario straight at the nearest coin (Mario-relative stick) # hector changed
# and prints what the fly senses (coin direction/distance, wall contact, coins, health). # hector changed
# Start the game FIRST (it creates the shared memory), then run this. 

SHM_PATH = "/dev/shm/mario_brain" 
SHM_SIZE = 68 # hector changed
INPUT_FORMAT = "<3fff3fffhhBB"   # pos, yaw, speed, coin_pos, angle_to_coin, dist_to_coin, coins, wedges, wall, coin_found # hector changed
INPUT_OFFSET = 8 # hector changed
OUTPUT_FORMAT = "<ffB"           # stick_x, stick_y, button_a # hector changed
OUTPUT_OFFSET = 56 # hector changed

fd = os.open(SHM_PATH, os.O_RDWR) 
shm = mmap.mmap(fd, SHM_SIZE) 
last = None 

try: 
    while True: 
        game_frame, = struct.unpack_from("<I", shm, 0) 
        if game_frame == last: 
            time.sleep(0.0005) 
            continue 

        (x, y, z, yaw, speed, cx, cy, cz, angle_to_coin, dist_to_coin, # hector changed
         coins, wedges, wall, coin_found) = struct.unpack_from(INPUT_FORMAT, shm, INPUT_OFFSET) # hector changed

        if coin_found: # hector changed
            stick_x = -math.sin(angle_to_coin)  # coin on the left (positive angle) -> go left # hector changed
            stick_y = math.cos(angle_to_coin)   # coin ahead -> go forward # hector changed
        else: # hector changed
            stick_x, stick_y = 0.0, 0.0 # hector changed
        struct.pack_into(OUTPUT_FORMAT, shm, OUTPUT_OFFSET, stick_x, stick_y, 0)  # no jump # hector changed
        struct.pack_into("<I", shm, 4, game_frame)                          # written LAST: "outputs ready" # hector changed
        last = game_frame 

        if game_frame % 30 == 0: 
            if coin_found: # hector changed
                side = "LEFT" if angle_to_coin > 0 else "RIGHT" # hector changed
                coin_text = f"coin {dist_to_coin:.0f} away, {math.degrees(angle_to_coin):+.0f} deg ({side}), {cy - y:+.0f} high" # hector changed
            else: # hector changed
                coin_text = "no coin found" # hector changed
            print(f"frame {game_frame}  pos=({x:.0f}, {y:.0f}, {z:.0f})  speed={speed:.1f}  " # hector changed
                  f"{coin_text}  wall={wall}  coins={coins}  wedges={wedges}") # hector changed
finally: 
    struct.pack_into(OUTPUT_FORMAT, shm, OUTPUT_OFFSET, 0.0, 0.0, 0)  # let go of everything # hector changed
    shm.close() 
    os.close(fd) 