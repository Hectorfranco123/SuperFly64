import time

import networkx as nx
import numpy as np
import scipy.sparse as sp


class fly_brain:
    
    def __init__(self, graphml_path):
        G = nx.read_graphml(graphml_path)
        self.node_list = list(G.nodes(data = True))
        self.kc_idx = []
        self.mbon_idx = []
        self.pam_idx = []
        self.ppl_idx = []
        for index, cell in enumerate(self.node_list):
            cell_prim_type = cell[1].get("primary_type")
            cell_add_type = cell[1].get("additional_type(s)")
            if "KC" in cell_prim_type or "KC" in cell_add_type:  
                self.kc_idx.append(index)
            elif "MBON" in cell_prim_type  or "MBON" in cell_add_type:
                self.mbon_idx.append(index)
            elif "PAM" in cell_prim_type  or "PAM" in cell_add_type:
                self.pam_idx.append(index)
            elif "PPL" in cell_prim_type  or "PPL" in cell_add_type:
                self.ppl_idx.append(index)
            else:
                raise ValueError ("Error, one of the cells is not the required mushroom body cell types")
        self.kc_idx = np.array(self.kc_idx)
        self.mbon_idx = np.array(self.mbon_idx)
        self.pam_idx = np.array(self.pam_idx)
        self.ppl_idx = np.array(self.ppl_idx)


brain = fly_brain("mushroom_body.graphml")

