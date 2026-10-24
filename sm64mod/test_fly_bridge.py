import mmap # hector added
import math # hector added
import os # hector added
import struct # hector added
import time # hector added
# hector added
# path sm64ex/brain/test_fly_bridge.py
# ==================== NOTES FOR THE PYTHON SIDE (from Hector) ==================== # hector added
# # hector added
# HOW THE HANDSHAKE WORKS # hector added
#   1. Start the game FIRST. It creates the shared memory /dev/shm/mario_brain. # hector added
#   2. Every frame the game writes Mario's info, then bumps game_frame. # hector added
#   3. Python reads the info, writes stick_x / stick_y / button_a, # hector added
#      then writes brain_frame = game_frame LAST. That tells the game "outputs ready". # hector added
#   4. The game waits up to 50 ms for that answer. If Python isn't running, # hector added
#      the game just plays normally (no freezing). # hector added
#   Python struct format for the whole 68-byte block: "<II3fff3fffhhBBxxffBxxx" # hector added
# # hector added
# INPUTS (written by the game) # hector added
#   pos, face_yaw, fwd_vel  Mario's position, facing (radians), forward speed # hector added
#   coin_pos                nearest coin's x, y, z (use y vs Mario's y to see if it's up high) # hector added
#   angle_to_coin           radians, -pi to pi, relative to where MARIO is facing: # hector added
#                             0 = straight ahead, positive = coin on Mario's LEFT, # hector added
#                             negative = coin on Mario's RIGHT, +/-pi = behind him # hector added
#   dist_to_coin            3D distance to the nearest coin # hector added
#   coin_found              1 = a coin was found. 0 = no coin: then dist_to_coin = -1 # hector added
#                           and coin_pos / angle_to_coin mean nothing, so CHECK THIS FIRST # hector added
#   coins                   coins collected # hector added
#   wedges                  health, 0 to 8 (8 = full) # hector added
#   wall_collision          1 = Mario is touching a wall right now # hector added
# # hector added
# OUTPUTS (written by Python) # hector added
#   stick_x, stick_y        -1 to 1, MARIO-RELATIVE (not camera-relative like a normal player): # hector added
#                             stick_y =  1 -> go forward (the way Mario faces) # hector added
#                             stick_x =  1 -> go to Mario's right, -1 -> his left # hector added
#                           Holding stick_x steady makes Mario keep turning, like a fly steering. # hector added
#                           The C code converts this for the camera, so the camera can be anywhere. # hector added
#                           To head straight at the coin: # hector added
#                             stick_x = -sin(angle_to_coin) # hector added
#                             stick_y =  cos(angle_to_coin) # hector added
#                           Values outside -1..1 get clamped, NaN is treated as 0. # hector added
#   button_a                1 = hold A (jump), 0 = release. # hector added
#                           To jump AGAIN, button_a must go back to 0 for at least one frame, # hector added
#                           just like a real controller (holding A only jumps once). # hector added
# # hector added
# THINGS TO KNOW # hector added
#   - If Hector touches his own stick, his stick wins (so he can rescue Mario). # hector added
#     Buttons combine: A from either one counts. # hector added
#   - Coin rings/lines more than 2000 units away don't exist in the game yet # hector added
#     (the game only creates them when Mario gets close). Build with # hector added
#     NODRAWINGDISTANCE=1 to make every coin exist so the fly can "smell" all of them. # hector added
#   - Want camera-relative steering instead? Set FLY_BODY_RELATIVE to 0 in controller_fly.c. # hector added
#   - If this layout ever changes, the Python format string must change too. # hector added
#     (The C side refuses to compile unless the block is exactly 68 bytes, as a reminder.) # hector added
# ================================================================================= # hector added
# hector added
# Bridge test: steers Mario straight at the nearest coin (Mario-relative stick) # hector changed
# and prints what the fly senses (coin direction/distance, wall contact, coins, health). # hector changed
# Start the game FIRST (it creates the shared memory), then run this. # hector added
# hector added
SHM_PATH = "/dev/shm/mario_brain" # hector added
SHM_SIZE = 68 # hector changed
INPUT_FORMAT = "<3fff3fffhhBB"   # pos, yaw, speed, coin_pos, angle_to_coin, dist_to_coin, coins, wedges, wall, coin_found # hector changed
INPUT_OFFSET = 8 # hector changed
OUTPUT_FORMAT = "<ffB"           # stick_x, stick_y, button_a # hector changed
OUTPUT_OFFSET = 56 # hector changed
# hector added
fd = os.open(SHM_PATH, os.O_RDWR) # hector added
shm = mmap.mmap(fd, SHM_SIZE) # hector added
last = None # hector added
# hector added
try: # hector added
    while True: # hector added
        game_frame, = struct.unpack_from("<I", shm, 0) # hector added
        if game_frame == last: # hector added
            time.sleep(0.0005) # hector added
            continue # hector added
# hector added
        (x, y, z, yaw, speed, cx, cy, cz, angle_to_coin, dist_to_coin, # hector changed
         coins, wedges, wall, coin_found) = struct.unpack_from(INPUT_FORMAT, shm, INPUT_OFFSET) # hector changed
# hector added
        if coin_found: # hector changed
            stick_x = -math.sin(angle_to_coin)  # coin on the left (positive angle) -> go left # hector changed
            stick_y = math.cos(angle_to_coin)   # coin ahead -> go forward # hector changed
        else: # hector changed
            stick_x, stick_y = 0.0, 0.0 # hector changed
        struct.pack_into(OUTPUT_FORMAT, shm, OUTPUT_OFFSET, stick_x, stick_y, 0)  # no jump # hector changed
        struct.pack_into("<I", shm, 4, game_frame)                          # written LAST: "outputs ready" # hector changed
        last = game_frame # hector added
# hector added
        if game_frame % 30 == 0: # hector added
            if coin_found: # hector changed
                side = "LEFT" if angle_to_coin > 0 else "RIGHT" # hector changed
                coin_text = f"coin {dist_to_coin:.0f} away, {math.degrees(angle_to_coin):+.0f} deg ({side})" # hector changed
            else: # hector changed
                coin_text = "no coin found" # hector changed
            print(f"frame {game_frame}  pos=({x:.0f}, {y:.0f}, {z:.0f})  speed={speed:.1f}  " # hector changed
                  f"{coin_text}  wall={wall}  coins={coins}  wedges={wedges}") # hector changed
finally: # hector added
    struct.pack_into(OUTPUT_FORMAT, shm, OUTPUT_OFFSET, 0.0, 0.0, 0)  # let go of everything # hector changed
    shm.close() # hector added
    os.close(fd) # hector added