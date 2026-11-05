#define _GNU_SOURCE // hector added
// hector added
#include <stdbool.h> // hector added
#include <stdio.h> // hector added
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
#include "game/ingame_menu.h" // hector added
#include "game/camera.h" // hector added
#ifdef BETTERCAMERA // hector added
#include "game/bettercamera.h" // hector added
#endif // hector added
#include "engine/graph_node.h" // hector added
#include "object_fields.h" // hector added
#include "object_constants.h" // hector added
#include "sm64.h" // hector added
#include "course_table.h" // hector added
#include "game/object_helpers.h" // hector added
#include "engine/surface_collision.h" // hector added
#include "behavior_data.h" // hector added
#include "model_ids.h" // hector added
#include "surface_terrains.h" // hector added
// hector added
/* path sm64ex/src/pc/controller/controller_fly.c
 * Fly-brain controller backend. // hector added
 * Each frame: write Mario's state to shared memory, wait (briefly) for the // hector added
 * Python fly brain to answer, then add the fly's buttons and stick to the pad. // hector added
 * If Python isn't running, the game carries on normally without stalling. */ // hector added
// hector added
#define FLY_TIMEOUT_MS  50  // longest the game waits for the brain each frame // hector added
#define FLY_MAX_MISSED  30  // after this many missed frames, stop waiting (brain gone) // hector added
#define FLY_SLOWMO_MAX  4   // slowest allowed slow motion: 1/4 speed // hector changed
#define FLY_STICK_MAX      64.0f  // biggest stick value the game uses after its dead zone (game_init.c) // hector added
#define FLY_STICK_DEADZONE  8      // the game ignores raw stick values smaller than this... // hector added
#define FLY_STICK_OFFSET    6      // ...and subtracts this from bigger ones // hector added
#define FLY_PI          3.14159265f // hector added
// hector added
// 1 = the fly's stick is MARIO-relative: stick_y = go forward, stick_x = go right of where Mario faces. // hector added
//     The game converts it for the camera, so the camera can be anywhere. // hector added
// 0 = normal SM64 behavior: the stick is relative to the camera, like a human player. // hector added
#define FLY_BODY_RELATIVE 1 // hector added
// hector added
#define FLY_STUCK_PUSH      0.3f  // the fly counts as "pushing" when its stick is at least this far over // hector added
#define FLY_STUCK_MOVE      1.0f  // moving less than this many units in a frame counts as not moving // hector added
#define FLY_TELEPORT_DIST   500.0f  // a jump bigger than this in one frame = warp/reset, not real movement // hector added
// hector added
// ---- Training coins ---- // hector added
// 1 = every time a main course loads (including fly resets), spawn a grid of extra yellow coins // hector added
//     around where Mario lands, so the fly has lots of nearby coins to learn from. // hector added
// 0 = normal SM64 coins only. // hector added
#define FLY_TRAINING_COINS  1 // hector added
#define FLY_COIN_GRID       7       // 7 x 7 grid (up to 48 coins; Mario's landing spot is skipped) // hector added
#define FLY_COIN_SPACING    300.0f  // distance between coins // hector added
#define FLY_COIN_MAX_STEP   400.0f  // skip spots much higher/lower than where Mario lands (cliffs, ledges) // hector added
#define FLY_COIN_HOVER      60.0f   // how high above the ground each coin floats // hector added
// hector added
// Trail coins: if brain/fly_trail.txt exists (made by brain/record_trail.py) and was recorded in // hector added
// THIS level, coins are placed along the recorded path instead of the grid. Best for slides like // hector added
// Peach's Secret Slide, where a grid around the start doesn't fit. The path is relative to the // hector added
// folder you start the game from (~/Desktop/sm64mod/sm64ex). // hector added
#define FLY_TRAIL_FILE      "brain/fly_trail.txt" // hector added
#define FLY_TRAIL_MAX       150     // most trail coins to place (the game can only hold so many objects) // hector added
// hector added
// Values copied from level_update.c (they're private to that file) // hector added
#define FLY_PLAY_MODE_NORMAL        0 // hector added
#define FLY_PLAY_MODE_CHANGE_LEVEL  4 // hector added
#define FLY_WARP_TYPE_NOT_WARPING   0 // hector added
#define FLY_WARP_TYPE_CHANGE_LEVEL  1 // hector added
#define FLY_COURSE_ENTRY_NODE       0x0A  // where Mario appears when entering a course through its painting // hector added
// hector added
// Set to 1 before a level load to skip the star select screen (defined in level_update.c) // hector added
extern s8 D_8032C9E0; // hector added
// Switches the game's play mode (defined in level_update.c, not declared in its header) // hector added
void set_play_mode(s16 playMode); // hector added
// hector added
static BrainLink *sLink = NULL; // hector added
static uint32_t sFrame = 0; // hector added
static int sMissed = FLY_MAX_MISSED;  // start "disconnected" so boot never stalls // hector added
// hector added
// For stuck detection // hector added
static f32 sLastPos[3]; // hector added
static bool sHaveLastPos = false; // hector added
static bool sFlyPushing = false;  // was the fly's stick actually driving Mario last frame? // hector added
static u8 sStuckFrames = 0; // hector added
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
// The game's dead zone (adjust_analog_stick in game_init.c) ignores raw stick values under 8 // hector added
// and subtracts 6 from the rest. Without undoing that, small fly outputs get bent off course // hector added
// (or one axis gets dropped). This turns the value we WANT the game to see back into the raw // hector added
// value to send. p is in -64..64. // hector added
static s8 fly_processed_to_raw(f32 p) { // hector added
    f32 raw; // hector added
    f32 sign = (p > 0.0f) ? 1.0f : -1.0f; // hector added
// hector added
    if (p > -0.5f && p < 0.5f) { // hector added
        return 0; // hector added
    } // hector added
    raw = p + FLY_STICK_OFFSET * sign; // hector added
    if (raw * sign < FLY_STICK_DEADZONE) { // hector added
        raw = FLY_STICK_DEADZONE * sign;  // smallest value the game still notices // hector added
    } // hector added
    return (s8) (raw + 0.5f * sign);  // round to the nearest whole value // hector added
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
    return fly_processed_to_raw(v * FLY_STICK_MAX); // hector changed
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
    *outX = fly_processed_to_raw(sinf(phi) * mag * FLY_STICK_MAX); // hector changed
    *outY = fly_processed_to_raw(-cosf(phi) * mag * FLY_STICK_MAX); // hector changed
} // hector added
// hector added
// Updates the stuck counter: the fly is pushing, but Mario has barely moved since last frame. // hector added
static void fly_update_stuck(void) { // hector added
    f32 dx, dz, moved; // hector added
// hector added
    if (sHaveLastPos) { // hector added
        dx = gMarioState->pos[0] - sLastPos[0]; // hector added
        dz = gMarioState->pos[2] - sLastPos[2]; // hector added
        moved = sqrtf(dx * dx + dz * dz); // hector added
// hector added
        if (moved > FLY_TELEPORT_DIST) { // hector added
            sStuckFrames = 0;  // warped or reset, not a real move // hector added
        } else if (sFlyPushing && moved < FLY_STUCK_MOVE) { // hector added
            if (sStuckFrames < 255) { // hector added
                sStuckFrames++; // hector added
            } // hector added
        } else { // hector added
            sStuckFrames = 0; // hector added
        } // hector added
    } // hector added
// hector added
    sLastPos[0] = gMarioState->pos[0]; // hector added
    sLastPos[1] = gMarioState->pos[1]; // hector added
    sLastPos[2] = gMarioState->pos[2]; // hector added
    sHaveLastPos = true; // hector added
} // hector added
// hector added
// Courses where the fly can reset and get training coins: the 15 main courses and Peach's Secret Slide. // hector added
static bool fly_course_allowed(void) { // hector added
    return COURSE_IS_MAIN_COURSE(gCurrCourseNum) || gCurrCourseNum == COURSE_PSS; // hector added
} // hector added
// hector added
// Restarts the current course from its entrance, reloading every object. // hector added
// Returns false (and does nothing) if a reset isn't safe right now. // hector added
static bool fly_try_level_reset(void) { // hector added
    if (gCurrentArea == NULL || !fly_course_allowed()) { // hector added
        return false;  // only inside the 15 main courses or Peach's Secret Slide // hector added
    } // hector added
    if (sCurrPlayMode != FLY_PLAY_MODE_NORMAL || sWarpDest.type != FLY_WARP_TYPE_NOT_WARPING // hector added
        || sDelayedWarpOp != WARP_OP_NONE) { // hector added
        return false;  // paused, or a warp is already happening // hector added
    } // hector added
// hector added
    // Fresh Mario for the new trial (coins are reset to 0 by the level load itself) // hector added
    gMarioState->health = 0x880; // hector added
    gMarioState->hurtCounter = 0; // hector added
    gMarioState->healCounter = 0; // hector added
    reset_dialog_render_state(); // hector added
// hector added
    // Reload this same course and skip the star select screen (keeps the current star/act) // hector added
    D_8032C9E0 = 1; // hector added
    sWarpDest.type = FLY_WARP_TYPE_CHANGE_LEVEL; // hector added
    sWarpDest.levelNum = gCurrLevelNum; // hector added
    sWarpDest.areaIdx = 1; // hector added
    sWarpDest.nodeId = FLY_COURSE_ENTRY_NODE; // hector added
    sWarpDest.arg = 0; // hector added
// hector added
    // Go straight to the game's "change level" step so the course really reloads. // hector added
    // Without this, warp_area() picks the warp up first and treats it like a teleport // hector added
    // inside the current level: it spawns a SECOND Mario object without unloading the // hector added
    // first one, and nothing gets reloaded. Every extra Mario object runs Mario's // hector added
    // movement again each frame, so Mario got faster with every reset. // hector added
    sTransitionTimer = 0; // hector added
    sTransitionUpdate = NULL; // hector added
    set_play_mode(FLY_PLAY_MODE_CHANGE_LEVEL); // hector added
// hector added
    sStuckFrames = 0; // hector added
    sHaveLastPos = false; // hector added
    return true; // hector added
} // hector added
// hector added
#if FLY_TRAINING_COINS // hector added
// Spawns coins along the recorded trail. Returns how many were placed, // hector added
// or -1 if there's no trail file or it was recorded in a different level. // hector added
static s32 fly_spawn_trail_coins(void) { // hector added
    FILE *file; // hector added
    char line[128]; // hector added
    int level; // hector added
    float x, y, z; // hector added
    s32 count = 0; // hector added
    struct Object *coin; // hector added
// hector added
    file = fopen(FLY_TRAIL_FILE, "r"); // hector added
    if (file == NULL) { // hector added
        return -1; // hector added
    } // hector added
// hector added
    // First line says which level the trail belongs to, e.g. "level 27" // hector added
    if (fgets(line, sizeof(line), file) == NULL || sscanf(line, "level %d", &level) != 1 // hector added
        || level != gCurrLevelNum) { // hector added
        fclose(file); // hector added
        return -1; // hector added
    } // hector added
// hector added
    // Every other line is one point: "x y z" (Mario's feet position when it was recorded) // hector added
    while (count < FLY_TRAIL_MAX && fgets(line, sizeof(line), file) != NULL) { // hector added
        if (sscanf(line, "%f %f %f", &x, &y, &z) != 3) { // hector added
            continue; // hector added
        } // hector added
        coin = spawn_object(gMarioObject, MODEL_YELLOW_COIN, bhvYellowCoin); // hector added
        if (coin == NULL) { // hector added
            break;  // the game's object pool is full // hector added
        } // hector added
        coin->oPosX = x; // hector added
        coin->oPosY = y + FLY_COIN_HOVER; // hector added
        coin->oPosZ = z; // hector added
        count++; // hector added
    } // hector added
// hector added
    fclose(file); // hector added
    return count; // hector added
} // hector added
#endif // hector added
// hector added
// Spawns the training coins. Called from init_level() in level_update.c after Mario is placed. // hector added
void fly_spawn_training_coins(void) { // hector added
#if FLY_TRAINING_COINS // hector added
    struct Surface *floor; // hector added
    struct Object *coin; // hector added
    f32 startX, startZ, groundY, x, y, z; // hector added
    s32 i, j; // hector added
    s32 half = FLY_COIN_GRID / 2; // hector added
// hector added
    s32 trailCoins; // hector added
// hector added
    if (gMarioObject == NULL || gCurrentArea == NULL || !fly_course_allowed()) { // hector added
        return;  // only in the 15 main courses or Peach's Secret Slide // hector added
    } // hector added
// hector added
    // A recorded trail for this level wins over the grid // hector added
    trailCoins = fly_spawn_trail_coins(); // hector added
    if (trailCoins >= 0) { // hector added
        printf("[fly] placed %d trail coins from %s\n", (int) trailCoins, FLY_TRAIL_FILE); // hector added
        return; // hector added
    } // hector added
// hector added
    if (!COURSE_IS_MAIN_COURSE(gCurrCourseNum)) { // hector added
        return;  // no grid on the slide: it doesn't fit a narrow track. Record a trail instead. // hector added
    } // hector added
// hector added
    // Ground under Mario's starting point (he usually starts in the air and drops in) // hector added
    startX = gMarioState->pos[0]; // hector added
    startZ = gMarioState->pos[2]; // hector added
    groundY = find_floor(startX, gMarioState->pos[1] + 100.0f, startZ, &floor); // hector added
    if (floor == NULL) { // hector added
        return; // hector added
    } // hector added
// hector added
    for (i = -half; i <= half; i++) { // hector added
        for (j = -half; j <= half; j++) { // hector added
            if (i == 0 && j == 0) { // hector added
                continue;  // leave Mario's landing spot empty // hector added
            } // hector added
            x = startX + i * FLY_COIN_SPACING; // hector added
            z = startZ + j * FLY_COIN_SPACING; // hector added
// hector added
            // Highest ground below a point a bit above Mario's ground level // hector added
            y = find_floor(x, groundY + FLY_COIN_MAX_STEP, z, &floor); // hector added
            if (floor == NULL) { // hector added
                continue;  // no ground here (off the edge of the course) // hector added
            } // hector added
            if (y < groundY - FLY_COIN_MAX_STEP) { // hector added
                continue;  // big drop: down a cliff or into a pit // hector added
            } // hector added
            if (floor->type == SURFACE_BURNING || floor->type == SURFACE_DEATH_PLANE // hector added
                || floor->type == SURFACE_DEEP_QUICKSAND || floor->type == SURFACE_INSTANT_QUICKSAND) { // hector added
                continue;  // don't lure the fly into lava, death planes or quicksand // hector added
            } // hector added
// hector added
            coin = spawn_object(gMarioObject, MODEL_YELLOW_COIN, bhvYellowCoin); // hector added
            if (coin == NULL) { // hector added
                return;  // the game's object pool is full // hector added
            } // hector added
            coin->oPosX = x; // hector added
            coin->oPosY = y + FLY_COIN_HOVER; // hector added
            coin->oPosZ = z; // hector added
        } // hector added
    } // hector added
#endif // hector added
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
        sLink->airborne = (gMarioState->action & ACT_FLAG_AIR) ? 1 : 0; // hector added
// hector added
        fly_update_stuck(); // hector added
        sLink->stuck_frames = sStuckFrames; // hector added
// hector changed
        fly_sense_nearest_coin(marioYaw); // hector changed
    } else { // hector changed
        sLink->coin_found = 0; // hector changed
        sLink->dist_to_coin = -1.0f; // hector changed
        sLink->wall_collision = 0; // hector changed
        sLink->airborne = 0; // hector added
        sLink->stuck_frames = 0; // hector added
    } // hector added
// hector added
    // Assume the fly isn't driving this frame until its stick is actually applied below // hector added
    sFlyPushing = false; // hector added
// hector added
    sLink->level_num = (uint8_t) gCurrLevelNum;  // lets Python tools know which level this is // hector added
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
    // Slow motion (record_trail.py --slow): stretch this frame so a human can keep up. // hector added
    // Only applies while Python is answering, so a crashed script can't leave the game slow. // hector added
    if (sLink->slow_motion > 1) { // hector added
        u8 factor = (sLink->slow_motion > FLY_SLOWMO_MAX) ? FLY_SLOWMO_MAX : sLink->slow_motion; // hector added
        struct timespec extra = { 0, (long) (factor - 1) * 33333333L };  // extra frames of 1/30 s // hector added
        nanosleep(&extra, NULL); // hector added
    } // hector added
// hector added
    // Python asked for a fresh trial: restart the course (skip this frame's inputs). // hector added
    // If it isn't safe yet, the request stays set and is tried again next frame. // hector added
    if (sLink->reset_request) { // hector added
        if (fly_try_level_reset()) { // hector added
            sLink->reset_request = 0; // hector added
            sLink->reset_count++; // hector added
            return; // hector added
        } // hector added
    } // hector added
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
        // Remember whether the fly was really pushing (used by stuck detection next frame) // hector added
        sFlyPushing = (sLink->stick_x * sLink->stick_x + sLink->stick_y * sLink->stick_y) // hector added
                      >= FLY_STUCK_PUSH * FLY_STUCK_PUSH; // hector added
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
