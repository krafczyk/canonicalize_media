import subprocess
import numpy as np
from numpy.typing import NDArray
import re
from pathlib import Path
import tempfile
from av_info.utils import to_seconds, to_timecode
from av_info.session import VideoStream, get_hwdec_options

def get_keyframe_times(video_stream: VideoStream) -> NDArray[np.float32]:
    """
    Extract keyframe (I-frame) timestamps from a video file using ffprobe.
    Returns a sorted list of floats (seconds).
    """
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", str(video_stream.idx),
        "-show_entries", "packet=pts_time,flags",
        "-of", "csv=p=0",
        video_stream.filepath
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    times: list[float] = []
    for line in result.stdout.splitlines():
        pts, flags = line.split(',')
        if 'K' in flags:
            times.append(float(pts))
    times.sort()
    return np.array(times, dtype=np.float32)


def closest_keyframe_before(
    target: float,
    keyframes: NDArray[np.float32],
) -> np.float32:
    """
    Return the largest key-frame timestamp ≤ *target*.

    Parameters
    ----------
    target
        Timestamp (seconds).
    keyframes
        **Sorted** 1-D float32 array.

    Returns
    -------
    np.float32
        0.0 if *target* is earlier than the first key-frame.
    """

    idx: int = int(np.searchsorted(keyframes, target, side="right") - 1)
    return keyframes[idx] if idx >= 0 else np.float32(0.0)


def closest_keyframe_after(
    target: float,
    keyframes: NDArray[np.float32],
) -> np.float32 | None:
    """
    Return the smallest key-frame timestamp ≥ *target*.

    Returns ``None`` if *target* is after the last key-frame.
    """
    idx: int = int(np.searchsorted(keyframes, target, side="left"))
    return None if idx >= keyframes.size else keyframes[idx]


def find_input_file_arg(args: list[str]) -> str | None:
    for i, arg in enumerate(args):
        if arg == '-i' and i + 1 < len(args):
            return args[i + 1]
    return None


def find_image(
    video_stream: VideoStream,
    image_path: str | Path,
    start_time: str | float | np.float32 = 0.0,
    end_time: str | float | np.float32 | None = None,
    frame_step: int = 5,
    keyframes: NDArray[np.float32] | None = None,
    device: int|None=None) -> np.float32:
    """
    Coarsely locate where an image appears in a video.
    Returns a timecode string.
    """
    # Prepare keyframes and start time
    if keyframes is None:
        keyframes = get_keyframe_times(video_stream)

    range_ops: list[str] = []

    start_secs = to_seconds(str(start_time))
    start_secs = closest_keyframe_before(start_secs, keyframes)

    if start_secs > 0.:
        range_ops.append("-ss")
        range_ops.append(to_timecode(start_secs))
    if end_time is not None:
        range_ops.append("-to")
        range_ops.append(to_timecode(to_seconds(str(end_time))))

    # Run ffmpeg SSIM analysis on frames sampled every frame_step
    with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as tmp:
        stats_file = tmp.name


    cmd: list[str] = [
        "ffmpeg", "-hide_banner", "-nostats",
        *get_hwdec_options(video_stream, device),
        *range_ops,
        "-i", str(video_stream.filepath),
        "-i", str(image_path),
        "-filter_complex", f"[0:v]framestep={frame_step}[sampled];[sampled][1:v]ssim=stats_file={stats_file}",
        "-f", "null", "-"
    ]
    _ = subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Parse stats file
    frame_nums: list[int] = []
    ssim_vals: list[float] = []
    pattern = re.compile(r'n:(\d+).*?\((\d+\.\d+)\)')
    with open(stats_file, 'r') as f:
        for line in f:
            m = pattern.search(line)
            if m:
                frame_nums.append(int(m.group(1)))
                ssim_vals.append(float(m.group(2)))

    best_sim = 0.0
    best_frame = 0
    for i, val in enumerate(ssim_vals):
        if val > best_sim:
            best_sim = val
            best_frame = frame_nums[i]

    return start_secs + (best_frame * frame_step) / np.float32(video_stream.frame_rate)


# def find_first_occurrence_noblack(video_file: Union[str, Path], image_path: Union[str, Path],
#                                    start_time: Union[str, float] = 0.0, fps: float = 24.0,
#                                    thresh_ratio: float = 0.5) -> str:
#     """
#     Find the rising edge of SSIM similarity for an image in a video.
#     """
#     keyframes = get_keyframe_times(video_file)
#     start_secs = to_seconds(str(start_time))
#     start_secs = closest_keyframe_before(start_secs, keyframes)

#     with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as tmp:
#         stats_file = tmp.name

#     cmd = [
#         "ffmpeg", "-hide_banner", "-nostats",
#         *hwdec,
#         "-ss", to_timecode(start_secs),
#         "-i", str(video_file),
#         "-i", str(image_path),
#         "-filter_complex", f"ssim=stats_file={stats_file}",
#         "-f", "null", "-"
#     ]
#     subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

#     # Parse stats file
#     frame_nums: List[int] = []
#     ssim_vals: List[float] = []
#     pattern = re.compile(r'n:(\d+).*?\((\d+\.\d+)\)')
#     with open(stats_file, 'r') as f:
#         for line in f:
#             m = pattern.search(line)
#             if m:
#                 frame_nums.append(int(m.group(1)))
#                 ssim_vals.append(float(m.group(2)))

#     best_sim = max(ssim_vals, default=0.0)
#     best_idx = ssim_vals.index(best_sim) if best_sim > 0 else 0
#     best_frame = frame_nums[best_idx]

#     thresh = thresh_ratio * best_sim
#     first_frame = best_frame
#     for i in range(best_idx, -1, -1):
#         if ssim_vals[i] < thresh:
#             break
#         first_frame = frame_nums[i]

#     likely_secs = start_secs + first_frame / fps
#     return to_timecode(likely_secs)


# def find_prior_black(initial_guess: Union[str, float], video_file: Union[str, Path],
#                      search_window: Optional[float] = None, min_duration: float = 0.1,
#                      pix_th: float = 0.1) -> Union[float, str]:
#     """
#     Locate the last black frame before a guessed time in the video.
#     Returns the timestamp (in seconds) or 'ERROR' if none found.
#     """
#     guess_secs = to_seconds(str(initial_guess))
#     keyframes = get_keyframe_times(video_file)

#     if search_window is not None:
#         start_secs = guess_secs - search_window
#         start_secs = closest_keyframe_before(start_secs, keyframes)
#         end_secs = closest_keyframe_after(guess_secs, keyframes) or guess_secs
#         if end_secs < start_secs:
#             raise ValueError("Search window invalid; end before start.")
#         time_args = ["-ss", to_timecode(start_secs), "-to", to_timecode(end_secs)]
#     else:
#         start_secs = 0.0
#         time_args = ["-to", to_timecode(guess_secs)]

#     cmd = [
#         "ffmpeg", "-hide_banner", "-nostats",
#         *hwdec,
#         *time_args,
#         "-i", str(video_file),
#         "-vf", f"blackdetect=d={min_duration}:pix_th={pix_th}",
#         "-an", "-f", "null", "-"
#     ]
#     proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)

#     endpoints: List[float] = []
#     for line in proc.stderr.splitlines():
#         # look for black_end value
#         m = re.search(r'black_end:(\d+\.\d+)', line)
#         if m:
#             endpoints.append(float(m.group(1)) + start_secs)

#     closest = None
#     min_diff = float('inf')
#     for t in endpoints:
#         if t < guess_secs:
#             diff = guess_secs - t
#             if diff < min_diff:
#                 min_diff = diff
#                 closest = t

#     if closest is None:
#         return 'ERROR'
#     return closest
