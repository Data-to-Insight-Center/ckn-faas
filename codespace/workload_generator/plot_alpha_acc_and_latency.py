# import pandas as pd
# import matplotlib.pyplot as plt
#
# # =========================================================
# # File paths
# # =========================================================
# para_file = "/workload_generator/data/alpha_with_acc_and_latency_MODE_S.csv"
# seq_file  = "/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/codespace/workload_generator/data/alpha_with_acc_and_latency_seq.csv"
#
# # =========================================================
# # Read CSV files with NO header
# # =========================================================
# df_para = pd.read_csv(para_file, header=None)
# df_seq  = pd.read_csv(seq_file, header=None)
#
# print("PARA shape:", df_para.shape)
# print("SEQ shape :", df_seq.shape)
#
# # =========================================================
# # Column indexes from your log format
# # =========================================================
# latency_idx = 3
# confidence_idx = 8
# alpha_idx = 20
#
# # =========================================================
# # Select only needed columns
# # =========================================================
# para = df_para.iloc[:, [alpha_idx, confidence_idx, latency_idx]].copy()
# seq  = df_seq.iloc[:, [alpha_idx, confidence_idx, latency_idx]].copy()
#
# para.columns = ["alpha", "confidence", "latency"]
# seq.columns  = ["alpha", "confidence", "latency"]
#
# # =========================================================
# # Convert to numeric
# # =========================================================
# for col in ["alpha", "confidence", "latency"]:
#     para[col] = pd.to_numeric(para[col], errors="coerce")
#     seq[col] = pd.to_numeric(seq[col], errors="coerce")
#
# # Drop rows with missing values
# para = para.dropna(subset=["alpha", "confidence", "latency"])
# seq  = seq.dropna(subset=["alpha", "confidence", "latency"])
#
# # =========================================================
# # Average by alpha
# # =========================================================
# para_avg = para.groupby("alpha", as_index=False).agg(
#     avg_confidence=("confidence", "mean"),
#     avg_latency=("latency", "mean")
# ).sort_values("alpha")
#
# seq_avg = seq.groupby("alpha", as_index=False).agg(
#     avg_confidence=("confidence", "mean"),
#     avg_latency=("latency", "mean")
# ).sort_values("alpha")
#
# print("\nParallel averages:")
# print(para_avg)
#
# print("\nSequential averages:")
# print(seq_avg)
#
# # =========================================================
# # Graph 1: Average Confidence vs Alpha
# # =========================================================
# plt.figure(figsize=(8, 5))
# plt.plot(para_avg["alpha"], para_avg["avg_confidence"], marker="o", label="Parallel")
# plt.plot(seq_avg["alpha"], seq_avg["avg_confidence"], marker="s", label="Sequential")
# plt.xlabel("Alpha")
# plt.ylabel("Average Confidence")
# plt.title("Average Confidence vs Alpha")
# plt.grid(True)
# plt.legend()
# plt.tight_layout()
# plt.savefig("average_confidence_vs_alpha.png", dpi=300)
# plt.show()
#
# # =========================================================
# # Graph 2: Average Latency vs Alpha
# # =========================================================
# plt.figure(figsize=(8, 5))
# plt.plot(para_avg["alpha"], para_avg["avg_latency"], marker="o", label="Parallel")
# plt.plot(seq_avg["alpha"], seq_avg["avg_latency"], marker="s", label="Sequential")
# plt.xlabel("Alpha")
# plt.ylabel("Average Latency")
# plt.title("Average Latency vs Alpha")
# plt.grid(True)
# plt.legend()
# plt.tight_layout()
# plt.savefig("average_latency_vs_alpha.png", dpi=300)
# plt.show()

###########
# both seq and para code end
########


import pandas as pd
import matplotlib.pyplot as plt

# =========================================================
# File path
# =========================================================
file_path = "/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/codespace/workload_generator/data/alpha_with_acc_and_latency_MODE_S.csv"

# =========================================================
# Read CSV file with NO header
# =========================================================
df = pd.read_csv(file_path, header=None)

print("MODE-S shape:", df.shape)

# =========================================================
# Column indexes from your log format
# =========================================================
latency_idx = 3
confidence_idx = 8
alpha_idx = 20

# =========================================================
# Select only needed columns
# =========================================================
data = df.iloc[:, [alpha_idx, confidence_idx, latency_idx]].copy()
data.columns = ["alpha", "confidence", "latency"]

# =========================================================
# Convert to numeric
# =========================================================
for col in ["alpha", "confidence", "latency"]:
    data[col] = pd.to_numeric(data[col], errors="coerce")

# Drop rows with missing values
data = data.dropna(subset=["alpha", "confidence", "latency"])

# =========================================================
# Average by alpha
# =========================================================
avg_data = data.groupby("alpha", as_index=False).agg(
    avg_confidence=("confidence", "mean"),
    avg_latency=("latency", "mean")
).sort_values("alpha")

print("\nMODE-S averages:")
print(avg_data)

# =========================================================
# Graph 1: Average Confidence vs Alpha
# =========================================================
plt.figure(figsize=(8, 5))
plt.plot(avg_data["alpha"], avg_data["avg_confidence"], marker="o")
plt.xlabel("Alpha")
plt.ylabel("Average Confidence")
plt.title("MODE-S: Average Confidence vs Alpha")
plt.grid(True)
plt.tight_layout()
plt.savefig("modes_average_confidence_vs_alpha.png", dpi=300)
plt.show()

# =========================================================
# Graph 2: Average Latency vs Alpha
# =========================================================
plt.figure(figsize=(8, 5))
plt.plot(avg_data["alpha"], avg_data["avg_latency"], marker="o")
plt.xlabel("Alpha")
plt.ylabel("Average Latency")
plt.title("MODE-S: Average Latency vs Alpha")
plt.grid(True)
plt.tight_layout()
plt.savefig("modes_average_latency_vs_alpha.png", dpi=300)
plt.show()