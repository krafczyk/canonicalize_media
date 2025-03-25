import subprocess
import json


def get_h264_level_name(level):
    """Return the H.264 level name for a given numeric level value."""
    mapping = {
        10: "1.0",
        11: "1.1",
        12: "1.2",
        13: "1.3",
        20: "2.0",
        21: "2.1",
        22: "2.2",
        30: "3.0",
        31: "3.1",
        32: "3.2",
        40: "4.0",
        41: "4.1",
        42: "4.2",
        50: "5.0",
        51: "5.1",
        52: "5.2"
    }
    return mapping.get(level, "unknown")


def get_hevc_level_name(level):
    """Return the HEVC level name for a given numeric level value."""
    mapping = {
        30:  "1",
        60:  "2",
        63:  "2.1",
        90:  "3",
        93:  "3.1",
        120: "4",
        123: "4.1",
        150: "5",
        153: "5.1",
        156: "5.2",
        180: "6",
        183: "6.1",
        186: "6.2"
    }
    return mapping.get(level, "unknown")


def mediainfo(filepath):
    # Get output from the mediainfo command-line tool
    try:
        output = subprocess.check_output(["mediainfo", "--Output=JSON", filepath])
        return json.loads(output)
    except ChildProcessError as e:
        print(e)
        return None
