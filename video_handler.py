import av
import threading


class VideoFrameFormat:
    RGB = 0
    NV12 = 1
    YUVJ420p = 2
    GRAY = 3


class VideoStatus:
    LOADING = 0
    LOADED = 1
    READY = 2
    EMPTY = -1


class VideoData:
    def __init__(self):
        self.container = None
        self.video_stream = None
        self.gen = None
        self.frame_format = None
        self.width = 0
        self.height = 0
        self.textures = {}
        self.frame_pix_format = None
        self.still = False
        self.status = VideoStatus.EMPTY
        self.current_frame = None
        self.seek_start_seconds = 0.0

    def get_next_frame(self):
        if self.still:
            if self.current_frame is None:
                frame = next(self.gen)
            else:
                frame = self.current_frame
        else:
            try:
                frame = next(self.gen)
            except StopIteration:
                frame = self.seek_start()

        self.current_frame = frame
        return frame

    def seek_start(self):
        if not self.still and self.status in (VideoStatus.LOADING,VideoStatus.LOADED, VideoStatus.READY):
            frame = seek_to_time(self.container, self.video_stream, self.seek_start_seconds)
        else:
            frame = self.current_frame

        return frame


def seek_to_time(container, stream, target_time):
    # Convert time in seconds to PTS (presentation timestamp)
    target_pts = int(target_time / stream.time_base)

    # Seek to the nearest keyframe before the target time
    container.seek(target_pts, stream=stream, any_frame=False, backward=True)

    # Decode frames until you reach the exact target time
    for frame in container.decode(stream):
        if frame.pts is not None and frame.time >= target_time:
            return frame
    return None


def load_video(path, video_data=VideoData()):
    try:
        if path.lower().endswith((".jpg", ".jpeg", ".png")):
            container = av.open(path, format="image2")
            frame_pix_format = VideoFrameFormat.RGB
            still = True
        else:
            hwaccel = av.codec.hwaccel.HWAccel("drm", allow_software_fallback=True)
            container = av.open(path, hwaccel=hwaccel)
            # Default to NV12 then adjust if needed.
            frame_pix_format = VideoFrameFormat.NV12
            still = False

        video_stream = container.streams.video[0]

        if video_stream.format.is_rgb:
            frame_pix_format = VideoFrameFormat.RGB
        elif video_stream.format.name == "gray":
            frame_pix_format = VideoFrameFormat.GRAY
        elif video_stream.format.name == "yuvj420p":
            frame_pix_format = VideoFrameFormat.YUVJ420p

        gen = container.decode(video=0)

        video_data.container = container
        video_data.video_stream = video_stream
        video_data.gen = gen
        video_data.width = video_stream.width
        video_data.height = video_stream.height
        video_data.frame_pix_format = frame_pix_format
        video_data.still = still
        video_data.current_frame = video_data.seek_start()

        video_data.status = VideoStatus.LOADED

    except Exception as e:
        print(f"Error loading video {path}: {e}")
    return video_data


class VideoHandler:
    def __init__(self):
        self.current_index = 0
        self.video = []
        self.video.append(VideoData())
        self.video.append(VideoData())

    def load_video_async(self, path, video_data):
        video_data.status = VideoStatus.LOADING
        thread = threading.Thread(target=load_video, args=(path, video_data))
        thread.start()
