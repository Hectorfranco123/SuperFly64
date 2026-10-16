import pandas as pd
import numpy as np
import networkx as nx

cell_types = pd.read_csv("consolidated_cell_types.csv")
neurons = pd.read_csv("neurons.csv")
connection_chunks = pd.read_csv("connections_princeton.csv", chunksize=10000)
# print(cell_types.dtypes)
# print(cell_types.memory_usage(deep=True))

#turns the primary_type and additional_type(s) columns into categorical data types to save memory
cell_types["primary_type"] = cell_types["primary_type"].astype("category")
cell_types["additional_type(s)"] = cell_types["additional_type(s)"].astype("category")
#print(cell_types.memory_usage(deep=True))

#finds the mushroom body neurons in the cell_types dataframe by filtering for primary types that contain "KC", "MBON", or "PAM"
mushroom_body = cell_types[(cell_types["primary_type"].str.contains("KC")) | (cell_types["primary_type"].str.contains("MBON")) | (cell_types["primary_type"].str.contains("PAM"))]
mushroom_connects = pd.DataFrame(columns=[ "pre_root_id", "post_root_id", "neuropil", "syn_count", "nt_type" ])

#creates a new dataframe called mushroom_connects that contains only the connections between mushroom body neurons by filtering
#the connection_chunks dataframe for rows where both the pre_root_id and post_root_id are in the mushroom_body dataframe
for chunk in connection_chunks:
    mushroom_connects = pd.concat([mushroom_connects, chunk[chunk["pre_root_id"].isin(mushroom_body["root_id"]) & chunk["post_root_id"].isin(mushroom_body["root_id"])]], ignore_index=True)

