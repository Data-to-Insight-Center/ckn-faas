# import csv
# import ast
# import matplotlib.pyplot as plt
# import matplotlib.patches as mpatches
# import pandas as pd
#
# csv_path = "/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/codespace/workload_generator/data/alpha analysis_para.csv"
#
# rows = []
#
# # --- 1. Read CSV ---
# with open(csv_path, newline="") as f:
#     reader = csv.reader(f)
#     header = next(reader)
#     sm_idx = header.index("selected_models")
#
#     for r in reader:
#         try:
#             alpha = float(r[-1])      # alpha is last column
#             models = ast.literal_eval(r[sm_idx])
#             rows.append((alpha, models))
#         except Exception:
#             continue
#
# df = pd.DataFrame(rows, columns=["alpha", "models"])
#
# # unique alphas and models
# alphas = sorted(df["alpha"].unique())
# all_models = sorted({m for lst in df["models"] for m in lst})
#
# # map alpha -> x index so spacing is always 1
# alpha_to_x = {a: i for i, a in enumerate(alphas)}
# x_positions = list(range(len(alphas)))
#
# # colors per model
# color_cycle = plt.rcParams["axes.prop_cycle"].by_key()["color"]
# model_color = {m: color_cycle[i % len(color_cycle)] for i, m in enumerate(all_models)}
#
# plt.figure(figsize=(10, 6))
#
# bar_width = 0.8      # full width of one alpha bar in index space
# tile_height = 1.0    # height of each request row
#
# for a in alphas:
#     x_base = alpha_to_x[a]  # integer x position for this alpha
#
#     # all requests for this alpha, in order
#     reqs = df[df["alpha"] == a]["models"].tolist()
#     current_bottom = 0.0
#
#     for models_in_request in reqs:
#         n_models = len(models_in_request)
#         if n_models == 0:
#             continue
#
#         model_width = bar_width / n_models
#
#         for i, m in enumerate(models_in_request):
#             # center of this tile in index space
#             x_center = x_base - bar_width/2 + (i + 0.5) * model_width
#
#             plt.bar(
#                 x=x_center,
#                 height=tile_height,
#                 width=model_width,
#                 bottom=current_bottom,
#                 color=model_color.get(m, "gray"),
#                 edgecolor="black",
#                 linewidth=0.4,
#                 align="center",
#             )
#
#         current_bottom += tile_height  # next request stacked above
#
# plt.xlabel("Alpha", fontsize=12)
# plt.ylabel("Requests", fontsize=12)
# plt.title("Model Selections per Request for Each Alpha", fontsize=14)
#
# # show original alpha values as labels
# plt.xticks(x_positions, [str(a) for a in alphas])
#
# # legend
# patches = [mpatches.Patch(color=col, label=mdl) for mdl, col in model_color.items()]
# plt.legend(handles=patches, title="Models", bbox_to_anchor=(1.05, 1), loc="upper left")
#
# plt.tight_layout()
# plt.show()

import csv
import ast
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import pandas as pd

# csv_path = "/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/codespace/workload_generator/data/alpha analysis_para.csv"
csv_path = "/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/codespace/workload_generator/data/alpha_with_acc_and_latency_MODE_S.csv"

rows = []

# Column positions from your log format
SELECTED_MODELS_IDX = 5
ALPHA_IDX = 20
SUCCESS_IDX = 11   # True / False

with open(csv_path, newline="") as f:
    reader = csv.reader(f)

    for r in reader:
        try:
            # skip short/bad rows
            if len(r) <= max(SELECTED_MODELS_IDX, ALPHA_IDX, SUCCESS_IDX):
                continue

            success_val = str(r[SUCCESS_IDX]).strip().lower()
            if success_val != "true":
                continue

            alpha = float(r[ALPHA_IDX])
            models = ast.literal_eval(r[SELECTED_MODELS_IDX].strip())

            if not isinstance(models, list):
                continue

            rows.append((alpha, models))

        except Exception:
            continue

df = pd.DataFrame(rows, columns=["alpha", "models"])

if df.empty:
    raise ValueError("No valid rows found. Please check CSV format and column indexes.")

alphas = sorted(df["alpha"].unique())
all_models = sorted({m for lst in df["models"] for m in lst})

alpha_to_x = {a: i for i, a in enumerate(alphas)}
x_positions = list(range(len(alphas)))

color_cycle = plt.rcParams["axes.prop_cycle"].by_key()["color"]
model_color = {m: color_cycle[i % len(color_cycle)] for i, m in enumerate(all_models)}

plt.figure(figsize=(10, 6))

bar_width = 0.8
tile_height = 1.0

for a in alphas:
    x_base = alpha_to_x[a]
    reqs = df[df["alpha"] == a]["models"].tolist()
    current_bottom = 0.0

    for models_in_request in reqs:
        n_models = len(models_in_request)
        if n_models == 0:
            continue

        model_width = bar_width / n_models

        for i, m in enumerate(models_in_request):
            x_center = x_base - bar_width / 2 + (i + 0.5) * model_width

            plt.bar(
                x=x_center,
                height=tile_height,
                width=model_width,
                bottom=current_bottom,
                color=model_color.get(m, "gray"),
                edgecolor="black",
                linewidth=0.4,
                align="center",
            )

        current_bottom += tile_height

plt.xlabel("Alpha", fontsize=12)
plt.ylabel("Requests", fontsize=12)
plt.title("Model Selections per Request for Each Alpha", fontsize=14)
plt.xticks(x_positions, [str(a) for a in alphas])

patches = [mpatches.Patch(color=col, label=mdl) for mdl, col in model_color.items()]
plt.legend(handles=patches, title="Models", bbox_to_anchor=(1.05, 1), loc="upper left")

plt.tight_layout()
plt.show()

