"""Print train.parquet columns, row counts and holdout matches. First thing to run on real data."""
from __future__ import annotations

from core.config import load_config, repo_path


def main():
    import pandas as pd

    from model.features import check_columns, holdout_fire_ids

    cfg = load_config()
    df = pd.read_parquet(repo_path(cfg["paths"]["train_table"]))
    print(f"rows: {len(df):,}")
    print("columns:", ", ".join(df.columns))
    check_columns(df, cfg)
    c = cfg["columns"]
    print(f"fires: {df[c['fire_id']].nunique():,}  positives: {(df[c['label']] == 1).sum():,}")
    if c["country"] in df:
        print(df.groupby(c["country"])[c["fire_id"]].nunique().rename("fires").to_string())
    for k, ids in holdout_fire_ids(df, cfg).items():
        print(f"holdout {k}: {len(ids)} fires")


if __name__ == "__main__":
    main()
