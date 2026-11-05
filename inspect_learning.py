import scipy.sparse as sp
import numpy as np

# Load learned weights
weights = sp.load_npz("learned.npz")

print("=== LEARNED BRAIN ===")
print("Matrix shape:", weights.shape)
print("Number of synapses:", weights.nnz)
print("Data type:", weights.dtype)

print("\n=== WEIGHT STATISTICS ===")
print("Minimum:", weights.data.min())
print("Maximum:", weights.data.max())
print("Mean:", weights.data.mean())
print("Standard deviation:", weights.data.std())

print("\n=== SAMPLE SYNAPTIC WEIGHTS ===")
print(weights.data[:20])
