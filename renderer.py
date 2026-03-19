from __future__ import annotations
import time

import av
import numpy as np
import pygame
import re
import ctypes
from OpenGL.GL import *
from OpenGL.GL.shaders import compileProgram, compileShader

import sys
import os

from pygame.locals import *  # type: ignore

if sys.version_info >= (3, 9):
    from importlib.resources import files, read_text
else:
    from importlib.resources import open_binary, read_text

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cue_engine import ActiveCue
from qplayer_config import (
    FramingShutter,
    Point,
    VideoCue,
    VideoFraming,
    FadeType,
    AlphaMode,
    ShaderParams,
)
from video_handler import VideoStatus, VideoHandler, VideoData, VideoFrameFormat

TEXTURE_UNIT_LOOKUP = [
    GL_TEXTURE0,
    GL_TEXTURE1,
    GL_TEXTURE2,
    GL_TEXTURE3,
    GL_TEXTURE4,
    GL_TEXTURE5,
    GL_TEXTURE6,
    GL_TEXTURE7,
    GL_TEXTURE8,
    GL_TEXTURE9,
    GL_TEXTURE10,
    GL_TEXTURE11,
    GL_TEXTURE12,
    GL_TEXTURE13,
    GL_TEXTURE14,
    GL_TEXTURE15,
]


class Renderer:
    def __init__(
        self,
        single_screen: bool = False,
        hidden_window: bool = False,
        enable_postprocess: bool = True,
        profile_render: bool = False,
        warp_mesh: tuple[int, int] = (16, 16),
        scene_scale: float = 1.0,
        hidden_window_size: tuple[int, int] = (1280, 720),
    ):

        self.mask_data = None
        self.bg_video = None
        self.homography_left = None
        self.homography_right = None
        self.corners = []
        self.old_corners = []
        self.framing = []
        self.old_framing = []
        self.transitioning = None
        self.transition_duration = None
        self.dimmer = 1.0
        self.alpha = 0.0
        self.SHADERS = {}
        self.current_shader = None
        self.hidden_window = hidden_window
        self.single_screen = single_screen or hidden_window
        self.enable_postprocess = enable_postprocess
        self.profile_render = profile_render
        self.warp_mesh = warp_mesh
        self.scene_scale = scene_scale
        self.hidden_window_size = hidden_window_size
        self.scene_fbo = 0
        self.scene_color_tex = 0
        self.output_fbo = 0
        self.output_color_tex = 0
        self.post_VAO = 0
        self.post_VBO = 0
        self.post_EBO = 0
        self.post_parameters: dict[str, float] = {
            "exposure": 0.7,
            "gammaOut": 2.2,
            "whitePoint": 1.0,
            "bloomStrength": 0.25,
            "bloomThreshold": 1.0,
            "sceneGammaIn": 2.2,
        }
        self.bloom_fbo = 0
        self.bloom_tex = 0
        self.bloom_pingpong_fbo = [0, 0]
        self.bloom_pingpong_tex = [0, 0]
        self.bloom_output_tex = 0
        self.fps_font = None
        self.fps_texture = 0
        self.fps_texture_size = (0, 0)
        self.last_fps_update = 0.0
        self.last_fps_value = 0.0
        self.bloom_w = 0
        self.bloom_h = 0
        # Runtime tuning/debug knobs for lower-power targets like the Pi.
        self.bloom_blur_passes = max(0, int(os.environ.get("PYPLAY_BLOOM_PASSES", "6")))
        self.show_fps_overlay = os.environ.get("PYPLAY_SHOW_FPS", "1") not in ("0", "false", "False")
        self.profile_interval = max(0.1, float(os.environ.get("PYPLAY_PROFILE_INTERVAL", "1.0")))
        self._last_profile_print = 0.0
        self.profile_cues = os.environ.get("PYPLAY_PROFILE_CUES", "0") in ("1", "true", "True")
        self.profile_gpu = os.environ.get("PYPLAY_PROFILE_GPU", "0") in ("1", "true", "True")
        self.ndi_debug = os.environ.get("PYPLAY_NDI_DEBUG", "0") in ("1", "true", "True")
        self._last_ndi_capture_debug = 0.0
        self.identity_homography = np.eye(3, dtype=np.float32).flatten()

        pygame.init()
        pygame.font.init()
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 0)
        pygame.display.gl_set_attribute(
            pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_ES
        )

        info = pygame.display.Info()
        self.window_size = (info.current_w, info.current_h)

        num_displays = pygame.display.get_num_displays()
        print("num displays:", num_displays)

        display_names = []

        for i in range(num_displays):
            name = None
            # newer pygame builds
            if hasattr(pygame.display, "get_display_name"):
                name = pygame.display.get_display_name(i)

            # older / stripped builds: fall back to size info
            desktop_sizes = pygame.display.get_desktop_sizes()
            w, h = desktop_sizes[i]
            if name is None:
                name = f"Display {i} ({w}x{h})"
            print(name)

        #self.window_size = (3840, 1200)

        sizes = pygame.display.get_desktop_sizes()
        self.left_w, self.left_h = sizes[0]

        if self.hidden_window:
            hidden_w = max(1, self.hidden_window_size[0])
            hidden_h = max(1, self.hidden_window_size[1])
            self.window_size = (hidden_w, hidden_h)
            self.left_w, self.height = self.window_size
            self.right_w, self.right_h = 0, self.height
            self.screen = pygame.display.set_mode(
                self.window_size, pygame.DOUBLEBUF | pygame.OPENGL | pygame.HIDDEN, vsync=1
            )
        elif self.single_screen or len(sizes) < 2:
            # Debug mode: one windowed output on a single display.
            debug_w = min(1280, self.left_w)
            debug_h = min(720, self.left_h)
            self.window_size = (debug_w, debug_h)
            self.left_w, self.height = self.window_size
            self.right_w, self.right_h = 0, self.height
            self.screen = pygame.display.set_mode(
                self.window_size, pygame.DOUBLEBUF | pygame.OPENGL, vsync=1
            )
        else:
            self.right_w, self.right_h = sizes[1]
            self.height = max(self.left_h, self.right_h)

            total_width = sum(w for (w, h) in sizes)
            max_height = max(h for (w, h) in sizes)
            os.environ["SDL_VIDEO_WINDOW_POS"] = "0,1"
            self.window_size = (total_width, max_height)

            # one big borderless window across both monitors
            self.screen = pygame.display.set_mode(
                self.window_size, pygame.NOFRAME | pygame.OPENGL
            )

        base_scene_size = self.window_size if self.single_screen else (self.left_w, self.left_h)
        self.scene_size = (
            max(1, int(base_scene_size[0] * self.scene_scale)),
            max(1, int(base_scene_size[1] * self.scene_scale)),
        )
        # self.screen = pygame.display.set_mode(
        #     self.window_size, pygame.DOUBLEBUF | pygame.OPENGL, vsync=1, display=0
        # )

        # self.screen2 = pygame.display.set_mode(
        #     self.window_size, pygame.DOUBLEBUF | pygame.OPENGL, vsync=1, display=1
        # )

        # pygame.display.toggle_fullscreen()
        pygame.display.set_caption("GAOS ArtNet Video Player")
        # pygame.mouse.set_visible(False)

        glViewport(0, 0, self.window_size[0], self.window_size[1])

        print("GL version:", glGetString(GL_VERSION))
        print(f"Driver {pygame.display.get_driver()}")

        self.register_shader_program("default")
        self.register_shader_program("default_additive")
        self.register_shader_program("default_multiply")
        self.register_shader_program("scene_default")
        self.register_shader_program("scene_default_additive")
        self.register_shader_program("scene_light_additive")
        self.register_shader_program("scene_holdout_alpha")
        self.register_shader_program("scene_light_multiply")
        self.register_shader_program("scene_default_multiply")
        self.register_shader_program("default_framing")
        self.register_shader_program("grid_wire")
        self.register_shader_program("tonemap")
        self.register_shader_program("bloom_extract")
        self.register_shader_program("bloom_blur")
        self.register_shader_program("overlay_text")
        self.register_shader_program("output_warp")
        self.set_shader("default")
        self.VAO = self.setup_geometry(rows=self.warp_mesh[1], cols=self.warp_mesh[0])
        self.setup_postprocess_resources()
        
        self.src_pts = np.array([[0, 0], [1, 0], [0, 1], [1, 1]], dtype=np.float32)
        self.set_corners([Point(0, 0), Point(1, 0), Point(0, 1), Point(1, 1)], "left")
        self.set_corners([Point(0, 0), Point(1, 0), Point(0, 1), Point(1, 1)], "right")

        self.clock = pygame.time.Clock()
        self.fps_font = pygame.font.SysFont("Consolas", 22)

        self.set_parameters(
            {
                "dimmer": 1.0,
                "alpha": 0.5,
                "alphaMode": 0,
                "alphaSoftness": 0.0,
                "scale": (1, 1),
                "brightness": 0.0,
                "contrast": 1.0,
                "gamma": 1.0,
                "homographyMatrix": self.identity_homography,
                "resolution": self.scene_size
            }
        )

    def render_frame(self, active_cues: list[ActiveCue], capture_frame: bool = False):
        # --- profiling start ---
        frame_start = time.perf_counter()
        decode_upload_time = 0.0  # total time spent in get_next_frame + update_textures
        texture_create_time = 0.0
        cue_draw_time = 0.0
        framing_time = 0.0
        mask_time = 0.0
        warp_time = 0.0
        flip_time = 0.0
        cue_timings = []
        # ------------------------

        scene_bind_start = time.perf_counter()
        target_fbo = self.scene_fbo if (self.enable_postprocess or not self.single_screen) else 0
        glBindFramebuffer(GL_FRAMEBUFFER, target_fbo)
        glViewport(0, 0, self.scene_size[0], self.scene_size[1])
        glClearColor(0.0, 0.0, 0.0, 0.0)
        glClear(GL_COLOR_BUFFER_BIT)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        scene_bind_time = time.perf_counter() - scene_bind_start

        # Clean up completed cues and free their video resources
        completed = [cue for cue in active_cues if cue.complete]
        for cue in completed:
            if cue.video_data:
                cue.video_data.release()
            
            if cue.alpha_video_data:
                cue.alpha_video_data.release()

        active_cues[:] = [
            cue for cue in active_cues if not cue.complete
        ]  # Remove completed cues

        for active_cue in active_cues:
            alpha = active_cue.alpha
            if getattr(active_cue.cue, "fadeType", FadeType.Linear) == FadeType.SCurve:
                alpha = self.smooth_step(active_cue.alpha)

            if isinstance(active_cue.cue, VideoCue):
                if active_cue.video_data.status == VideoStatus.LOADED:
                    create_start = time.perf_counter()
                    self.create_textures(active_cue.video_data)
                    texture_create_time += time.perf_counter() - create_start
                    active_cue.video_data.status = VideoStatus.READY

                if (
                    active_cue.video_data.status == VideoStatus.READY
                    and active_cue.paused == False
                    and not active_cue.video_data.still
                ):
                    t0 = time.perf_counter()
                    frame = active_cue.video_data.get_next_frame()
                    self.update_textures(active_cue.video_data, frame)
                    decode_upload_time += time.perf_counter() - t0

                if active_cue.alpha_video_data.status == VideoStatus.LOADED:
                    create_start = time.perf_counter()
                    self.create_textures(active_cue.alpha_video_data)
                    texture_create_time += time.perf_counter() - create_start
                    active_cue.alpha_video_data.status = VideoStatus.READY

                if (
                    active_cue.alpha_video_data.status == VideoStatus.READY
                    and active_cue.paused == False
                    and not active_cue.alpha_video_data.still
                ):
                    t0 = time.perf_counter()
                    frame = active_cue.alpha_video_data.get_next_frame()
                    self.update_textures(active_cue.alpha_video_data, frame)
                    decode_upload_time += time.perf_counter() - t0

                if active_cue.alpha_video_data.status == VideoStatus.EMPTY:
                    if active_cue.video_data.status == VideoStatus.READY:
                        active_cue.start_playback_clock()
                        scene_shader_name = self.get_scene_shader_name(active_cue)
                        cue_start = time.perf_counter()
                        if scene_shader_name == "scene_light_additive_holdout":
                            self.draw_additive_holdout_to_scene(
                                active_cue.video_data,
                                active_cue.alpha,
                                active_cue.shader_parameters,
                            )
                        else:
                            self.set_shader(scene_shader_name)
                            if active_cue.shader_parameters:
                                self.set_parameters(active_cue.shader_parameters)
                            self.set_parameters({
                                "resolution": self.scene_size,
                                "time": self.clock.get_time()/1000,
                            })
                            self.draw_texture_to_scene(active_cue.video_data, active_cue.alpha)
                        cue_elapsed = time.perf_counter() - cue_start
                        cue_draw_time += cue_elapsed
                        if self.profile_cues:
                            cue_timings.append((cue_elapsed, active_cue.qid, scene_shader_name))
                else:
                    if (
                        active_cue.video_data.status == VideoStatus.READY
                        and active_cue.alpha_video_data.status == VideoStatus.READY
                    ):
                        active_cue.start_playback_clock()
                        scene_shader_name = self.get_scene_shader_name(active_cue)
                        cue_start = time.perf_counter()
                        if scene_shader_name == "scene_light_additive_holdout":
                            self.draw_additive_holdout_to_scene(
                                active_cue.video_data,
                                active_cue.alpha,
                                active_cue.shader_parameters,
                            )
                        else:
                            self.set_shader(scene_shader_name)
                            if active_cue.shader_parameters:
                                self.set_parameters(active_cue.shader_parameters)
                            self.set_parameters({
                                "resolution": self.scene_size,
                                "time": self.clock.get_time()/1000,
                            })
                            self.draw_texture_to_scene(
                                active_cue.video_data,
                                active_cue.alpha,
                                active_cue.alpha_video_data,
                                active_cue.cue.alphaMode,
                                active_cue.cue.alphaSoftness,
                            )
                        cue_elapsed = time.perf_counter() - cue_start
                        cue_draw_time += cue_elapsed
                        if self.profile_cues:
                            cue_timings.append((cue_elapsed, active_cue.qid, scene_shader_name))
            elif isinstance(active_cue.cue, VideoFraming):
                framing_start = time.perf_counter()
                if active_cue.cue.framing:
                    self.set_framing(active_cue.cue.framing, alpha)
                if active_cue.cue.corners:
                    self.set_corners(active_cue.cue.corners, "left")
                if active_cue.alpha == 1.0:
                    active_cue.complete = True
                framing_time += time.perf_counter() - framing_start

        if self.framing is not None:
            params = {}
            offset_angle = 0.0
            current_shader = self.current_shader
            self.set_shader("default_framing")

            for shutter in self.framing:
                params["fr_rotation"] = (
                    shutter.rotation / 180.0 * np.pi
                ) + offset_angle
                params["fr_maskStart"] = (
                    1.0 - shutter.maskStart - (shutter.softness / 2)
                )
                params["fr_softness"] = shutter.softness
                self.set_parameters(params)
                glBindVertexArray(self.left_VAO)
                glDrawElements(GL_TRIANGLES, self.left_index_count, GL_UNSIGNED_INT, None)
                glBindVertexArray(0)
                offset_angle += np.pi / 2

            self.set_shader(current_shader)

        if self.mask_data:
            if self.mask_data.status == VideoStatus.LOADED:
                create_start = time.perf_counter()
                self.create_textures(self.mask_data)
                texture_create_time += time.perf_counter() - create_start
                self.mask_data.status = VideoStatus.READY

                t0 = time.perf_counter()
                frame = self.mask_data.get_next_frame()
                self.update_textures(self.mask_data, frame)
                decode_upload_time += time.perf_counter() - t0

            # Draw mask
            current_shader = self.current_shader
            self.set_shader("mask")

            glBlendFunc(GL_DST_COLOR, GL_ZERO)
            mask_start = time.perf_counter()
            self.draw_texture_to_scene(self.mask_data, 1.0)
            mask_time += time.perf_counter() - mask_start
            self.set_shader(current_shader)

        if self.framing is not None:
            params = {
                # per-screen homography
                "homographyMatrix": self.homography_left,

                # overlay styling
                "gridColor": [1.0, 0.5, 1.0],
                "opacity": 0.7,
            }

            if 0==1:
                current_shader = self.current_shader
                self.set_shader("grid_wire")

                glEnable(GL_BLEND)
                glBlendFunc(GL_SRC_ALPHA, GL_ONE)

                # LEFT
                self.set_parameters(params)
                glViewport(0, 0, self.left_w, self.height)
                glBindVertexArray(self.left_VAO)
                glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self.grid_line_ebo)
                glDrawElements(GL_LINES, self.grid_line_count, GL_UNSIGNED_INT, None)
                glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self.left_EBO)
                glBindVertexArray(0)

                # Right
                params["gridColor"] =  [0.0, 1.0, 0.0]
                params["homographyMatrix"]=self.homography_right

                self.set_parameters(params)
                glViewport(self.left_w, 0, self.right_w, self.height)
                glBindVertexArray(self.right_VAO)
                glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self.grid_line_ebo)
                glDrawElements(GL_LINES, self.grid_line_count, GL_UNSIGNED_INT, None)
                glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self.right_EBO)
                glBindVertexArray(0)

                # Restore fill mode
                glDisable(GL_BLEND)
                glBindVertexArray(0)
                glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, 0)

                self.set_shader(current_shader)

        post_start = time.perf_counter()
        if self.enable_postprocess:
            self.draw_bloom_pass()
            self.draw_tonemap_pass()
            warp_start = time.perf_counter()
            self.draw_output_warp(self.output_color_tex, flip_y=True)
            warp_time += time.perf_counter() - warp_start
        elif not self.single_screen:
            warp_start = time.perf_counter()
            self.draw_output_warp(self.scene_color_tex, flip_y=True)
            warp_time += time.perf_counter() - warp_start
        post_time = time.perf_counter() - post_start
        if self.show_fps_overlay:
            self.draw_fps_overlay()
        captured_frame = self.capture_output_frame_rgb() if capture_frame else None
        flip_start = time.perf_counter()
        pygame.display.flip()
        flip_time = time.perf_counter() - flip_start

        self.clock.tick(25)

        # --- profiling end / print ---
        frame_end = time.perf_counter()
        frame_time = frame_end - frame_start
        frame_ms = frame_time * 1000.0
        decode_ms = decode_upload_time * 1000.0
        texture_create_ms = texture_create_time * 1000.0
        other_ms = frame_ms - decode_ms
        post_ms = post_time * 1000.0
        setup_ms = scene_bind_time * 1000.0
        cue_draw_ms = cue_draw_time * 1000.0
        framing_ms = framing_time * 1000.0
        mask_ms = mask_time * 1000.0
        warp_ms = warp_time * 1000.0
        flip_ms = flip_time * 1000.0
        fps_inst = 1.0 / frame_time if frame_time > 0 else 0.0
        self.last_fps_value = fps_inst

        if self.profile_render and (frame_end - self._last_profile_print) >= self.profile_interval:
            video_cue_count = sum(1 for cue in active_cues if isinstance(cue.cue, VideoCue))
            still_count = sum(
                1
                for cue in active_cues
                if isinstance(cue.cue, VideoCue) and cue.video_data and cue.video_data.still
            )
            alpha_video_count = sum(
                1
                for cue in active_cues
                if isinstance(cue.cue, VideoCue) and cue.alpha_video_data.status != VideoStatus.EMPTY
            )
            print(
                "[RenderProfile] "
                f"fps={fps_inst:5.1f} frame={frame_ms:6.2f}ms "
                f"tex_create={texture_create_ms:6.2f}ms decode_upload={decode_ms:6.2f}ms post={post_ms:6.2f}ms "
                f"scene_draw={cue_draw_ms:6.2f}ms warp={warp_ms:6.2f}ms flip={flip_ms:6.2f}ms "
                f"mask={mask_ms:5.2f}ms framing={framing_ms:5.2f}ms "
                f"other={max(0.0, other_ms - texture_create_ms - post_ms - setup_ms - cue_draw_ms - mask_ms - framing_ms - warp_ms - flip_ms):6.2f}ms "
                f"cues={len(active_cues)} video={video_cue_count} still={still_count} alpha={alpha_video_count} "
                f"post={'on' if self.enable_postprocess else 'off'} bloom_passes={self.bloom_blur_passes} "
                f"warp_mesh={self.warp_mesh[0]}x{self.warp_mesh[1]} scene_scale={self.scene_scale:.2f}"
            )
            if self.profile_cues and cue_timings:
                slowest = sorted(cue_timings, reverse=True)[:3]
                slow_text = " ".join(
                    f"qid={qid} shader={shader} ms={elapsed * 1000.0:5.2f}"
                    for elapsed, qid, shader in slowest
                )
                print(f"[RenderProfile:Cues] {slow_text}")
            self._last_profile_print = frame_end
        return captured_frame

    @staticmethod
    def smooth_step(alpha):
        return alpha * alpha * (3 - 2 * alpha)

    def maybe_profile_sync(self):
        if self.profile_gpu:
            glFinish()

    def get_scene_shader_name(self, active_cue) -> str:
        cue = active_cue.cue
        shader_name = getattr(cue, "shader", "default")

        if (
            shader_name == "default_additive_holdout"
            and getattr(cue, "alphaPath", "") in (None, "")
            and float(getattr(cue, "alphaSoftness", 0.0) or 0.0) == 0.0
            and float(getattr(cue, "rotation", 0.0) or 0.0) == 0.0
            and float(getattr(cue, "contrast", 1.0) or 1.0) == 1.0
            and float(getattr(cue, "gamma", 1.0) or 1.0) == 1.0
        ):
            return "scene_light_additive_holdout"

        if (
            shader_name == "default_additive"
            and getattr(cue, "alphaPath", "") in (None, "")
            and float(getattr(cue, "alphaSoftness", 0.0) or 0.0) == 0.0
            and float(getattr(cue, "rotation", 0.0) or 0.0) == 0.0
            and float(getattr(cue, "contrast", 1.0) or 1.0) == 1.0
            and float(getattr(cue, "gamma", 1.0) or 1.0) == 1.0
        ):
            return "scene_light_additive"
        if (
            shader_name == "default_multiply"
            and getattr(cue, "alphaPath", "") in (None, "")
            and float(getattr(cue, "alphaSoftness", 0.0) or 0.0) == 0.0
            and float(getattr(cue, "rotation", 0.0) or 0.0) == 0.0
            and float(getattr(cue, "contrast", 1.0) or 1.0) == 1.0
            and float(getattr(cue, "gamma", 1.0) or 1.0) == 1.0
        ):
            return "scene_light_multiply"

        scene_name = f"scene_{shader_name}"
        if scene_name in self.SHADERS:
            return scene_name
        return shader_name

    def draw_additive_holdout_to_scene(
        self,
        video: VideoData,
        alpha: float,
        shader_parameters: dict | None,
    ):
        self.set_shader("scene_holdout_alpha")
        if shader_parameters:
            self.set_parameters(shader_parameters)
        self.set_parameters({
            "resolution": self.scene_size,
            "time": self.clock.get_time()/1000,
        })
        self.draw_texture_to_scene(video, alpha)

        self.set_shader("scene_light_additive")
        if shader_parameters:
            self.set_parameters(shader_parameters)
        self.set_parameters({
            "resolution": self.scene_size,
            "time": self.clock.get_time()/1000,
        })
        self.draw_texture_to_scene(video, alpha)

    def draw_texture_to_scene(
        self,
        video: VideoData,
        alpha: float,
        alpha_video: VideoData | None = None,
        alphaMode=AlphaMode.Opaque,
        alphaSoftness=0.0,
    ):
        # print(f"Draw Texture: alpha:{alpha}, alphaMode:{alphaMode},  video1Format: {video.frame_pix_format}")

        if video.current_frame is None:
            return

        self.maybe_profile_sync()
        self.bind_texture(alpha, self.dimmer, video)
        self.set_parameters({"video1Format": video.frame_pix_format})

        if alpha_video:
            if alpha_video.status == VideoStatus.READY:
                self.bind_texture_layer(alpha_video, 1)
                self.set_parameters(
                    {
                        "alphaMode": AlphaMode.to_number(alphaMode),
                        "alphaSoftness": alphaSoftness,
                        "video2Format": alpha_video.frame_pix_format,
                        "video2ColourSpace": alpha_video.colour_space,
                        "video1Format": video.frame_pix_format,
                        "video1ColourSpace": video.colour_space
                    }
                )
        else:
            self.set_parameters({"alphaMode": 0,
                                 "video1Format": video.frame_pix_format,
                                 "video1ColourSpace": video.colour_space})

        glViewport(0, 0, self.scene_size[0], self.scene_size[1])
        glBindVertexArray(self.post_VAO)
        glDrawElements(GL_TRIANGLES, 6, GL_UNSIGNED_INT, None)
        glBindVertexArray(0)
        self.maybe_profile_sync()

    def draw_output_warp(self, texture_id: int, flip_y: bool = False):
        self.maybe_profile_sync()
        glBindFramebuffer(GL_FRAMEBUFFER, 0)
        glDisable(GL_BLEND)
        glClearColor(0.0, 0.0, 0.0, 1.0)
        glClear(GL_COLOR_BUFFER_BIT)

        self.set_shader("output_warp")
        self.set_parameters({"sceneTex": 0, "flipY": 1 if flip_y else 0})
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, texture_id)

        glViewport(0, 0, self.left_w, self.height)
        self.set_parameters({"homographyMatrix": self.homography_left})
        glBindVertexArray(self.left_VAO)
        glDrawElements(GL_TRIANGLES, self.left_index_count, GL_UNSIGNED_INT, None)

        if not self.single_screen and self.right_w > 0:
            glViewport(self.left_w, 0, self.right_w, self.height)
            self.set_parameters({"homographyMatrix": self.homography_right})
            glBindVertexArray(self.right_VAO)
            glDrawElements(GL_TRIANGLES, self.right_index_count, GL_UNSIGNED_INT, None)

        glBindVertexArray(0)
        glBindTexture(GL_TEXTURE_2D, 0)
        self.maybe_profile_sync()

    def set_framing(self, framing: list[FramingShutter], alpha: float):
        target_len = max(len(self.framing), len(framing))

        if alpha <= 0.0:
            if (
                len(self.framing) < target_len
            ):  # existing framing list is shorter than new, add extra empty frames.
                padded_old = self.framing + [FramingShutter(0.0, 0.0, 0.0)] * (
                    target_len - len(self.framing)
                )
                self.framing = padded_old

            self.old_framing = self.framing  # Keep a copy of the old framing
            # print(f"Set framing: alpha:{alpha}, maskStart[0]:{self.framing[0].maskStart}")
            return
        elif alpha >= 1.0:
            self.framing = framing[:]
            # print(f"Set framing: alpha:{alpha}, maskStart[0]:{self.framing[0].maskStart}")
            return

        if (
            len(framing) < target_len
        ):  # New framing is shorter than the old framing - add extra blank frames.
            padded_new = framing + [FramingShutter(0.0, 0.0, 0.0)] * (
                target_len - len(framing)
            )
        else:
            padded_new = framing[:target_len]

        # Now interpolate each shutter between padded_old and padded_new.
        interpolated = []
        for old_shutter, new_shutter in zip(self.old_framing, padded_new):
            interpolated_shutter = FramingShutter(
                rotation=(1 - alpha) * old_shutter.rotation
                + alpha * new_shutter.rotation,
                maskStart=(1 - alpha) * old_shutter.maskStart
                + alpha * new_shutter.maskStart,
                softness=(1 - alpha) * old_shutter.softness
                + alpha * new_shutter.softness,
            )
            interpolated.append(interpolated_shutter)

        self.framing = interpolated
        # print(f"Set framing: alpha:{alpha}, maskStart[0]:{self.framing[0].maskStart}")

    def set_corners(self, corners: list[Point], screen: str = "left"):
        # store per screen
        if screen == "right":
            self.right_corners = corners
        else:
            self.left_corners = corners

        try:
            corners_np = np.array(
                [
                    [corners[0].x, corners[0].y],
                    [corners[1].x, corners[1].y],
                    [corners[2].x, corners[2].y],
                    [corners[3].x, corners[3].y],
                ],
                dtype=np.float32,
            )
            h = self.compute_homography_manual(corners_np, self.src_pts).T.flatten()
            if screen == "right":
                self.homography_right = h
            else:
                self.homography_left = h

            self.set_parameters({"homographyMatrix": h})
        except Exception:
            pass

    def set_parameters(self, parameters):
        if parameters.get("dimmer", None) is not None:
            self.dimmer = parameters.get("dimmer")
        if parameters.get("fade_time", None) is not None:
            self.transition_duration = parameters.get("fade_time")

        for parameter in parameters:
            location = self.SHADERS[self.current_shader]["uniform_locators"].get(
                parameter, None
            )
            if location is not None:

                uniform_type = (
                    self.SHADERS[self.current_shader]["uniform_types"]
                    .get(parameter)
                    .value
                )
                value = parameters.get(parameter)

                # print(f"Set {parameter} to {value} ({uniform_type})")

                if uniform_type == GL_FLOAT:
                    glUniform1f(location, float(value))
                elif uniform_type == GL_FLOAT_VEC2:
                    glUniform2f(location, *value)  # Expecting tuple (x, y)
                elif uniform_type == GL_FLOAT_VEC3:
                    glUniform3f(location, *value)  # Expecting tuple (x, y, z)
                elif uniform_type == GL_FLOAT_VEC4:
                    glUniform4f(location, *value)  # Expecting tuple (x, y, z, w)

                elif uniform_type == GL_INT:
                    glUniform1i(location, int(value))
                elif uniform_type == GL_INT_VEC2:
                    glUniform2i(location, *value)  # Expecting tuple (x, y)
                elif uniform_type == GL_INT_VEC3:
                    glUniform3i(location, *value)  # Expecting tuple (x, y, z)
                elif uniform_type == GL_INT_VEC4:
                    glUniform4i(location, *value)  # Expecting tuple (x, y, z, w)

                elif uniform_type == GL_FLOAT_MAT2:
                    glUniformMatrix2fv(location, 1, GL_FALSE, value)
                elif uniform_type == GL_FLOAT_MAT3:
                    glUniformMatrix3fv(location, 1, GL_FALSE, value)
                elif uniform_type == GL_FLOAT_MAT4:
                    glUniformMatrix4fv(location, 1, GL_FALSE, value)

                elif uniform_type == GL_SAMPLER_2D or uniform_type == GL_SAMPLER_CUBE:
                    glUniform1i(
                        location, int(value)
                    )  # Samplers take texture unit index

                else:
                    print(
                        f"Warning: Unsupported uniform type {hex(uniform_type)} for '{name}'"
                    )

    def set_shader(self, shader_name):
        if shader_name not in self.SHADERS:
            shader_name = "default"

        if self.current_shader != shader_name:
            self.current_shader = shader_name
            glUseProgram(self.SHADERS[shader_name]["shader"])

        if self.SHADERS[shader_name].get("blend_mode", None):
            glBlendFunc(*self.SHADERS[shader_name]["blend_mode"])
        # if not shader_name.startswith("default"):
        #     print(f"Set shader to {shader_name}")

    def load_shader_source(self, path: str, quiet: bool = False) -> str | None:
        """
        Attempts to load a shader file from the file system or from pyPlay's built in shaders directory.

        :param path: the path to the shader file.
        :return: the contents of the shader as a string.
        """
        try:
            # shader_path_concat = f"shaders/{path}"
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()

            if sys.version_info >= (3, 9):
                template_traversable = files("shaders").joinpath(path)
                return template_traversable.read_text()
            else:
                return read_text("shaders", path)
        except Exception as e:
            if not quiet:
                print(
                    f"Couldn't find/read the shader: '{path}'. \n" f"Inner exception: {e}"
                )
            # raise FileNotFoundError(f"Couldn't find/read the shader: '{path}'. \n"
            #                         f"Inner exception: {e}")
        return None

    def register_shader_program(self, shader_name):
        shader_aliases = {
            "default_additive_holdout": "default_additive",
        }
        source_shader_name = shader_aliases.get(shader_name, shader_name)

        vertex_shader = self.load_shader_source(f"{source_shader_name}.vs.glsl", quiet=True)
        if not vertex_shader:
            vertex_shader = self.load_shader_source("default.vs.glsl")

        fragment_shader = self.load_shader_source(f"{source_shader_name}.fs.glsl")

        shader_hash = hash(vertex_shader + fragment_shader)
        if self.SHADERS.get(shader_name):
            if self.SHADERS[shader_name]["hash"] == shader_hash:
                return

        shader = compileProgram(
            compileShader(vertex_shader, GL_VERTEX_SHADER),
            compileShader(fragment_shader, GL_FRAGMENT_SHADER),
        )

        uniforms = []
        locators = {}
        uniform_types = {}

        num_uniforms = glGetProgramiv(shader, GL_ACTIVE_UNIFORMS)
        for i in range(num_uniforms):
            # Prepare buffers for uniform data
            name_buffer = ctypes.create_string_buffer(256)
            length = ctypes.c_int()
            size = ctypes.c_int()
            uniform_type = ctypes.c_uint()

            # Query uniform information
            glGetActiveUniform(shader, i, 256, length, size, uniform_type, name_buffer)
            uni_name = name_buffer.value.decode("utf-8")  # Convert to string

            # Get uniform details
            location = glGetUniformLocation(shader, uni_name)
            locators[uni_name] = location
            uniform_types[uni_name] = uniform_type
            uniforms.append(uni_name)

        blend_mode = self.get_shader_blend_mode(fragment_shader)

        self.SHADERS[shader_name] = {
            "shader": shader,
            "uniforms": uniforms,
            "uniform_locators": locators,
            "uniform_types": uniform_types,
            "blend_mode": blend_mode,
            "hash": hash(vertex_shader + fragment_shader),
        }

        return shader


    def get_shader_blend_mode(self, shader_source):
        # find all blend pragmas; pick the last one if there are multiple
        matches = re.findall(
            r'^\s*#pragma\s+blend\s+([A-Za-z0-9_]+)\s+([A-Za-z0-9_]+)',
            shader_source,
            re.MULTILINE
        )

        if matches:
            src_tok, dst_tok = matches[-1]
            # normalize tokens
            src = src_tok.lstrip('_').upper()
            dst = dst_tok.lstrip('_').upper()

            mapping = {
                'ZERO': GL_ZERO,
                'ONE': GL_ONE,
                'SRC_COLOR': GL_SRC_COLOR,
                'ONE_MINUS_SRC_COLOR': GL_ONE_MINUS_SRC_COLOR,
                'DST_COLOR': GL_DST_COLOR,
                'ONE_MINUS_DST_COLOR': GL_ONE_MINUS_DST_COLOR,
                'SRC_ALPHA': GL_SRC_ALPHA,
                'ONE_MINUS_SRC_ALPHA': GL_ONE_MINUS_SRC_ALPHA,
                'DST_ALPHA': GL_DST_ALPHA,
                'ONE_MINUS_DST_ALPHA': GL_ONE_MINUS_DST_ALPHA,
                'CONSTANT_COLOR': GL_CONSTANT_COLOR,
                'ONE_MINUS_CONSTANT_COLOR': GL_ONE_MINUS_CONSTANT_COLOR,
                'CONSTANT_ALPHA': GL_CONSTANT_ALPHA,
                'ONE_MINUS_CONSTANT_ALPHA': GL_ONE_MINUS_CONSTANT_ALPHA,
                'SRC_ALPHA_SATURATE': GL_SRC_ALPHA_SATURATE,
            }

            try:
               return mapping[src], mapping[dst]
            except KeyError:
                print(f"Unknown blend factor tokens: '{src_tok}' or '{dst_tok}'")


        return GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA


    def bind_texture(self, alpha, dimmer, video_data, clamp=GL_CLAMP_TO_EDGE):
        self.set_parameters({"dimmer": dimmer, "alpha": alpha})

        # For each video, bind its textures to designated texture units and set sampler uniforms.
        # Video1 textures.
        if video_data.status == VideoStatus.READY:
            self.bind_texture_layer(video_data, 0, clamp)
        else:
            self.set_parameters({"dimmer": 0.0})

    @staticmethod
    def create_texture(
        width: int,
        height: int,
        data: np.ndarray,
        internal_format: int | Constant,
        external_format: int | Constant,
        border: list[float],
        data_type: int | Constant = GL_UNSIGNED_BYTE,
    ):
        tex = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, tex)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)

        glTexImage2D(
            GL_TEXTURE_2D,
            0,
            internal_format,
            width,
            height,
            0,
            external_format,
            data_type,
            data,
        )
        glBindTexture(GL_TEXTURE_2D, 0)

        return tex

    # --- New Texture Creation / Update Functions ---
    @staticmethod
    def extract_float_rgb_frame(frame: av.VideoFrame) -> np.ndarray | None:
        frame_format = frame.format.name.lower()
        if "gbr" not in frame_format or "pf32" not in frame_format:
            return None

        data = frame.to_ndarray()
        if data.ndim != 3:
            return None

        if data.shape[0] in (3, 4):
            image = np.moveaxis(data, 0, -1).astype(np.float32, copy=False)
        elif data.shape[2] in (3, 4):
            image = data.astype(np.float32, copy=False)
        else:
            return None

        if image.shape[2] == 3:
            alpha = np.ones((image.shape[0], image.shape[1], 1), dtype=np.float32)
            image = np.concatenate([image, alpha], axis=2)
        return image

    def create_textures(self, video_data: VideoData):

        textures = {}

        frame = video_data.get_next_frame()
        if frame is None:
            print("create_textures: no frame available, skipping texture creation")
            # Leave video_data.status as LOADED so we can retry next frame
            return

        if isinstance(frame, np.ndarray):
            internal_format = GL_RGBA16F if video_data.hdr_still else GL_RGBA8
            data_type = GL_FLOAT if video_data.hdr_still else GL_UNSIGNED_BYTE
            textures["RGB"] = self.create_texture(
                video_data.width,
                video_data.height,
                frame,
                internal_format,
                GL_RGBA,
                [0, 0, 0, 1.0],
                data_type,
            )
            video_data.frame_pix_format = VideoFrameFormat.RGB
            video_data.textures = textures
            return

        frame_format = frame.format.name.lower()
        float_rgb = self.extract_float_rgb_frame(frame)

        if float_rgb is not None:
            textures["RGB"] = self.create_texture(
                video_data.width,
                video_data.height,
                float_rgb,
                GL_RGBA16F,
                GL_RGBA,
                [0, 0, 0, 1.0],
                GL_FLOAT,
            )
            video_data.frame_pix_format = VideoFrameFormat.RGB
        elif frame_format == "nv12":
            y_plane = np.frombuffer(frame.planes[0], dtype=np.uint8).reshape(
                video_data.height, video_data.width
            )
            uv_raw = np.frombuffer(frame.planes[1], dtype=np.uint8).reshape(
                video_data.height // 2, video_data.width // 2
            )
            uv_plane = uv_raw.reshape(video_data.height // 2, video_data.width // 2)
            textures["Y"] = self.create_texture(
                video_data.width,
                video_data.height,
                y_plane,
                GL_R8,
                GL_RED,
                [0, 0, 0, 1.0],
            )

            # UV plane texture (dimensions are width/2 x height/2)
            textures["UV"] = self.create_texture(
                video_data.width // 2,
                video_data.height // 2,
                uv_plane,
                GL_RG8,
                GL_RG,
                [0.5, 0.5, 0.5, 1.0],
            )
            video_data.frame_pix_format = VideoFrameFormat.NV12

        elif "yuv420p" in frame_format or "yuvj420p" in frame_format:
            planes = ["Y", "U", "V"]
            for p in range(3):
                plane = np.frombuffer(frame.planes[p], dtype=np.uint8).reshape(
                    self.get_video_plane_size(frame, p)
                )
                textures[planes[p]] = self.create_texture(
                    plane.shape[1],
                    plane.shape[0],
                    plane,
                    GL_R8,
                    GL_RED,
                    [0, 0, 0, 1.0] if p == 0 else [0.5, 0.5, 0.5, 1.0],
                )

            video_data.frame_pix_format = VideoFrameFormat.YUVJ420p

        elif "rgba" in frame_format or "rgb" in frame_format:
            rgba_data = frame.to_ndarray(format="rgba")
            textures["RGB"] = self.create_texture(
                video_data.width,
                video_data.height,
                rgba_data,
                GL_RGBA8,
                GL_RGBA,
                [0, 0, 0, 1.0],
            )
            video_data.frame_pix_format = VideoFrameFormat.RGB

        elif "gray" in frame_format:
            rgb_data = frame.to_ndarray()
            textures["Y"] = self.create_texture(
                video_data.width,
                video_data.height,
                rgb_data,
                GL_R8,
                GL_RED,
                [0, 0, 0, 1.0],
            )
            video_data.frame_pix_format = VideoFrameFormat.GRAY

        video_data.textures = textures

    @staticmethod
    def get_video_plane_size(frame: av.VideoFrame, plane: int):
        (h, w) = (
            frame.planes[plane].buffer_size // frame.planes[plane].line_size,
            frame.planes[plane].line_size,
        )

        return h, w

    def update_textures(self, video_data: VideoData, frame: av.VideoFrame):

        if frame is None:
            return

        if isinstance(frame, np.ndarray):
            data_type = GL_FLOAT if video_data.hdr_still else GL_UNSIGNED_BYTE
            glBindTexture(GL_TEXTURE_2D, video_data.textures["RGB"])
            glTexSubImage2D(
                GL_TEXTURE_2D,
                0,
                0,
                0,
                video_data.width,
                video_data.height,
                GL_RGBA,
                data_type,
                frame,
            )
            glBindTexture(GL_TEXTURE_2D, 0)
            return

        frame_format = frame.format.name.lower()
        float_rgb = self.extract_float_rgb_frame(frame)

        if float_rgb is not None:
            glBindTexture(GL_TEXTURE_2D, video_data.textures["RGB"])
            glTexSubImage2D(
                GL_TEXTURE_2D,
                0,
                0,
                0,
                video_data.width,
                video_data.height,
                GL_RGBA,
                GL_FLOAT,
                float_rgb,
            )
            glBindTexture(GL_TEXTURE_2D, 0)
        elif frame_format == "nv12":
            y_plane = np.frombuffer(frame.planes[0], dtype=np.uint8).reshape(
                video_data.height, video_data.width
            )
            uv_raw = np.frombuffer(frame.planes[1], dtype=np.uint8).reshape(
                video_data.height // 2, video_data.width // 2
            )
            uv_plane = uv_raw.reshape(video_data.height // 2, video_data.width // 2)

            glBindTexture(GL_TEXTURE_2D, video_data.textures["Y"])
            glTexSubImage2D(
                GL_TEXTURE_2D,
                0,
                0,
                0,
                video_data.width,
                video_data.height,
                GL_RED,
                GL_UNSIGNED_BYTE,
                y_plane,
            )
            glBindTexture(GL_TEXTURE_2D, video_data.textures["UV"])
            glTexSubImage2D(
                GL_TEXTURE_2D,
                0,
                0,
                0,
                video_data.width // 2,
                video_data.height // 2,
                GL_RG,
                GL_UNSIGNED_BYTE,
                uv_plane,
            )
            glBindTexture(GL_TEXTURE_2D, 0)

        elif "yuv420p" in frame_format or "yuvj420p" in frame_format:

            planes = ["Y", "U", "V"]
            for p in range(3):
                (h, w) = self.get_video_plane_size(frame, p)
                plane = np.frombuffer(frame.planes[p], dtype=np.uint8).reshape(
                    self.get_video_plane_size(frame, p)
                )
                glBindTexture(GL_TEXTURE_2D, video_data.textures[planes[p]])
                glTexSubImage2D(
                    GL_TEXTURE_2D, 0, 0, 0, w, h, GL_RED, GL_UNSIGNED_BYTE, plane
                )

            glBindTexture(GL_TEXTURE_2D, 0)

        elif "rgba" in frame_format or "rgb" in frame_format:
            rgba_data = frame.to_ndarray(format="rgba")
            glBindTexture(GL_TEXTURE_2D, video_data.textures["RGB"])
            glTexSubImage2D(
                GL_TEXTURE_2D,
                0,
                0,
                0,
                video_data.width,
                video_data.height,
                GL_RGBA,
                GL_UNSIGNED_BYTE,
                rgba_data,
            )
            glBindTexture(GL_TEXTURE_2D, 0)
        elif "gray" in frame_format:
            rgb_data = frame.to_ndarray()
            glBindTexture(GL_TEXTURE_2D, video_data.textures["Y"])
            glTexSubImage2D(
                GL_TEXTURE_2D,
                0,
                0,
                0,
                video_data.width,
                video_data.height,
                GL_RED,
                GL_UNSIGNED_BYTE,
                rgb_data,
            )
            glBindTexture(GL_TEXTURE_2D, 0)
        else:
            print(f"Unsupported video frame format: '{frame.format.name}'!")

    def bind_texture_layer(self, video_data, layer, clamp=GL_CLAMP_TO_EDGE):
        if len(video_data.textures) == 0:
            # Something didn't work while creating textures, avoid crashing by failing silently
            return

        tex_unit = layer * 3
        locator_base = f"video{(layer+1)}"

        params = {locator_base + "Format": video_data.frame_pix_format}

        glActiveTexture(TEXTURE_UNIT_LOOKUP[tex_unit])
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, clamp)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, clamp)

        if video_data.frame_pix_format == VideoFrameFormat.RGB:
            glBindTexture(GL_TEXTURE_2D, video_data.textures["RGB"])
            params[locator_base + "RGB"] = tex_unit
        elif video_data.frame_pix_format == VideoFrameFormat.NV12:
            glBindTexture(GL_TEXTURE_2D, video_data.textures["Y"])
            params[locator_base + "Y"] = tex_unit
            glActiveTexture(TEXTURE_UNIT_LOOKUP[tex_unit + 1])
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, clamp)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, clamp)
            glBindTexture(GL_TEXTURE_2D, video_data.textures["UV"])
            params[locator_base + "UV"] = tex_unit + 1
        elif video_data.frame_pix_format == VideoFrameFormat.GRAY:
            glBindTexture(GL_TEXTURE_2D, video_data.textures["Y"])
            params[locator_base + "Y"] = tex_unit
            glActiveTexture(TEXTURE_UNIT_LOOKUP[tex_unit + 1])
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, clamp)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, clamp)
        else:  # YUVJ420p
            glBindTexture(GL_TEXTURE_2D, video_data.textures["Y"])
            params[locator_base + "Y"] = tex_unit
            glActiveTexture(TEXTURE_UNIT_LOOKUP[tex_unit + 1])
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, clamp)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, clamp)
            glBindTexture(GL_TEXTURE_2D, video_data.textures["U"])
            params[locator_base + "U"] = tex_unit + 1
            glActiveTexture(TEXTURE_UNIT_LOOKUP[tex_unit + 2])
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, clamp)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, clamp)
            glBindTexture(GL_TEXTURE_2D, video_data.textures["V"])
            params[locator_base + "V"] = tex_unit + 2

        self.set_parameters(params)

    @staticmethod
    def compute_homography_manual(src, dst):
        """Computes a homography matrix manually without OpenCV."""
        a = []
        for i in range(4):
            mx, y = src[i][0], src[i][1]
            u, v = dst[i][0], dst[i][1]
            a.append([-mx, -y, -1, 0, 0, 0, mx * u, y * u, u])
            a.append([0, 0, 0, -mx, -y, -1, mx * v, y * v, v])

        # Swap the last two items so that the points go from LR reading-order to clockwise
        a[2], a[3] = a[3], a[2]

        a = np.array(a)
        u, s, v = np.linalg.svd(a)
        h = v[-1, :].reshape(3, 3)
        return h / h[2, 2]

    @staticmethod
    def setup_pygame():
        pygame.init()
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 0)
        pygame.display.gl_set_attribute(
            pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_ES
        )
        window_size = (1024, 640)
        pygame.display.set_mode(window_size, DOUBLEBUF | OPENGL, vsync=0)
        pygame.display.set_caption("GAOS ArtNet Video Player")
        glViewport(0, 0, window_size[0], window_size[1])
        print("GL version:", glGetString(GL_VERSION))
        print(f"Driver {pygame.display.get_driver()}")


    def create_grid_mesh(self, cols=16, rows=16):
    # cols, rows = number of quads across / down
    # vertices = (cols+1) * (rows+1)
        verts = []
        for j in range(rows + 1):
            v = j / rows
            for i in range(cols + 1):
                u = i / cols
                # start with positions in NDC-ish 0..1; we'll scale with viewport
                # pos.x, pos.y, pos.z,  uv.x, uv.y
                verts.extend([u, v, 0.0, u, v])

        verts = np.array(verts, dtype=np.float32)

        # build indices: two triangles per cell
        indices = []
        for j in range(rows):
            for i in range(cols):
                i0 = j * (cols + 1) + i
                i1 = i0 + 1
                i2 = i0 + (cols + 1)
                i3 = i2 + 1
                # tri 1
                indices.extend([i0, i1, i2])
                # tri 2
                indices.extend([i1, i3, i2])

        indices = np.array(indices, dtype=np.uint32)

        # create GL buffers
        VAO = glGenVertexArrays(1)
        VBO = glGenBuffers(1)
        EBO = glGenBuffers(1)

        glBindVertexArray(VAO)

        glBindBuffer(GL_ARRAY_BUFFER, VBO)
        glBufferData(GL_ARRAY_BUFFER, verts.nbytes, verts, GL_DYNAMIC_DRAW)

        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, EBO)
        glBufferData(GL_ELEMENT_ARRAY_BUFFER, indices.nbytes, indices, GL_STATIC_DRAW)

        self.vertex_stride = 5 * 4  # 5 floats * 4 bytes
        # position
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, self.vertex_stride, ctypes.c_void_p(0))
        glEnableVertexAttribArray(0)
        # uv
        glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, self.vertex_stride, ctypes.c_void_p(12))
        glEnableVertexAttribArray(1)

        glBindVertexArray(0)

        index_count = len(indices)

        grid = [[(j / cols, i / rows) for j in range(cols + 1)]
            for i in range(rows + 1)]

        return VAO, VBO, EBO, index_count, grid


    def setup_geometry(self,rows=16,  cols=16):
 
        (self.left_VAO,
        self.left_VBO,
        self.left_EBO,
        self.left_index_count, self.left_grid) = self.create_grid_mesh(rows, cols)

        (self.right_VAO,
        self.right_VBO,
        self.right_EBO,
        self.right_index_count, self.right_grid) = self.create_grid_mesh(rows, cols)

        self.cols = cols
        self.rows= rows

        num_cols = cols + 1
        num_rows = rows + 1

        line_indices = []
        for y in range(num_rows):
            for x in range(cols):
                i0 = y * num_cols + x
                i1 = i0 + 1
                line_indices += [i0, i1]

        for y in range(rows):
            for x in range(num_cols):
                i0 = y * num_cols + x
                i1 = i0 + num_cols
                line_indices += [i0, i1]

        self.line_indices = np.array(line_indices, dtype=np.uint32)

        # # create a GL buffer for them
        self.grid_line_ebo = glGenBuffers(1)
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self.grid_line_ebo)
        glBufferData(GL_ELEMENT_ARRAY_BUFFER, self.line_indices.nbytes, self.line_indices, GL_STATIC_DRAW)
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, 0)
        self.grid_line_count = len(self.line_indices)

        print("VAO, VBO, and EBO created")


    def update_vbo_vertex(self, screen: str, i: int, j: int, x: float, y: float):
        grid = self.left_grid if screen == "left" else self.right_grid

        # 1) update Python copy
        grid[i][j] = (x, y)

        # 2) compute which vertex index this is
        # row-major: i = 0..divs, j = 0..divs
        idx = i * (self.cols + 1) + j   # 0-based vertex index

        # each vertex = 5 floats = 20 bytes
        offset_bytes = idx * self.vertex_stride  # start of this vertex

        # we only change position (first 2 floats), not texcoords
        data = np.array([x, y], dtype=np.float32)

        glBindBuffer(GL_ARRAY_BUFFER, self.left_VBO if screen == "left" else self.right_VBO)
        glBufferSubData(GL_ARRAY_BUFFER, offset_bytes, data.nbytes, data)
        glBindBuffer(GL_ARRAY_BUFFER, 0)

    def set_background(self, bg_video_data):
        self.bg_video = bg_video_data
        pass

    def set_mask(self, mask_data):
        self.mask_data = mask_data
        pass

    def get_post_parameters(self) -> dict[str, float]:
        return self.post_parameters.copy()

    def set_post_parameters(self, parameters: dict[str, float]):
        for key, value in parameters.items():
            if key in self.post_parameters:
                self.post_parameters[key] = float(value)

    def setup_postprocess_resources(self):
        self.scene_fbo, self.scene_color_tex = self.create_scene_fbo(
            self.scene_size[0], self.scene_size[1], hdr=True
        )
        self.output_fbo, self.output_color_tex = self.create_scene_fbo(
            self.scene_size[0], self.scene_size[1], hdr=False
        )
        self.bloom_w = max(1, self.scene_size[0] // 4)
        self.bloom_h = max(1, self.scene_size[1] // 4)
        (
            self.bloom_fbo,
            self.bloom_tex,
            self.bloom_pingpong_fbo,
            self.bloom_pingpong_tex,
        ) = self.create_bloom_fbos(self.bloom_w, self.bloom_h)
        self.post_VAO, self.post_VBO, self.post_EBO = self.create_postprocess_quad()

    @staticmethod
    def create_scene_fbo(width: int, height: int, hdr: bool = True):
        fbo = glGenFramebuffers(1)
        glBindFramebuffer(GL_FRAMEBUFFER, fbo)

        color_tex = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, color_tex)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        glTexImage2D(
            GL_TEXTURE_2D,
            0,
            GL_RGBA16F if hdr else GL_RGBA8,
            width,
            height,
            0,
            GL_RGBA,
            GL_HALF_FLOAT if hdr else GL_UNSIGNED_BYTE,
            None,
        )
        glFramebufferTexture2D(
            GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, color_tex, 0
        )

        status = glCheckFramebufferStatus(GL_FRAMEBUFFER)
        if hdr and status != GL_FRAMEBUFFER_COMPLETE:
            print(
                f"[Renderer] RGBA16F FBO unsupported (0x{status:04X}), falling back to RGBA8."
            )
            glTexImage2D(
                GL_TEXTURE_2D,
                0,
                GL_RGBA8,
                width,
                height,
                0,
                GL_RGBA,
                GL_UNSIGNED_BYTE,
                None,
            )
            glFramebufferTexture2D(
                GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, color_tex, 0
            )

            status = glCheckFramebufferStatus(GL_FRAMEBUFFER)
        if status != GL_FRAMEBUFFER_COMPLETE:
            raise RuntimeError(f"Scene FBO incomplete: 0x{status:04X}")

        glBindTexture(GL_TEXTURE_2D, 0)
        glBindFramebuffer(GL_FRAMEBUFFER, 0)
        return fbo, color_tex

    @staticmethod
    def create_postprocess_quad():
        vertices = np.array(
            [
                # positions   # texCoords
                -1.0,
                1.0,
                0.0,
                0.0,
                -1.0,
                -1.0,
                0.0,
                1.0,
                1.0,
                -1.0,
                1.0,
                1.0,
                1.0,
                1.0,
                1.0,
                0.0,
            ],
            dtype=np.float32,
        )
        indices = np.array([0, 1, 2, 2, 3, 0], dtype=np.uint32)

        vao = glGenVertexArrays(1)
        vbo = glGenBuffers(1)
        ebo = glGenBuffers(1)

        glBindVertexArray(vao)
        glBindBuffer(GL_ARRAY_BUFFER, vbo)
        glBufferData(GL_ARRAY_BUFFER, vertices.nbytes, vertices, GL_STATIC_DRAW)
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, ebo)
        glBufferData(GL_ELEMENT_ARRAY_BUFFER, indices.nbytes, indices, GL_STATIC_DRAW)

        glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 4 * vertices.itemsize, ctypes.c_void_p(0))
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, 4 * vertices.itemsize, ctypes.c_void_p(2 * vertices.itemsize))
        glEnableVertexAttribArray(1)

        glBindVertexArray(0)
        return vao, vbo, ebo

    @staticmethod
    def create_bloom_fbos(width: int, height: int):
        def make_tex():
            tex = glGenTextures(1)
            glBindTexture(GL_TEXTURE_2D, tex)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
            glTexImage2D(
                GL_TEXTURE_2D,
                0,
                GL_RGBA16F,
                width,
                height,
                0,
                GL_RGBA,
                GL_HALF_FLOAT,
                None,
            )
            return tex

        # extract target
        bloom_fbo = glGenFramebuffers(1)
        bloom_tex = make_tex()
        glBindFramebuffer(GL_FRAMEBUFFER, bloom_fbo)
        glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, bloom_tex, 0)

        # ping-pong targets
        pingpong_fbo = [glGenFramebuffers(1), glGenFramebuffers(1)]
        pingpong_tex = [make_tex(), make_tex()]
        for i in range(2):
            glBindFramebuffer(GL_FRAMEBUFFER, pingpong_fbo[i])
            glFramebufferTexture2D(
                GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, pingpong_tex[i], 0
            )

        glBindTexture(GL_TEXTURE_2D, 0)
        glBindFramebuffer(GL_FRAMEBUFFER, 0)
        return bloom_fbo, bloom_tex, pingpong_fbo, pingpong_tex

    def draw_bloom_pass(self):
        glDisable(GL_BLEND)
        glViewport(0, 0, self.bloom_w, self.bloom_h)

        # Bright extract
        self.set_shader("bloom_extract")
        self.set_parameters(
            {
                "hdrScene": 0,
                "threshold": self.post_parameters["bloomThreshold"],
                "sceneGammaIn": self.post_parameters["sceneGammaIn"],
            }
        )
        glBindFramebuffer(GL_FRAMEBUFFER, self.bloom_fbo)
        glClearColor(0.0, 0.0, 0.0, 1.0)
        glClear(GL_COLOR_BUFFER_BIT)
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, self.scene_color_tex)
        glBindVertexArray(self.post_VAO)
        glDrawElements(GL_TRIANGLES, 6, GL_UNSIGNED_INT, None)

        # Blur ping-pong
        self.set_shader("bloom_blur")
        self.set_parameters({"image": 0, "texelSize": (1.0 / self.bloom_w, 1.0 / self.bloom_h)})
        horizontal = True
        first = True
        last_tex = self.bloom_tex
        for _ in range(self.bloom_blur_passes):
            target = 0 if horizontal else 1
            glBindFramebuffer(GL_FRAMEBUFFER, self.bloom_pingpong_fbo[target])
            self.set_parameters({"horizontal": 1 if horizontal else 0})
            glActiveTexture(GL_TEXTURE0)
            glBindTexture(GL_TEXTURE_2D, self.bloom_tex if first else last_tex)
            glDrawElements(GL_TRIANGLES, 6, GL_UNSIGNED_INT, None)
            last_tex = self.bloom_pingpong_tex[target]
            horizontal = not horizontal
            first = False

        self.bloom_output_tex = last_tex
        glBindVertexArray(0)
        glBindTexture(GL_TEXTURE_2D, 0)
        glBindFramebuffer(GL_FRAMEBUFFER, 0)

    def draw_tonemap_pass(self):
        current_shader = self.current_shader
        glDisable(GL_BLEND)
        glBindFramebuffer(GL_FRAMEBUFFER, self.output_fbo)
        glViewport(0, 0, self.scene_size[0], self.scene_size[1])
        glClearColor(0.0, 0.0, 0.0, 1.0)
        glClear(GL_COLOR_BUFFER_BIT)

        self.set_shader("tonemap")
        self.set_parameters(
            {
                "hdrScene": 0,
                "bloomTex": 1,
                "exposure": self.post_parameters["exposure"],
                "gammaOut": self.post_parameters["gammaOut"],
                "whitePoint": self.post_parameters["whitePoint"],
                "bloomStrength": self.post_parameters["bloomStrength"],
                "sceneGammaIn": self.post_parameters["sceneGammaIn"],
            }
        )

        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, self.scene_color_tex)
        glActiveTexture(GL_TEXTURE1)
        glBindTexture(GL_TEXTURE_2D, self.bloom_output_tex)
        glBindVertexArray(self.post_VAO)
        glDrawElements(GL_TRIANGLES, 6, GL_UNSIGNED_INT, None)
        glBindVertexArray(0)
        glBindTexture(GL_TEXTURE_2D, 0)
        glBindFramebuffer(GL_FRAMEBUFFER, 0)

        if current_shader:
            self.set_shader(current_shader)

    def capture_output_frame_rgb(self):
        width, height = self.window_size
        glBindFramebuffer(GL_FRAMEBUFFER, 0)
        glPixelStorei(GL_PACK_ALIGNMENT, 1)
        data = glReadPixels(0, 0, width, height, GL_RGBA, GL_UNSIGNED_BYTE)
        if data is None:
            if self.ndi_debug:
                print("[NDI] glReadPixels returned no data")
            return None
        frame = np.frombuffer(data, dtype=np.uint8).reshape(height, width, 4)
        if self.ndi_debug:
            now = time.time()
            if now - self._last_ndi_capture_debug >= 1.0:
                print(f"[NDI] Captured framebuffer {width}x{height}")
                self._last_ndi_capture_debug = now
        return np.flipud(frame[:, :, :3]).copy()

    def draw_fps_overlay(self):
        if self.fps_font is None:
            return

        now = time.perf_counter()
        if now - self.last_fps_update >= 0.25:
            self.last_fps_update = now
            self.update_fps_texture(f"FPS {self.last_fps_value:5.1f}")

        if self.fps_texture == 0 or self.fps_texture_size == (0, 0):
            return

        current_shader = self.current_shader
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        self.set_shader("overlay_text")
        self.set_parameters({"overlayTex": 0})

        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, self.fps_texture)

        overlay_w, overlay_h = self.fps_texture_size
        glViewport(12, self.window_size[1] - overlay_h - 12, overlay_w, overlay_h)
        glBindVertexArray(self.post_VAO)
        glDrawElements(GL_TRIANGLES, 6, GL_UNSIGNED_INT, None)
        glBindVertexArray(0)
        glBindTexture(GL_TEXTURE_2D, 0)
        glViewport(0, 0, self.window_size[0], self.window_size[1])

        if current_shader:
            self.set_shader(current_shader)

    def update_fps_texture(self, text: str):
        if self.fps_font is None:
            return

        # Render the overlay text with a transparent background so it never masks content.
        surface = self.fps_font.render(text, True, (255, 255, 255))
        rgba_surface = surface.convert_alpha()
        rgba_data = pygame.image.tostring(rgba_surface, "RGBA", False)
        width, height = rgba_surface.get_size()

        if self.fps_texture == 0:
            self.fps_texture = glGenTextures(1)
            glBindTexture(GL_TEXTURE_2D, self.fps_texture)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        else:
            glBindTexture(GL_TEXTURE_2D, self.fps_texture)

        if self.fps_texture_size != (width, height):
            glTexImage2D(
                GL_TEXTURE_2D,
                0,
                GL_RGBA8,
                width,
                height,
                0,
                GL_RGBA,
                GL_UNSIGNED_BYTE,
                rgba_data,
            )
            self.fps_texture_size = (width, height)
        else:
            glTexSubImage2D(
                GL_TEXTURE_2D,
                0,
                0,
                0,
                width,
                height,
                GL_RGBA,
                GL_UNSIGNED_BYTE,
                rgba_data,
            )

        glBindTexture(GL_TEXTURE_2D, 0)
