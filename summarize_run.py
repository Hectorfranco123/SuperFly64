"""
Summarizes a training log: finish rate in blocks of trials, finish times, and where he dies.
Usage:
    python3 summarize_run.py learning_v18.csv
    python3 summarize_run.py learning_v18.csv --block 25     (blocks of 25 trials instead of 50)
"""
import argparse
import csv
from collections import Counter
def main():
    p = argparse.ArgumentParser(description="Summarize a run_fly.py log")
    p.add_argument("log", help="the CSV made by run_fly.py --log")
    p.add_argument("--block", type=int, default=50, help="trials per row in the table (default 50)")
    args = p.parse_args()
    rows = []
    ghosts = 0
    with open(args.log) as f:
        for r in csv.DictReader(f):
            if float(r["seconds"]) < 1.0:  # 0.5 s "ghost finish" rows from the old logging bug
                ghosts += 1
                continue
            rows.append(r)
    if not rows:
        print("No trials in this file.")
        return
    finished = [r["finished"] == "1" for r in rows]
    trials = [int(r["trial"]) for r in rows]
    # Finish rate per block of trials
    print(f"{args.log}: {len(rows)} trials")
    if ghosts:
        print(f"(skipped {ghosts} ghost-finish rows)")
    print()
    print(f"{'Trials':>12}  {'Finished':>10}  {'Rate':>6}")
    for start in range(0, len(rows), args.block):
        chunk = finished[start:start + args.block]
        first, last = trials[start], trials[min(start + args.block, len(rows)) - 1]
        print(f"{first:>5}-{last:<6}  {sum(chunk):>4} / {len(chunk):<3}  {100 * sum(chunk) / len(chunk):>5.0f}%")
    print(f"{'Overall':>12}  {sum(finished):>4} / {len(rows):<3}  {100 * sum(finished) / len(rows):>5.0f}%")
    # Finish times
    times = [float(r["finish_seconds"]) for r in rows if r["finished"] == "1" and r["finish_seconds"]]
    print()
    if times:
        times.sort()
        print(f"Finish times: best {times[0]:.2f} s, middle {times[len(times) // 2]:.2f} s, "
              f"worst {times[-1]:.2f} s  (star time: under 21 s)")
        stars = sum(1 for t in times if t < 21.0)
        if stars:
            print(f"STAR TIMES: {stars}!")
    else:
        print("No finishes.")
    # Deaths: how many coins he had when he died (same number = same spot on the slide)
    deaths = [r for r in rows if r["left_course"] == "1"]
    if deaths:
        coin_counts = Counter(int(r["coins"]) // 5 * 5 for r in deaths)  # grouped in fives
        print()
        print(f"Deaths: {len(deaths)}. Coins when he died (same coins = same spot):")
        for coins, n in sorted(coin_counts.items()):
            print(f"  {coins:>3}-{coins + 4:<3} coins: {n}")
    # Longest streaks
    best_streak = streak = 0
    worst_streak = dstreak = 0
    for done in finished:
        streak = streak + 1 if done else 0
        dstreak = 0 if done else dstreak + 1
        best_streak = max(best_streak, streak)
        worst_streak = max(worst_streak, dstreak)
    print()
    print(f"Longest finish streak: {best_streak}   Longest death streak: {worst_streak}")
if __name__ == "__main__":
    main()