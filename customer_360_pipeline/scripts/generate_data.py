#!/usr/bin/env python3
"""
CLI script to generate synthetic multi-source customer datasets.
Supports 'small' starter sample, 'medium', and 'large' (100k+ records) with fixed random seed.
"""

import argparse
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.generator import DataGenerator


def main():
    parser = argparse.ArgumentParser(description="Synthetic Customer 360 Dataset Generator")
    parser.add_argument(
        "--scale",
        type=str,
        choices=["small", "medium", "large"],
        default="small",
        help="Dataset scale: small (~400 records), medium (~50k records), large (200k+ records)",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/sample",
        help="Directory to write CSV files",
    )
    parser.add_argument(
        "--labels-dir",
        type=str,
        default="data/expected_labels",
        help="Directory to write ground truth labels",
    )
    args = parser.parse_args()

    print(f"Generating '{args.scale}' dataset with seed={args.seed}...")
    generator = DataGenerator(seed=args.seed)
    counts = generator.generate(
        scale=args.scale,
        output_dir=args.output_dir,
        labels_dir=args.labels_dir,
    )

    print("\nDataset generation complete!")
    print(f"Output directory: {args.output_dir}")
    print(f"Ground truth labels: {args.labels_dir}")
    print("Row counts generated:")
    for k, v in counts.items():
        print(f"  - {k}: {v:,} rows")


if __name__ == "__main__":
    main()
