# path sm64ex/brain/test_steering.py 
# made by hector
""" 
Checks the fly's steering WITHOUT the game. 

It shows the brain a coin at fixed angles (left, ahead, right, behind), lets the brain settle 
for 2 seconds of simulated time, and prints which way the fly would send Mario. 
Learning is switched off during the test, so your saved weights are never changed. 

  python3 test_steering.py                      fresh brain 
  python3 test_steering.py --load learned.npz   your trained brain 

What "good" looks like: the fly's direction has the SAME SIGN as the coin's angle 
(coin on the left = positive = fly goes left), and gets close to it. 
""" 

import argparse 
import math 

import numpy as np 

from fly_brain import fly_brain 


def settle(brain, state, frames=60): 
    # Fresh start for each test angle: no leftover activity from the previous one 
    brain.firing_rates.fill(0.0) 
    brain.kc_trace.fill(0.0) 
    brain.coin_count = None 
    brain.wedges = None 
    brain.frames_without_coin = 0 
    brain.last_jump = 0 
    for _ in range(frames): 
        rates = brain.step(state) 
    return rates 


def main(): 
    p = argparse.ArgumentParser(description="Test the fly's steering without the game.") 
    p.add_argument("--graph", default="mushroom_body.graphml") 
    p.add_argument("--load", default=None, help="saved weights to test (.npz)") 
    args = p.parse_args() 

    brain = fly_brain(args.graph, load_npz=args.load) 
    brain.apply_plasticity = lambda: None  # no learning during the test 

    print(f"Testing {'weights from ' + args.load if args.load else 'a fresh brain'}") 
    print("coin angle | fly goes  | stick_x  stick_y | left pool  right pool | KCs saturated") 
    print("-" * 82) 

    tests = [("no coin", None)] + [(f"{d:+5d} deg", d) for d in (-150, -90, -45, -15, 0, 15, 45, 90, 150)] 
    for label, deg in tests: 
        state = { 
            "coin_found": 0 if deg is None else 1, 
            "angle_to_coin": 0.0 if deg is None else math.radians(deg), 
            "dist_to_coin": 300.0, 
            "speed": 15.0, 
            "wall": 0, 
            "coins": 0, 
            "wedges": 8, 
        } 
        rates = settle(brain, state) 
        stick_x, stick_y, button_a = brain.decode_motor(rates) 

        # Direction the fly sends Mario, Mario-relative: + = left, - = right (same as angle_to_coin) 
        if abs(stick_x) < 1e-6 and abs(stick_y) < 1e-6: 
            goes = "  (none)" 
        else: 
            goes = f"{math.degrees(math.atan2(-stick_x, stick_y)):+6.0f} deg" 

        left = rates[brain.left_tuners].mean() 
        right = rates[brain.right_tuners].mean() 
        saturated = (rates[brain.kc_idx] > 0.9).mean() * 100 
        print(f"{label:>10} | {goes:>9} | {stick_x:+6.2f}  {stick_y:+6.2f}  | " 
              f"{left:8.3f}  {right:9.3f}  | {saturated:6.1f}%") 

    print() 
    print("Read it like this:") 
    print("  - 'no coin' should go roughly straight (0 deg). A big angle there = a built-in turning bias.") 
    print("  - For each coin angle, 'fly goes' should have the same sign as the coin angle.") 
    print("  - If 'KCs saturated' is near 100%, the brain's own activity is drowning out the coin signal.") 


if __name__ == "__main__": 
    main() 