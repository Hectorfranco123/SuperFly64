import time

import networkx as nx
import numpy as np
import scipy.sparse as sp


class fly_brain:
    
    def __init__(self, graphml_path):
        # Load the serialized biological connectome graph from the GraphML XML file
        G = nx.read_graphml(graphml_path)

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

        self.coin_count = None
        self.wedges = None

        self.kc_trace = np.zeros(len(self.node_ids))


        # Linear algebra conversion and synaptic sign assignment:
        # 1. nx.to_scipy_sparse_array: builds raw adjacency matrix A where entry A_ij represents source i -> target j.
        # 2. .transpose(): transposes matrix to W = A^T so entry W_ji represents presynaptic sender i -> postsynaptic receiver j.
        #    Row j accumulates inputs; Column i originates from sender i.
        # 3. .multiply(1xN vector): broadcasts across columns so every outgoing synapse of sender i is scaled by its presynaptic valence v_i,
        #    strictly enforcing Dale's Principle (a neuron's outgoing projections share its excitatory/inhibitory chemical identity).
        self.sparse_array = nx.to_scipy_sparse_array(G, nodelist = self.node_ids, weight = "syn_count", format = "csr").transpose().multiply(self.val_vectors.reshape(1, len(self.val_vectors)))

        # Normalize incoming synaptic density per postsynaptic neuron
        # so no single neuron receives infinite incoming drive
        max_in_weight = np.abs(self.sparse_array).sum(axis=1).max()
        if max_in_weight > 0:
            self.sparse_array = self.sparse_array / (max_in_weight * 0.1)  # Keeps baseline gain responsive

        
        # Randomly shuffle Kenyon Cell indices once at startup and partition into 4 sensory modalities:
        # - 50% Directional Tuners: Gaussian compass cells tuned to specific relative coin angles
        # - 25% Proximity Tuners: Exponential distance cells that fire stronger as Mario gets closer to a coin
        # - 15% Velocity Feedback: Proprioceptive cells encoding Mario's normalized forward speed
        # - 10% Collision Hazard Pool: Mechanosensory/nociceptive cells that fire upon wall impact
        rng.shuffle(self.kc_idx)
        n = len(self.kc_idx)
        indices = np.round(np.cumsum([0.5, .25, .15, .10]) * n).astype(int)
        self.directional_tuners = self.kc_idx[0 : indices[0]].copy()
        self.proximity_tuners = self.kc_idx[indices[0] : indices[1]].copy()
        self.velocity_feedback = self.kc_idx[indices[1] : indices[2]].copy()
        self.collision_hazardpool = self.kc_idx[indices[2] :].copy()
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

            # proximity tuner calculations:
            # Exponential decay scaling from 1.0 (touching coin) down toward 0.0 at long distances
            decay_scalar = np.exp(-(dist_to_coin) / 1000)

            # Write directional array and broadcast proximity scalar directly into preallocated sensory slices
            self.sensory_inputs[self.directional_tuners] = directional_firing_rates
            self.sensory_inputs[self.proximity_tuners] = decay_scalar

        # velocity feedback calculations: normalize Mario's speed against top running speed (32.0) and clamp to [0, 1]
        clamped_speed = np.clip(speed / 32, 0, 1)
        
        # Broadcast scalar velocity and binary wall collision flag across their respective KC pools
        self.sensory_inputs[self.velocity_feedback] = clamped_speed
        self.sensory_inputs[self.collision_hazardpool] = wall_collision

        # Enforce biological sparse coding (mimicking Anterior Paired Lateral / APL global feedback inhibition):
        # Silence all active neurons below the 95th percentile so only the top ~5% strongest Kenyon Cells fire
        self.sensory_inputs[~(self.sensory_inputs > np.percentile(self.sensory_inputs, 95)) & (self.sensory_inputs > 0)] = 0
        if (self.coin_count is None or coins > self.coin_count):
            self.sensory_inputs[self.pam_idx] = 1
        if (self.wedges is None or wedges < self.wedges or (clamped_speed == 0 and wall_collision == 1)):
            self.sensory_inputs[self.ppl_idx] = 1
        return self.sensory_inputs


    # Advances the connectome dynamical simulation by one frame (dt = 1/30s).
    # Time Complexity: O(E + N), where E is non-zero synapses (~sparse CSR dot product) and N is 5586 neurons.
    def step(self, state_dict):
        # 1. Encode external game environment variables into sparse Kenyon Cell sensory currents
        sense = self.encode_sensory(state_dict)
        # 2. Compute internal recurrent synaptic drive (W * r_t) across all excitatory/inhibitory connections
        recurrent_synaptic_input = self.sparse_array.dot(self.firing_rates)
        # 3. Sum internal synaptic input and external sensory input, rectifying and clamping to [0.0, 1.0]
        total_drive = np.clip(recurrent_synaptic_input + sense, 0, 1)
        # 4. Leaky Integrate-and-Fire (LIF) membrane update: blend 70% previous state with 30% new target drive
        self.firing_rates = ((1 - self.alpha) * self.firing_rates) + (self.alpha * total_drive)
        self.apply_plasticity()
        return self.firing_rates

    # Decodes the full brain firing rate vector into SM64 controller commands: (stick_x, stick_y, button_a).
    # Matches the C shared-memory struct format "<ffB".
    def decode_motor(self, firing_rates):
        # Compute overall Mushroom Body arousal gate (scaled mean MBON activity bounded to [0.1, 1.0])
        # to modulate steering sharpness based on motivational state
        mbon_arousal = np.clip(firing_rates[self.mbon_idx].mean() * 5.0, 0.1, 1.0)
        # Extract mean activity of the wall collision hazard pool and aversive MBON pool
        hazard_arousal = firing_rates[self.collision_hazardpool].mean()
        avoidance_arousal = firing_rates[self.avoidance_mbon].mean()
        # Forward/backward axis (stick_y): net approach drive minus weighted avoidance, amplified by gain of 4
        stick_y = np.clip((firing_rates[self.approach_mbon].mean() - (0.5 * avoidance_arousal)) * 4, -1, 1)
        # Left/right steering axis (stick_x): bilateral difference between right-tuned and left-tuned compass pools,
        # scaled by gain of 2 and gated by MBON arousal (negative = steer left, positive = steer right)
        stick_x = np.clip((firing_rates[self.right_tuners].mean() - firing_rates[self.left_tuners].mean()) * 2 * mbon_arousal, -1, 1)
        # Jump reflex (button_a): triggered when either avoidance MBONs or wall collision sensors exceed 0.5
        button_a = 0
        if (avoidance_arousal > 0.5 or hazard_arousal > 0.5):
            # Enforce mandatory 1-frame button release latch so holding jump doesn't lock Mario out of future jumps
            if (self.last_jump == 1):
                button_a = 0
            else:
                button_a = 1
        # Update latch memory for the next frame and return C-compatible primitive types
        self.last_jump = button_a
        return (float(stick_x), float(stick_y), int(button_a))

    def apply_plasticity(self):
        self.kc_trace = np.clip((self.kc_trace * 0.9) + self.firing_rates[self.kc_idx], 0, 1)
        self.mean_pam = np.clip(self.firing_rates[self.pam_idx].mean(), 0, 1)
        self.mean_ppl = np.clip(self.firing_rates[self.ppl_idx].mean(), 0, 1)
