#define _GNU_SOURCE // hector added
// hector added
#include <stdbool.h> // hector added
#include <stdint.h> // hector added
#include <string.h> // hector added
#include <time.h> // hector added
#include <math.h> // hector added
#include <fcntl.h> // hector added
#include <unistd.h> // hector added
#include <sys/mman.h> // hector added
#include <sys/stat.h> // hector added
#include <ultra64.h> // hector added
// hector added
#include "controller_api.h" // hector added
#include "controller_fly.h" // hector added
#include "game/level_update.h" // hector added
#include "game/object_list_processor.h" // hector added
#include "game/interaction.h" // hector added
#include "game/area.h" // hector added
#include "game/camera.h" // hector added
#ifdef BETTERCAMERA // hector added
#include "game/bettercamera.h" // hector added
#endif // hector added
#include "engine/graph_node.h" // hector added
#include "object_fields.h" // hector added
#include "object_constants.h" // hector added
// hector added
/* path sm64ex/src/pc/controller/controller_fly.c
 * Fly-brain controller backend. // hector added
 * Each frame: write Mario's state to shared memory, wait (briefly) for the // hector added
 * Python fly brain to answer, then add the fly's buttons and stick to the pad. // hector added
 * If Python isn't running, the game carries on normally without stalling. */ // hector added
// hector added
#define FLY_TIMEOUT_MS  50  // longest the game waits for the brain each frame // hector added
#define FLY_MAX_MISSED  30  // after this many missed frames, stop waiting (brain gone) // hector added
#define FLY_STICK_RANGE 80.0f  // raw stick value for a full push (a real N64 stick tops out near 80) // hector added
#define FLY_PI          3.14159265f // hector added
// hector added
// 1 = the fly's stick is MARIO-relative: stick_y = go forward, stick_x = go right of where Mario faces. // hector added
//     The game converts it for the camera, so the camera can be anywhere. // hector added
// 0 = normal SM64 behavior: the stick is relative to the camera, like a human player. // hector added
#define FLY_BODY_RELATIVE 1 // hector added
// hector added
static BrainLink *sLink = NULL; // hector added
static uint32_t sFrame = 0; // hector added
static int sMissed = FLY_MAX_MISSED;  // start "disconnected" so boot never stalls // hector added
// hector added
static void fly_init(void) { // hector added
    int fd; // hector added
    void *mem; // hector added
// hector added
    if (sLink != NULL) { // hector added
        return;  // already set up // hector added
    } // hector added
// hector added
    fd = shm_open(FLY_SHM_NAME, O_CREAT | O_RDWR, 0666); // hector added
    if (fd < 0) { // hector added
        return;  // no shared memory: game runs without the fly // hector added
    } // hector added
// hector added
    if (ftruncate(fd, sizeof(BrainLink)) != 0) { // hector added
        close(fd); // hector added
        return; // hector added
    } // hector added
// hector added
    mem = mmap(NULL, sizeof(BrainLink), PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0); // hector added
    close(fd);  // the mapping stays valid after closing the file // hector added
    if (mem == MAP_FAILED) { // hector added
        return; // hector added
    } // hector added
// hector added
    sLink = (BrainLink *) mem; // hector added
    memset((void *) sLink, 0, sizeof(BrainLink)); // hector added
    sLink->brain_frame = UINT32_MAX;  // "no answer yet", never matches a real frame // hector added
} // hector added
// hector added
// Returns true if this object is a coin Mario could collect right now. // hector added
static bool fly_is_collectable_coin(struct Object *obj) { // hector added
    if (!(obj->activeFlags & ACTIVE_FLAG_ACTIVE)) { // hector added
        return false;  // deleted or inactive // hector added
    } // hector added
    if (obj->oInteractType != INTERACT_COIN) { // hector added
        return false;  // not a coin // hector added
    } // hector added
    if (obj->oInteractStatus & INT_STATUS_INTERACTED) { // hector added
        return false;  // already collected this frame // hector added
    } // hector added
    if (obj->oIntangibleTimer != 0) { // hector added
        return false;  // can't be touched yet (just spawned, inside a Boo, hidden blue coin...) // hector added
    } // hector added
    if (!(obj->header.gfx.node.flags & GRAPH_RENDER_ACTIVE) // hector added
        || (obj->header.gfx.node.flags & GRAPH_RENDER_INVISIBLE)) { // hector added
        return false;  // not visible // hector added
    } // hector added
    return true; // hector added
} // hector added
// hector added
// Searches one object list for the coin closest to Mario. // hector added
static void fly_search_list(s32 listIndex, struct Object **best, f32 *bestDistSq) { // hector added
    struct ObjectNode *listHead = &gObjectLists[listIndex]; // hector added
    struct Object *obj = (struct Object *) listHead->next; // hector added
    f32 dx, dy, dz, distSq; // hector added
// hector added
    while (obj != (struct Object *) listHead) { // hector added
        if (fly_is_collectable_coin(obj)) { // hector added
            dx = obj->oPosX - gMarioState->pos[0]; // hector added
            dy = obj->oPosY - gMarioState->pos[1]; // hector added
            dz = obj->oPosZ - gMarioState->pos[2]; // hector added
            distSq = dx * dx + dy * dy + dz * dz; // hector added
            if (distSq < *bestDistSq) { // hector added
                *bestDistSq = distSq; // hector added
                *best = obj; // hector added
            } // hector added
        } // hector added
        obj = (struct Object *) obj->header.next; // hector added
    } // hector added
} // hector added
// hector added
// Finds the nearest coin and fills in coin_pos, angle_to_coin, dist_to_coin, coin_found. // hector added
static void fly_sense_nearest_coin(f32 marioYaw) { // hector added
    struct Object *best = NULL; // hector added
    f32 bestDistSq = 1e30f; // hector added
    f32 dx, dz, worldAngle, relAngle; // hector added
// hector added
    // Coins live in the "level" list; jumping blue coins live in the "generic actor" list. // hector added
    fly_search_list(OBJ_LIST_LEVEL, &best, &bestDistSq); // hector added
    fly_search_list(OBJ_LIST_GENACTOR, &best, &bestDistSq); // hector added
// hector added
    if (best == NULL) { // hector added
        sLink->coin_found = 0; // hector added
        sLink->coin_pos[0] = 0.0f; // hector added
        sLink->coin_pos[1] = 0.0f; // hector added
        sLink->coin_pos[2] = 0.0f; // hector added
        sLink->angle_to_coin = 0.0f; // hector added
        sLink->dist_to_coin = -1.0f; // hector added
        return; // hector added
    } // hector added
// hector added
    sLink->coin_found = 1; // hector added
    sLink->coin_pos[0] = best->oPosX; // hector added
    sLink->coin_pos[1] = best->oPosY; // hector added
    sLink->coin_pos[2] = best->oPosZ; // hector added
    sLink->dist_to_coin = sqrtf(bestDistSq); // hector added
// hector added
    // SM64 yaw: Mario's forward direction is (sin(yaw), cos(yaw)) on the X/Z ground plane, // hector added
    // so the direction to the coin as a yaw is atan2(dx, dz). // hector added
    dx = best->oPosX - gMarioState->pos[0]; // hector added
    dz = best->oPosZ - gMarioState->pos[2]; // hector added
    worldAngle = atan2f(dx, dz); // hector added
// hector added
    // Make it relative to where Mario is facing and wrap into -pi..pi // hector added
    relAngle = worldAngle - marioYaw; // hector added
    while (relAngle > FLY_PI) { // hector added
        relAngle -= 2.0f * FLY_PI; // hector added
    } // hector added
    while (relAngle < -FLY_PI) { // hector added
        relAngle += 2.0f * FLY_PI; // hector added
    } // hector added
    sLink->angle_to_coin = relAngle; // hector added
} // hector added
// hector added
// Converts the fly's -1..1 stick value into the game's raw stick value. // hector added
static s8 fly_stick_to_raw(float v) { // hector added
    if (v != v) { // hector added
        return 0;  // NaN from Python: treat as centered // hector added
    } // hector added
    if (v > 1.0f) { // hector added
        v = 1.0f; // hector added
    } // hector added
    if (v < -1.0f) { // hector added
        v = -1.0f; // hector added
    } // hector added
    return (s8) (v * FLY_STICK_RANGE); // hector added
} // hector added
// hector added
// Finds the camera angle the game will use to turn the stick into a direction this frame. // hector added
// Returns false if there's no camera (menus, transitions). // hector added
static bool fly_get_camera_yaw(f32 *camYaw) { // hector added
#ifdef BETTERCAMERA // hector added
    // Puppycam (BETTERCAMERA=1) uses its own angle, the same formula mario.c uses // hector added
    if (gLakituState.mode == CAMERA_MODE_NEWCAM) { // hector added
        *camYaw = (s16) (-newcam_yaw + 0x4000) * (2.0f * FLY_PI / 65536.0f); // hector added
        return true; // hector added
    } // hector added
#endif // hector added
    if (gMarioState->area == NULL || gMarioState->area->camera == NULL) { // hector added
        return false; // hector added
    } // hector added
    *camYaw = gMarioState->area->camera->yaw * (2.0f * FLY_PI / 65536.0f); // hector added
    return true; // hector added
} // hector added
// hector added
// Converts the fly's Mario-relative stick into the camera-relative stick the game expects. // hector added
// The game turns the stick into a direction with: direction = atan2(stickX, -stickY) + cameraYaw, // hector added
// so this does that math backwards. // hector added
static void fly_body_to_camera_stick(float sx, float sy, s8 *outX, s8 *outY) { // hector added
    f32 mag, relAngle, marioYaw, camYaw, phi; // hector added
// hector added
    // Clean up bad values from Python (NaN or outside -1..1) // hector added
    if (sx != sx) { // hector added
        sx = 0.0f; // hector added
    } // hector added
    if (sy != sy) { // hector added
        sy = 0.0f; // hector added
    } // hector added
    mag = sqrtf(sx * sx + sy * sy); // hector added
    if (mag < 0.001f) { // hector added
        *outX = 0; // hector added
        *outY = 0; // hector added
        return; // hector added
    } // hector added
    if (mag > 1.0f) { // hector added
        mag = 1.0f;  // pushing diagonally can't go past full tilt // hector added
    } // hector added
// hector added
    if (!fly_get_camera_yaw(&camYaw)) { // hector added
        // No camera to convert against: fall back to camera-relative // hector added
        *outX = fly_stick_to_raw(sx); // hector added
        *outY = fly_stick_to_raw(sy); // hector added
        return; // hector added
    } // hector added
// hector added
    // Direction the fly wants, relative to Mario's facing (same convention as angle_to_coin: // hector added
    // 0 = forward, positive = left, negative = right) // hector added
    relAngle = atan2f(-sx, sy); // hector added
    marioYaw = gMarioState->faceAngle[1] * (2.0f * FLY_PI / 65536.0f); // hector added
// hector added
    // Angle the stick must point, measured the way the game measures it // hector added
    phi = marioYaw + relAngle - camYaw; // hector added
// hector added
    *outX = (s8) (sinf(phi) * mag * FLY_STICK_RANGE); // hector added
    *outY = (s8) (-cosf(phi) * mag * FLY_STICK_RANGE); // hector added
} // hector added
// hector added
// Waits until the brain has answered this frame. Returns false on timeout. // hector added
static bool fly_wait_for_brain(uint32_t frame) { // hector added
    struct timespec start, now; // hector added
    struct timespec nap = { 0, 100000 };  // 0.1 ms between checks // hector added
    long elapsedMs; // hector added
// hector added
    clock_gettime(CLOCK_MONOTONIC, &start); // hector added
// hector added
    while (sLink->brain_frame != frame) { // hector added
        clock_gettime(CLOCK_MONOTONIC, &now); // hector added
        elapsedMs = (now.tv_sec - start.tv_sec) * 1000 + (now.tv_nsec - start.tv_nsec) / 1000000; // hector added
        if (elapsedMs >= FLY_TIMEOUT_MS) { // hector added
            return false; // hector added
        } // hector added
        nanosleep(&nap, NULL); // hector added
    } // hector added
// hector added
    return true; // hector added
} // hector added
// hector added
static void fly_read(OSContPad *pad) { // hector added
    f32 marioYaw; // hector added
    s16 wedges; // hector added
// hector added
    if (sLink == NULL) { // hector added
        return; // hector added
    } // hector added
// hector added
    // 1. Send Mario's state to the brain (only when Mario actually exists in a level) // hector changed
    if (gMarioState != NULL && gMarioState->marioObj != NULL) { // hector changed
        marioYaw = gMarioState->faceAngle[1] * (2.0f * FLY_PI / 65536.0f); // hector changed
// hector changed
        sLink->pos[0] = gMarioState->pos[0]; // hector added
        sLink->pos[1] = gMarioState->pos[1]; // hector added
        sLink->pos[2] = gMarioState->pos[2]; // hector added
        sLink->face_yaw = marioYaw; // hector changed
        sLink->fwd_vel = gMarioState->forwardVel; // hector added
        sLink->coins = gMarioState->numCoins; // hector added
// hector changed
        wedges = gMarioState->health >> 8; // hector changed
        if (wedges < 0) { // hector changed
            wedges = 0; // hector changed
        } // hector changed
        sLink->wedges = wedges; // hector changed
// hector changed
        sLink->wall_collision = (gMarioState->wall != NULL) ? 1 : 0; // hector changed
// hector changed
        fly_sense_nearest_coin(marioYaw); // hector changed
    } else { // hector changed
        sLink->coin_found = 0; // hector changed
        sLink->dist_to_coin = -1.0f; // hector changed
        sLink->wall_collision = 0; // hector changed
    } // hector added
// hector added
    // 2. Announce a new frame (everything above must be written before this) // hector changed
    sFrame++; // hector added
    __sync_synchronize(); // hector added
    sLink->game_frame = sFrame; // hector added
// hector added
    // 3. Disconnected: don't block. If the brain answered last frame, it's back. // hector added
    if (sMissed >= FLY_MAX_MISSED) { // hector added
        if (sLink->brain_frame == sFrame - 1) { // hector added
            sMissed = 0; // hector added
        } // hector added
        return; // hector added
    } // hector added
// hector added
    // 3b. Connected: wait for this frame's answer // hector added
    if (!fly_wait_for_brain(sFrame)) { // hector added
        sMissed++; // hector added
        return;  // no fresh inputs this frame, so don't apply stale ones // hector added
    } // hector added
    sMissed = 0; // hector added
    __sync_synchronize(); // hector added
// hector added
    // 4. Apply the fly's outputs. A combines with yours; // hector changed
    //    the stick is only used when you aren't touching yours. // hector added
    if (sLink->button_a) { // hector changed
        pad->button |= A_BUTTON; // hector changed
    } // hector changed
    if (pad->stick_x == 0 && pad->stick_y == 0) { // hector added
#if FLY_BODY_RELATIVE // hector added
        if (gMarioState != NULL && gMarioState->marioObj != NULL) { // hector added
            fly_body_to_camera_stick(sLink->stick_x, sLink->stick_y, &pad->stick_x, &pad->stick_y); // hector added
        } // hector added
#else // hector added
        pad->stick_x = fly_stick_to_raw(sLink->stick_x); // hector changed
        pad->stick_y = fly_stick_to_raw(sLink->stick_y); // hector changed
#endif // hector added
    } // hector added
} // hector added
// hector added
static u32 fly_rawkey(void) { // hector added
    return VK_INVALID;  // the fly never binds keys (must not be NULL) // hector added
} // hector added
// hector added
static void fly_shutdown(void) { // hector added
    if (sLink != NULL) { // hector added
        munmap((void *) sLink, sizeof(BrainLink)); // hector added
        sLink = NULL; // hector added
    } // hector added
} // hector added
// hector added
struct ControllerAPI controller_fly = { // hector added
    0,              // vkbase: unused, the fly has no bindable keys // hector added
    fly_init, // hector added
    fly_read, // hector added
    fly_rawkey, // hector added
    NULL,           // no rumble // hector added
    NULL, // hector added
    NULL,           // no reconfig // hector added
    fly_shutdown // hector added
}; // hector added