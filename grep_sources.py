#!/usr/bin/env python3

import argparse, os, re, subprocess, sys, time
parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)

parser.add_argument("-i", action="store_true", help="Case insensitive search")
parser.add_argument("--json", action="store_true", help="Output in json format")
parser.add_argument("--max-lines", help="Maximum lines to show per file", default=5)
parser.add_argument("--skip-anaconda-dirs", help="Skip anaconda directories", default=True)
parser.add_argument("--skip-node-module-dirs", help="Skip node_module directories", default=True)
parser.add_argument("--skip-google-cloud-sdk-dirs", help="Skip google-cloud-sdk directories", default=True)
parser.add_argument("--skip-dotdirs", help="Skip directories matching .*", default=True)
parser.add_argument("--show-permission-errors", action="store_true", help="List files and directories unable to search due to permission errors")
parser.add_argument("regex", help="Regular expression to search for")
parser.add_argument("files_and_directories", nargs="*", help="Files and directories to recursively search", default=[])

file_require_regex = r"\.(c|h|c\+\+|h\+\+|cpp|hpp|js|ts|html|rb|py|ipynb)$"
required_suffixes = tuple(".c|.h|.c++|.h++|.cpp|.hpp|.js|.ts|.html|.rb|.py|.ipynb".split("|"))

#omit = set("site-packages".split("|"))

args = parser.parse_args()

file_modtimes = {}

canonicals = set()

permission_errors = set()

def add_file(filename):
    try:
        file_modtimes[filename] = os.path.getmtime(filename)
    except PermissionError:
        permission_errors.add(filename)


def add_directory(directory, inode=None):
    if not inode:
        inode = os.stat(directory).st_ino
    if inode in canonicals:
        return
    canonicals.add(inode)
    if directory.endswith("/node_modules") and args.skip_node_module_dirs:
        return
    if args.skip_dotdirs and os.path.basename(directory).startswith("."):
        return
    if directory.endswith("/google-cloud-sdk") and args.skip_google_cloud_sdk_dirs:
        return
    dirs = {}
    files = set()
    try:
        entries = list(os.scandir(directory))
    except PermissionError:
        permission_errors.add(directory)
        return
    for entry in entries:
        try:
            if entry.is_symlink():
                continue
            elif entry.is_dir():
                dirs[entry.name] = entry
            elif entry.is_file():
                files.add(entry.name)
        except PermissionError:
            permission_errors.add(os.path.join(directory, entry.name))

    if args.skip_anaconda_dirs and "condabin" in dirs and "bin" in dirs and "conda-meta" in dirs:
        return

    # start_time = time.time()
    # start_nfiles = len(file_modtimes)

    for file in files:
        #if re.search(file_require_regex, file):
        if file.endswith(required_suffixes):
            add_file(os.path.join(directory, file))

    for (dirname, entry) in dirs.items():
        add_directory(os.path.join(directory, dirname), inode=entry.inode())

    # added_files = len(file_modtimes) - start_nfiles
    # duration = time.time() - start_time
    # if duration > 0.1 and added_files / duration < 10:
    #     print(f"BUST searching {directory}: Took {duration:.1f} seconds to add {added_files} files")



def run_grep(cmdline):
    p = subprocess.Popen(cmdline, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf8")
    (out, err) = [x.strip() for x in p.communicate()]
    ret = p.wait()
    if not ret or not err:
        return out
    if err:
        raise Exception(
            f'Call to subprocess_check failed with return code {ret}\nStandard error: "{err}"\nStandard out: "{out}"')

now = time.time()

def interpret_time(t):
    age = now - t
    opts = [
        ("seconds", age),
        ("minutes", age/60),
        ("hours",   age/60/60),
        ("days",    age/60/60/24),
        ("months",  age/60/60/24/365.24*12),
        ("years",   age/60/60/24/365.24)
    ]
    for (i, (unit, amount)) in enumerate(opts):
        if i+1 == len(opts) or opts[i+1][1] < 1:
            return f"{amount:.1f} {unit} ago"

def main():
    files_and_directories = args.files_and_directories
    if not files_and_directories:
        rc_file = os.path.expanduser("~/.grep_sources_dirs")
        print(f"No files or directories specified;  reading from {rc_file}")
        sys.stdout.flush()
        if not os.path.exists(rc_file):
            print(f"Error: you must provide files or directories on commandline, or defaults in {rc_file}", file=sys.stderr)
            parser.print_help()
            sys.exit(1)
        files_and_directories = open(rc_file).read().strip().split("\n")

    for file_or_dir in files_and_directories:
        if os.path.isfile(file_or_dir):
            add_file(file_or_dir)
        elif os.path.isdir(file_or_dir):
            add_directory(file_or_dir)
        else:
            raise Exception(f"Cannot find '{file_or_dir}'")

    msg = f"Searching {len(file_modtimes)} files."
    if permission_errors:
        msg += f" ({len(permission_errors)} files/dirs skipped due to lack of permission.)"
    print(msg)
    sys.stdout.flush()

    if args.show_permission_errors and permission_errors:
        print("Missing permissions for:")
        for filename in sorted(permission_errors):
            print(filename)
        print()
        sys.stdout.flush()

    filenames_to_search = sorted(file_modtimes.keys(), key=lambda filename: file_modtimes[filename], reverse=True)

    for filename in filenames_to_search:
        cmdline = ["grep", "-m", str(args.max_lines)]
        if args.i:
            cmdline.append("-i")
        cmdline += [args.regex, filename]
        out = run_grep(cmdline)
        if out:
            print(f"{os.path.basename(filename)} {interpret_time(file_modtimes[filename])} ({filename})")
            for line in out.split("\n"):
                if len(line) > 95:
                    line = line[:95] + "..."
                print(f"    {line}")
            print()
            sys.stdout.flush()

main()


