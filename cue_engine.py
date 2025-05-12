from __future__ import annotations

import os.path
import time
from enum import IntEnum

import pygame

from qplayer_config import *
# from renderer import Renderer
from video_handler import VideoHandler, VideoData, VideoStatus

CUE_EVENT = pygame.USEREVENT + 3


class CueStatus(IntEnum):
    COMPLETE = 0
    LOADED = 1
    RUNNING = 2
    LOOPING = 3
    PAUSED = 4
    EMPTY = -1


class ActiveCue:
    def __init__(self, cue: CueUnion):
        self.cue = cue
        self.alpha = 0.0
        self.dimmer = 1.0
        self.qid = str(cue.qid)
        self.cue_start_time = time.time()
        if isinstance(cue, VideoCue):
            self.z_index = cue.zIndex
        else:
            self.z_index = 0
        self.video_data = VideoData()
        self.alpha_video_data = VideoData()
        self.media_startTime = timedelta()
        self.media_duration = timedelta()
        self.media_volume = 0.0
        self.media_fadeIn = 0.0
        self.media_fadeOut = 0.0
        self.media_fadeType = FadeType.Linear
        self.media_loopMode = LoopMode.OneShot
        self.media_loopCount = 0
        self.loop_counter = 0
        self.endLoop = False
        self.complete = False
        self.paused = False
        self.pause_time: float = 0
        self.state_reported: Optional[CueStatus] = CueStatus.EMPTY
        self.shader_parameters: Optional[dict[str, float]] = None
        self.shader_parameters_original: Optional[dict[str, float]] = None

    def pause(self):
        self.paused = True
        self.pause_time = time.time()

    def unpause(self):
        pause_time = time.time() - self.pause_time
        self.cue_start_time += pause_time
        self.paused = False

    def position(self):
        if (
            self.video_data.status == VideoStatus.READY
            and self.video_data.current_frame is not None
        ):
            if self.video_data.still:
                elapsed = time.time() - self.cue_start_time
                if self.paused:
                    elapsed = self.pause_time - self.cue_start_time

                if elapsed < self.media_fadeIn:
                    return elapsed
                else:
                    return self.media_fadeIn
            else:
                pts = self.video_data.current_frame.pts
                time_base = self.video_data.current_frame.time_base
                if pts is not None and time_base is not None:
                    return float(pts * time_base)

        return 0.0


class CueEngine:
    def __init__(
        self, cues: list[CueUnion], renderer, video_handler: VideoHandler, base_path: str
    ):

        self.callback = None
        self.clock = pygame.time.Clock()

        self.dimmer = 1.0
        self.cues: dict[str, CueUnion] = {}
        self.renderer = renderer
        self.video_handler = video_handler
        self.active_cues: list[ActiveCue] = []
        self.last_cue = -1
        self.qid_list: list[str] = []
        self.base_path = base_path

        self.set_cues(cues)

    def set_cues(self, cues: list[CueUnion]):
        for cue in cues:
            self.cues[str(cue.qid)] = cue
            self.qid_list.append(str(cue.qid))

            # Load any shaders referenced by the cues in advance
            if isinstance(cue, VideoCue):
                if cue.shader != None and cue.shader != "":
                    try:
                        self.renderer.register_shader_program(cue.shader)
                    except Exception as ex:
                        print(f"Error while loading custom shader: {ex}")

        # Stop all cues that no longer exist
        for acue in self.active_cues:
            if acue.qid in self.cues:
                acue.complete = True

    def register_callback(self, callback, args):
        self.callback = callback
        self.callback_args = args

    def stop(self, cue_id: Optional[str] = None):
        if cue_id is None:
            for cue in self.active_cues:
                cue.complete = True
            return

        match = next((q for q in self.active_cues if q.qid == cue_id), None)
        if match:
            if match.alpha == 1.0:
                self.handle_stop(
                    match,
                    StopMode.Immediate,
                    match.media_fadeType,
                    match.media_fadeOut,
                    LoopMode.OneShot,
                    1,
                )

    def pause(self, cue_id: str):
        match = next((q for q in self.active_cues if q.qid == cue_id), None)
        if match:
            match.pause()

    def unpause(self, cue_id: str):
        match = next((q for q in self.active_cues if q.qid == cue_id), None)
        if match:
            match.unpause()

    def preload(self, cue_id: str, start_time: float):
        match = next((q for q in self.active_cues if q.qid == cue_id), None)
        if not match:
            self.go(cue_id, True, start_time)
        pass

    def go(self, cue_id: str = "next", paused: bool = False, start_time: float = 0.0):
        if cue_id == "next":
            self.last_cue = (self.last_cue + 1) % len(self.qid_list)
            cue_id = self.qid_list[self.last_cue]

        cue = self.cues.get(cue_id)
        if not cue:
            return

        self.last_cue = next(
            (i for i, qid in enumerate(self.qid_list) if qid == cue_id), -1
        )

        match = next((q for q in self.active_cues if q.qid == cue_id), None)

        if match:
            if match.paused:
                self.unpause(cue_id)
            else:
                # handle already running cue
                # if not isinstance(cue, VideoCueUnion):
                #     return

                match.media_loopMode = cue.loopMode
                match.media_loopCount = cue.loopCount

                if isinstance(cue, VideoCue):
                    match.video_data.seek_start_seconds = (
                        cue.startTime.total_seconds() if cue.startTime else 0
                    )
                    match.video_data.seek_start()
                    match.alpha_video_data.seek_start()

                    match.cue_start_time = time.time()

                    match.media_startTime = cue.startTime or timedelta()
                    match.media_duration = cue.duration or timedelta()
                    match.media_volume = cue.volume or 1
                    match.media_fadeIn = cue.fadeIn or 0
                    match.media_fadeOut = cue.fadeOut or 0
                    match.media_fadeType = cue.fadeType or FadeType.Linear
                    match.shader_parameters = self.shader_params_to_dict(cue.uniforms)
                    match.shader_parameters["brightness"] = cue.brightness
                    match.shader_parameters["contrast"] = cue.contrast
                    match.shader_parameters["gamma"] = cue.gamma
                    # match.shader_parameters["dimmer"] = cue.dimmer
                    match.shader_parameters["rotation"] = cue.rotation
                    match.shader_parameters["offset"] = (cue.offset.x, cue.offset.y)
                    match.shader_parameters["scale"] = (cue.scale, cue.scale)
                    match.shader_parameters_original = match.shader_parameters.copy()
                elif isinstance(cue, VideoFraming):
                    match.media_fadeIn = cue.fadeIn
                    match.media_fadeType = cue.fadeType
                elif isinstance(cue, ShaderParams):
                    match.media_fadeIn = cue.fadeIn
                    match.media_fadeType = cue.fadeType
                    match.shader_parameters = self.shader_params_to_dict(cue.uniforms)
                    match.shader_parameters_original = match.shader_parameters.copy()

                match.loop_counter = 0
                match.state_reported = 0

        else:
            if (
                isinstance(cue, VideoCue)
                or isinstance(cue, VideoFraming)
                or isinstance(cue, ShaderParams)
            ):
                self.begin_new_playback(cue, paused=paused)

            elif isinstance(cue, StopCue):
                match = next(
                    (q for q in self.active_cues if q.qid == cue.stopQid), None
                )
                if match:
                    self.handle_stop(
                        match,
                        cue.stopMode,
                        cue.fadeType,
                        cue.fadeOutTime,
                        cue.loopMode,
                        cue.loopCount,
                    )

    def begin_new_playback(self, cue: CueUnion, paused: bool = False):
        active_cue = ActiveCue(cue)
        active_cue.video_data.seek_start_seconds = getattr(
            cue, "startTime", timedelta(0)
        ).total_seconds()

        # Local copies can be manipulated by events.
        active_cue.media_startTime = getattr(
            cue, "startTime", active_cue.media_startTime
        )
        active_cue.media_duration = getattr(cue, "duration", active_cue.media_duration)

        active_cue.media_volume = getattr(cue, "volume", 0)
        active_cue.media_fadeIn = getattr(cue, "fadeIn", 0)
        active_cue.media_fadeOut = getattr(cue, "fadeOut", 0)
        active_cue.media_fadeType = getattr(cue, "fadeType", FadeType.Linear)
        active_cue.media_loopMode = cue.loopMode
        active_cue.media_loopCount = cue.loopCount
        active_cue.paused = paused
        active_cue.pause_time = active_cue.cue_start_time
        active_cue.shader_parameters = self.shader_params_to_dict(getattr(cue, "uniforms", []))
        active_cue.shader_parameters_original = active_cue.shader_parameters.copy()

        if isinstance(cue, VideoCue):
            active_cue.shader_parameters["brightness"] = cue.brightness
            active_cue.shader_parameters["contrast"] = cue.contrast
            active_cue.shader_parameters["gamma"] = cue.gamma
            # active_cue.shader_parameters["dimmer"] = cue.dimmer
            active_cue.shader_parameters["rotation"] = cue.rotation
            active_cue.shader_parameters["offset"] = (cue.offset.x, cue.offset.y)
            active_cue.shader_parameters["scale"] = (cue.scale, cue.scale)
            active_cue.shader_parameters_original = active_cue.shader_parameters.copy()

            self.video_handler.load_video_async(self.resolve_path(cue.path), active_cue.video_data)
            if cue.alphaPath:
                self.video_handler.load_video_async(
                    self.resolve_path(cue.alphaPath), active_cue.alpha_video_data
                )

        pygame.event.post(pygame.event.Event(CUE_EVENT, data=active_cue))

    def handle_stop(
        self,
        match: ActiveCue,
        stop_mode: StopMode,
        fade_type: FadeType,
        fade_out_time: float,
        loop_mode: LoopMode,
        loop_count: int,
    ):
        if stop_mode == StopMode.Immediate:
            if fade_out_time == 0.0:
                match.complete = True
            else:
                # Make this a one shot fading cue starting now.
                match.endLoop = True
                match.media_duration = timedelta(seconds=fade_out_time)
                match.media_fadeIn = 0.0
                match.media_fadeOut = fade_out_time
                match.media_fadeType = fade_type
                match.media_loopMode = loop_mode
                match.media_loopCount = loop_count
                match.cue_start_time = time.time()
        else:
            match.endLoop = True
            match.media_loopMode = LoopMode.OneShot
            if match.media_duration == 0:
                match.media_duration = timedelta(seconds=fade_out_time)
                match.cue_start_time = time.time()

    def tick(self) -> None:
        now = time.time()

        for active_cue in self.active_cues:
            if not active_cue.paused:
                runtime: float = now - active_cue.cue_start_time
                if active_cue.media_fadeIn > 0.0:
                    active_cue.alpha = runtime / active_cue.media_fadeIn
                    if active_cue.alpha > 1.0:
                        active_cue.alpha = 1.0
                else:
                    active_cue.alpha = 1.0

                # How long is the video?
                duration = active_cue.media_duration.total_seconds()
                if (
                    duration == 0
                    and active_cue.video_data
                    and active_cue.video_data.video_stream
                ):
                    duration = float(
                        active_cue.video_data.video_stream.duration
                        * active_cue.video_data.video_stream.time_base
                    )
                    active_cue.media_duration = timedelta(seconds=duration)

                if active_cue.media_loopMode == LoopMode.HoldLastFrame:
                    duration = 10000000                  # If hold last frame, pretend video is very long

                # Check if we are looping
                if (
                    not active_cue.endLoop and
                    (
                        active_cue.media_loopMode == LoopMode.LoopedInfinite or  # looping forever?
                        (
                            active_cue.media_loopMode == LoopMode.Looped and     # Within loop limit?
                            active_cue.media_loopCount > (active_cue.loop_counter + 1)
                        )
                    )
                ):
                    # Looping
                    if duration <= runtime:
                        active_cue.loop_counter += 1
                        active_cue.cue_start_time = now
                        active_cue.media_fadeIn = 0
                        active_cue.video_data.seek_start()
                else:  # Not looping
                    if duration > 0.0:
                        fade_start_time = duration - active_cue.media_fadeOut
                        if runtime >= fade_start_time:
                            if active_cue.media_fadeOut > 0.0:
                                active_cue.alpha = 1.0 - (
                                    runtime - fade_start_time / active_cue.media_fadeOut
                                )
                                if active_cue.alpha < 0.0:
                                    active_cue.alpha = 0.0
                                    active_cue.complete = True
                            else:
                                active_cue.alpha = 0.0
                                active_cue.complete = True

            if isinstance(active_cue.cue, ShaderParams):
                match = next(
                    (q for q in self.active_cues if q.qid == active_cue.cue.videoQid),
                    None,
                )
                if match:
                    alpha = active_cue.alpha
                    if active_cue.cue.fadeType == FadeType.SCurve:
                        alpha = self.smooth_step(alpha)

                    if not active_cue.shader_parameters:
                        # Make a copy of the current values
                        if match.shader_parameters:
                            active_cue.shader_parameters = (
                                match.shader_parameters.copy()
                            )
                        else:
                            active_cue.shader_parameters = {}

                    if active_cue.cue.uniforms:
                        old = match.shader_parameters_original
                        new = active_cue.shader_parameters
                        self.interpolate_dicts(match.shader_parameters, old, new, alpha)
                        # print(f"Interpolated shader parameters: {match.shader_parameters}")

                    if alpha == 1.0:
                        active_cue.complete = True
                else:
                    active_cue.complete = True

        if self.callback:
            self.callback(self.active_cues)

    def get_status(self):
        status = {
            "status": "Running",
            "Active Cue Count": len(self.active_cues),
            "Active Cues": []
        }

        for active_cue in self.active_cues:
            cue_status = {
                "id": active_cue.cue.qid,
                "Name": active_cue.cue.name,
                "type": active_cue.cue.type,
                "time": active_cue.position(),
                "state": active_cue.state_reported.name,
                "video_state": active_cue.video_data.status.name,
                "uniforms": active_cue.shader_parameters
            }
            cue_status["uniforms"]["alpha"] = active_cue.alpha

            status["Active Cues"].append(cue_status)

        return status

    def resolve_path(self, filename: str) -> str:
        if '\\' in filename:
            filename = filename.replace('\\', '/')
        if os.path.isfile(filename):
            return filename
        else:
            return os.path.join(self.base_path, filename)

    @staticmethod
    def interpolate_dicts(dst: dict[str, Any], old: dict[str, Any], new: dict[str, Any], alpha: float):
        # keys = set(old) | set(new)  # Union of keys
        # interp = {}

        for key in dst:
            old_val = old[key]
            if not isinstance(old_val, tuple) and key in new:
                new_val = new[key]
                dst[key] = (1 - alpha) * old_val + alpha * new_val

    @staticmethod
    def smooth_step(alpha):
        return alpha * alpha * (3 - 2 * alpha)

    @staticmethod
    def shader_params_to_dict(shader_params: list[ShaderParam]) -> dict[str, float]:
        return {p.name: p.value for p in shader_params}
