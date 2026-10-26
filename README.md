# tokyo-flood-record-jp

Reproducible collection of the 浸水実績図 (flood records, 1974 to 2019) of Tokyo from the Flood Risk
Information System of the Tokyo Metropolitan Government. The dataset card is generated into
`data/README.md` (not tracked; the data is published at
https://huggingface.co/datasets/yuiseki/tokyo-flood-record-jp).

```
uv run python scripts/01_download.py      # the page, its listing, the 43 zips and N03 of Tokyo (data/raw/<date>, data/docs)
uv run python scripts/02_export_parquet.py
uv run python scripts/03_verify.py        # each Parquet vs its zips, parsed by hand; the municipality check
uv run python scripts/04_card.py
uv run python src/publish.py [--push]     # dry run by default
```

Code: MIT. Data: CC BY 4.0, see the card.
