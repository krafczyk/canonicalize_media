from setuptools import setup, Extension, find_packages
from pathlib import Path
import os
import subprocess

def pkg_config(library: str, flag: str) -> list[str]:
    try:
        output = subprocess.check_output(["pkg-config", flag, library])
        return output.decode().split()
    except subprocess.CalledProcessError:
        return []

def get_include_dirs(library: str) -> list[str]:
    # Get flags like "-I/usr/include/ffmpeg" and strip off the "-I"
    flags = pkg_config(library, '--cflags-only-I')
    return [flag[2:] for flag in flags if flag.startswith('-I')]

def get_library_dirs(library: str) -> list[str]:
    # Get flags like "-L/usr/lib" and strip off the "-L"
    flags = pkg_config(library, '--libs-only-L')
    return [flag[2:] for flag in flags if flag.startswith('-L')]

def get_libraries(library: str) -> list[str]:
    # Get flags like "-lavformat" and strip off the "-l"
    flags = pkg_config(library, '--libs-only-l')
    return [flag[2:] for flag in flags if flag.startswith('-l')]

# Get the FFmpeg configuration from pkg-config for libavformat, libavcodec, and libavutil.
include_dirs = (
    get_include_dirs("libavformat") +
    get_include_dirs("libavutil") +
    get_include_dirs("libavcodec")
)

library_dirs = (
    get_library_dirs("libavformat") +
    get_library_dirs("libavutil") +
    get_library_dirs("libavcodec")
)

libraries = (
    get_libraries("libavformat") +
    get_libraries("libavutil") +
    get_libraries("libavcodec")
)

# Define the extension module.
module = Extension(
    'av_info._ffmpeg',
    sources=['src/ffmpeg.cpp'],  # your C++ source file
    language='c++',
    include_dirs=include_dirs,
    library_dirs=library_dirs,
    libraries=libraries,
)

# --- Automated Script Discovery ---

HERE = Path(__file__).parent.resolve()
BIN_DIR = HERE / "bin"
CLI_DIR = HERE / "av_info" / "cli"

def discover_shell_scripts() -> list[str]:
    """Return executable non-Python files in ./bin/."""
    if not BIN_DIR.exists():
        return []
    return [
        str(p)
        for p in BIN_DIR.iterdir()
        if p.is_file()
        and os.access(p, os.X_OK)
        and p.suffix == ".sh"
    ]

def discover_console_scripts() -> list[str]:
    """
    Build console-script entry points for every .py in av_info/cli/.
    Command name  : file-stem with underscores → dashes  (locate_image -> locate-image)
    Entry point   : 'av_info.cli.<module>:main'
    """
    if not CLI_DIR.exists():
        return []
    entries = []
    for path in CLI_DIR.glob("*.py"):
        if path.name == "__init__.py":
            continue
        cmd  = path.stem.replace("_", "-")
        mod  = f"av_info.cli.{path.stem}"
        entries.append(f"{cmd} = {mod}:main")
    return entries


def parse_requirements(fname: str = "requirements.txt") -> list[str]:
    """
    Return a list of PEP-508 requirement strings taken from *fname*.
    Ignores blank lines and comments that start with '#'.
    """
    req_path = Path(__file__).with_name(fname)
    if not req_path.exists():
        return []

    lines = req_path.read_text().splitlines()
    reqs  = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue            # skip comments / empty lines
        reqs.append(line)
    return reqs


_ = setup(
    name="av_info",
    version="1.0",
    description="A Python extension module for FFmpeg interfacing built with setuptools.",
    ext_modules=[module],
    packages=find_packages(),

    # Entry points for console scripts
    scripts=discover_shell_scripts(),

    # Entry points for Python console scripts
    entry_points = {
        "console_scripts": discover_console_scripts(),
    },

    python_requires=">=3.9",
    install_requires=parse_requirements(),
)
