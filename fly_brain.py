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

        # Sigma value for how wide the bell curve for the fly should be
        self.sigma = 0.35

        # Alpha value for the integration rate (how much of the previous firing rate the neurons should retain,
        # neurons have membrance capacitance, they don't instantly lose their previous state)
        self.alpha = 0.3

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

        approach_mbon = self.mbon_idx[self.val_vectors > 0]


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

        
        
        rng.shuffle(self.kc_idx)
        n = len(self.kc_idx)
        indices = np.round(np.cumsum([0.5, .25, .15, .10]) * n).astype(int)
        self.directional_tuners = self.kc_idx[0 : indices[0]].copy()
        self.proximity_tuners = self.kc_idx[indices[0] : indices[1]].copy()
        self.velocity_feedback = self.kc_idx[indices[1] : indices[2]].copy()
        self.collision_hazardpool = self.kc_idx[indices[2] :].copy()
        # Evenly spaced angles from -pi to +pi for the directional pool
        self.pref_angles = np.linspace(-np.pi, np.pi, len(self.directional_tuners))

        self.sensory_inputs = np.zeros(len(self.node_ids))
        self.firing_rates = np.zeros(len(self.node_ids))

    # state_dict should include amrio's enviornment variables angle_to_coin, dist_to_coin, speed, and wall_collision
    def encode_sensory(self, state_dict):
        self.sensory_inputs.fill(0.0)
        angle_to_coin, dist_to_coin, speed, wall_collision = state_dict.get("angle_to_coin"), state_dict.get("dist_to_coin"), state_dict.get("speed"), state_dict.get("wall")
        if (state_dict.get("coin_found")) == 1:
            # directional tuner calculations
            diff = self.pref_angles - angle_to_coin
            sin_diff = np.sin(diff)
            cos_diff = np.cos(diff)
            angles = np.arctan2(sin_diff, cos_diff)
            directional_firing_rates = np.exp(-0.5 * ((angles / self.sigma) ** 2))

            # proximity tuner calculations
            decay_scalar = np.exp(-(dist_to_coin) / 1000)

            self.sensory_inputs[self.directional_tuners] = directional_firing_rates
            self.sensory_inputs[self.proximity_tuners] = decay_scalar

        # velocity feedback calculations
        clamped_speed = np.clip(speed / 32, 0, 1)
        
        self.sensory_inputs[self.velocity_feedback] = clamped_speed
        self.sensory_inputs[self.collision_hazardpool] = wall_collision

        self.sensory_inputs[~(self.sensory_inputs > np.percentile(self.sensory_inputs, 95)) & (self.sensory_inputs > 0)] = 0
        return self.sensory_inputs


    def step(self, state_dict):
        sense = self.encode_sensory(state_dict)
        recurrent_synaptic_input = self.sparse_array.dot(self.firing_rates)
        total_drive = np.clip(recurrent_synaptic_input + sense, 0, 1)
        self.firing_rates = ((1 - self.alpha) * self.firing_rates) + (self.alpha * total_drive)
        return self.firing_rates

brain = fly_brain("mushroom_body.graphml")
state_dict = {"coin_found": 1, "angle_to_coin": 0.5, "dist_to_coin": 500, "speed": 16, "wall": 0}

for i in range(10):
    brain.step(state_dict)
print(np.count_nonzero(brain.firing_rates))
