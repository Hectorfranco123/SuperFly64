import networkx as nx
import pandas as pd

cell_types = pd.read_csv("consolidated_cell_types.csv").fillna("")
neurons = pd.read_csv("neurons.csv").fillna("")
connection_chunks = pd.read_csv("connections_princeton.csv", chunksize=10000)


# turns the primary_type and additional_type(s) columns into categorical data types to save memory
cell_types["primary_type"] = cell_types["primary_type"].astype("category")
cell_types["additional_type(s)"] = cell_types["additional_type(s)"].astype("category")


# finds the mushroom body neurons in the cell_types dataframe by filtering for primary types that contain "KC", "MBON", "PAM", or "PPL"
# and then merges it with neurons.csv to add all those attributes for each cell as well
mushroom_body = cell_types[(cell_types["primary_type"].str.contains("KC|MBON|PAM|PPL", na=False)) | (cell_types["additional_type(s)"].str.contains("KC|MBON|PAM|PPL", na=False))]
mushroom_body = pd.merge(mushroom_body, neurons, how = "left", on = "root_id")
# creates a new dataframe called mushroom_connects that contains only the connections between mushroom body neurons by filtering
# the connection_chunks dataframe for rows where both the pre_root_id and post_root_id are in the mushroom_body dataframe (using a Python set for O(1) lookup speed)
filtered_chunks = []
mushroom_id_set = set(mushroom_body["root_id"])
for chunk in connection_chunks:
    filtered_chunks.append(chunk[chunk["pre_root_id"].isin(mushroom_id_set) & chunk["post_root_id"].isin(mushroom_id_set)])
mushroom_connects = pd.concat(filtered_chunks, ignore_index=True)

# groups the connections by IDs and prevents networkx graphing from dropping any duplicate connections
graphed_connects = mushroom_connects.groupby(by = ["pre_root_id", "post_root_id"], as_index = False).agg({"syn_count": "sum", "nt_type": "first"})

# creates the networkx graph and adds all the individual cell attributes and exports it to a mushroom_body.graphml file
network_graph = nx.from_pandas_edgelist(graphed_connects, source = "pre_root_id", target = "post_root_id", edge_attr = ["syn_count", "nt_type"], create_using = nx.DiGraph())
mushroom_dict = mushroom_body.set_index("root_id").to_dict("index")
nx.set_node_attributes(network_graph, values = mushroom_dict)
nx.write_graphml(network_graph, path = "mushroom_body.graphml")

