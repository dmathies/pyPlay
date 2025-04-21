from __future__ import annotations

import time
import pygame
from qplayer_config import *
#from renderer import Renderer
from video_handler import VideoHandler, VideoData, VideoStatus

CUE_EVENT = pygame.USEREVENT + 3


class ActiveCue:
    def __init__(self, cue: CueUnion):
        self.cue = cue
        self.alpha = 0.0
        self.dimmer = 1.0
        self.alpha = 0.0
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
        self.pause_time = None
        self.state_reported = None
        self.shader_parameters = None


    def pause(self):
        self.paused = True
        self.pause_time = time.time()

    def unpause(self):
        pause_time = time.time() - self.pause_time
        self.cue_start_time += pause_time
        self.paused = False

    def position(self):
        if self.video_data.status == VideoStatus.READY and self.video_data.current_frame is not None:
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
        self, cues: list[CueUnion], renderer, video_handler: VideoHandler
    ):

        self.callback = None
        self.clock = pygame.time.Clock()

        self.dimmer = 1.0
        self.cues = {}
        self.renderer = renderer
        self.video_handler = video_handler
        self.active_cues: list[ActiveCue] = []
        self.last_cue = -1
        self.qid_list: list[str] = []

        self.set_cues(cues)

    def set_cues(self, cues: list[CueUnion]):
        for cue in cues:
            self.cues[str(cue.qid)] = cue
            self.qid_list.append(str(cue.qid))

        # Stop all cues that no longer exist
        for cue in self.active_cues:
            if cue.qid in self.cues:
                cue.complete = True

    def register_callback(self, callback, args):
        self.callback = callback
        self.callback_args = args

    def stop(self, cue_id:str =None):
        if cue_id is None:
            for cue in self.active_cues:
                cue.complete = True
            return

        match = next((q for q in self.active_cues if q.qid == cue_id), None)
        if match:
            if match.alpha == 1.0:
                self.handle_stop(match, StopMode.Immediate, match.media_fadeType, match.media_fadeOut, LoopMode.OneShot, 1)

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

    def go(self, cue_id: str="next", paused: bool=False, start_time: float = 0.0):
        if cue_id == "next":
            self.last_cue = (self.last_cue + 1) % len(self.qid_list)
            cue_id = self.qid_list[self.last_cue]

        cue = self.cues.get(cue_id)
        if not cue:
            return

        self.last_cue = next((i for i, qid in enumerate(self.qid_list) if qid == cue_id), -1)

        match = next((q for q in self.active_cues if q.qid == cue_id), None)

        if match:
            if match.paused:
                self.unpause(cue_id)
            else:
                # handle already running cue
                match.video_data.seek_start_seconds = cue.startTime.total_seconds()
                match.video_data.seek_start()
                match.alpha_video_data.seek_start()

                match.cue_start_time = time.time()

                if getattr(cue, 'startTime', False):
                    match.media_startTime = cue.startTime
                if getattr(cue, 'duration', False):
                    match.media_duration = cue.duration
                if getattr(cue, 'volume', False):
                    match.media_volume = cue.volume
                if getattr(cue, 'fadeIn', False):
                    match.media_fadeIn = cue.fadeIn
                if getattr(cue, 'fadeOut', False):
                    match.media_fadeOut = cue.fadeOut
                if getattr(cue, 'fadeType', False):
                    match.media_fadeType = cue.fadeType
                if getattr(cue, 'loopMode', False):
                    match.media_loopMode = cue.loopMode
                if getattr(cue, 'loopCount', False):
                    match.media_loopCount = cue.loopCount
                if getattr(cue, 'uniforms', False):
                    match.shader_parameters = cue.uniforms

                match.loop_counter = 0
                match.state_reported = None

        else:
            if isinstance(cue, VideoCue) or isinstance(cue, VideoFraming) or isinstance(cue, ShaderParams):
                self.begin_new_playback(cue, paused=paused)

            elif isinstance(cue, StopCue):
                match = next( (q for q in self.active_cues if q.qid == cue.stopQid), None )
                if match:
                    self.handle_stop(match, cue.stopMode, cue.fadeType, cue.fadeOutTime, cue.loopMode, cue.loopCount)


    def begin_new_playback(self, cue: CueUnion, paused:bool = False):
        active_cue = ActiveCue(cue)
        if getattr(cue, 'startTime', False):
            active_cue.video_data.seek_start_seconds = cue.startTime.total_seconds()

        # Local copies can be manipulated by events.
        if getattr(cue, 'startTime', False):
            active_cue.media_startTime = cue.startTime
        if getattr(cue, 'duration', False):
            active_cue.media_duration = cue.duration

        active_cue.media_volume = getattr(cue, 'volume', 0)
        active_cue.media_fadeIn = getattr(cue, 'fadeIn', 0)
        active_cue.media_fadeOut = getattr(cue, 'fadeOut', 0)
        active_cue.media_fadeType = getattr(cue, 'fadeType', FadeType.Linear)
        active_cue.media_loopMode = cue.loopMode
        active_cue.media_loopCount = cue.loopCount
        active_cue.paused = paused
        active_cue.pause_time = active_cue.cue_start_time

        if isinstance(cue, VideoCue):
            self.video_handler.load_video_async(
                cue.path, active_cue.video_data
            )
            if cue.alphaPath:
                self.video_handler.load_video_async(
                    cue.alphaPath, active_cue.alpha_video_data
                )

        pygame.event.post(pygame.event.Event(CUE_EVENT, data=active_cue))

    def handle_stop(self, match: ActiveCue, stop_mode: StopMode, fade_type: FadeType,  fade_out_time: float, loop_mode: LoopMode, loop_count: int):
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



    def tick(self):
        now = time.time()

        for active_cue in self.active_cues:
            if not active_cue.paused:
                runtime:float = now - active_cue.cue_start_time
                if active_cue.media_fadeIn > 0.0:
                    active_cue.alpha = runtime / active_cue.media_fadeIn
                    if active_cue.alpha > 1.0:
                        active_cue.alpha = 1.0
                else:
                    active_cue.alpha = 1.0

                # Check if we are looping
                if active_cue.endLoop or (active_cue.media_loopMode != LoopMode.LoopedInfinite and not (
                   active_cue.media_loopMode == LoopMode.Looped and active_cue.media_loopCount > (active_cue.loop_counter+1))):
                    # Not looping
                    if active_cue.media_duration.total_seconds() > 0.0:
                        fade_start_time = (
                            active_cue.media_duration.total_seconds() - active_cue.media_fadeOut
                        )
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
                else: # Looping
                    if active_cue.media_duration.total_seconds() <= runtime:
                        active_cue.loop_counter += 1
                        active_cue.cue_start_time = now
                        active_cue.media_fadeIn = 0
                        active_cue.video_data.seek_start()
            if isinstance(active_cue.cue, ShaderParams):

                match = next((q for q in self.active_cues if q.qid == active_cue.cue.videoQid), None)
                if match:
                    alpha = active_cue.alpha
                    if active_cue.cue.fadeType == FadeType.Smooth:
                        alpha = self.smooth_step(alpha)

                    if not active_cue.shader_parameters:
                        # Make a copy of the current values
                        if match.shader_parameters:
                            active_cue.shader_parameters = match.shader_parameters.copy()
                        else:
                            active_cue.shader_parameters = {}

                    if active_cue.cue.uniforms:
                        old = active_cue.shader_parameters
                        new = active_cue.cue.uniforms
                        interpolated = self.interpolate_dicts(old, new, alpha)
                        match.shader_parameters = interpolated
                        # print(f"Interpolated shader parameters: {match.shader_parameters}")

                    if alpha==1.0:
                        active_cue.complete = True
                else:
                    active_cue.complete = True

        if self.callback:
            self.callback(self.active_cues)


    @staticmethod
    def interpolate_dicts(old, new, alpha):
        keys = set(old) | set(new)  # Union of keys
        interp = {}

        for key in keys:
            old_val = old.get(key, 0.0)
            new_val = new.get(key, 0.0)
            interp[key] = (1 - alpha) * old_val + alpha * new_val

        return interp


    @staticmethod
    def smooth_step(alpha):
        return alpha * alpha * (3 - 2 * alpha)
