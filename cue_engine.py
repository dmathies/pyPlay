from __future__ import annotations

import time
import pygame
from qplayer_config import *
from renderer import Renderer
from video_handler import VideoHandler, VideoData

CUE_EVENT = pygame.USEREVENT + 3

class ActiveCue:
  def __init__(self, cue: CueUnion):
    self.cue = cue
    self.alpha = 0.0
    self.dimmer = 1.0
    self.alpha = 0.0
    self.qid = cue.qid
    self.que_start_time = time.time()
    self.z_index = cue.zIndex
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

class CueEngine:
  def __init__(self, cues: [CueUnion], renderer: Renderer, video_handler: VideoHandler):

    self.clock = pygame.time.Clock()

    self.dimmer = 1.0
    self.cues = {}
    self.renderer = renderer
    self.video_handler = video_handler
    self.active_cues: list[ActiveCue] = []
    self.last_cue = -1
    self.qid_list = [str]

    for cue in cues:
      self.cues[cue.qid] = cue
      self.qid_list.append(cue.qid)

  def stop(self, cue_id: str):
    pass

  def pause(self, cue_id: str):
    pass

  def preload(self, cue_id: str, start_time: timedelta):
    pass

  def go(self, cue_id: str):
    if cue_id=="next":
      self.last_cue = (self.last_cue + 1) % len(self.qid_list)
      cue_id = self.qid_list[self.last_cue]

    cue = self.cues.get(cue_id)
    if not cue:
      return

    print(f"Go cue: {cue.qid}, name: {cue.name}\n")

    match = next((q for q in self.active_cues if q.qid == cue_id), None)

    if match:
      # handle already running cue
      pass
    else:
      if isinstance(cue, VideoCue):
        active_cue = ActiveCue(cue)
        active_cue.video_data.seek_start_seconds = cue.startTime.total_seconds()

        # Local copies can be manipulated by events.
        active_cue.media_startTime = cue.startTime
        active_cue.media_duration = cue.duration
        active_cue.media_volume = cue.volume
        active_cue.media_fadeIn = cue.fadeIn
        active_cue.media_fadeOut = cue.fadeOut
        active_cue.media_fadeType = cue.fadeType
        active_cue.media_loopMode = cue.loopMode
        active_cue.media_loopCount = cue.loopCount

        self.video_handler.load_video_async(active_cue.cue.path, active_cue.video_data)
        if active_cue.cue.alphaPath:
          self.video_handler.load_video_async(active_cue.cue.alphaPath, active_cue.alpha_video_data)
        pygame.event.post(pygame.event.Event(CUE_EVENT, data=active_cue))

      elif isinstance(cue, VideoFraming):
        self.renderer.set_framing(cue.framing)
        self.renderer.set_corners(cue.corners)

      elif isinstance(cue, StopCue):
        match = next((q for q in self.active_cues if q.qid == cue.stopQid), None)
        if match:
          if cue.stopMode == StopMode.Immediate:
            if cue.fadeOutTime == 0.0:
              match.complete = True
            else:
              # Make this a one shot fading cue starting now.
              match.endLoop = True
              match.media_duration = timedelta(seconds=cue.fadeOutTime)
              match.media_fadeIn = 0.0
              match.media_fadeOut = cue.fadeOutTime
              match.media_fadeType = cue.fadeType
              match.media_loopMode = cue.loopMode
              match.media_loopCount = cue.loopCount
              match.que_start_time = time.time()
          else:
            match.endLoop = True

  def tick(self):
    now = time.time()

    for active_cue in self.active_cues:
      runtime = now - active_cue.que_start_time
      if active_cue.media_fadeIn >0.0:
        active_cue.alpha = runtime / active_cue.media_fadeIn
        if active_cue.alpha >1.0: active_cue.alpha=1.0
      else:
        active_cue.alpha = 1.0

      if active_cue.media_duration.total_seconds()>0.0:
        fade_start_time= active_cue.media_duration.total_seconds() - active_cue.media_fadeOut
        if runtime >= fade_start_time:
          if active_cue.media_fadeOut >0.0:
            active_cue.alpha = 1.0 - (runtime-fade_start_time / active_cue.media_fadeOut)
            if active_cue.alpha <0.0: active_cue.alpha=0.0
          else:
            active_cue.alpha = 0.0

        if active_cue.alpha == 0.0:
          if active_cue.endLoop == False and active_cue.media_loopMode in (LoopMode.LoopedInfinite, LoopMode.Looped):
            if active_cue.media_loopMode==LoopMode.LoopedInfinite or active_cue.media_loopCount> active_cue.loop_counter:
              active_cue.loop_counter+=1
              active_cue.que_start_time=now
              active_cue.video_data.seek_start()
            else:
              active_cue.complete=True
          else:
            active_cue.complete=True
      else:
        if active_cue.endLoop:
          active_cue.complete=True

