import ast
import pandas as pd
import matplotlib.pyplot as plt

csv_path = "analysis_outputs/mode_s_candidates.csv"

df = pd.read_csv(csv_path)

# Convert string list columns if needed
def safe_list_str(x):
    try:
        val = ast.literal_eval(x) if isinstance(x, str) else x
        if isinstance(val, list):
            return "[" + ", ".join(val) + "]"
        return str(val)
    except Exception:
        return str(x)

df["subset_label"] = df["subset"].apply(safe_list_str)

# Keep only finite rows
df = df[pd.notnull(df["est_latency_s"])]
df = df[pd.notnull(df["extra_info_1"])]

# Rename for clarity
df["mode_s_cost"] = df["extra_info_1"]

# Sort by cost
df_sorted = df.sort_values("mode_s_cost", ascending=True)

# -----------------------------
# 1. Top-k lowest MODE-S cost
# -----------------------------
top_k = 10
top_df = df_sorted.head(top_k)

plt.figure(figsize=(12, 6))
bars = plt.bar(top_df["subset_label"], top_df["mode_s_cost"])
if len(bars) > 0:
    bars[0].set_hatch("//")

plt.xlabel("Model combinations")
plt.ylabel("MODE-S cost")
plt.title("Top Candidate Ensembles by MODE-S Cost")
plt.xticks(rotation=30, ha="right")
plt.tight_layout()
plt.savefig("analysis_outputs/mode_s_topk_cost.png", dpi=200, bbox_inches="tight")
plt.show()

# -----------------------------
# 2. Top-k lowest estimated latency
# -----------------------------
df_lat = df.sort_values("est_latency_s", ascending=True).head(top_k)

plt.figure(figsize=(12, 6))
bars = plt.bar(df_lat["subset_label"], df_lat["est_latency_s"])
if len(bars) > 0:
    bars[0].set_hatch("//")

plt.xlabel("Model combinations")
plt.ylabel("Estimated latency Te (s)")
plt.title("Top Candidate Ensembles by Estimated MODE-S Latency")
plt.xticks(rotation=30, ha="right")
plt.tight_layout()
plt.savefig("analysis_outputs/mode_s_topk_latency.png", dpi=200, bbox_inches="tight")
plt.show()

# -----------------------------
# 3. Scatter plot: cost vs latency
# -----------------------------
plt.figure(figsize=(8, 6))
plt.scatter(df["est_latency_s"], df["mode_s_cost"])

plt.xlabel("Estimated latency Te (s)")
plt.ylabel("MODE-S cost")
plt.title("MODE-S Cost vs Estimated Latency")
plt.tight_layout()
plt.savefig("analysis_outputs/mode_s_cost_vs_latency.png", dpi=200, bbox_inches="tight")
plt.show()

# -----------------------------
# 4. Cost vs ensemble size
# -----------------------------
plt.figure(figsize=(8, 6))
plt.scatter(df["size"], df["mode_s_cost"])

plt.xlabel("Ensemble size")
plt.ylabel("MODE-S cost")
plt.title("MODE-S Cost vs Ensemble Size")
plt.tight_layout()
plt.savefig("analysis_outputs/mode_s_cost_vs_size.png", dpi=200, bbox_inches="tight")
plt.show()

print("MODE-S plots saved to analysis_outputs/")