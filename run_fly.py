"""
Runs the fly brain live in Super Mario 64.

Usage:
    python3 run_fly.py
    python3 run_fly.py --save learned.npz
    python3 run_fly.py --load learned.npz
    python3 run_fly.py --frozen
    python3 run_fly.py --trial-seconds 45 --trials 20 --log learning.csv --save learned.npz
    python3 run_fly.py --trial-seconds 120 --trials 40 --log corner.csv --trace corner_trace.csv  (then: python3 analyze_corner.py corner.csv corner_trace.csv)  # hector added
"""

import argparse
import csv
import mmap
import os
import struct
import time

import scipy.sparse as sp

from fly_brain import fly_brain


# Shared memory configuration
SHM_PATH = "/dev/shm/mario_brain"
SHM_SIZE = 76  # 72 -> 76: the game added trail_missed at offset 72  # hector changed

# Must match controller_fly.h exactly
INPUT_FORMAT = "<3fff3fffhhBBBB"
INPUT_OFFSET = 8

OUTPUT_FORMAT = "<ffB"
OUTPUT_OFFSET = 56

RESET_REQUEST_OFFSET = 65
RESET_COUNT_OFFSET = 66
LEVEL_NUM_OFFSET = 67  # hector added
TRAINING_LEVEL_OFFSET = 69  # the course the game says the fly trains in (0 = none yet)  # hector added
FINISH_FRAMES_OFFSET = 70  # Peach's Slide finish-line time in frames (uint16), 0 = not crossed yet  # hector added
STAR_TIME_FRAMES = 630  # under 21 seconds (630 frames) earns the slide's second star  # hector added
FINISH_REWARD_FRAMES = 15  # reward for 0.5 s after the finish (1 s overshot the next trial, see fly_brain.py)  # hector changed
TRAIL_MISSED_OFFSET = 72  # the game's count of trail coins passed without collecting (wraps at 255)  # hector added
DEATH_PUNISH_FRAMES = 30  # keep the brain running 1 s after a death so the death punishment is delivered  # hector added

FRAME_BUDGET_MS = 40.0


def parse_args():
    p = argparse.ArgumentParser(
        description="Run the fly brain live in SM64."
    )

    p.add_argument(
        "--graph",
        default="mushroom_body.graphml"
    )

    p.add_argument(
        "--load",
        default=None
    )

    p.add_argument(
        "--save",
        default=None
    )

    p.add_argument(
        "--frozen",
        action="store_true"
    )

    p.add_argument(
        "--trial-seconds",
        type=float,
        default=0
    )

    p.add_argument(
        "--trials",
        type=int,
        default=0
    )

    p.add_argument(
        "--log",
        default=None
    )
# hector added
    p.add_argument(  # hector added
        "--autosave",  # hector added
        type=int,  # hector added
        default=25,  # hector added
        help="with --save, also save the weights every N finished trials (0 = only at the end)"  # hector added
    )  # hector added
    p.add_argument(  # hector added
        "--trace",  # hector added
        default=None,  # hector added
        help="also log every frame (position, speed, stick) to this CSV, for analyze_corner.py"  # hector added
    )  # hector added

    return p.parse_args()


def save_weights_safely(brain, path):  # hector added
    # Saves to a temporary file first, then swaps it in, so a crash or power loss in the  # hector added
    # middle of saving can never leave you with a half-written (broken) weights file.  # hector added
    final_path = path if path.endswith(".npz") else path + ".npz"  # hector added
    temp_path = final_path[:-4] + ".saving.npz"  # hector added
    brain.save_plasticity(temp_path)  # hector added
    os.replace(temp_path, final_path)  # hector added
# hector added
# hector added
def reset_brain_for_new_trial(brain):
    """
    Reset short-term neural activity.
    Preserve learned synaptic weights.
    """

    brain.coin_count = None
    brain.wedges = None

    brain.frames_without_coin = 0

    brain.firing_rates.fill(0.0)
    brain.kc_trace.fill(0.0)

    brain.last_jump = 0
    if hasattr(brain, "miss_hold"):  # hector added
        brain.miss_hold = 0  # hector added


def main():

    args = parse_args()

    print("Loading connectome:", args.graph)

    brain = fly_brain(
        args.graph,
        load_npz=args.load
    )

    # Ensure CSR format for sparse matrix operations.
    if not isinstance(
        brain.sparse_array,
        (sp.csr_array, sp.csr_matrix)
    ):
        brain.sparse_array = sp.csr_array(
            brain.sparse_array
        )

    # Frozen mode disables learning.
    if args.frozen:
        brain.set_learning_rate(0.0)
        brain.apply_plasticity = lambda: None

    mode = "frozen" if args.frozen else "learning"

    print(
        f"Brain ready: {mode}, "
        f"learning rate: {brain.get_learning_rate()}"
    )

    # Connect to game shared memory.
    fd = os.open(SHM_PATH, os.O_RDWR)

    shm = mmap.mmap(
        fd,
        SHM_SIZE,
        access=mmap.ACCESS_WRITE
    )

    last_frame = None

    trial_mode = args.trial_seconds > 0

    trial = 0

    trial_start = time.monotonic()

    trial_frames = 0
    trial_min_wedges = 8
    trial_wall_frames = 0
    trial_stuck_max = 0

    trial_coins = 0
    coins_ready = False  # becomes True once the game's coin count resets to 0 for the new trial  # hector added
    trial_left_course = 0  # hector added
    trial_missed = 0  # coins passed without collecting them this trial  # hector added
    prev_target = None  # the coin the game was pointing the fly at last frame  # hector added
    prev_coins = 0  # hector added
    miss_check = 0  # frames left to see whether the coin count rises (then it wasn't a miss)  # hector added
    miss_check_coins = 0  # hector added
    last_trail_missed = None  # the game's missed-coin count last frame  # hector added
    death_punish_left = 0  # frames left to deliver the death punishment before ending the trial  # hector added
    trial_finished = 0  # 1 = crossed the finish line this trial  # hector added
    trial_finish_seconds = ""  # the slide timer at the finish line  # hector added
    finish_reward_left = 0  # frames of finish reward still to give  # hector added
    finish_ready = False  # becomes True once the game's finish time reads 0 for the new trial  # hector added

    reset_pending = False

    last_reset_count = struct.unpack_from(
        "<B",
        shm,
        RESET_COUNT_OFFSET
    )[0]

    # The game decides the training course: the first course Mario is in while this script runs.  # hector changed
    # If Mario ends up in a different level (he died or exited to the castle), the trial  # hector added
    # ends early and the game sends him back into that course.  # hector changed
    known_course = shm[TRAINING_LEVEL_OFFSET]  # hector changed
    in_course = False  # has Mario been seen inside the training course during this trial?  # hector changed
    if known_course:  # hector added
        print(f"Training course: level {known_course}")  # hector added
    else:  # hector added
        print("No training course yet: walk Mario into the course you want (e.g. Peach's Secret Slide).")  # hector changed
        print("Trials start once he's inside.")  # hector added
# hector added
    # Timing statistics.
    step_times = []
    slow_frames = 0

    # CSV logging.
    log_file = None
    log_writer = None

    if args.log:

        new_file = not os.path.exists(args.log)

        log_file = open(
            args.log,
            "a",
            newline=""
        )

        log_writer = csv.writer(log_file)

        if new_file:
            log_writer.writerow([
                "mode",
                "trial",
                "seconds",
                "frames",
                "coins",
                "min_wedges",
                "wall_frames",
                "max_stuck_frames",  # hector changed
                "left_course",  # hector changed
                "finished",  # hector added
                "finish_seconds",  # hector changed
                "missed"  # hector added
            ])

            log_file.flush()

    # Per-frame trace: where Mario is, how fast, and what the fly pressed, every frame of every trial.  # hector added
    # analyze_corner.py compares deaths and finishes at the corner where he keeps flying off.  # hector added
    trace_file = None  # hector added
    trace_writer = None  # hector added
    if args.trace:  # hector added
        new_trace = not os.path.exists(args.trace)  # hector added
        trace_file = open(args.trace, "a", newline="")  # hector added
        trace_writer = csv.writer(trace_file)  # hector added
        if new_trace:  # hector added
            trace_writer.writerow(["trial", "frame", "x", "y", "z", "yaw", "speed", "stick_x", "stick_y",  # hector added
                                   "button_a", "airborne", "coins", "angle_to_coin", "dist_to_coin", "wall"])  # hector added
# hector added
    # Request reset to start trial 1.
    if trial_mode:

        struct.pack_into(
            "<B",
            shm,
            RESET_REQUEST_OFFSET,
            1
        )

        reset_pending = True

        print(
            "Requested course reset for trial 1 (it happens once Mario is in a course)."  # hector changed
        )

    try:

        while True:

            # Wait for a new game frame.
            game_frame, = struct.unpack_from(
                "<I",
                shm,
                0
            )

            if game_frame == last_frame:

                time.sleep(0.0005)
                continue

            # Read game telemetry.
            (
                x, y, z,
                yaw,
                speed,
                cx, cy, cz,
                angle_to_coin,
                dist_to_coin,
                coins,
                wedges,
                wall,
                coin_found,
                airborne,
                stuck_frames
            ) = struct.unpack_from(
                INPUT_FORMAT,
                shm,
                INPUT_OFFSET
            )

            # Detect completed course reset.
            reset_count, = struct.unpack_from(
                "<B",
                shm,
                RESET_COUNT_OFFSET
            )

            if reset_count != last_reset_count:

                last_reset_count = reset_count

                reset_pending = False

                reset_brain_for_new_trial(brain)

                trial += 1

                trial_start = time.monotonic()

                trial_frames = 0
                trial_min_wedges = 8
                trial_wall_frames = 0
                trial_stuck_max = 0
                trial_coins = 0
                # For the first few frames after a reset the game still reports the LAST trial's coins,  # hector added
                # which got logged as this trial's (the trial after a finish showed the same count).  # hector added
                coins_ready = False  # hector added
                trial_left_course = 0  # hector added
                trial_missed = 0  # hector added
                prev_target = None  # hector added
                miss_check = 0  # hector added
                death_punish_left = 0  # hector added
                trial_finished = 0  # hector added
                trial_finish_seconds = ""  # hector added
                finish_reward_left = 0  # hector added
                # For the first frames after a reset the game can still report the LAST trial's finish  # hector added
                # time, which logged 0.5 s "ghost finishes" (6 in the v15 run) and gave an extra reward.  # hector added
                finish_ready = False  # hector added
# hector added
                # The new level may take a few frames to load, so don't judge "left the course"  # hector added
                # until Mario has been seen back inside it  # hector added
                in_course = False  # hector added

                print(
                    f"\n--- TRIAL {trial} STARTED ---"
                )

            # Did Mario die or leave the course? (The level number changed under him.)  # hector added
            level_num = shm[LEVEL_NUM_OFFSET]  # hector added
            training_level = shm[TRAINING_LEVEL_OFFSET]  # hector added
            if training_level and training_level != known_course:  # hector added
                known_course = training_level  # hector added
                print(f"\nTraining course: level {known_course}")  # hector added
            left_course = False  # hector added
            if training_level and level_num == training_level:  # hector changed
                in_course = True  # hector added
            elif in_course and not reset_pending:  # hector added
                left_course = True  # hector added
                in_course = False  # hector added
                trial_left_course = 1  # hector added
                print("\nMario left the course (died or exited). Sending him back in.")  # hector added
                # Before, the trial ended (and the brain was reset) on this same frame, so the death  # hector added
                # punishment was cut off after one frame. Keep the brain running for 1 s first.  # hector added
                death_punish_left = DEATH_PUNISH_FRAMES  # hector added
            dying = death_punish_left > 0  # hector added
            if dying:  # hector added
                death_punish_left -= 1  # hector added
            if trial_left_course and death_punish_left == 0 and not trial_mode and not reset_pending:  # hector changed
                # No trials: after the death punishment, put Mario back into the course  # hector changed
                struct.pack_into("<B", shm, RESET_REQUEST_OFFSET, 1)  # hector added
                reset_pending = True  # hector added
# hector added
            # Did Mario cross the Peach's Slide finish line? (Only counts inside the training course.)  # hector added
            finish_frames, = struct.unpack_from("<H", shm, FINISH_FRAMES_OFFSET)  # hector added
            if finish_frames == 0:  # hector added
                finish_ready = True  # the old finish time has cleared: a new finish is real  # hector added
            if finish_frames and finish_ready and in_course and not trial_finished and not reset_pending:  # hector changed
                trial_finished = 1  # hector added
                trial_finish_seconds = round(finish_frames / 30.0, 2)  # hector added
                finish_reward_left = FINISH_REWARD_FRAMES  # hector added
                star = "  STAR TIME (under 21 s)!" if finish_frames < STAR_TIME_FRAMES else ""  # hector added
                print(f"\nFINISHED the slide in {trial_finish_seconds} s.{star}")  # hector added
                if hasattr(brain, "finish_reward"):  # hector added
                    print(f"Finish reward strength: {brain.finish_reward(trial_finish_seconds):.1f} "  # hector added
                          f"(a coin is 1.0; max {brain.finish_reward_max:.1f} at {brain.star_time_seconds:.0f} s or faster)")  # hector added
            finishing = finish_reward_left > 0  # hector added
            if finishing:  # hector added
                finish_reward_left -= 1  # hector added
            if trial_finished and finish_reward_left == 0 and not trial_mode and not reset_pending:  # hector added
                # No trials: after the finish reward, start again from the top of the slide  # hector added
                struct.pack_into("<B", shm, RESET_REQUEST_OFFSET, 1)  # hector added
                reset_pending = True  # hector added
# hector added
            # Missed coin: the GAME now counts trail coins Mario passes without collecting (offset 72).  # hector changed
            # The old check here (target coin changed but the coin count didn't rise) no longer works:  # hector changed
            # with look-ahead aiming the target is a spot further down the trail, not the next coin.  # hector changed
            missed = 0  # hector added
            trail_missed_now = shm[TRAIL_MISSED_OFFSET]  # hector added
            if last_trail_missed is not None and in_course and not reset_pending:  # hector added
                new_misses = (trail_missed_now - last_trail_missed) % 256  # the count wraps at 255  # hector added
                if 0 < new_misses < 20:  # (a huge jump would be a level reload, not real misses)  # hector added
                    missed = 1  # hector added
                    trial_missed += new_misses  # hector added
            last_trail_missed = trail_missed_now  # hector added

            # Build neural input state.
            state = {
                "coin_found": coin_found,
                "angle_to_coin": angle_to_coin,
                "dist_to_coin": dist_to_coin,
                "speed": speed,
                "wall": wall,
                "coins": coins,
                "wedges": wedges,
                "airborne": airborne,
                "stuck_frames": stuck_frames,  # hector changed
                "dead": 1 if left_course else 0,  # fly_brain.py punishes this (PPL1)  # hector added
                "missed": missed,  # passed a coin without collecting it (small punishment)  # hector added
                "finished": 1 if finishing else 0,  # fly_brain.py rewards this (PAM)  # hector added
                "finish_seconds": trial_finish_seconds if finishing else 0,  # faster finish = bigger reward  # hector added
            }

            # Run brain.
            t0 = time.perf_counter()

            rates = brain.step(state)

            stick_x, stick_y, button_a = (
                brain.decode_motor(rates)
            )

            step_ms = (
                time.perf_counter() - t0
            ) * 1000.0

            step_times.append(step_ms)

            if step_ms > FRAME_BUDGET_MS:
                slow_frames += 1

            # Send controller output.
            struct.pack_into(
                OUTPUT_FORMAT,
                shm,
                OUTPUT_OFFSET,
                stick_x,
                stick_y,
                button_a
            )

            # Write brain_frame LAST.
            struct.pack_into(
                "<I",
                shm,
                4,
                game_frame
            )

            last_frame = game_frame

            if trace_writer and in_course and not reset_pending and trial > 0:  # hector added
                trace_writer.writerow([trial, trial_frames, round(x, 1), round(y, 1), round(z, 1),  # hector added
                                       round(yaw, 4), round(speed, 2), round(float(stick_x), 3),  # hector added
                                       round(float(stick_y), 3), int(button_a), airborne, coins,  # hector added
                                       round(angle_to_coin, 4), round(dist_to_coin, 1), wall])  # hector added

            # Trial statistics.
            trial_frames += 1

            if coins == 0:  # hector added
                coins_ready = True  # the level has reloaded: coin count is back to 0  # hector added
            if coins_ready:  # hector added
                trial_coins = max(  # hector changed
                    trial_coins,  # hector changed
                    coins  # hector changed
                )  # hector changed

            trial_min_wedges = min(
                trial_min_wedges,
                wedges
            )

            trial_wall_frames += wall

            trial_stuck_max = max(
                trial_stuck_max,
                stuck_frames
            )

            # Check whether trial has finished.
            trial_over = (
                trial_mode
                and not reset_pending
                and trial > 0
                and (
                    (trial_left_course and death_punish_left == 0)  # died: end after the death punishment  # hector changed
                    or (trial_finished and finish_reward_left == 0)  # crossed the finish line  # hector added
                    or time.monotonic() - trial_start  # hector changed
                    >= args.trial_seconds
                )  # hector added
            )

            if trial_over:

                seconds = (
                    time.monotonic() - trial_start
                )

                print(
                    f"\n--- TRIAL {trial} COMPLETE ---"
                )

                print(
                    f"Coins: {trial_coins}"
                )

                print(
                    f"Duration: {seconds:.1f}s"
                )

                print(
                    f"Lowest health: "
                    f"{trial_min_wedges}/8"
                )

                print(
                    f"Frames: {trial_frames}"
                )

                if trial_left_course:  # hector added
                    print("Ended early: Mario left the course (died or exited)")  # hector added
                if trial_finished:  # hector added
                    print(f"Finished the slide in {trial_finish_seconds} s")  # hector added
                print(f"Missed coins: {trial_missed}")  # hector added
# hector added
                # Save trial statistics.
                if log_writer:

                    log_writer.writerow([
                        mode,
                        trial,
                        round(seconds, 1),
                        trial_frames,
                        trial_coins,
                        trial_min_wedges,
                        trial_wall_frames,
                        trial_stuck_max,  # hector changed
                        trial_left_course,  # hector changed
                        trial_finished,  # hector added
                        trial_finish_seconds,  # hector changed
                        trial_missed  # hector added
                    ])

                    log_file.flush()
                if trace_file:  # hector added
                    trace_file.flush()  # hector added

                # Stop after requested number of trials.
                if args.trials and trial >= args.trials:

                    print(
                        f"\nFinished {trial} trials."
                    )

                    break

                # Request next course reset.
                struct.pack_into(
                    "<B",
                    shm,
                    RESET_REQUEST_OFFSET,
                    1
                )

                reset_pending = True

                # Autosave every N trials so a crash or sleep doesn't lose hours of learning  # hector added
                if args.save and args.autosave and trial % args.autosave == 0:  # hector added
                    save_weights_safely(brain, args.save)  # hector added
                    print(f"Autosaved learned weights to {args.save} (after trial {trial})")  # hector added
# hector added
            # Print status once per second.
            if game_frame % 30 == 0:

                if step_times:

                    avg = (
                        sum(step_times) /
                        len(step_times)
                    )

                    maximum = max(step_times)

                else:

                    avg = 0
                    maximum = 0

                if coin_found:

                    coin_text = (
                        f"coin {dist_to_coin:.0f} away "
                        f"{angle_to_coin * 57.2958:+.0f} deg"
                    )

                else:

                    coin_text = "no coin"

                print(
                    f"frame {game_frame} | "
                    f"{coin_text} | "
                    f"stick=({stick_x:+.2f}, "
                    f"{stick_y:+.2f}) | "
                    f"A={button_a} | "
                    f"coins={coins} | "
                    f"health={wedges} | "
                    f"wall={wall} | "
                    f"stuck={stuck_frames} | "
                    f"brain={avg:.1f}ms avg / "
                    f"{maximum:.1f}ms max"
                )

                # What the fly is learning: dopamine bursts this frame, and how much its  # hector added
                # approach (go) and avoidance (stop/jump) connections have changed (x1.00 = unchanged)  # hector added
                if hasattr(brain, "learning_summary"):  # hector added
                    approach_x, avoidance_x = brain.learning_summary()  # hector added
                    print(f"      learning: reward burst {brain.last_reward_burst:.2f}  "  # hector added
                          f"punish burst {brain.last_punish_burst:.2f}  "  # hector added
                          f"approach x{approach_x:.2f}  avoidance x{avoidance_x:.2f}  "  # hector changed
                          f"missed so far {trial_missed}")  # hector added

                if slow_frames:

                    print(
                        f"WARNING: {slow_frames} frames "
                        f"exceeded {FRAME_BUDGET_MS:.0f}ms."
                    )

                step_times.clear()

                slow_frames = 0

    except KeyboardInterrupt:

        print("\nStopping fly brain.")

    finally:

        # Release controller inputs.
        struct.pack_into(
            OUTPUT_FORMAT,
            shm,
            OUTPUT_OFFSET,
            0.0,
            0.0,
            0
        )

        # Save learned weights.
        if args.save:

            save_weights_safely(brain, args.save)  # hector changed

            print(
                f"Saved learned weights to {args.save}"
            )

        # Close CSV.
        if log_file:

            log_file.close()
        if trace_file:  # hector added
            trace_file.close()  # hector added

        shm.close()

        os.close(fd)


if __name__ == "__main__":
    main()