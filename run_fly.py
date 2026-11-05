
"""
Runs the fly brain live in Super Mario 64.

Usage:
    python3 run_fly.py
    python3 run_fly.py --save learned.npz
    python3 run_fly.py --load learned.npz
    python3 run_fly.py --frozen
    python3 run_fly.py --trial-seconds 45 --trials 20 --log learning.csv --save learned.npz
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
SHM_SIZE = 72

# Must match controller_fly.h exactly
INPUT_FORMAT = "<3fff3fffhhBBBB"
INPUT_OFFSET = 8

OUTPUT_FORMAT = "<ffB"
OUTPUT_OFFSET = 56

RESET_REQUEST_OFFSET = 65
RESET_COUNT_OFFSET = 66

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

    return p.parse_args()


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

    reset_pending = False

    last_reset_count = struct.unpack_from(
        "<B",
        shm,
        RESET_COUNT_OFFSET
    )[0]

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
                "max_stuck_frames"
            ])

            log_file.flush()

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
            "Requested course reset for trial 1."
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

                print(
                    f"\n--- TRIAL {trial} STARTED ---"
                )

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
                "stuck_frames": stuck_frames
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

            # Trial statistics.
            trial_frames += 1

            trial_coins = max(
                trial_coins,
                coins
            )

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
                and time.monotonic() - trial_start
                >= args.trial_seconds
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
                        trial_stuck_max
                    ])

                    log_file.flush()

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

            brain.save_plasticity(args.save)

            print(
                f"Saved learned weights to {args.save}"
            )

        # Close CSV.
        if log_file:

            log_file.close()

        shm.close()

        os.close(fd)


if __name__ == "__main__":
    main()
