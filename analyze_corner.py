"""  # hector added
Compares the trials where Mario dies at the corner with the ones where he makes it.  # hector added
  # hector added
Record first (logs every frame to a trace file):  # hector added
    python3 run_fly.py --trial-seconds 120 --trials 40 --log corner.csv --trace corner_trace.csv \\  # hector added
        --load learned_best_67pct.npz --save corner_scratch.npz  # hector added
Then:  # hector added
    python3 analyze_corner.py corner.csv corner_trace.csv  # hector added
  # hector added
How it works:  # hector added
  1. Where each death trial fell off (first frame of "falling off", airborne == 2). The middle  # hector added
     of those spots is "the corner".  # hector added
  2. Where the dying runs were 3, 2, 1 and 0.5 s before falling: those become checkpoints.  # hector added
  3. For EVERY trial (deaths and finishes), the frame where Mario passed closest to each checkpoint:  # hector added
     his speed, his facing compared with the way the track goes, how hard the fly pushed and turned,  # hector added
     and how far left/right of the checkpoint he was.  # hector added
  4. Prints deaths vs finishes side by side, and draws corner_paths.png (top-down view).  # hector added
"""  # hector added
  # hector added
import csv  # hector added
import math  # hector added
import sys  # hector added
import warnings  # hector added
from collections import defaultdict  # hector added
  # hector added
import numpy as np  # hector added
  # hector added
FPS = 30  # hector added
CHECKPOINTS = [(90, "3 s before"), (60, "2 s before"), (30, "1 s before"), (15, "0.5 s before")]  # hector added
MAX_MATCH_DISTANCE = 600.0  # a trial must pass within this many units of a checkpoint to count  # hector added
  # hector added
  # hector added
def load_trials(log_path):  # hector added
    outcome = {}  # trial -> "death" / "finish"  # hector added
    with open(log_path) as f:  # hector added
        for row in csv.DictReader(f):  # hector added
            if float(row["seconds"]) < 1.0:  # skip old 0.5 s "ghost finish" rows  # hector added
                continue  # hector added
            t = int(row["trial"])  # hector added
            if row["finished"] == "1":  # hector added
                outcome[t] = "finish"  # hector added
            elif row["left_course"] == "1":  # hector added
                outcome[t] = "death"  # hector added
    return outcome  # hector added
  # hector added
  # hector added
def load_trace(trace_path):  # hector added
    frames = defaultdict(list)  # hector added
    with open(trace_path) as f:  # hector added
        for row in csv.DictReader(f):  # hector added
            frames[int(row["trial"])].append(row)  # hector added
    cols = ["x", "y", "z", "yaw", "speed", "stick_x", "stick_y", "airborne"]  # hector added
    out = {}  # hector added
    for t, rows in frames.items():  # hector added
        out[t] = {c: np.array([float(r[c]) for r in rows]) for c in cols}  # hector added
    return out  # hector added
  # hector added
  # hector added
def fall_frame(tr):  # hector added
    idx = np.where(tr["airborne"] == 2)[0]  # hector added
    return int(idx[0]) if len(idx) else len(tr["x"]) - 1  # hector added
  # hector added
  # hector added
def angle_diff(a):  # hector added
    return (a + math.pi) % (2 * math.pi) - math.pi  # hector added
  # hector added
  # hector added
def describe(vals):  # hector added
    vals = [v for v in vals if v is not None]  # hector added
    if not vals:  # hector added
        return "   -  ", None, 0  # hector added
    a = np.array(vals)  # hector added
    return f"{a.mean():7.2f} ±{a.std():5.2f}", a, len(a)  # hector added
  # hector added
  # hector added
def welch_p(a, b):  # hector added
    try:  # hector added
        from scipy.stats import ttest_ind  # hector added
        if a is None or b is None or len(a) < 2 or len(b) < 2:  # hector added
            return None  # hector added
        with warnings.catch_warnings():  # hector added
            warnings.simplefilter("ignore")  # hector added
            p = ttest_ind(a, b, equal_var=False).pvalue  # hector added
        return None if np.isnan(p) else p  # all values identical: no test possible  # hector added
    except Exception:  # hector added
        return None  # hector added
  # hector added
  # hector added
def main():  # hector added
    if len(sys.argv) < 3:  # hector added
        print(__doc__)  # hector added
        sys.exit(1)  # hector added
    outcome = load_trials(sys.argv[1])  # hector added
    trace = load_trace(sys.argv[2])  # hector added
    deaths = [t for t, o in outcome.items() if o == "death" and t in trace]  # hector added
    finishes = [t for t, o in outcome.items() if o == "finish" and t in trace]  # hector added
    print(f"Trials with a trace: {len(deaths)} deaths, {len(finishes)} finishes")  # hector added
    if len(deaths) < 3 or len(finishes) < 3:  # hector added
        print("Need at least 3 of each. Record more trials.")  # hector added
        sys.exit(1)  # hector added
  # hector added
    # 1. The corner = middle of the fall-off spots  # hector added
    falls = np.array([[trace[t][c][fall_frame(trace[t])] for c in ("x", "y", "z")] for t in deaths])  # hector added
    corner = np.median(falls, axis=0)  # hector added
    spread = np.median(np.linalg.norm(falls - corner, axis=1))  # hector added
    print(f"\nThe corner (middle fall-off spot): x={corner[0]:.0f} y={corner[1]:.0f} z={corner[2]:.0f}  "  # hector added
          f"(deaths fell off within ~{spread:.0f} units of it)")  # hector added
    far = [t for t, p in zip(deaths, falls) if np.linalg.norm(p - corner) > 1500]  # hector added
    if far:  # hector added
        print(f"  Note: {len(far)} deaths happened somewhere else (trials {far[:10]})")  # hector added
    deaths = [t for t, p in zip(deaths, falls) if np.linalg.norm(p - corner) <= 1500]  # hector added
  # hector added
    # 2. Checkpoints on the way in (where the dying runs were k frames before falling)  # hector added
    cps = []  # hector added
    for k, name in CHECKPOINTS:  # hector added
        pts = []  # hector added
        for t in deaths:  # hector added
            f = fall_frame(trace[t]) - k  # hector added
            if f >= 0:  # hector added
                pts.append([trace[t][c][f] for c in ("x", "y", "z")])  # hector added
        if pts:  # hector added
            cps.append((k, name, np.median(np.array(pts), axis=0)))  # hector added
    points = [c[2] for c in cps] + [corner]  # hector added
  # hector added
    # 3. Measure every trial at each checkpoint  # hector added
    print("\nDeaths vs finishes as Mario passes each checkpoint (mean ± spread).")  # hector added
    print("  facing vs track: degrees between where Mario faces and the way the track goes")  # hector added
    print("  side offset: units left (+) / right (-) of the checkpoint, looking down the track")  # hector added
    print("  p: chance the difference is luck (under 0.05 = a real difference)\n")  # hector added
    biggest = []  # hector added
    for i, (k, name, cp) in enumerate(cps):  # hector added
        nxt = points[i + 1]  # hector added
        d = np.array([nxt[0] - cp[0], nxt[2] - cp[2]])  # hector added
        d = d / (np.linalg.norm(d) or 1.0)  # hector added
        track_yaw = math.atan2(d[0], d[1])  # SM64: facing (sin yaw, cos yaw) in x, z  # hector added
        stats = {"death": defaultdict(list), "finish": defaultdict(list)}  # hector added
        for group, trials in (("death", deaths), ("finish", finishes)):  # hector added
            for t in trials:  # hector added
                tr = trace[t]  # hector added
                pos = np.stack([tr["x"], tr["y"], tr["z"]], axis=1)  # hector added
                dist = np.linalg.norm(pos - cp, axis=1)  # hector added
                j = int(np.argmin(dist))  # hector added
                if dist[j] > MAX_MATCH_DISTANCE:  # hector added
                    continue  # never came near this checkpoint  # hector added
                off = pos[j] - cp  # hector added
                side = off[0] * d[1] - off[2] * d[0]  # hector added
                s = stats[group]  # hector added
                s["speed"].append(tr["speed"][j])  # hector added
                s["facing vs track (deg)"].append(math.degrees(angle_diff(tr["yaw"][j] - track_yaw)))  # hector added
                s["push (stick size)"].append(math.hypot(tr["stick_x"][j], tr["stick_y"][j]))  # hector added
                s["turn (stick left/right)"].append(tr["stick_x"][j])  # hector added
                s["side offset (units)"].append(side)  # hector added
        nd = len(stats["death"]["speed"])  # hector added
        nf = len(stats["finish"]["speed"])  # hector added
        print(f"--- {name} the corner  (deaths n={nd}, finishes n={nf}) ---")  # hector added
        print(f"  {'':26s} {'deaths':>15s}   {'finishes':>15s}      p")  # hector added
        for key in stats["death"]:  # hector added
            dtxt, da, _ = describe(stats["death"][key])  # hector added
            ftxt, fa, _ = describe(stats["finish"][key])  # hector added
            p = welch_p(da, fa)  # hector added
            ptxt = f"{p:.3f}" if p is not None else "  -"  # hector added
            flag = "  <-- different" if p is not None and p < 0.05 else ""  # hector added
            print(f"  {key:26s} {dtxt:>15s}   {ftxt:>15s}   {ptxt}{flag}")  # hector added
            if p is not None and da is not None and fa is not None:  # hector added
                sd = math.sqrt((da.var() + fa.var()) / 2) or 1.0  # hector added
                biggest.append((abs(da.mean() - fa.mean()) / sd, p, name, key, da.mean(), fa.mean()))  # hector added
        print()  # hector added
  # hector added
    # Plain-English summary: the biggest real differences  # hector added
    real = sorted([b for b in biggest if b[1] < 0.05], reverse=True)  # hector added
    print("=== Biggest differences between deaths and finishes ===")  # hector added
    if not real:  # hector added
        print("None of the measures clearly differ. The deaths may come from something not logged here")  # hector added
        print("(for example, a bump or a jump), or more trials are needed.")  # hector added
    for size, p, name, key, dm, fm in real[:5]:  # hector added
        print(f"  {name} the corner, {key}: deaths {dm:.2f} vs finishes {fm:.2f}  (p={p:.3f})")  # hector added
  # hector added
    # 4. Top-down picture of the paths around the corner  # hector added
    try:  # hector added
        import matplotlib  # hector added
        matplotlib.use("Agg")  # hector added
        import matplotlib.pyplot as plt  # hector added
        fig, ax = plt.subplots(figsize=(8, 8))  # hector added
        for group, trials, color in (("finishes", finishes, "tab:blue"), ("deaths", deaths, "tab:red")):  # hector added
            for n, t in enumerate(trials):  # hector added
                tr = trace[t]  # hector added
                near = np.hypot(tr["x"] - corner[0], tr["z"] - corner[2]) < 2500  # hector added
                end = fall_frame(tr) + 1 if group == "deaths" else len(tr["x"])  # hector added
                near[end:] = False  # hector added
                ax.plot(tr["x"][near], tr["z"][near], color=color, alpha=0.35, lw=1,  # hector added
                        label=group if n == 0 else None)  # hector added
        ax.scatter(falls[:, 0], falls[:, 2], color="black", s=12, zorder=3, label="fell off here")  # hector added
        for k, name, cp in cps:  # hector added
            ax.scatter([cp[0]], [cp[2]], marker="x", color="green", s=60, zorder=4)  # hector added
            ax.annotate(name, (cp[0], cp[2]), fontsize=8, color="green")  # hector added
        ax.set_xlim(corner[0] - 2500, corner[0] + 2500)  # hector added
        ax.set_ylim(corner[2] - 2500, corner[2] + 2500)  # hector added
        ax.set_aspect("equal")  # hector added
        ax.set_xlabel("x")  # hector added
        ax.set_ylabel("z")  # hector added
        ax.set_title("Paths around the corner: deaths (red) vs finishes (blue)")  # hector added
        ax.legend(loc="best")  # hector added
        fig.savefig("corner_paths.png", dpi=120, bbox_inches="tight")  # hector added
        print("\nSaved corner_paths.png (top-down view of the corner)")  # hector added
    except ImportError:  # hector added
        print("\n(matplotlib not installed, so no picture: pip install matplotlib)")  # hector added
  # hector added
  # hector added
if __name__ == "__main__":  # hector added
    main()  # hector added
#python3 analyze_corner.py corner.csv corner_trace.csv
#pip install matplotlib