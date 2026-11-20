import time

import networkx as nx
import numpy as np
import scipy.sparse as sp


class fly_brain:
    
    def __init__(self, graphml_path, load_npz = None):
        # Load the serialized biological connectome graph from the GraphML XML file
        G = nx.read_graphml(graphml_path)
        self.frames_without_coin = 0 #hector added: tracks how many frames have passed without a coin being found, to reset the brain's state and avoid learning from a death

        self.time_punishment_threshold = 150  # 5 seconds at 30 FPS #hector added: if Mario has not found a coin in this many frames, the brain will reset its state to avoid learning from a death

        self.death_detected = False #hector added: tracks if Mario has died in the current run, to reset the brain's state and avoid learning from a death
        # Extract all nodes with their associated biological attribute dictionaries as tuples: (node_id, data)
        self.node_list = list(G.nodes(data = True))

        # Explicitly track 18-digit FlyWire root_ids in exact iteration order to preserve deterministic mapping
        self.node_ids = []

        # Integer index lists: store array indices (0 to 5585) corresponding to each functional cell class
        self.kc_idx = []    # Kenyon Cells: sparse sensory expansion layer (inputs)
        self.mbon_idx = []  # Mushroom Body Output Neurons: motor control readout (outputs)
        self.pam_idx = []   # Protocerebral Anterior Medial: appetitive dopaminergic reward cluster
        self.ppl_idx = []   # Protocerebral Posterior Lateral: aversive dopaminergic punishment cluster

        # List to store the continuous fast synaptic sign/valence scalar for each presynaptic neuron
        self.val_vectors = []

        # Sigma value for how wide the bell curve for the fly should be (radians)
        self.sigma = 0.35

        # Alpha value for the integration rate (how much of the previous firing rate the neurons should retain,
        # neurons have membrance capacitance, they don't instantly lose their previous state)
        self.alpha = 0.3

        # Scalar learning rate (eta) governing the magnitude of dopamine-gated synaptic weight updates
        # Learning is now RELATIVE: each frame a synapse changes by (learning_rate x dopamine x KC trace) times  # hector added
        # ITS OWN original strength. Before, the change was absolute (up to ~0.04 per frame) while the  # hector added
        # synapses start around 0.005, so a second of dopamine slammed them to 0 or 1 (what both runs showed).  # hector added
        self.learning_rate = 0.0025  # tested: each coin = about +1% approach, one stuck episode = about -10%  # hector changed
        self.max_weight_factor = 20.0  # a learned synapse can grow to 20x its original strength, or shrink to 0  # hector changed
        self.weight_recovery = 0.0005  # every frame, learned weights drift 0.05% of the way back to original  # hector added
        #   (slow forgetting: ~1 minute timescale) so a bad stretch can't lock the fly into doing nothing forever  # hector added
        self.coin_reward_frames = 5  # hold the coin reward for 5 frames (it used to be 1 frame vs. long punishments)  # hector added
        self.reward_hold = 0  # frames of coin reward left  # hector added
        self.hit_punish_frames = 5  # hold the punishment for losing health for 5 frames  # hector added
        self.death_punish_frames = 30  # hold the punishment for dying for 30 frames (1 s)  # hector changed
        self.punish_hold = 0  # frames of hit punishment left  # hector changed
        self.death_hold = 0  # frames of death punishment left  # hector added
        # How strongly dying and falling off TEACH (a coin's reward is 1.0). They count more than a coin, so  # hector added
        # that going too fast and flying off the slide costs more than the extra coins that speed bought.  # hector added
        # (Last run: coins kept rewarding speed, the fly sped up every trial and flew off earlier and earlier.)  # hector added
        # Lowered from 3.0: one death (3.0 x 30 frames = 90) outweighed almost two finishes (~3.5 x 15 = 52),  # hector added
        # so a few deaths in a row cut the forward drive, he slowed, turned weaker, and died more (a slump).  # hector added
        # At 1.5 one death (45) is about the same size as one finish.  # hector added
        self.death_punishment = 1.5  # hector changed
        self.fall_punishment = 2.0  # while falling off the course (game reports airborne == 2)  # hector added
        # Finishing the slide: the faster the finish, the bigger the reward (a coin is 1.0).  # hector added
        #   finish at finish_slow_seconds or slower -> finish_reward_min  # hector added
        #   finish at star_time_seconds or faster   -> finish_reward_max  # hector added
        #   in between, it rises evenly as the time gets closer to star time  # hector added
        # Lowered from 3.0 / 8.0: in 500 trials, the trial right after EVERY finish (99 of 99) flew off  # hector added
        # early, at ~41 s. The big finish reward pushed the forward drive up too much, the next trial  # hector added
        # was too fast, then deaths slowly pushed it back down: learning swung back and forth (stuck at  # hector added
        # ~20%) instead of settling. A smaller finish reward (held 0.5 s instead of 1 s in run_fly.py)  # hector added
        # is about 6x weaker overall, so one finish nudges the fly instead of overshooting it.  # hector added
        # going faster on top of that is the bonus.  # hector added
        self.finish_reward_min = 2.0  # hector changed
        self.finish_reward_max = 4.0  # hector changed
        self.star_time_seconds = 21.0  # under 21 s earns the slide's second star  # hector added
        # Narrowed from 40: over 21-40 s the reward only changed ~0.1 per second, so a 25.3 s finish (3.55)  # hector added
        # and a 26.5 s finish (3.42) felt the same and he settled at ~26 s. Over 21-28 s each second faster  # hector added
        # is worth ~0.29 (25.3 s -> 2.77, 26.5 s -> 2.43), so faster finishes clearly teach more.  # hector added
        self.finish_slow_seconds = 28.0  # hector changed
        # ---- Situation cells (lets the fly learn WHERE to slow down) ----  # hector added
        # Before, every Kenyon Cell sensed ONE thing (direction, distance, speed or walls), so a fall  # hector added
        # punished the same cells that were active on the straights: the fly could only learn one  # hector added
        # overall speed (flat ~20% finishes over 1,265 trials). Real Kenyon Cells combine several inputs,  # hector added
        # so now some do too: each "situation cell" fires for one combination of SPEED and how SHARP the  # hector added
        # turn toward the next coin is.  # hector added
        self.kc_split = [0.30, 0.15, 0.05, 0.10, 0.40]  # direction, distance, speed, wall, situation cells  # hector added
        self.situation_speed_max = 2.5  # situation cells cover speeds up to 2.5x running speed (80 units/frame)  # hector added
        self.situation_speed_width = 0.3  # how wide each cell's speed range is (in units of running speed)  # hector added
        self.situation_turn_width = 0.35  # how wide each cell's turn range is (radians, about 20 degrees)  # hector added
        self.situation_active_fraction = 0.25  # only the 25% best-matching situation cells fire  # hector added
        # How fast the memory of "which cells were just active" fades each frame. 0.9 faded in ~1/3 s, but  # hector added
        # a fall comes ~1 s after the mistake at the turn; 0.97 keeps it for about a second.  # hector added
        self.trace_decay = 0.97  # hector added
        self.learn_sparse_cells_only = True  # only direction + situation cells learn (see the plasticity map)  # hector added
        self.boredom_cap = 0.05  # boredom punishment maxes out at 0.05 (was 1.0). Punishment LOWERS the urge  # hector added
        #   to move, so strong boredom punishment made an idle fly even more idle (a trap it couldn't escape)  # hector added
        self.stuck_punishment = 0.5  # punishment for being pinned against a wall (was 1.0)  # hector added
        # Missed coin: Mario passed a trail coin without collecting it (run_fly.py detects it). It happens  # hector added
        # right AT the mistake (usually overshooting a turn), many times per run, so it lands on the cells  # hector added
        # that were active then (e.g. "fast, coin at a sharp angle") and teaches easing off there.  # hector added
        # Starts small (a coin's reward is 1.0); raise it if misses don't go down over the trials.  # hector added
        self.miss_punishment = 0.3  # hector added
        self.miss_punish_frames = 5  # hold it for 5 frames, like the coin reward  # hector added
        self.miss_hold = 0  # frames of missed-coin punishment left  # hector added
        # Spontaneous activity of the approach output neurons: the fly's own baseline urge to move. Real neurons  # hector added
        # fire a little on their own; without this, a fresh fly's forward drive was ~0 and it never moved,  # hector added
        # so it never found a coin to learn from. Learning and punishment act on top of it (avoidance can  # hector added
        # still cancel it), so it's part of the fly's brain, not a rule that moves Mario.  # hector added
        self.tonic_approach = 0.1  # hector added
        # What drives learning: the reward/punishment the fly RECEIVES (coin, finish, hit, stuck, death),  # hector added
        # as BURSTS above its recent normal level. Not the dopamine neurons' total firing: in the real  # hector added
        # connectome they also get steady input from the rest of the brain and fire a little all the time,  # hector added
        # and learning from that background kept weakening the urge to move even while Mario was  # hector added
        # collecting coins (Mario slowed to a stop by coin 7, then never moved again). Bursts also  # hector added
        # "habituate": a long punishment (pinned against a wall) counts strongly for ~3 s, then fades.  # hector added
        self.reward_signal = 0.0  # reward given this frame (0 to 1), set in encode_sensory  # hector added
        self.punish_signal = 0.0  # punishment given this frame (0 to 1)  # hector added
        self.dopamine_baseline_rate = 0.01  # how fast the "normal level" follows (about 3 seconds)  # hector added
        self.dopamine_threshold = 0.02  # bursts smaller than this above normal are ignored  # hector added
        self.pam_baseline = None  # normal reward-cluster level (set from the first frame)  # hector added
        self.ppl_baseline = None  # normal punishment-cluster level  # hector added
        self.last_reward_burst = 0.0  # for run_fly.py's status line  # hector added
        self.last_punish_burst = 0.0  # hector added

        # Speed limit for the fly, in SM64 units per frame. Running tops out at 32; slides go much faster.  # hector added
        # Above max_speed the fly eases off its forward push, and far above it, pulls back to brake.  # hector added
        # Kept above 32 so braking never makes Mario turn around while running on flat ground.  # hector added
        self.max_speed = 45.0  # hector added
        self.last_speed = 0.0  # hector added
        self.min_push = 0.35  # minimum push (0 to 1) so learning can slow the fly but never stop it  # hector added
        # True = ONLY the fly's neurons move Mario: no minimum push, no speed limiter, and jumping comes  # hector added
        # from the fly's own avoidance neurons instead of a hand-written "stuck" rule.  # hector added
        # False = the helper rules above are switched back on (min_push, max_speed, stuck jump).  # hector added
        self.pure_fly = True  # hector added
        self.min_agreement = 0.1  # below this, the direction cells don't clearly point anywhere: go straight  # hector added
        # Turning effort: how hard the stick is pushed when the fly wants to TURN. On a slide, SM64 turns  # hector added
        # Mario by (stick push)^2 (mario_actions_moving.c, update_sliding), so a fly with a weak forward  # hector added
        # drive (e.g. push 0.4) could only turn at ~16% strength and slowly drifted off the outside of  # hector added
        # the corner even while steering the right way. Now the push is at least turn_effort x how far off  # hector added
        # to the side the direction cells say the coin is. The DIRECTION is unchanged (still the vote).  # hector added
        # 0 = off (old behavior).  # hector added
        self.turn_effort = 1.5  # hector added
        self.jump_stuck_frames = 15  # jump after being blocked this many frames in a row (1/2 s)  # hector changed
        self.jump_retry_frames = 45  # after a jump, wait this long (1.5 s) before trying another  # hector added
        self.jump_cooldown = 0  # frames left before the next jump is allowed  # hector added
        self.last_stuck = 0  # stuck_frames from the game, saved for decode_motor  # hector added
        self.last_airborne = 0  # 1 = Mario is in the air, saved for decode_motor  # hector added
        # Mechanical latch state for button_a: tracks whether Mario jumped on the previous frame
        # so the controller can enforce a 1-frame release cycle required by the SM64 engine
        self.last_jump = 0

        # Deterministic random number generator (seeded at 42) so Kenyon Cell sensory partitioning
        # is 100% reproducible across runs
        rng = np.random.default_rng(42)

        # Single-pass O(N) extraction loop over the connectome nodes and attributes
        for index, (node_id, data) in enumerate(self.node_list):
            self.node_ids.append(node_id)

            # Continuous valence calculation using Synister classifier probability averages:
            # Net valence = Excitatory drive (Acetylcholine) minus Inhibitory drive (GABA + Glutamate)
            if data.get("ach_avg") == 0 and data.get("gaba_avg") == 0 and data.get("glut_avg") == 0:
                # Fallback: if continuous averages are unpopulated (0), assign discrete signs from the primary nt_type label
                if data.get("nt_type") == "ACH":
                    self.val_vectors.append(1)    # Acetylcholine is fast excitatory in Drosophila
                elif data.get("nt_type") == "GABA":  
                    self.val_vectors.append(-1)   # GABA is fast inhibitory
                elif data.get("nt_type") == "GLUT":
                    self.val_vectors.append(-1)   # Glutamate acts primarily as an inhibitory transmitter in fly central circuits
                else:
                   self.val_vectors.append(0.5)   # Default modest positive valence for unclassified/modulatory transmitters
            else:
                # Compute continuous signed valence score ranging between -1.0 (strongly inhibitory) and +1.0 (strongly excitatory)
                self.val_vectors.append(data.get("ach_avg") - (data.get("gaba_avg") + data.get("glut_avg")))

            # Classify the neuron into its functional compartment by checking both primary and secondary cell type annotations
            cell_prim_type = data.get("primary_type")
            cell_add_type = data.get("additional_type(s)")
            if "KC" in cell_prim_type or "KC" in cell_add_type:  
                self.kc_idx.append(index)
            elif "MBON" in cell_prim_type  or "MBON" in cell_add_type:
                self.mbon_idx.append(index)
            elif "PAM" in cell_prim_type  or "PAM" in cell_add_type:
                self.pam_idx.append(index)
            elif "PPL" in cell_prim_type  or "PPL" in cell_add_type:
                self.ppl_idx.append(index)
            else:
                # Sanity check: ensure no extraneous, non-Mushroom-Body neurons leaked through the upstream filtering pipeline
                raise ValueError ("Error, one of the cells is not the required mushroom body cell types")

        # Convert index lists to 1D contiguous NumPy integer arrays for O(1) vector slicing during simulation updates
        self.kc_idx = np.array(self.kc_idx)
        self.mbon_idx = np.array(self.mbon_idx)
        self.pam_idx = np.array(self.pam_idx)
        self.ppl_idx = np.array(self.ppl_idx)

        # Convert valence scalars into a 1D NumPy array aligned with the neuron index positions (shape: (5586,))
        self.val_vectors = np.array(self.val_vectors)

        # Partition Mushroom Body Output Neurons (MBONs) into competing behavioral pools based on neurotransmitter valence:
        # - Approach MBONs (valence > 0, Cholinergic): drive forward attraction toward goals/coins
        # - Avoidance MBONs (valence < 0, GABA/Glutamatergic): brake forward motion and trigger escape/jump reflexes
        self.approach_mbon = self.mbon_idx[self.val_vectors[self.mbon_idx] > 0]
        self.avoidance_mbon = self.mbon_idx[self.val_vectors[self.mbon_idx] < 0]

        # State trackers for previous frame telemetry to detect reward (coin pickup) and punishment (damage) deltas
        self.coin_count = None
        self.wedges = None

        # Eligibility trace buffer for Kenyon Cells: tracks recent presynaptic sensory activity over a ~1-2s decaying window
        self.kc_trace = np.zeros(len(self.kc_idx))


        # Linear algebra conversion and synaptic sign assignment:
        # 1. nx.to_scipy_sparse_array: builds raw adjacency matrix A where entry A_ij represents source i -> target j.
        # 2. .transpose(): transposes matrix to W = A^T so entry W_ji represents presynaptic sender i -> postsynaptic receiver j.
        #    Row j accumulates inputs; Column i originates from sender i.
        # 3. .multiply(1xN vector): broadcasts across columns so every outgoing synapse of sender i is scaled by its presynaptic valence v_i,
        #    strictly enforcing Dale's Principle (a neuron's outgoing projections share its excitatory/inhibitory chemical identity).
        # Always build the ORIGINAL (untrained) weights: learning is measured relative to them.  # hector added
        fresh = nx.to_scipy_sparse_array(  # hector changed
            G,
            nodelist=self.node_ids,
            weight="syn_count",
            format="csr"
        ).transpose().multiply(  # hector changed
            self.val_vectors.reshape(1, len(self.val_vectors))
        )  # hector changed

        max_in_weight = abs(fresh).sum(axis=1).max()  # hector changed

        if max_in_weight > 0:  # hector changed
            fresh = fresh / (max_in_weight * 0.1)  # hector changed

        # IMPORTANT: Convert to CSR before plasticity-map initialization.
        fresh = sp.csr_matrix(fresh)  # hector changed
        fresh.sum_duplicates()  # hector changed
        fresh.sort_indices()  # hector changed
        fresh.eliminate_zeros()  # hector changed
        self.sparse_array = fresh  # hector added

        # Saved weights from a previous run. NOT eliminate_zeros: a synapse learned down to 0 must stay  # hector added
        # in the matrix so it can recover later (before, saving + loading deleted those for good).  # hector added
        self._loaded_weights = None  # hector added
        if load_npz is not None:  # hector changed
            loaded = sp.csr_matrix(sp.load_npz(load_npz))  # hector added
            loaded.sum_duplicates()  # hector added
            loaded.sort_indices()  # hector added
            if (loaded.shape != fresh.shape or not np.array_equal(loaded.indptr, fresh.indptr)  # hector added
                    or not np.array_equal(loaded.indices, fresh.indices)):  # hector added
                raise ValueError(f"{load_npz} was saved by an older version of fly_brain.py and doesn't "  # hector added
                                 "line up with this one. Start fresh (run without --load).")  # hector added
            self._loaded_weights = loaded  # hector added

        

        
        # Randomly shuffle Kenyon Cell indices once at startup and partition into 4 sensory modalities:
        # - 50% Directional Tuners: Gaussian compass cells tuned to specific relative coin angles
        # - 25% Proximity Tuners: Exponential distance cells that fire stronger as Mario gets closer to a coin
        # - 15% Velocity Feedback: Proprioceptive cells encoding Mario's normalized forward speed
        # - 10% Collision Hazard Pool: Mechanosensory/nociceptive cells that fire upon wall impact
        rng.shuffle(self.kc_idx)
        n = len(self.kc_idx)
        indices = np.round(np.cumsum(self.kc_split) * n).astype(int)  # hector changed
        self.directional_tuners = self.kc_idx[0 : indices[0]].copy()
        self.proximity_tuners = self.kc_idx[indices[0] : indices[1]].copy()
        self.velocity_feedback = self.kc_idx[indices[1] : indices[2]].copy()
        self.collision_hazardpool = self.kc_idx[indices[2] : indices[3]].copy()  # hector changed
        self.situation_cells = self.kc_idx[indices[3] :].copy()  # hector added
        # Each situation cell's favorite combination: a speed and a turn sharpness (0 = straight ahead,  # hector added
        # pi = straight behind). Random but fixed (seeded), spread over every combination.  # hector added
        self.situation_pref_speed = rng.uniform(0.0, self.situation_speed_max, len(self.situation_cells))  # hector added
        self.situation_pref_turn = rng.uniform(0.0, np.pi, len(self.situation_cells))  # hector added
        # Precompute sparse matrix locations used by dopamine plasticity.
# This avoids repeatedly searching the sparse matrix during gameplay.

        self.approach_positions, self.approach_trace_indices = (
            self._build_plasticity_map(self.approach_mbon)
        )

        self.avoidance_positions, self.avoidance_trace_indices = (
            self._build_plasticity_map(self.avoidance_mbon)
        )
        # Only SPARSE Kenyon Cells learn: the direction cells and the situation cells. The distance, speed  # hector added
        # and wall pools fire all together, so learning on them is the same everywhere on the slide.  # hector added
        if self.learn_sparse_cells_only:  # hector added
            sparse_cells = np.isin(self.kc_idx, np.concatenate([self.directional_tuners, self.situation_cells]))  # hector added
            keep = sparse_cells[self.approach_trace_indices]  # hector added
            self.approach_positions = self.approach_positions[keep]  # hector added
            self.approach_trace_indices = self.approach_trace_indices[keep]  # hector added
            keep = sparse_cells[self.avoidance_trace_indices]  # hector added
            self.avoidance_positions = self.avoidance_positions[keep]  # hector added
            self.avoidance_trace_indices = self.avoidance_trace_indices[keep]  # hector added
        # Original strength of every learnable synapse (learning is scaled and bounded by these)  # hector added
        self.approach_base = self.sparse_array.data[self.approach_positions].copy()  # hector added
        self.avoidance_base = self.sparse_array.data[self.avoidance_positions].copy()  # hector added
        # Now that the map is built from the original weights, switch to the saved ones if loading  # hector added
        if self._loaded_weights is not None:  # hector added
            self.sparse_array = self._loaded_weights  # hector added
        # Evenly spaced angles from -pi to +pi for the directional pool
        self.pref_angles = np.linspace(-np.pi, np.pi, len(self.directional_tuners))

        # Preallocate persistent 1D dense state vectors (shape: (5586,)) in __init__ to avoid O(N) heap allocations
        # and garbage collection pauses during the 30 FPS real-time control loop:
        # - sensory_inputs: transient external sensory buffer wiped and refilled every frame
        # - firing_rates: persistent internal neural activation state across frames
        self.sensory_inputs = np.zeros(len(self.node_ids))
        self.firing_rates = np.zeros(len(self.node_ids))

        # Bilateral steering sub-pools (Population Vector Readout):
        # Per the SM64 bridge spec, positive angle_to_coin means the coin is to Mario's LEFT,
        # and negative angle_to_coin means the coin is to Mario's RIGHT.
        self.left_tuners = self.directional_tuners[self.pref_angles > 0]
        self.right_tuners = self.directional_tuners[self.pref_angles < 0]

    # state_dict should include mario's enviornment variables angle_to_coin, dist_to_coin, speed, and wall_collision
    # Time Complexity: O(N) vectorized over Kenyon Cell slices | Space Complexity: O(1) in-place buffer updates
    def encode_sensory(self, state_dict):
        # Reset transient sensory buffer in-place to 0.0 without allocating a new array
        self.sensory_inputs.fill(0.0)
        # Unpack current frame telemetry from the shared-memory state dictionary
        angle_to_coin, dist_to_coin, speed, wall_collision, coins, wedges = state_dict.get("angle_to_coin"), state_dict.get("dist_to_coin"), state_dict.get("speed"), state_dict.get("wall"), state_dict.get("coins"), state_dict.get("wedges")
        if (state_dict.get("coin_found")) == 1:
            # directional tuner calculations:
            # Compute shortest circular angular distance in [-pi, pi] using atan2(sin(diff), cos(diff))
            # so the compass wraps smoothly across the -pi/+pi boundary behind Mario
            diff = self.pref_angles - angle_to_coin
            sin_diff = np.sin(diff)
            cos_diff = np.cos(diff)
            angles = np.arctan2(sin_diff, cos_diff)
            # Evaluate Gaussian receptive field (bell curve) centered at each neuron's preferred angle
            directional_firing_rates = np.exp(-0.5 * ((angles / self.sigma) ** 2))
            # Enforce biological sparse coding (APL feedback inhibition) on the direction cells only:  #commbined with rommels code
            # keep the top ~5% strongest direction-tuned Kenyon Cells and silence the rest  #commbined with rommels code
            directional_firing_rates[~(directional_firing_rates > np.percentile(directional_firing_rates, 95)) & (directional_firing_rates > 0)] = 0  #commbined with rommels code

            # proximity tuner calculations:
            # Exponential decay scaling from 1.0 (touching coin) down toward 0.0 at long distances
            decay_scalar = np.exp(-(dist_to_coin) / 1000)

            # Write directional array and broadcast proximity scalar directly into preallocated sensory slices
            self.sensory_inputs[self.directional_tuners] = directional_firing_rates
            self.sensory_inputs[self.proximity_tuners] = decay_scalar
# hector added
            # situation cells: how close the current (speed, turn sharpness) is to each cell's favorite  # hector added
            speed_now = np.clip(speed / 32, 0, self.situation_speed_max)  # hector added
            turn_now = abs(angle_to_coin)  # sharpness only; left/right is the direction cells' job  # hector added
            situation_rates = np.exp(-0.5 * (((self.situation_pref_speed - speed_now) / self.situation_speed_width) ** 2  # hector added
                                             + ((self.situation_pref_turn - turn_now) / self.situation_turn_width) ** 2))  # hector added
            cutoff = np.percentile(situation_rates, 100 * (1 - self.situation_active_fraction))  # hector added
            situation_rates[situation_rates < cutoff] = 0  # sparse: only the best-matching cells fire  # hector added
            self.sensory_inputs[self.situation_cells] = situation_rates  # hector added

        # velocity feedback calculations: normalize Mario's speed against top running speed (32.0) and clamp to [0, 1]
        clamped_speed = np.clip(speed / 32, 0, 1)
        self.last_speed = speed  # hector added
        self.last_stuck = state_dict.get("stuck_frames", 0) or 0  # hector added
        self.last_airborne = state_dict.get("airborne", 0) or 0  # hector added
        
        # Broadcast scalar velocity and binary wall collision flag across their respective KC pools
        self.sensory_inputs[self.velocity_feedback] = clamped_speed
        self.sensory_inputs[self.collision_hazardpool] = wall_collision

        # (Sparse coding now happens on the direction cells above, instead of across all sensory inputs here)  #commbined with rommels code
        # Initialize telemetry trackers on the very first frame without firing false dopamine bursts
        if (self.coin_count is None or self.wedges is None):
            self.wedges = wedges
            self.coin_count = coins
            self.reward_hold = 0  # hector added
            self.punish_hold = 0  # hector added
            self.death_hold = 0  # hector added
            self.miss_hold = 0  # hector added
            self.reward_signal = 0.0  # hector added
            self.punish_signal = 0.0  # hector added
            return self.sensory_inputs
        # Stage 3: Dopaminergic Teaching Signals

        # Detect coin collection
        coin_collected = coins > self.coin_count

        if coin_collected:
            # Reset inactivity timer
            self.frames_without_coin = 0

            # Activate appetitive PAM reward neurons (held for coin_reward_frames, see below)  # hector changed
            self.reward_hold = self.coin_reward_frames  # hector changed

        else:
            # Increase time without collecting a coin
            self.frames_without_coin += 1

        # Coin reward, held for a few frames so it can actually compete with punishments  # hector added
        if self.reward_hold > 0:  # hector added
            self.sensory_inputs[self.pam_idx] = 1  # hector added
            self.reward_hold -= 1  # hector added

        # Crossing the Peach's Slide finish line: the biggest reward (run_fly.py sends it for 0.5 s)  # hector added
        if state_dict.get("finished", 0) == 1:  # hector added
            self.sensory_inputs[self.pam_idx] = 1  # hector added
            self.frames_without_coin = 0  # hector added

        # Gradually increase punishment after 5 seconds
        time_since_threshold = max(
            0,
            self.frames_without_coin - self.time_punishment_threshold
        )

        time_punishment = np.clip(
            time_since_threshold / 750,
            0,
            self.boredom_cap  # hector changed
        )

        # Activate PPL1 punishment neurons proportionally
        if time_punishment > 0:
            self.sensory_inputs[self.ppl_idx] = time_punishment

        # Punish damage (held for a few frames, like the coin reward)  # hector changed
        if wedges < self.wedges:
            self.punish_hold = max(self.punish_hold, self.hit_punish_frames)  # hector changed

        # Punish getting stuck
        if clamped_speed < 0.05 and wall_collision == 1:
            self.sensory_inputs[self.ppl_idx] = np.maximum(self.sensory_inputs[self.ppl_idx], self.stuck_punishment)  # hector changed

        # Strong punishment when Mario dies (held for half a second)  # hector changed
        if state_dict.get("dead", 0) == 1:
            self.death_hold = max(self.death_hold, self.death_punish_frames)  # hector changed
        # Falling off: in the air over a death floor / the void. Punished at once, while the fly still  # hector added
        # "remembers" what it was doing (death is only reported seconds later, back in the castle).  # hector added
        falling = state_dict.get("airborne", 0) == 2  # hector added
        if falling or self.death_hold > 0:  # hector added
            self.sensory_inputs[self.ppl_idx] = 1  # hector added
        if self.punish_hold > 0:  # hector added
            self.sensory_inputs[self.ppl_idx] = 1  # hector added
            self.punish_hold -= 1  # hector added
        # Missed coin (small punishment, held a few frames)  # hector added
        if state_dict.get("missed", 0) == 1:  # hector added
            self.miss_hold = self.miss_punish_frames  # hector added
        if self.miss_hold > 0:  # hector added
            self.sensory_inputs[self.ppl_idx] = np.maximum(self.sensory_inputs[self.ppl_idx], self.miss_punishment)  # hector added
            self.miss_hold -= 1  # hector added

        # Update previous telemetry
        self.wedges = wedges
        self.coin_count = coins

        # Remember what reward/punishment was given this frame (this is what learning uses)  # hector added
        self.reward_signal = float(self.sensory_inputs[self.pam_idx].max())  # hector added
        if state_dict.get("finished", 0) == 1:  # hector added
            self.reward_signal = max(self.reward_signal, self.finish_reward(state_dict.get("finish_seconds", 0)))  # hector added
        self.punish_signal = float(self.sensory_inputs[self.ppl_idx].max())  # hector added
        if falling:  # hector added
            self.punish_signal = max(self.punish_signal, self.fall_punishment)  # hector added
        if self.death_hold > 0:  # hector added
            self.punish_signal = max(self.punish_signal, self.death_punishment)  # hector added
            self.death_hold -= 1  # hector added

        return self.sensory_inputs


    # Advances the connectome dynamical simulation by one frame (dt = 1/30s).
    # Time Complexity: O(E + N), where E is non-zero synapses (~sparse CSR dot product) and N is 5586 neurons.
    def step(self, state_dict):
        # 1. Encode external game environment variables into sparse Kenyon Cell sensory currents
        sense = self.encode_sensory(state_dict)
        sense[self.approach_mbon] += self.tonic_approach  # spontaneous activity (see __init__)  # hector added
        # 2. Compute internal recurrent synaptic drive (W * r_t) across all excitatory/inhibitory connections
        recurrent_synaptic_input = self.sparse_array.dot(self.firing_rates)
        # 3. Sum internal synaptic input and external sensory input, rectifying and clamping to [0.0, 1.0]
        total_drive = np.clip(recurrent_synaptic_input + sense, 0, 1)
        # 4. Leaky Integrate-and-Fire (LIF) membrane update: blend 70% previous state with 30% new target drive
        self.firing_rates = ((1 - self.alpha) * self.firing_rates) + (self.alpha * total_drive)
        # 5. Execute three-factor dopaminergic synaptic plasticity to update KC -> MBON weights
        self.apply_plasticity()
        return self.firing_rates

    # Decodes the full brain firing rate vector into SM64 controller commands: (stick_x, stick_y, button_a).
    # Matches the C shared-memory struct format "<ffB".
    # The fly steers TOWARD the direction its direction-tuned Kenyon Cells vote for (population vector), # hector added
    # and the approach/avoidance MBONs decide how HARD it pushes. A weaker push now means "go slower # hector added
    # toward the coin" instead of "slide sideways", so a coin 15 deg to the left gives a 15 deg turn. # hector added
    def decode_motor(self, firing_rates):
        # Compute overall Mushroom Body arousal gate (scaled mean MBON activity bounded to [0.35, 1.0])  #commbined with rommels code
        # to modulate steering sharpness based on motivational state
        mbon_arousal = np.clip(firing_rates[self.mbon_idx].mean() * 5.0, 0.35, 1.0)  #commbined with rommels code
        # Extract mean activity of the wall collision hazard pool and aversive MBON pool
        hazard_arousal = firing_rates[self.collision_hazardpool].mean()
        avoidance_arousal = firing_rates[self.avoidance_mbon].mean()

        # How hard to push (0 to 1): net approach drive minus weighted avoidance, amplified by gain of 4 # hector changed
        push = np.clip((firing_rates[self.approach_mbon].mean() * 1.05 - (0.5 * avoidance_arousal)) * 4, 0, 1) # hector changed
        # Minimum push so learning can slow the fly down but never switch it off completely # hector added
        # (helper rule: off in pure_fly mode, so a weak fly really moves weakly)  # hector added
        if not self.pure_fly:  # hector added
            push = max(push, self.min_push)  # hector changed

        # Which way to go: each direction cell votes for its preferred angle, weighted by how strongly # hector added
        # it fires. The sum of those arrows points where the fly "thinks" the coin is. # hector added
        # Same convention as angle_to_coin: 0 = straight ahead, positive = left, negative = right. # hector added
        direction_rates = firing_rates[self.directional_tuners] # hector added
        vote_forward = (direction_rates * np.cos(self.pref_angles)).sum() # hector added
        vote_left = (direction_rates * np.sin(self.pref_angles)).sum() # hector added
        # Agreement between the votes: near 1 when the cells clearly point one way (a coin), # hector added
        # near 0 when they're just background noise from the rest of the brain (no coin). # hector added
        total_vote = direction_rates.sum() # hector added
        agreement = np.hypot(vote_forward, vote_left) / total_vote if total_vote > 0 else 0.0 # hector added
        if agreement < self.min_agreement: # hector added
            heading = 0.0  # no clear coin signal: go straight # hector added
        else: # hector added
            heading = np.arctan2(vote_left, vote_forward) # hector added
        # How much to trust that vote: MBON arousal (0.35 to 1) blends between straight ahead and the vote # hector added
        heading = heading * mbon_arousal # hector added

        # Speed limiter: no change up to max_speed; at 1.5x max_speed the push is gone,  # hector added
        # and at 2x max_speed the fly pulls fully back to brake (stick_y = -1)  # hector added
        # (helper rule: off in pure_fly mode)  # hector added
        if not self.pure_fly and self.last_speed > self.max_speed:  # hector changed
            brake = np.clip((self.last_speed - self.max_speed) / (0.5 * self.max_speed), 0, 2)  # hector added
            push = push - brake # hector added

        if push >= 0: # hector added
            # Push hard enough to actually turn (see turn_effort in __init__)  # hector added
            push = min(1.0, max(push, self.turn_effort * abs(np.sin(heading))))  # hector added
            # Point the stick at the chosen direction (Mario-relative, see controller_fly.h) # hector added
            stick_x = np.clip(-np.sin(heading) * push, -1, 1) # hector added
            stick_y = np.clip(np.cos(heading) * push, -1, 1) # hector added
        else: # hector added
            # Braking: pull straight back # hector added
            stick_x = 0.0 # hector added
            stick_y = np.clip(push, -1, 0) # hector added

        # Jump reflex (button_a): triggered when Mario has been truly blocked for jump_stuck_frames.  # hector changed
        # Why not on wall contact: "wall" also fires when Mario just brushes a wall (constantly on the  # hector added
        # slide's banked sides), and the wall cells crossed 0.5 in only 2 frames, so the fly jumped  # hector added
        # off the track. stuck_frames only counts when the fly is pushing but Mario isn't moving,  # hector added
        # which is the one case where a jump actually helps (wall, tree, ledge in the way).  # hector added
        # Only from the ground, and once per 1.5 s: Mario stays "stuck" while he's in the air and right  # hector added
        # after landing, so without these the fly hopped against the wall nonstop. One jump, then  # hector added
        # give it time to work (or for the stuck count to clear) before trying again.  # hector added
        button_a = 0
        if self.pure_fly:  # hector added
            # The fly's own decision: jump when its avoidance output neurons (MBONs) fire strongly.  # hector added
            # Their input weights are the learned ones, so the fly can LEARN when jumping is worth it.  # hector added
            # The 1-frame release below is not a rule about when to jump: a button has to be let go  # hector added
            # for a frame before SM64 counts the next press as a new jump.  # hector added
            if avoidance_arousal > 0.5:  # hector added
                button_a = 0 if self.last_jump == 1 else 1  # hector added
        elif self.jump_cooldown > 0:  # hector changed
            self.jump_cooldown -= 1  # hector added
        elif (self.last_stuck >= self.jump_stuck_frames and not self.last_airborne):  # hector changed
            # Enforce mandatory 1-frame button release latch so holding jump doesn't lock Mario out of future jumps
            if (self.last_jump == 1):
                button_a = 0
            else:
                button_a = 1
                self.jump_cooldown = self.jump_retry_frames  # hector added
        # Update latch memory for the next frame and return C-compatible primitive types
        self.last_jump = button_a
        return (float(stick_x), float(stick_y), int(button_a))

    def _build_plasticity_map(self, mbon_rows):
        """
        Precompute CSR data positions for KC -> MBON synapses.

        Runs once during initialization, not every game frame.
        """

        positions = []
        trace_indices = []

        matrix = self.sparse_array

        for row in mbon_rows:

            start = matrix.indptr[row]
            end = matrix.indptr[row + 1]

            columns = matrix.indices[start:end]

            locations = np.searchsorted(
                columns,
                self.kc_idx
            )

            valid = locations < len(columns)

            valid_indices = np.flatnonzero(valid)

            valid[valid_indices] &= (
                columns[locations[valid_indices]]
                == self.kc_idx[valid_indices]
            )

            trace_positions = np.flatnonzero(valid)

            data_positions = start + locations[valid]

            # Ignore zero-valued synapses.
            nonzero = matrix.data[data_positions] != 0

            positions.extend(data_positions[nonzero])
            trace_indices.extend(trace_positions[nonzero])

        return (
            np.asarray(positions, dtype=np.intp),
            np.asarray(trace_indices, dtype=np.intp)
        )


    def _update_plasticity_subset(
        self,
        positions,
        trace_indices,
        dopamine,
        direction,
        base  # hector added
    ):
        """
        Update existing synaptic weights directly in CSR data.

        direction:
            +1 = strengthen
            -1 = weaken
        """

        if len(positions) == 0:
            return

        change = (
            direction
            * self.learning_rate
            * dopamine
            * self.kc_trace[trace_indices]
            * base  # relative to each synapse's original strength  # hector added
        )

        values = self.sparse_array.data[positions]

        self.sparse_array.data[positions] = np.clip(
            values + change,
            0.0,
            self.max_weight_factor * base  # hector changed
        )

    # Stage 4 Three-Factor Synaptic Plasticity (Kenyon Cell eligibility trace x Dopamine x MBON compartment).
    # Modifies existing non-zero synapses in-place within the CSR matrix while preserving Dale's Principle ([0, 1] bounds).
    
    def apply_plasticity(self):

        # Update eligibility trace.
        self.kc_trace *= self.trace_decay  # was 0.9 (see __init__)  # hector changed

        self.kc_trace += self.firing_rates[self.kc_idx]

        np.clip(
            self.kc_trace,
            0.0,
            1.0,
            out=self.kc_trace
        )

        # Dopamine population activity.
        mean_pam = np.clip(
            self.firing_rates[self.pam_idx].mean(),
            0.0,
            1.0
        )

        mean_ppl = np.clip(
            self.firing_rates[self.ppl_idx].mean(),
            0.0,
            1.0
        )

        # Learning signal: the reward/punishment just received, as BURSTS above its normal level (see __init__)  # hector changed
        if self.pam_baseline is None:  # hector added
            self.pam_baseline = self.reward_signal  # hector changed
            self.ppl_baseline = self.punish_signal  # hector changed
        reward_burst = max(0.0, self.reward_signal - self.pam_baseline - self.dopamine_threshold)  # hector changed
        punish_burst = max(0.0, self.punish_signal - self.ppl_baseline - self.dopamine_threshold)  # hector changed
        self.pam_baseline += self.dopamine_baseline_rate * (self.reward_signal - self.pam_baseline)  # hector changed
        self.ppl_baseline += self.dopamine_baseline_rate * (self.punish_signal - self.ppl_baseline)  # hector changed
        self.last_reward_burst = reward_burst  # hector added
        self.last_punish_burst = punish_burst  # hector added
        mean_pam = reward_burst  # from here on, "dopamine" means the burst  # hector added
        mean_ppl = punish_burst  # hector added
# hector added
        # Slow forgetting: learned weights drift back toward their original strength every frame  # hector added
        d = self.sparse_array.data  # hector added
        d[self.approach_positions] += self.weight_recovery * (self.approach_base - d[self.approach_positions])  # hector added
        d[self.avoidance_positions] += self.weight_recovery * (self.avoidance_base - d[self.avoidance_positions])  # hector added

        # Skip neutral frames.
        if mean_pam < 0.005 and mean_ppl < 0.005:
            return

        # REWARD:
        # Strengthen approach connections.
        # Weaken avoidance connections.

        if mean_pam > 0:

            self._update_plasticity_subset(
                self.approach_positions,
                self.approach_trace_indices,
                mean_pam,
                +1,
                self.approach_base  # hector added
            )

            self._update_plasticity_subset(
                self.avoidance_positions,
                self.avoidance_trace_indices,
                mean_pam,
                -1,
                self.avoidance_base  # hector added
            )

        # PUNISHMENT:
        # Weaken approach connections.
        # Strengthen avoidance connections.

        if mean_ppl > 0:

            self._update_plasticity_subset(
                self.approach_positions,
                self.approach_trace_indices,
                mean_ppl,
                -1,
                self.approach_base  # hector added
            )

            self._update_plasticity_subset(
                self.avoidance_positions,
                self.avoidance_trace_indices,
                mean_ppl,
                +1,
                self.avoidance_base  # hector added
            )

    # Serializes the learned sparse synaptic weight matrix to disk as a compressed .npz archive
    def finish_reward(self, finish_seconds):  # hector added
        # How strongly a finish teaches, from its time: closer to star time (21 s) = bigger (see __init__)  # hector added
        if not finish_seconds:  # hector added
            return self.finish_reward_min  # hector added
        closeness = (self.finish_slow_seconds - finish_seconds) / (self.finish_slow_seconds - self.star_time_seconds)  # hector added
        closeness = min(1.0, max(0.0, closeness))  # hector added
        return self.finish_reward_min + (self.finish_reward_max - self.finish_reward_min) * closeness  # hector added

    def learning_summary(self):  # hector added
        # Average learned strength vs. original (1.00 = unchanged), for run_fly.py's status line  # hector added
        d = self.sparse_array.data  # hector added
        approach = float((d[self.approach_positions] / self.approach_base).mean())  # hector added
        avoidance = float((d[self.avoidance_positions] / self.avoidance_base).mean())  # hector added
        return approach, avoidance  # hector added

    def save_plasticity(self, path):
        sp.save_npz(path, self.sparse_array)

    def get_learning_rate(self):
        return self.learning_rate

    def set_learning_rate(self, ln):
        self.learning_rate = ln