import argparse
from typing import cast
import os
import subprocess

if __name__ == "__main__":
    from mk_ic import install
    install()

    parser = argparse.ArgumentParser("Rick and Morty Combine")
    _ = parser.add_argument(
        "--v1",
        help="Path to the first version.",
        type=str,
        required=True,
    )
    _ = parser.add_argument(
        "--v2",
        help="Path to the second version.",
        type=str,
        required=True,
    )
    _ = parser.add_argument(
        "--output",
        help="Path to the output directory.",
        required=False,
        default="output.mkv"
    )
    _ = parser.add_argument(
        "--dry-run",
        help="If set, don't actually run commands with side-effects, just print the command that would be run.",
        action="store_true",)
    args = parser.parse_args()

    v1_dir = cast(str, args.v1)
    v2_dir = cast(str, args.v2)
    output = cast(str, args.output)
    dry_run = cast(bool, args.dry_run)

    # Build list of input files by walking
    v1_files = []
    for dirpath, _, filenames in os.walk(v1_dir):
        for f in filenames:
            if 'Extra' in dirpath:
                continue
            if 'Sample' in dirpath:
                continue
            if f.endswith(".mkv") or f.endswith(".mp4"):
                v1_files.append(os.path.join(dirpath, f))

    v2_files = []
    for dirpath, _, filenames in os.walk(v2_dir):
        for f in filenames:
            if 'Extra' in dirpath:
                continue
            if 'Sample' in dirpath:
                continue
            if f.endswith(".mkv") or f.endswith(".mp4"):
                v2_files.append(os.path.join(dirpath, f))

    v1_files.sort()
    v2_files.sort()

    assert len(v1_files) == len(v2_files), f"Number of files in v1 ({len(v1_files)}) and v2 ({len(v2_files)}) do not match."

    for v1_file, v2_file in zip(v1_files, v2_files):
        base_name = os.path.basename(v1_file)
        output_path = os.path.join(output, base_name)
        cmd = [
            "python",
            "rick_and_morty_1.py",
            "--inputs", v1_file,
            v2_file,
            "--output", output_path,
        ]
        if dry_run:
            print(cmd)
        else:
            print(f"Running: {cmd}")
            subprocess.run(cmd, check=True)
