"""
A simple Python utility to split a large file into smaller chunks and merge them back.

Usage:
  Split: python file_split_merge.py split <path_to_file> [--size MB]
  Merge: python file_split_merge.py merge <prefix> [--output path]

Examples:
  python file_split_merge.py split big_file.zip --size 40
  python file_split_merge.py merge big_file.zip --output restored.zip
"""
import os
import glob
import argparse

DEFAULT_CHUNK_MB = 40

def split_file(file_path: str, chunk_size: int):
    """
    Split `file_path` into chunks of up to `chunk_size` bytes.
    Chunks are named: <file_path>.part001, .part002, ...
    """
    with open(file_path, 'rb') as f:
        index = 1
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            part_name = f"{file_path}.part{index:03d}"
            with open(part_name, 'wb') as pf:
                pf.write(chunk)
            print(f"Wrote chunk: {part_name}")
            index += 1

def merge_file(prefix: str, output_path: str):
    """
    Merge all files matching `<prefix>.partNNN` into `output_path`.
    """
    parts = sorted(glob.glob(f"{prefix}.part*"))
    if not parts:
        print(f"No parts found with prefix {prefix}.part")
        return
    with open(output_path, 'wb') as out:
        for part in parts:
            print(f"Appending {part}")
            with open(part, 'rb') as pf:
                out.write(pf.read())
    print(f"Merged into: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Split and merge large files for GitHub-friendly commits"
    )
    subparsers = parser.add_subparsers(dest='command')

    # Split command
    sp = subparsers.add_parser('split', help='Split a file into smaller chunks')
    sp.add_argument('file', help='Path to the file to split')
    sp.add_argument(
        '--size', type=int, default=DEFAULT_CHUNK_MB,
        help=f"Maximum chunk size in MB (default: {DEFAULT_CHUNK_MB})"
    )

    # Merge command
    mp = subparsers.add_parser('merge', help='Merge chunks back into original file')
    mp.add_argument('prefix', help='Original file prefix (e.g., big_file.zip)')
    mp.add_argument(
        '--output', help='Output filename (default: <prefix>.merged)',
        default=None
    )

    args = parser.parse_args()
    if args.command == 'split':
        bytes_size = args.size * 1024 * 1024
        split_file(args.file, bytes_size)
    elif args.command == 'merge':
        out_name = args.output or f"{args.prefix}.merged"
        merge_file(args.prefix, out_name)
    else:
        parser.print_help()

if __name__ == '__main__':
    main()