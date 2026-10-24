#ifndef CONTROLLER_FLY_H // hector added
#define CONTROLLER_FLY_H // hector added
// hector added
/* // hector added
 * path sm64ex/src/pc/controller/controller_fly.h
 * ==================== NOTES FOR THE PYTHON SIDE (from Hector) ==================== // hector added
 * // hector added
 * HOW THE HANDSHAKE WORKS // hector added
 *   1. Start the game FIRST. It creates the shared memory /dev/shm/mario_brain. // hector added
 *   2. Every frame the game writes Mario's info, then bumps game_frame. // hector added
 *   3. Python reads the info, writes stick_x / stick_y / button_a, // hector added
 *      then writes brain_frame = game_frame LAST. That tells the game "outputs ready". // hector added
 *   4. The game waits up to 50 ms for that answer. If Python isn't running, // hector added
 *      the game just plays normally (no freezing). // hector added
 *   Python struct format for the whole 68-byte block: "<II3fff3fffhhBBxxffBxxx" // hector added
 * // hector added
 * INPUTS (written by the game) // hector added
 *   pos, face_yaw, fwd_vel  Mario's position, facing (radians), forward speed // hector added
 *   coin_pos                nearest coin's x, y, z (use y vs Mario's y to see if it's up high) // hector added
 *   angle_to_coin           radians, -pi to pi, relative to where MARIO is facing: // hector added
 *                             0 = straight ahead, positive = coin on Mario's LEFT, // hector added
 *                             negative = coin on Mario's RIGHT, +/-pi = behind him // hector added
 *   dist_to_coin            3D distance to the nearest coin // hector added
 *   coin_found              1 = a coin was found. 0 = no coin: then dist_to_coin = -1 // hector added
 *                           and coin_pos / angle_to_coin mean nothing, so CHECK THIS FIRST // hector added
 *   coins                   coins collected // hector added
 *   wedges                  health, 0 to 8 (8 = full) // hector added
 *   wall_collision          1 = Mario is touching a wall right now // hector added
 * // hector added
 * OUTPUTS (written by Python) // hector added
 *   stick_x, stick_y        -1 to 1, MARIO-RELATIVE (not camera-relative like a normal player): // hector added
 *                             stick_y =  1 -> go forward (the way Mario faces) // hector added
 *                             stick_x =  1 -> go to Mario's right, -1 -> his left // hector added
 *                           Holding stick_x steady makes Mario keep turning, like a fly steering. // hector added
 *                           The C code converts this for the camera, so the camera can be anywhere. // hector added
 *                           To head straight at the coin: // hector added
 *                             stick_x = -sin(angle_to_coin) // hector added
 *                             stick_y =  cos(angle_to_coin) // hector added
 *                           Values outside -1..1 get clamped, NaN is treated as 0. // hector added
 *   button_a                1 = hold A (jump), 0 = release. // hector added
 *                           To jump AGAIN, button_a must go back to 0 for at least one frame, // hector added
 *                           just like a real controller (holding A only jumps once). // hector added
 * // hector added
 * THINGS TO KNOW // hector added
 *   - If Hector touches his own stick, his stick wins (so he can rescue Mario). // hector added
 *     Buttons combine: A from either one counts. // hector added
 *   - Coin rings/lines more than 2000 units away don't exist in the game yet // hector added
 *     (the game only creates them when Mario gets close). Build with // hector added
 *     NODRAWINGDISTANCE=1 to make every coin exist so the fly can "smell" all of them. // hector added
 *   - Want camera-relative steering instead? Set FLY_BODY_RELATIVE to 0 in controller_fly.c. // hector added
 *   - If this layout ever changes, the Python format string must change too. // hector added
 *     (The C side refuses to compile unless the block is exactly 68 bytes, as a reminder.) // hector added
 * ================================================================================= // hector added
 */ // hector added
// hector added
#include <stdint.h> // hector added
#include "controller_api.h" // hector added
// hector added
// Name of the shared memory block. On Linux it appears as /dev/shm/mario_brain // hector added
#define FLY_SHM_NAME "/mario_brain" // hector added
// hector added
// The block shared between the game (C) and the fly brain (Python). // hector added
// Python must use exactly this layout: struct format "<II3fff3fffhhBBxxffBxxx" (68 bytes). // hector changed
// Angles are radians. angle_to_coin: 0 = coin straight ahead, positive = coin to Mario's LEFT, // hector changed
// negative = coin to Mario's RIGHT, range -pi to pi. // hector changed
typedef struct { // hector added
    // ---- written by the game every frame ---- // hector changed
    volatile uint32_t game_frame;   // offset 0:  game bumps this after writing everything below // hector changed
    volatile uint32_t brain_frame;  // offset 4:  Python sets this = game_frame when outputs are ready // hector changed
    float pos[3];                   // offset 8:  Mario's position (x, y, z) // hector added
    float face_yaw;                 // offset 20: Mario's facing angle, radians // hector changed
    float fwd_vel;                  // offset 24: Mario's forward speed // hector added
    float coin_pos[3];              // offset 28: nearest coin position (x, y, z) // hector changed
    float angle_to_coin;            // offset 40: nearest coin's direction relative to Mario's heading // hector changed
    float dist_to_coin;             // offset 44: 3D distance to nearest coin (-1 if no coin found) // hector changed
    int16_t coins;                  // offset 48: coins collected // hector changed
    int16_t wedges;                 // offset 50: health as power meter wedges, 0 to 8 // hector changed
    uint8_t wall_collision;         // offset 52: 1 if Mario is touching a wall, else 0 // hector changed
    uint8_t coin_found;             // offset 53: 1 if a coin was found, 0 if none (coin fields invalid) // hector changed
    uint8_t _pad1[2];               // offset 54: padding, unused // hector changed
    // ---- written by Python ---- // hector changed
    float stick_x;                  // offset 56: -1 to 1. MARIO-relative: positive = go to Mario's right // hector changed
    float stick_y;                  // offset 60: -1 to 1. MARIO-relative: positive = go forward // hector changed
    // To head straight at the coin: stick_x = -sin(angle_to_coin), stick_y = cos(angle_to_coin) // hector changed
    uint8_t button_a;               // offset 64: 1 = hold A (jump), 0 = release // hector changed
    uint8_t _pad2[3];               // offset 65: padding, unused // hector changed
} BrainLink; // hector added
// hector added
_Static_assert(sizeof(BrainLink) == 68, "BrainLink layout changed: update the Python side too"); // hector changed
// hector added
extern struct ControllerAPI controller_fly; // hector added
// hector added
#endif // hector added