import subprocess
import numpy as np
from numpy.typing import NDArray
import re
import sys
from pathlib import Path
import tempfile
from typing import cast
from av_info.session import VideoStream, get_hwdec_options
from dataclasses import dataclass


TimecodeLike = str | float | np.float32


def to_timecode(ts: TimecodeLike) -> str:
    """
    Translate a numeric timestamp (seconds) or existing timecode to a string in MM:SS.mmm or HH:MM:SS.mmm format.
    Hours will be elided if zero.
    If input has a ':' it is returned unchanged.
    """
    if isinstance(ts, str) and ':' in ts:
        return ts
    seconds = float(ts)
    mins = int(seconds // 60)
    secs = seconds - mins * 60
    return f"{mins:02d}:{secs:06.3f}"


def to_seconds(timecode: TimecodeLike) -> float:
    """
    Convert a timecode string (HH:MM:SS.mmm, MM:SS.mmm, or SS.mmm) to total seconds.
    """
    if isinstance(timecode, float) or type(timecode) is np.float32:
        return float(timecode)

    if not isinstance(timecode, str):
        raise TypeError(f"Expected str or float, got {type(timecode)}")

    parts = timecode.split(':')
    if len(parts) == 3:
        hours = float(parts[0])
        minutes = float(parts[1])
        seconds = float(parts[2])
    elif len(parts) == 2:
        hours = 0.0
        minutes = float(parts[0])
        seconds = float(parts[1])
    elif len(parts) == 1:
        hours = 0.0
        minutes = 0.0
        seconds = float(parts[0])
    else:
        raise ValueError(f"Invalid timecode format: {timecode}")
    return hours * 3600 + minutes * 60 + seconds


def is_zero_timecode(ts: TimecodeLike) -> bool:
    if isinstance(ts, str):
        if to_seconds(ts) == 0.0:
            return True
        else:
            return False
    return float(ts) == 0.0


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


def run(cmd:list[str], verbose: bool=False) -> subprocess.CompletedProcess[str]:
    try:
        if verbose:
            print(" ".join(cmd), file=sys.stderr)
        return subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        if verbose:
            print("Output:", cast(str,e.stdout), file=sys.stderr)
            print("Error output:", cast(str,e.stderr), file=sys.stderr)
        raise


class SeekOptions:
    video_stream: VideoStream
    target_start_time: str | None = None
    target_end_time: str | None = None
    course_seek: str | None = None
    fine_seek: str | None = None
    end: str | None = None
    dur: float | None = None
    true_seek: float | None = None
    true_fps: float | None = None

    def __init__(self, video_stream: VideoStream, start_time: TimecodeLike|None=None, end_time: TimecodeLike|None=None, keyframes: NDArray[np.float32] | None = None, mode: str="course"):
        """
        Initialize seek options with a file path and timecodes.
        If keyframes are provided, they will be used to adjust the seek times.
        """
        if start_time:
            self.target_start_time = to_timecode(start_time)
        if end_time:
            self.target_end_time = to_timecode(end_time)
            self.end = to_timecode(end_time)
            if start_time:
                self.dur = to_seconds(end_time) - to_seconds(start_time)
            else:
                self.dur = to_seconds(end_time)

        self.video_stream = video_stream
        if keyframes is None:
            keyframes = get_keyframe_times(video_stream)

        if mode == "course" and start_time:
            start_secs = to_seconds(str(start_time))
            if start_secs > 0.0:
                # find the closest keyframe before the start time
                nearest_keyframe = closest_keyframe_before(start_secs, keyframes)
                self.course_seek = to_timecode(nearest_keyframe)
                self.fine_seek = to_timecode(start_secs - nearest_keyframe)
            else:
                self.course_seek = None
                self.fine_seek = None

        elif mode == "precise" and start_time:
            self.fine_seek = to_timecode(start_time)
        elif start_time:
            raise ValueError(f"Invalid mode: {mode}. Use 'course' or 'precise'.")

    def to_ffmpeg_args(self) -> dict[str, list[str]]:
        """
        Convert the seek options to a list of ffmpeg arguments.
        """
        result: dict[str, list[str]] = {
            "course": [],
            "input": ["-i", self.video_stream.filepath],
            "fine": [],
        }
        if self.course_seek:
            result["course"] = ["-ss", self.course_seek]
        result["input"] = ["-i", self.video_stream.filepath]
        if self.fine_seek:
            result["fine"].extend(["-ss", self.fine_seek])
        if self.dur:
            result["fine"].extend([ "-t", f"{self.dur:.3f}"])
        return result

    def calibrate(self, num_frames: int=24, column: str="pts_time", method: str ="ffprobe", device: int|None=None, verbose:bool=False):
        """
        Calibrate the seek options using ffprobe or ffmpeg to get accurate frame timestamps.
        """
        fine_seek = to_seconds(self.fine_seek) if self.fine_seek else 0.

        # Course seek calibration, if course_seek is not defined, we'll calibrate fps
        if method == "ffprobe":
            if self.course_seek:
                seek_options = ["-read_intervals", f"{self.course_seek}%+#{num_frames}" ]
            else:
                seek_options = ["-read_intervals", f"0%+#{num_frames}" ]

            cmd = [ 
                "ffprobe", "-v", "error",
                *seek_options,
                "-select_streams", str(self.video_stream.idx),
                "-show_entries", f"frame={column}",
                "-of", "csv=p=0",
                self.video_stream.filepath ]
            subprocess_result = run(cmd, verbose=verbose)
            ffprobe_output = subprocess_result.stdout.splitlines()
            frame_vals = np.array(list(map(
                lambda n: np.float32(n),
                ffprobe_output)))
        elif method == "ffmpeg":
            if self.course_seek:
                seek_options = [ "-ss", self.course_seek, "-i", self.video_stream.filepath ]
            else:
                seek_options = [ "-i", self.video_stream.filepath ]

            hwdec = get_hwdec_options(self.video_stream, device)

            cmd = [
                "ffmpeg", "-hide_banner", "-copyts", "-vsync", "0",
                *hwdec,
                *seek_options,
                "-frames:v", str(num_frames),
                "-map", f"0:v:{self.video_stream.idx2}", "-an", "-vf", "showinfo", "-f", "null", "-"]
            subprocess_result = run(cmd, verbose=verbose)
            ffmpeg_output = subprocess_result.stderr.splitlines()
            pts_time_re = re.compile(r'pts_time:(\d+\.\d+)')
            frame_val_list: list[float] = []
            for line in ffmpeg_output:
                m = pts_time_re.search(line)
                if m:
                    frame_val_list.append(float(m.group(1)))
            frame_vals = np.array(frame_val_list, dtype=np.float32)
        else:
            raise ValueError(f"Invalid method: {method}. Use 'ffprobe' or 'ffmpeg'.")

        first_frame = cast(np.float32, frame_vals[0])
        last_frame = cast(np.float32, frame_vals[-1])

        # Set the calibrated true FPS
        true_fps = np.float32((num_frames - 1)/(last_frame-first_frame))
        self.true_fps = float(true_fps)

        # Check if the course seek is significantly different from the first frame time.
        if self.course_seek:
            course_diff = first_frame - to_seconds(self.course_seek)
            if abs(course_diff) > 1./true_fps:
                print(f"WARNING: keyframe based course seek not frame accurate. calibrating.", file=sys.stderr)
                # adjust the course seek so it's frame-perfect 
                self.course_seek = to_timecode(first_frame)
                # Theory, we just need to directly adjust fine_seek by the diff to make it frame perfect as well
                if self.fine_seek:
                    self.fine_seek = to_timecode(to_seconds(self.fine_seek) - course_diff)
            fine_seek = to_seconds(self.fine_seek) if self.fine_seek else 0.
            self.true_seek = to_seconds(self.course_seek) + fine_seek
        else:
            if self.fine_seek:
                self.true_seek = to_seconds(self.fine_seek)

        if self.true_seek is None:
            self.true_seek = 0.


    def get_frame_time(self, n: int, frame_step: int = 1) -> np.float32:
        """
        Given a frame number from an ffmpeg statistics extraction,
        Return the frame's true timestamp in seconds.
        """

        if self.true_fps is None or self.true_seek is None:
            base_seek: float = 0
            if self.course_seek:
                base_seek += to_seconds(self.course_seek)
            elif self.fine_seek:
                base_seek += to_seconds(self.fine_seek)

            if self.video_stream.frame_rate <= 0:
                raise ValueError("Frame rate must be greater than zero.")
            return np.float32(base_seek + (n * frame_step) / np.float32(self.video_stream.frame_rate))
        else:
            return np.float32(self.true_seek + (n * frame_step) / self.true_fps)


def find_image(
    seek_options: SeekOptions,
    image_path: str | Path,
    frame_step: int = 5,
    device: int|None=None,
    found_thresh: float=10.,
    verbose:bool=False) -> np.float32:
    """
    Coarsely locate where an image appears in a video.
    Returns a timecode string.
    """
    # Run ffmpeg SSIM analysis on frames sampled every frame_step
    with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as tmp:
        stats_file = tmp.name
    stats_file = "ssim.log"

    video_stream = seek_options.video_stream
    seek_opts = seek_options.to_ffmpeg_args()
    cmd: list[str] = [
        "ffmpeg", "-hide_banner", "-nostats",
        *(seek_opts["course"]),
        *(seek_opts["input"]),
        "-i", str(image_path),
        "-filter_complex", f"[0:v]framestep={frame_step}[sampled];[sampled][1:v]ssim=stats_file={stats_file}",
        *(seek_opts["fine"]),
        "-f", "null", "-"
    ]
    _ = run(cmd, verbose=verbose)

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

    if best_sim < found_thresh:
        print(f"No significant match found. Best SSIM: {best_sim:.4f} < {found_thresh:.4f}", file=sys.stderr)
        return np.float32(-1.0)

    # Zoom in on detected area to find best possible frame

    sim_thresh = 0.9*best_sim
    upper_frame = best_frame
    lower_frame = best_frame
    for i in range (best_frame, len(ssim_vals)):
        if ssim_vals[i] < sim_thresh:
            break
        upper_frame = frame_nums[i]
    for i in range (best_frame, -1, -1):
        if ssim_vals[i] < sim_thresh:
            break
        lower_frame = frame_nums[i]

    upper_frame += 1
    lower_frame -= 1
    if lower_frame < 0:
        lower_frame = 0
    if upper_frame >= len(frame_nums):
        upper_frame = len(frame_nums) - 1

    # Build new seek range
    upper_time = seek_options.get_frame_time(upper_frame, frame_step=frame_step)
    lower_time = seek_options.get_frame_time(lower_frame, frame_step=frame_step)

    seek_options = SeekOptions(
        seek_options.video_stream,
        lower_time,
        upper_time)
    seek_opts = seek_options.to_ffmpeg_args()

    with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as tmp:
        stats_file = tmp.name

    video_stream = seek_options.video_stream
    cmd: list[str] = [
        "ffmpeg", "-hide_banner", "-nostats",
        *get_hwdec_options(video_stream, device),
        *(seek_opts["course"]),
        *(seek_opts["input"]),
        "-i", str(image_path),
        "-filter_complex", f"ssim=stats_file={stats_file}",
        *(seek_opts["fine"]),
        "-f", "null", "-"
    ]
    _ = run(cmd, verbose=verbose)

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

    # Check if there's a plateau

    sim_thresh = best_sim
    upper_frame = best_frame
    lower_frame = best_frame
    for i in range (best_frame, len(ssim_vals)):
        if ssim_vals[i] < sim_thresh:
            break
        upper_frame = frame_nums[i]
    for i in range (best_frame, -1, -1):
        if ssim_vals[i] < sim_thresh:
            break
        lower_frame = frame_nums[i]

    upper_frame += 1
    lower_frame -= 1
    if lower_frame < 0:
        lower_frame = 0
    if upper_frame >= len(frame_nums):
        upper_frame = len(frame_nums) - 1

    # Get 'center' frame
    best_frame = (upper_frame + lower_frame) // 2

    return seek_options.get_frame_time(best_frame, frame_step=1)


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


@dataclass
class black_gap:
    start: float
    end: float
    duration: float


def find_black(seek_options: SeekOptions,
               min_duration: float = 0.1,
               pix_th: float = 0.1,
               device: int|None=None) -> list[black_gap]:
    """
    Locate the last black frame before a guessed time in the video.
    Returns the timestamp (in seconds) or 'ERROR' if none found.
    """

    video_stream = seek_options.video_stream
    hwdec = get_hwdec_options(video_stream, device=device)

    cmd = [
        "ffmpeg", "-hide_banner", "-nostats",
        *hwdec,
        *seek_options.to_ffmpeg_args(),
        "-vf", f"blackdetect=d={min_duration}:pix_th={pix_th}",
        "-an", "-f", "null", "-"
    ]
    proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)

    black_detect_re = re.compile(
        r'black_start:(\d+\.\d+) black_end:(\d+\.\d+) black_duration:(\d+\.\d+)'
    )

    start_time = seek_options.true_seek or 0.
    endpoints: list[black_gap] = []
    for line in proc.stderr.splitlines():
        # extract black_start and black_end times
        if m := black_detect_re.search(line):
            bg = black_gap(
                start=float(m.group(1))+start_time,
                end=float(m.group(2))+start_time,
                duration=float(m.group(3))
            )
            endpoints.append(bg)
    return endpoints
