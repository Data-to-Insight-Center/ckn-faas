import csv
import matplotlib.pyplot as plt

# -------- FILE PATHS --------
file_parallel = "/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/codespace/workload_generator/data/avg_latency_vs_arrival_para.csv"
file_sequential = "/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/codespace/workload_generator/data/avg_latency_vs_arrival_seq.csv"

# -------- FUNCTION TO COMPUTE AVERAGE CONFIDENCE --------
def get_avg_confidence(file_path):
    confidences = []

    with open(file_path, "r") as f:
        reader = csv.reader(f)
        for row in reader:
            try:
                conf = float(row[8])  # confidence column
                confidences.append(conf)
            except:
                continue

    if len(confidences) == 0:
        return 0
    return sum(confidences) / len(confidences)


# -------- COMPUTE AVERAGES --------
avg_para = get_avg_confidence(file_parallel)
avg_seq = get_avg_confidence(file_sequential)

print(f"Parallel Avg Confidence: {avg_para:.4f}")
print(f"Sequential Avg Confidence: {avg_seq:.4f}")


# -------- PLOT BAR CHART --------
labels = ["Parallel", "Sequential"]
values = [avg_para, avg_seq]

plt.figure(figsize=(5, 4))
plt.bar(labels, values)

plt.ylabel("Average Confidence", fontsize=12)
plt.title("Average Confidence Comparison", fontsize=14)

# show values on bars
for i, v in enumerate(values):
    plt.text(i, v + 0.01, f"{v:.3f}", ha='center')

plt.tight_layout()
plt.show()