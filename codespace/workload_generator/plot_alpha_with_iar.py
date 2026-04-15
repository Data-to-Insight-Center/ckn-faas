import math
import pandas as pd
import matplotlib.pyplot as plt

CSV_PATH = "/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/codespace/workload_generator/data/alpha analysis_seq_para.csv"
OUT_PNG = "alpha_vs_runtime_subplots_by_iar.png"

# Column indexes from your logger
IAR_COL_IDX = 2
RUNTIME_COL_IDX = 4
ALPHA_COL_IDX = 20


def load_data(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path, header=None)

    df = df.rename(columns={
        IAR_COL_IDX: "IAR",
        RUNTIME_COL_IDX: "RunTime",
        ALPHA_COL_IDX: "alpha",
    })

    df["IAR"] = pd.to_numeric(df["IAR"], errors="coerce")
    df["RunTime"] = pd.to_numeric(df["RunTime"], errors="coerce")
    df["alpha"] = pd.to_numeric(df["alpha"], errors="coerce")

    df = df.dropna(subset=["IAR", "RunTime", "alpha"]).copy()
    return df


def plot_subplots_by_iar(df: pd.DataFrame, out_png: str) -> None:
    iar_values = sorted(df["IAR"].unique())

    n = len(iar_values)
    ncols = 3
    nrows = math.ceil(n / ncols)

    fig, axes = plt.subplots(nrows=nrows, ncols=ncols, figsize=(5 * ncols, 4 * nrows))
    axes = axes.flatten()

    for idx, iar in enumerate(iar_values):
        ax = axes[idx]
        group = df[df["IAR"] == iar].sort_values("RunTime")

        ax.plot(group["RunTime"], group["alpha"], marker="o")
        ax.set_title(f"IAR = {int(iar)}")
        ax.set_xlabel("RunTime (s)")
        ax.set_ylabel("Alpha")
        ax.grid(True)

    # Hide unused subplot axes
    for j in range(len(iar_values), len(axes)):
        axes[j].axis("off")

    fig.suptitle("Alpha vs RunTime for Each IAR", fontsize=16)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(out_png, dpi=200)
    plt.show()

    print(f"[OK] Plot saved to: {out_png}")


def main():
    df = load_data(CSV_PATH)
    print(df[["IAR", "RunTime", "alpha"]].head())
    plot_subplots_by_iar(df, OUT_PNG)


if __name__ == "__main__":
    main()