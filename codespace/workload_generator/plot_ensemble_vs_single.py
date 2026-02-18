# #!/usr/bin/env python3
# import ast, json, re
# import numpy as np
# import pandas as pd
# import matplotlib.pyplot as plt
# from pathlib import Path
#
# # ==========================
# # Paths (point to YOUR files)
# # ==========================
# CSV_PATH = Path("/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/codespace/workload_generator/data/ensemble_and _model_wise_accuracy.csv")
# LABELS_JSON = Path("Labels.json")
#
# # Must match logger MODEL_LIST order
# MODEL_LIST = [
#     "mobilenet_v3_small",
#     "resnet18",
#     "resnet34",
#     "resnet50",
#     "resnet101",
#     "vit_b_16",
# ]
#
# # -----------------------------
# # Helpers
# # -----------------------------
# def _norm_text(s: str) -> str:
#     s = (s or "").strip().lower()
#     s = s.replace("_", " ").replace("-", " ")
#     return re.sub(r"\s+", " ", s)
#
# def _tokens(s: str) -> tuple:
#     return tuple(re.findall(r"[a-z]+", (s or "").lower()))
#
# def load_synsets(path: Path):
#     raw = json.loads(path.read_text())
#     d = {}
#     for wnid, names in raw.items():
#         parts = [_norm_text(p) for p in str(names).split(",")]
#         parts = [p for p in (x.strip() for x in parts) if p]
#         if parts:
#             d[str(wnid)] = set(parts)
#     return d
#
# def strict_match_wnid_label(wnid: str, pred_label: str, wnid2names) -> bool:
#     """Correct iff tokens(pred) == tokens(synonym) for ANY synonym of the WNID."""
#     if not wnid or not pred_label: return False
#     syns = wnid2names.get(str(wnid), set())
#     if not syns: return False
#     pt = _tokens(pred_label)
#     if not pt: return False
#     for s in syns:
#         if _tokens(s) == pt:
#             return True
#     return False
#
# def parse_selected_models(val):
#     """
#     Return a set of model names from 'selected_models' as written by logger.py.
#     Handles:
#       - "['vit_b_16', 'resnet101']" (string)
#       - ['vit_b_16', 'resnet101']   (list)
#       - empty/other -> empty set
#     """
#     if isinstance(val, (list, set, tuple)):
#         return set(map(str, val))
#     if isinstance(val, str):
#         try:
#             parsed = ast.literal_eval(val)
#             if isinstance(parsed, (list, set, tuple)):
#                 return set(map(str, parsed))
#         except Exception:
#             pass
#         hits = re.findall(r"'([^']+)'|\"([^\"]+)\"", val)
#         toks = {a or b for a, b in hits if (a or b)}
#         if toks:
#             return toks
#         crude = [x.strip().strip("[] '\"") for x in val.split(",")]
#         return {x for x in crude if x}
#     return set()
#
# # -----------------------------
# # Load CSV robustly
# # -----------------------------
# try:
#     df = pd.read_csv(CSV_PATH, engine="python")
#     if "selected_folder" not in df.columns:
#         raise KeyError
# except Exception:
#     per_label = [f"{m}_label" for m in MODEL_LIST]
#     per_prob  = [f"{m}_prob"  for m in MODEL_LIST]
#     per_wait  = [f"{m}_wait"  for m in MODEL_LIST]
#     LOG_HEADER = [
#         "ID","Deadline","IAR","RespTime","RunTime",
#         "selected_models","label","Accuracy","combiner_policy",
#         "e2e_time_ms","Success","selected_folder",
#         "ModelSize", *per_label, *per_prob, *per_wait, "main_policy",
#     ]
#     df = pd.read_csv(CSV_PATH, header=None, names=LOG_HEADER, engine="python")
#
# df["selected_set"] = df["selected_models"].apply(parse_selected_models)
#
# # Convert per-model probabilities; logger writes -1.0 for “missing”
# for m in MODEL_LIST:
#     col = f"{m}_prob"
#     if col in df.columns:
#         df[col] = pd.to_numeric(df[col], errors="coerce").replace(-1.0, np.nan)
#
# # -----------------------------
# # Ground truth / labels
# # -----------------------------
# if not LABELS_JSON.exists():
#     raise FileNotFoundError("Labels.json not found; required for strict matching.")
# wnid2names = load_synsets(LABELS_JSON)
#
# gt_wnid   = df["selected_folder"].astype(str)
# ens_label = df["label"].astype(str)
# ens_prob  = pd.to_numeric(df["Accuracy"], errors="coerce")
#
# ens_correct = pd.Series([
#     strict_match_wnid_label(w, y, wnid2names) if pd.notna(w) and pd.notna(y) else False
#     for w, y in zip(gt_wnid, ens_label)
# ], dtype="boolean")  # nullable boolean dtype
#
# # -----------------------------
# # Per-model metrics (selected-only)
# # -----------------------------
# model_prob_series   = {}   # probabilities where model was selected & prob present
# model_correct_flags = {}   # boolean correctness aligned to those rows
# support = {}               # number of rows contributing to a model
#
# for m in MODEL_LIST:
#     lbl_col  = f"{m}_label"
#     prob_col = f"{m}_prob"
#
#     probs_all  = pd.to_numeric(df.get(prob_col, pd.Series(np.nan, index=df.index)), errors="coerce")
#     labels_all = df.get(lbl_col, pd.Series("", index=df.index)).astype(str)
#
#     # STRICT: only rows where this model is in selected_models AND prob is present
#     mask_selected = df["selected_set"].apply(lambda S, _m=m: _m in S)
#     mask_eval     = mask_selected & probs_all.notna()
#
#     probs_m = probs_all.where(mask_eval)
#     model_prob_series[m] = probs_m
#
#     # correctness as nullable boolean series (no dtype warning)
#     corr = pd.Series(pd.NA, index=df.index, dtype="boolean")
#     if mask_eval.any():
#         vals = pd.Series(
#             [
#                 strict_match_wnid_label(wn, pred, wnid2names)
#                 for wn, pred in zip(gt_wnid[mask_eval], labels_all[mask_eval])
#             ],
#             index=df.index[mask_eval],
#             dtype="boolean",
#         )
#         corr.loc[mask_eval] = vals
#     model_correct_flags[m] = corr
#     support[m] = int(mask_eval.sum())
#
# # -----------------------------
# # Build arrays for plots (hide zero-support models)
# # -----------------------------
# names = ["model set"]
# prob_series = [ens_prob.dropna()]
# acc_rates   = [float(ens_correct.dropna().astype(bool).mean()) if len(ens_correct.dropna()) else np.nan]
#
# for m in MODEL_LIST:
#     if support[m] == 0:
#         continue
#     probs_m = model_prob_series[m].dropna()
#     corr_m  = model_correct_flags[m].dropna()
#     if len(probs_m) == 0 or len(corr_m) == 0:
#         continue
#
#     names.append(m)
#     prob_series.append(probs_m.astype(float))
#     acc_rates.append(float(corr_m.astype(bool).mean()))
#
# err_rates = [1.0 - a if np.isfinite(a) else np.nan for a in acc_rates]
# mean_probs = [float(np.nanmean(s)) for s in prob_series]
# std_probs  = [float(np.nanstd(s))  for s in prob_series]
#
# # -----------------------------
# # Diagnostics
# # -----------------------------
# print("\n=== Support & strict accuracy (selected rows only) ===")
# print(f"{'Ensemble':>20}: n={int(ens_prob.notna().sum())}  acc={float(ens_correct.dropna().astype(bool).mean())*100:.2f}%")
# for m in MODEL_LIST:
#     n = support[m]
#     if n == 0:
#         print(f"{m:>20}: n=0 (not selected)")
#     else:
#         corr_m = model_correct_flags[m]
#         acc = float(corr_m.dropna().astype(bool).mean()) if corr_m.notna().any() else float("nan")
#         print(f"{m:>20}: n={n:<5}  acc={acc*100:.2f}%")
#
# # -----------------------------
# # Plot 1: Box plot (use tick_labels to avoid deprecation)
# # -----------------------------
# plt.style.use("seaborn-v0_8-paper")
# plt.figure(figsize=(11,5))
# bp = plt.boxplot(
#     prob_series,
#     tick_labels=names,          # <- updated param name
#     showmeans=True, meanline=True, patch_artist=True,
#     whis=1.5, widths=0.6, showfliers=False,
#     flierprops=dict(marker='o', markerfacecolor='gray', markeredgecolor='gray', markersize=4, alpha=0.35),
# )
# colors = ["#2ecc71"] + ["#3498db"]*(len(names)-1)
# for box, c in zip(bp["boxes"], colors):
#     box.set_facecolor(c); box.set_edgecolor("black"); box.set_linewidth(1.0)
# for elem in ["medians","means","whiskers","caps"]:
#     for line in bp[elem]:
#         line.set_color("black"); line.set_linewidth(1.0)
#
# plt.xticks(rotation=20, ha="right")
# plt.ylabel("Probability")
# # plt.title("Confidence (Probability): Model Set vs Models")
# plt.ylim(0, 1.05); plt.grid(axis="y", linestyle="--", alpha=0.35)
# plt.tight_layout()
# out1 = CSV_PATH.with_name("boxplot_selected_strict_new.png")
# # plt.savefig(out1, dpi=300)
# plt.show()
#
# # -----------------------------
# # Plot 2: Stacked bars (% correct vs incorrect)
# # -----------------------------
# plt.figure(figsize=(11,5))
# x = np.arange(len(names)); width = 0.6
# plt.bar(x, acc_rates, width=width, label="% Correct", color="#2ecc71", edgecolor="black")
# plt.bar(x, [1-a for a in acc_rates], bottom=acc_rates, width=width,
#         label="% Incorrect", color="#e74c3c", edgecolor="black")
# plt.xticks(x, names, rotation=20, ha="right")
# plt.ylabel("Fraction of Predictions")
# plt.title("Correct vs Incorrect (Strict): Ensemble vs Models")
# plt.ylim(0, 1.05); plt.legend()
# for i, acc in enumerate(acc_rates):
#     if np.isfinite(acc): plt.text(x[i], acc + 0.02, f"{acc*100:.1f}%", ha="center", fontsize=9)
# plt.tight_layout()
# out2 = CSV_PATH.with_name("correctness_selected_strict.png")
# # plt.savefig(out2, dpi=300)
# plt.show()
#
# # -----------------------------
# # Console summary
# # -----------------------------
# print("\n==== Summary (strict, selected-only) ====")
# for i, n in enumerate(names):
#     print(f"{n:>20} | mean prob={mean_probs[i]:.4f} (std {std_probs[i]:.4f}) | %correct={acc_rates[i]*100:.2f}%")
# print("\n✅ Saved:")
# print(" -", out1)
# print(" -", out2)






# #!/usr/bin/env python3
# import ast, json, re
# import numpy as np
# import pandas as pd
# import matplotlib.pyplot as plt
# from pathlib import Path
#
# # ==========================
# # Paths (point to YOUR files)
# # ==========================
# CSV_PATH = Path("/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/codespace/workload_generator/data/ensemble_and _model_wise_accuracy.csv")
# LABELS_JSON = Path("Labels.json")
#
# MODEL_LIST = [
#     "mobilenet_v3_small",
#     "resnet18",
#     "resnet34",
#     "resnet50",
#     "resnet101",
#     "vit_b_16",
# ]
#
# # -----------------------------
# # Helpers
# # -----------------------------
# def _norm_text(s: str) -> str:
#     s = (s or "").strip().lower()
#     s = s.replace("_", " ").replace("-", " ")
#     return re.sub(r"\s+", " ", s)
#
# def _tokens(s: str) -> tuple:
#     return tuple(re.findall(r"[a-z]+", (s or "").lower()))
#
# def load_synsets(path: Path):
#     raw = json.loads(path.read_text())
#     d = {}
#     for wnid, names in raw.items():
#         parts = [_norm_text(p) for p in str(names).split(",")]
#         parts = [p for p in (x.strip() for x in parts) if p]
#         if parts:
#             d[str(wnid)] = set(parts)
#     return d
#
# def strict_match_wnid_label(wnid: str, pred_label: str, wnid2names) -> bool:
#     if not wnid or not pred_label:
#         return False
#     syns = wnid2names.get(str(wnid), set())
#     if not syns:
#         return False
#     pt = _tokens(pred_label)
#     if not pt:
#         return False
#     for s in syns:
#         if _tokens(s) == pt:
#             return True
#     return False
#
# def parse_selected_models(val):
#     if isinstance(val, (list, set, tuple)):
#         return set(map(str, val))
#     if isinstance(val, str):
#         try:
#             parsed = ast.literal_eval(val)
#             if isinstance(parsed, (list, set, tuple)):
#                 return set(map(str, parsed))
#         except Exception:
#             pass
#         hits = re.findall(r"'([^']+)'|\"([^\"]+)\"", val)
#         toks = {a or b for a, b in hits if (a or b)}
#         if toks:
#             return toks
#         crude = [x.strip().strip("[] '\"") for x in val.split(",")]
#         return {x for x in crude if x}
#     return set()
#
# # -----------------------------
# # Load CSV robustly
# # -----------------------------
# try:
#     df = pd.read_csv(CSV_PATH, engine="python")
#     if "selected_folder" not in df.columns:
#         raise KeyError
# except Exception:
#     per_label = [f"{m}_label" for m in MODEL_LIST]
#     per_prob  = [f"{m}_prob"  for m in MODEL_LIST]
#     per_wait  = [f"{m}_wait"  for m in MODEL_LIST]
#     LOG_HEADER = [
#         "ID","Deadline","IAR","RespTime","RunTime",
#         "selected_models","label","Accuracy","combiner_policy",
#         "e2e_time_ms","Success","selected_folder",
#         "ModelSize", *per_label, *per_prob, *per_wait, "main_policy",
#     ]
#     df = pd.read_csv(CSV_PATH, header=None, names=LOG_HEADER, engine="python")
#
# df["selected_set"] = df["selected_models"].apply(parse_selected_models)
#
# # Convert per-model probabilities; logger writes -1.0 for “missing”
# for m in MODEL_LIST:
#     col = f"{m}_prob"
#     if col in df.columns:
#         df[col] = pd.to_numeric(df[col], errors="coerce").replace(-1.0, np.nan)
#
# # -----------------------------
# # Ground truth / labels
# # -----------------------------
# if not LABELS_JSON.exists():
#     raise FileNotFoundError("Labels.json not found; required for strict matching.")
# wnid2names = load_synsets(LABELS_JSON)
#
# gt_wnid   = df["selected_folder"].astype(str)
# ens_label = df["label"].astype(str)
# ens_prob  = pd.to_numeric(df["Accuracy"], errors="coerce")
#
# ens_correct = pd.Series([
#     strict_match_wnid_label(w, y, wnid2names) if pd.notna(w) and pd.notna(y) else False
#     for w, y in zip(gt_wnid, ens_label)
# ], dtype="boolean")
#
# # -----------------------------
# # Per-model metrics (selected-only)
# # -----------------------------
# model_prob_series = {}
# support = {}
#
# for m in MODEL_LIST:
#     prob_col = f"{m}_prob"
#     probs_all = pd.to_numeric(df.get(prob_col, pd.Series(np.nan, index=df.index)), errors="coerce")
#
#     mask_selected = df["selected_set"].apply(lambda S, _m=m: _m in S)
#     mask_eval     = mask_selected & probs_all.notna()
#
#     model_prob_series[m] = probs_all.where(mask_eval)
#     support[m] = int(mask_eval.sum())
#
# # -----------------------------
# # Build arrays for boxplot
# # -----------------------------
# names = ["model set"]
# prob_series = [ens_prob.dropna()]
#
# for m in MODEL_LIST:
#     if support[m] == 0:
#         continue
#     probs_m = model_prob_series[m].dropna()
#     if len(probs_m) == 0:
#         continue
#     names.append(m)
#     prob_series.append(probs_m.astype(float))
#
# # ======================================================
# # ✅ Boxplot: increase X/Y axis tick text sizes
# # ======================================================
# plt.style.use("seaborn-v0_8-paper")
#
# FIG_W, FIG_H = 11, 5
# X_TICK_FONTSIZE = 17   # ✅ increase this
# Y_TICK_FONTSIZE = 14   # ✅ increase this
# YLABEL_FONTSIZE = 18   # ✅ increase this
#
# plt.figure(figsize=(FIG_W, FIG_H))
# bp = plt.boxplot(
#     prob_series,
#     tick_labels=names,
#     showmeans=True, meanline=True, patch_artist=True,
#     whis=1.5, widths=0.6, showfliers=False,
#     flierprops=dict(marker='o', markerfacecolor='gray', markeredgecolor='gray', markersize=4, alpha=0.35),
# )
#
# colors = ["#2ecc71"] + ["#3498db"]*(len(names)-1)
# for box, c in zip(bp["boxes"], colors):
#     box.set_facecolor(c)
#     box.set_edgecolor("black")
#     box.set_linewidth(1.0)
#
# for elem in ["medians","means","whiskers","caps"]:
#     for line in bp[elem]:
#         line.set_color("black")
#         line.set_linewidth(1.0)
#
# # ✅ Increase tick label sizes
# plt.xticks(rotation=20, ha="right", fontsize=X_TICK_FONTSIZE)
# plt.yticks(fontsize=Y_TICK_FONTSIZE)
#
# # ✅ Increase y-axis label size
# plt.ylabel("Probability", fontsize=YLABEL_FONTSIZE)
#
# plt.ylim(0, 1.05)
# plt.grid(axis="y", linestyle="--", alpha=0.35)
#
# plt.tight_layout()
#
# out1 = CSV_PATH.with_name("boxplot_selected_strict_new.png")
# plt.savefig(out1, dpi=400, bbox_inches="tight")
# plt.show()
#
# print("✅ Saved:", out1)


# #!/usr/bin/env python3
# import ast, json, re
# import numpy as np
# import pandas as pd
# import matplotlib.pyplot as plt
# from pathlib import Path
#
# # ==========================
# # Paths (point to YOUR files)
# # ==========================
# CSV_PATH = Path("/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/codespace/workload_generator/data/accuracy_confidence_logs_2_3_S_probD.csv")
# LABELS_JSON = Path("Labels.json")
#
# MODEL_LIST = [
#     "mobilenet_v3_small",
#     "resnet18",
#     "resnet34",
#     "resnet50",
#     "resnet101",
#     "vit_b_16",
# ]
#
# # -----------------------------
# # Helpers
# # -----------------------------
# def _norm_text(s: str) -> str:
#     s = (s or "").strip().lower()
#     s = s.replace("_", " ").replace("-", " ")
#     return re.sub(r"\s+", " ", s)
#
# def _tokens(s: str) -> tuple:
#     return tuple(re.findall(r"[a-z]+", (s or "").lower()))
#
# def load_synsets(path: Path):
#     raw = json.loads(path.read_text())
#     d = {}
#     for wnid, names in raw.items():
#         parts = [_norm_text(p) for p in str(names).split(",")]
#         parts = [p for p in (x.strip() for x in parts) if p]
#         if parts:
#             d[str(wnid)] = set(parts)
#     return d
#
# def strict_match_wnid_label(wnid: str, pred_label: str, wnid2names) -> bool:
#     if not wnid or not pred_label:
#         return False
#     syns = wnid2names.get(str(wnid), set())
#     if not syns:
#         return False
#     pt = _tokens(pred_label)
#     if not pt:
#         return False
#     for s in syns:
#         if _tokens(s) == pt:
#             return True
#     return False
#
# def parse_selected_models(val):
#     """
#     Works for:
#       ['resnet101']
#       "['resnet34', 'resnet18', 'mobilenet_v3_small']"
#     """
#     if isinstance(val, (list, set, tuple)):
#         return set(map(str, val))
#
#     if isinstance(val, str):
#         s = val.strip()
#         # Try literal eval first
#         try:
#             parsed = ast.literal_eval(s)
#             if isinstance(parsed, (list, set, tuple)):
#                 return set(map(str, parsed))
#         except Exception:
#             pass
#
#         # Fallback: extract quoted tokens
#         hits = re.findall(r"'([^']+)'|\"([^\"]+)\"", s)
#         toks = {a or b for a, b in hits if (a or b)}
#         if toks:
#             return toks
#
#         # Last fallback: crude split
#         crude = [x.strip().strip("[] '\"") for x in s.split(",")]
#         return {x for x in crude if x}
#
#     return set()
#
# # -----------------------------
# # ✅ Build LOG_HEADER for NEW log (has main_policy + alpha)
# # -----------------------------
# per_label = [f"{m}_label" for m in MODEL_LIST]
# per_prob  = [f"{m}_prob"  for m in MODEL_LIST]
# per_wait  = [f"{m}_wait"  for m in MODEL_LIST]
#
# LOG_HEADER = [
#     "ID","Deadline","IAR","RespTime","RunTime",
#     "selected_models","label","Accuracy","combiner_policy",
#     "e2e_time_ms","Success","selected_folder",
#     "ModelSize",
#     *per_label,
#     *per_prob,
#     *per_wait,
#     "main_policy",
#     "alpha",
# ]
#
# # -----------------------------
# # ✅ Always read as headerless (your file rows start with REQ-xxxx)
# # -----------------------------
# df = pd.read_csv(
#     CSV_PATH,
#     header=None,
#     names=LOG_HEADER,
#     engine="python",
#     na_values=["", "nan", "NaN", "-1", "-1.0"]
# )
#
# # Parse selected models set
# df["selected_set"] = df["selected_models"].apply(parse_selected_models)
#
# # Convert per-model probabilities; logger writes -1.0 for missing
# for m in MODEL_LIST:
#     col = f"{m}_prob"
#     if col in df.columns:
#         df[col] = pd.to_numeric(df[col], errors="coerce").replace(-1.0, np.nan)
#
# # -----------------------------
# # Ground truth / labels
# # -----------------------------
# if not LABELS_JSON.exists():
#     raise FileNotFoundError("Labels.json not found; required for strict matching.")
# wnid2names = load_synsets(LABELS_JSON)
#
# gt_wnid   = df["selected_folder"].astype(str)
# ens_label = df["label"].astype(str)
#
# # ⚠️ Here "Accuracy" is used as the “model set probability/confidence” in your logs
# ens_prob  = pd.to_numeric(df["Accuracy"], errors="coerce")
#
# ens_correct = pd.Series([
#     strict_match_wnid_label(w, y, wnid2names) if pd.notna(w) and pd.notna(y) else False
#     for w, y in zip(gt_wnid, ens_label)
# ], dtype="boolean")
#
# # -----------------------------
# # Per-model probability (selected-only)
# # -----------------------------
# model_prob_series = {}
# support = {}
#
# for m in MODEL_LIST:
#     prob_col = f"{m}_prob"
#     probs_all = pd.to_numeric(df.get(prob_col, pd.Series(np.nan, index=df.index)), errors="coerce")
#
#     mask_selected = df["selected_set"].apply(lambda S, _m=m: _m in S)
#     mask_eval     = mask_selected & probs_all.notna()
#
#     model_prob_series[m] = probs_all.where(mask_eval)
#     support[m] = int(mask_eval.sum())
#
# # -----------------------------
# # Build arrays for boxplot
# # -----------------------------
# names = ["model set"]
# prob_series = [ens_prob.dropna()]
#
# for m in MODEL_LIST:
#     if support[m] == 0:
#         continue
#     probs_m = model_prob_series[m].dropna()
#     if len(probs_m) == 0:
#         continue
#     names.append(m)
#     prob_series.append(probs_m.astype(float))
#
# # ======================================================
# # Boxplot styling (same as you had)
# # ======================================================
# plt.style.use("seaborn-v0_8-paper")
#
# FIG_W, FIG_H = 11, 5
# X_TICK_FONTSIZE = 17
# Y_TICK_FONTSIZE = 14
# YLABEL_FONTSIZE = 18
#
# plt.figure(figsize=(FIG_W, FIG_H))
# bp = plt.boxplot(
#     prob_series,
#     tick_labels=names,
#     showmeans=True, meanline=True, patch_artist=True,
#     whis=1.5, widths=0.6, showfliers=False,
#     flierprops=dict(marker='o', markerfacecolor='gray', markeredgecolor='gray', markersize=4, alpha=0.35),
# )
#
# colors = ["#2ecc71"] + ["#3498db"] * (len(names) - 1)
# for box, c in zip(bp["boxes"], colors):
#     box.set_facecolor(c)
#     box.set_edgecolor("black")
#     box.set_linewidth(1.0)
#
# for elem in ["medians", "means", "whiskers", "caps"]:
#     for line in bp[elem]:
#         line.set_color("black")
#         line.set_linewidth(1.0)
#
# plt.xticks(rotation=20, ha="right", fontsize=X_TICK_FONTSIZE)
# plt.yticks(fontsize=Y_TICK_FONTSIZE)
# plt.ylabel("Probability", fontsize=YLABEL_FONTSIZE)
#
# plt.ylim(0, 1.05)
# plt.grid(axis="y", linestyle="--", alpha=0.35)
#
# plt.tight_layout()
#
# out1 = CSV_PATH.with_name("boxplot_selected_strict_new.png")
# plt.savefig(out1, dpi=400, bbox_inches="tight")
# plt.show()
#
# print("✅ Saved:", out1)



#!/usr/bin/env python3
"""
Boxplot of confidence/probability distributions from MODE-S workload logs (headerless CSV),
with Option A:

✅ Separate ensemble distributions:
  - "model set (size 2)"
  - "model set (size 3)"

And keep per-model probability distributions (only when that model was selected).

Notes:
- Assumes your CSV rows start with REQ-... so we read with header=None and LOG_HEADER.
- Treats df["Accuracy"] as the ensemble confidence/probability (your current logging behavior).
- Treats per-model *_prob columns as per-model confidence (with -1.0 meaning missing).
"""

# import ast, json, re
# from pathlib import Path
# import numpy as np
# import pandas as pd
# import matplotlib.pyplot as plt
#
# # ==========================
# # Paths (point to YOUR files)
# # ==========================
# CSV_PATH = Path("/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/codespace/workload_generator/data/accuracy_confidence_logs_2_3_S_probD.csv")
# LABELS_JSON = Path("Labels.json")
#
# MODEL_LIST = [
#     "mobilenet_v3_small",
#     "resnet18",
#     "resnet34",
#     "resnet50",
#     "resnet101",
#     "vit_b_16",
# ]
#
# # -----------------------------
# # Helpers
# # -----------------------------
# def parse_selected_models(val):
#     """Parse selected_models like "['resnet34', 'resnet18']" into a set."""
#     if isinstance(val, (list, set, tuple)):
#         return set(map(str, val))
#
#     if isinstance(val, str):
#         s = val.strip()
#         # Try literal eval first
#         try:
#             parsed = ast.literal_eval(s)
#             if isinstance(parsed, (list, set, tuple)):
#                 return set(map(str, parsed))
#         except Exception:
#             pass
#
#         # Fallback: extract quoted tokens
#         hits = re.findall(r"'([^']+)'|\"([^\"]+)\"", s)
#         toks = {a or b for a, b in hits if (a or b)}
#         if toks:
#             return toks
#
#         # Last fallback: crude split
#         crude = [x.strip().strip("[] '\"") for x in s.split(",")]
#         return {x for x in crude if x}
#
#     return set()
#
# # -----------------------------
# # Build LOG_HEADER for your NEW log format (ends with main_policy, alpha)
# # -----------------------------
# per_label = [f"{m}_label" for m in MODEL_LIST]
# per_prob  = [f"{m}_prob"  for m in MODEL_LIST]
# per_wait  = [f"{m}_wait"  for m in MODEL_LIST]
#
# LOG_HEADER = [
#     "ID","Deadline","IAR","RespTime","RunTime",
#     "selected_models","label","Accuracy","combiner_policy",
#     "e2e_time_ms","Success","selected_folder",
#     "ModelSize",
#     *per_label,
#     *per_prob,
#     *per_wait,
#     "main_policy",
#     "alpha",
# ]
#
# def main():
#     # -----------------------------
#     # Read headerless CSV
#     # -----------------------------
#     df = pd.read_csv(
#         CSV_PATH,
#         header=None,
#         names=LOG_HEADER,
#         engine="python",
#         na_values=["", "nan", "NaN", "-1", "-1.0"]
#     )
#
#     # Normalize ModelSize
#     df["ModelSize"] = pd.to_numeric(df["ModelSize"], errors="coerce").fillna(0).astype(int)
#
#     # Parse selected models
#     df["selected_set"] = df["selected_models"].apply(parse_selected_models)
#
#     # Convert ensemble "Accuracy" (used as confidence/prob) to numeric
#     df["Accuracy"] = pd.to_numeric(df["Accuracy"], errors="coerce")
#
#     # Convert per-model probabilities; treat -1.0 as missing
#     for m in MODEL_LIST:
#         col = f"{m}_prob"
#         if col in df.columns:
#             df[col] = pd.to_numeric(df[col], errors="coerce").replace(-1.0, np.nan)
#
#     # -----------------------------
#     # ✅ Option A: separate ensemble distributions for size 2 and size 3
#     # -----------------------------
#     ens_prob_2 = df.loc[df["ModelSize"] == 2, "Accuracy"].dropna()
#     ens_prob_3 = df.loc[df["ModelSize"] == 3, "Accuracy"].dropna()
#
#     names = []
#     prob_series = []
#
#     # Only add if present (so code won't crash when a size is missing)
#     if len(ens_prob_2) > 0:
#         names.append("model set (size 2)")
#         prob_series.append(ens_prob_2.astype(float))
#     if len(ens_prob_3) > 0:
#         names.append("model set (size 3)")
#         prob_series.append(ens_prob_3.astype(float))
#
#     # -----------------------------
#     # Per-model probability distributions (selected-only)
#     # -----------------------------
#     support = {}
#     for m in MODEL_LIST:
#         prob_col = f"{m}_prob"
#         probs_all = pd.to_numeric(df.get(prob_col, pd.Series(np.nan, index=df.index)), errors="coerce")
#
#         mask_selected = df["selected_set"].apply(lambda S, _m=m: _m in S)
#         mask_eval = mask_selected & probs_all.notna()
#
#         support[m] = int(mask_eval.sum())
#         probs_m = probs_all.where(mask_eval).dropna()
#         if len(probs_m) == 0:
#             continue
#
#         names.append(m)
#         prob_series.append(probs_m.astype(float))
#
#     if len(prob_series) == 0:
#         raise RuntimeError("No data found to plot. Check CSV_PATH and column alignment.")
#
#     # ======================================================
#     # Boxplot styling (same look as your previous plot)
#     # ======================================================
#     plt.style.use("seaborn-v0_8-paper")
#
#     FIG_W, FIG_H = 11, 5
#     X_TICK_FONTSIZE = 17
#     Y_TICK_FONTSIZE = 14
#     YLABEL_FONTSIZE = 18
#
#     plt.figure(figsize=(FIG_W, FIG_H))
#     bp = plt.boxplot(
#         prob_series,
#         tick_labels=names,
#         showmeans=True, meanline=True, patch_artist=True,
#         whis=1.5, widths=0.6, showfliers=False,
#         flierprops=dict(marker='o', markerfacecolor='gray', markeredgecolor='gray', markersize=4, alpha=0.35),
#     )
#
#     # Colors:
#     # - first 2 boxes (if both exist) -> green
#     # - remaining -> blue
#     # If only one ensemble size exists, first box green, rest blue.
#     n_ens_boxes = 0
#     for nm in names:
#         if nm.startswith("model set"):
#             n_ens_boxes += 1
#         else:
#             break
#
#     colors = (["#2ecc71"] * n_ens_boxes) + (["#3498db"] * (len(names) - n_ens_boxes))
#
#     for box, c in zip(bp["boxes"], colors):
#         box.set_facecolor(c)
#         box.set_edgecolor("black")
#         box.set_linewidth(1.0)
#
#     for elem in ["medians", "means", "whiskers", "caps"]:
#         for line in bp[elem]:
#             line.set_color("black")
#             line.set_linewidth(1.0)
#
#     plt.xticks(rotation=20, ha="right", fontsize=X_TICK_FONTSIZE)
#     plt.yticks(fontsize=Y_TICK_FONTSIZE)
#     plt.ylabel("Confidence", fontsize=YLABEL_FONTSIZE)
#
#     plt.ylim(0, 1.05)
#     plt.grid(axis="y", linestyle="--", alpha=0.35)
#     plt.tight_layout()
#
#     out_png = CSV_PATH.with_name("boxplot_selected_size2_size3_and_models.png")
#     plt.savefig(out_png, dpi=400, bbox_inches="tight")
#     plt.show()
#
#     print("✅ Saved:", out_png)
#     print(f"Ensemble size-2 points: {len(ens_prob_2)}")
#     print(f"Ensemble size-3 points: {len(ens_prob_3)}")
#     print("Per-model support (#rows evaluated where model was selected & prob present):")
#     for m in MODEL_LIST:
#         print(f"  - {m}: {support.get(m, 0)}")
#
# if __name__ == "__main__":
#     main()




import ast, re
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# ==========================
# Paths (point to YOUR files)
# ==========================
CSV_PATH = Path("/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/codespace/workload_generator/data/accuracy_confidence_logs_2_3_S_probD.csv")

MODEL_LIST = [
    "mobilenet_v3_small",
    "resnet18",
    "resnet34",
    "resnet50",
    "resnet101",
    "vit_b_16",
]

# -----------------------------
# Helpers
# -----------------------------
def parse_selected_models(val):
    """Parse selected_models like "['resnet34', 'resnet18']" into a set."""
    if isinstance(val, (list, set, tuple)):
        return set(map(str, val))

    if isinstance(val, str):
        s = val.strip()
        # Try literal eval first
        try:
            parsed = ast.literal_eval(s)
            if isinstance(parsed, (list, set, tuple)):
                return set(map(str, parsed))
        except Exception:
            pass

        # Fallback: extract quoted tokens
        hits = re.findall(r"'([^']+)'|\"([^\"]+)\"", s)
        toks = {a or b for a, b in hits if (a or b)}
        if toks:
            return toks

        # Last fallback: crude split
        crude = [x.strip().strip("[] '\"") for x in s.split(",")]
        return {x for x in crude if x}

    return set()

# -----------------------------
# Build LOG_HEADER for your log format (ends with main_policy, alpha)
# -----------------------------
per_label = [f"{m}_label" for m in MODEL_LIST]
per_prob  = [f"{m}_prob"  for m in MODEL_LIST]
per_wait  = [f"{m}_wait"  for m in MODEL_LIST]

LOG_HEADER = [
    "ID","Deadline","IAR","RespTime","RunTime",
    "selected_models","label","Accuracy","combiner_policy",
    "e2e_time_ms","Success","selected_folder",
    "ModelSize",
    *per_label,
    *per_prob,
    *per_wait,
    "main_policy",
    "alpha",
]

def main():
    # -----------------------------
    # Read headerless CSV
    # -----------------------------
    df = pd.read_csv(
        CSV_PATH,
        header=None,
        names=LOG_HEADER,
        engine="python",
        na_values=["", "nan", "NaN", "-1", "-1.0"]
    )

    # Normalize ModelSize
    df["ModelSize"] = pd.to_numeric(df["ModelSize"], errors="coerce").fillna(0).astype(int)

    # Parse selected models
    df["selected_set"] = df["selected_models"].apply(parse_selected_models)

    # Convert ensemble "Accuracy" (used as confidence/prob) to numeric
    df["Accuracy"] = pd.to_numeric(df["Accuracy"], errors="coerce")

    # Convert per-model probabilities; treat -1.0 as missing
    for m in MODEL_LIST:
        col = f"{m}_prob"
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").replace(-1.0, np.nan)

    # ------------------------------------------------------------
    # ✅ Ensemble distributions (size 2 and size 3) from Accuracy
    # ------------------------------------------------------------
    ens_prob_2 = df.loc[df["ModelSize"] == 2, "Accuracy"].dropna()
    ens_prob_3 = df.loc[df["ModelSize"] == 3, "Accuracy"].dropna()

    names = []
    prob_series = []

    if len(ens_prob_2) > 0:
        names.append("model set (size 2)")
        prob_series.append(ens_prob_2.astype(float))
    if len(ens_prob_3) > 0:
        names.append("model set (size 3)")
        prob_series.append(ens_prob_3.astype(float))

    # ------------------------------------------------------------
    # ✅ Single-model distributions (ONLY ModelSize==1)
    # This makes Fig 4 consistent with your Table 2 medians
    # ------------------------------------------------------------
    support = {}
    for m in MODEL_LIST:
        prob_col = f"{m}_prob"
        probs_all = pd.to_numeric(df.get(prob_col, pd.Series(np.nan, index=df.index)), errors="coerce")

        mask_selected = df["selected_set"].apply(lambda S, _m=m: _m in S)
        mask_m1 = df["ModelSize"] == 1
        mask_eval = mask_m1 & mask_selected & probs_all.notna()

        support[m] = int(mask_eval.sum())
        probs_m = probs_all.where(mask_eval).dropna()

        if len(probs_m) == 0:
            continue

        names.append(m)
        prob_series.append(probs_m.astype(float))

    if len(prob_series) == 0:
        raise RuntimeError("No data found to plot. Check CSV_PATH and column alignment.")

    # ======================================================
    # Boxplot styling (keep SAME look; solid=median, dashed=mean)
    # ======================================================
    plt.style.use("seaborn-v0_8-paper")

    FIG_W, FIG_H = 11, 5
    X_TICK_FONTSIZE = 17
    Y_TICK_FONTSIZE = 14
    YLABEL_FONTSIZE = 18

    plt.figure(figsize=(FIG_W, FIG_H))
    bp = plt.boxplot(
        prob_series,
        tick_labels=names,
        showmeans=True, meanline=True, patch_artist=True,
        whis=1.5, widths=0.6, showfliers=False,
        flierprops=dict(
            marker='o', markerfacecolor='gray', markeredgecolor='gray',
            markersize=4, alpha=0.35
        ),
    )

    # Color first two (ensemble) boxes green, rest blue
    n_ens_boxes = 0
    for nm in names:
        if nm.startswith("model set"):
            n_ens_boxes += 1
        else:
            break

    colors = (["#2ecc71"] * n_ens_boxes) + (["#3498db"] * (len(names) - n_ens_boxes))

    for box, c in zip(bp["boxes"], colors):
        box.set_facecolor(c)
        box.set_edgecolor("black")
        box.set_linewidth(1.0)

    # Ensure median and mean lines are black
    # (median is solid line; mean is dashed line)
    for elem in ["medians", "means", "whiskers", "caps"]:
        for line in bp[elem]:
            line.set_color("black")
            line.set_linewidth(1.0)

    plt.xticks(rotation=20, ha="right", fontsize=X_TICK_FONTSIZE)
    plt.yticks(fontsize=Y_TICK_FONTSIZE)
    plt.ylabel("Confidence", fontsize=YLABEL_FONTSIZE)

    plt.ylim(0, 1.05)
    plt.grid(axis="y", linestyle="--", alpha=0.35)
    plt.tight_layout()

    out_png = CSV_PATH.with_name("boxplot_selected_size2_size3_and_models.png")
    plt.savefig(out_png, dpi=400, bbox_inches="tight")
    plt.show()

    print("✅ Saved:", out_png)
    print(f"Ensemble size-2 points: {len(ens_prob_2)}")
    print(f"Ensemble size-3 points: {len(ens_prob_3)}")
    print("Per-model support (#rows evaluated where ModelSize==1 & model was selected & prob present):")
    for m in MODEL_LIST:
        print(f"  - {m}: {support.get(m, 0)}")

    # Optional: print the medians/means used (for debugging)
    print("\nMedians (solid) and Means (dashed) used in the plot:")
    for nm, s in zip(names, prob_series):
        print(f"{nm:25s} median={np.median(s):.3f}  mean={np.mean(s):.3f}  n={len(s)}")

if __name__ == "__main__":
    main()
