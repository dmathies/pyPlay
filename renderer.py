from __future__ import annotations

import av
import numpy as np
import pygame
import re
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
    def __init__(self):

        self.homography_matrix = None
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

        pygame.init()
        info = pygame.display.Info()
        primary_w = info.current_w
        pygame.display.quit()

        os.environ['SDL_VIDEO_FULLSCREEN_DISPLAY'] = "1"
        os.environ['SDL_VIDEO_WINDOW_POS'] = f"{primary_w},0"
        os.environ['SDL_VIDEO_MINIMIZE_ON_FOCUS_LOSS'] = '0'


        pygame.init()
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 0)
        pygame.display.gl_set_attribute(
            pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_ES
        )

        info = pygame.display.Info()
        self.window_size = (info.current_w, info.current_h)

        # self.window_size = (1920, 1200)

        self.screen = pygame.display.set_mode(
            (0,0), pygame.FULLSCREEN | pygame.DOUBLEBUF | pygame.OPENGL, vsync=1
        )
        # pygame.display.toggle_fullscreen()
        pygame.display.set_caption("GAOS ArtNet Video Player")
        pygame.mouse.set_visible(False)

        glViewport(0, 0, *self.window_size)
        print("GL version:", glGetString(GL_VERSION))
        print(f"Driver {pygame.display.get_driver()}")

        self.register_shader_program("default")
        self.register_shader_program("default_framing")
        self.set_shader("default")
        self.VAO = self.setup_geometry()
        self.src_pts = np.array([[0, 0], [1, 0], [0, 1], [1, 1]], dtype=np.float32)
        self.set_corners([Point(0, 0), Point(1, 0), Point(0, 1), Point(1, 1)], 1.0)

        self.clock = pygame.time.Clock()

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
                "homographyMatrix": self.homography_matrix,
                "resolution": self.window_size
            }
        )

    def render_frame(self, active_cues: list[ActiveCue]):
        glClear(GL_COLOR_BUFFER_BIT)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        active_cues[:] = [
            cue for cue in active_cues if not cue.complete
        ]  # Remove completed cues

        for active_cue in active_cues:
            alpha = active_cue.alpha
            if getattr(active_cue.cue, "fadeType", FadeType.Linear) == FadeType.SCurve:
                alpha = self.smooth_step(active_cue.alpha)

            if isinstance(active_cue.cue, VideoCue):
                if active_cue.video_data.status == VideoStatus.LOADED:
                    self.create_textures(active_cue.video_data)
                    active_cue.video_data.status = VideoStatus.READY

                if (
                    active_cue.video_data.status == VideoStatus.READY
                    and active_cue.paused == False
                ):
                    frame = active_cue.video_data.get_next_frame()
                    self.update_textures(active_cue.video_data, frame)

                if active_cue.alpha_video_data.status == VideoStatus.LOADED:
                    self.create_textures(active_cue.alpha_video_data)
                    active_cue.alpha_video_data.status = VideoStatus.READY

                if (
                    active_cue.alpha_video_data.status == VideoStatus.READY
                    and active_cue.paused == False
                ):
                    frame = active_cue.alpha_video_data.get_next_frame()
                    self.update_textures(active_cue.alpha_video_data, frame)

                if active_cue.alpha_video_data.status == VideoStatus.EMPTY:
                    if active_cue.video_data.status == VideoStatus.READY:
                        self.set_shader(active_cue.cue.shader)
                        if active_cue.shader_parameters:
                            self.set_parameters(active_cue.shader_parameters)
                        self.set_parameters({
                            "resolution": self.window_size,
                            "time": self.clock.get_time()/1000,
                            "homographyMatrix": self.homography_matrix
                        })
                        self.draw_texture(active_cue.video_data, active_cue.alpha)
                else:
                    if (
                        active_cue.video_data.status == VideoStatus.READY
                        and active_cue.alpha_video_data.status == VideoStatus.READY
                    ):
                        self.set_shader(active_cue.cue.shader)
                        if active_cue.shader_parameters:
                            self.set_parameters(active_cue.shader_parameters)
                        self.set_parameters({
                            "resolution": self.window_size,
                            "time": self.clock.get_time()/1000,
                            "homographyMatrix": self.homography_matrix
                        })
                        self.draw_texture(
                            active_cue.video_data,
                            active_cue.alpha,
                            active_cue.alpha_video_data,
                            active_cue.cue.alphaMode,
                            active_cue.cue.alphaSoftness,
                        )
            elif isinstance(active_cue.cue, VideoFraming):
                if active_cue.cue.framing:
                    self.set_framing(active_cue.cue.framing, alpha)
                if active_cue.cue.corners:
                    self.set_corners(active_cue.cue.corners, alpha)
                if active_cue.alpha == 1.0:
                    active_cue.complete = True

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
                glBindVertexArray(self.VAO)
                glDrawElements(GL_TRIANGLES, 6, GL_UNSIGNED_INT, None)
                glBindVertexArray(0)
                offset_angle += np.pi / 2

            self.set_shader(current_shader)

        pygame.display.flip()

        self.clock.tick(30)

    @staticmethod
    def smooth_step(alpha):
        return alpha * alpha * (3 - 2 * alpha)

    def draw_texture(
        self,
        video: VideoData,
        alpha: float,
        alpha_video: VideoData | None = None,
        alphaMode=AlphaMode.Opaque,
        alphaSoftness=0.0,
    ):
        glBindVertexArray(self.VAO)

        # print(f"Draw Texture: alpha:{alpha}, alphaMode:{alphaMode},  video1Format: {video.frame_pix_format}")

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

        glDrawElements(GL_TRIANGLES, 6, GL_UNSIGNED_INT, None)
        glBindVertexArray(0)

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

    def set_corners(self, corners: list[Point], alpha: float):
        self.corners = corners

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
            self.homography_matrix = self.compute_homography_manual(
                corners_np, self.src_pts
            ).T.flatten()
            self.set_parameters({"homographyMatrix": self.homography_matrix})
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
        if self.current_shader == shader_name:
            return

        if shader_name not in self.SHADERS:
            self.current_shader = "default"
            glUseProgram(self.SHADERS["default"]["shader"])
            return

        # if not shader_name.startswith("default"):
        #     print(f"{shader_name} shader loaded")

        self.current_shader = shader_name
        glUseProgram(self.SHADERS[shader_name]["shader"])
        if self.SHADERS[shader_name].get("blend_mode",None):
            glBlendFunc(*self.SHADERS[shader_name]["blend_mode"])

    def load_shader_source(self, path: str) -> str | None:
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
            print(
                f"Couldn't find/read the shader: '{path}'. \n" f"Inner exception: {e}"
            )
            # raise FileNotFoundError(f"Couldn't find/read the shader: '{path}'. \n"
            #                         f"Inner exception: {e}")
        return None

    def register_shader_program(self, shader_name):
        vertex_shader = self.load_shader_source(f"{shader_name}.vs.glsl")
        if not vertex_shader:
            vertex_shader = self.load_shader_source("default.vs.glsl")

        fragment_shader = self.load_shader_source(f"{shader_name}.fs.glsl")

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


    def bind_texture(self, alpha, dimmer, video_data, clamp=GL_CLAMP_TO_BORDER):
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
    ):
        tex = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, tex)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_BORDER)
        border_color = np.array(border, dtype=np.float32)
        glTexParameterfv(GL_TEXTURE_2D, GL_TEXTURE_BORDER_COLOR, border_color)

        glTexImage2D(
            GL_TEXTURE_2D,
            0,
            internal_format,
            width,
            height,
            0,
            external_format,
            GL_UNSIGNED_BYTE,
            data,
        )
        glBindTexture(GL_TEXTURE_2D, 0)

        return tex

    # --- New Texture Creation / Update Functions ---
    def create_textures(self, video_data: VideoData):

        textures = {}

        frame = video_data.get_next_frame()

        if frame.format.name == "NV12":
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

        elif "yuv420p" in frame.format.name or "yuvj420p" in frame.format.name:
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

        elif "rgb" in frame.format.name:
            rgb_data = frame.to_ndarray()
            textures["RGB"] = self.create_texture(
                video_data.width,
                video_data.height,
                rgb_data,
                GL_RGB8,
                GL_RGB,
                [0, 0, 0, 1.0],
            )
            video_data.frame_pix_format = VideoFrameFormat.RGB

        elif "rgba" in frame.format.name:
            rgb_data = frame.to_ndarray()
            textures["RGB"] = self.create_texture(
                video_data.width,
                video_data.height,
                rgb_data,
                GL_RGBA8,
                GL_RGBA,
                [0, 0, 0, 1.0],
            )
            video_data.frame_pix_format = VideoFrameFormat.RGB
        elif "gray" in frame.format.name:
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

        if frame.format.name == "NV12":
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

        elif "yuv420p" in frame.format.name or "yuvj420p" in frame.format.name:

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

        elif "rgba" in frame.format.name:
            rgb_data = frame.to_ndarray()
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
                rgb_data,
            )
            glBindTexture(GL_TEXTURE_2D, 0)
        elif "gray" in frame.format.name:
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
        elif "rgb" in frame.format.name:
            rgb_data = frame.to_ndarray()
            glBindTexture(GL_TEXTURE_2D, video_data.textures["RGB"])
            glTexSubImage2D(
                GL_TEXTURE_2D,
                0,
                0,
                0,
                video_data.width,
                video_data.height,
                GL_RGB,
                GL_UNSIGNED_BYTE,
                rgb_data,
            )
            glBindTexture(GL_TEXTURE_2D, 0)
        else:
            print(f"Unsupported video frame format: '{frame.format.name}'!")

    def bind_texture_layer(self, video_data, layer, clamp=GL_CLAMP_TO_BORDER):
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

    @staticmethod
    def setup_geometry():
        # Define a full-screen quad.
        vertices = np.array(
            [
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
        glVertexAttribPointer(
            0, 2, GL_FLOAT, GL_FALSE, 4 * vertices.itemsize, ctypes.c_void_p(0)
        )
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(
            1,
            2,
            GL_FLOAT,
            GL_FALSE,
            4 * vertices.itemsize,
            ctypes.c_void_p(2 * vertices.itemsize),
        )
        glEnableVertexAttribArray(1)
        glBindVertexArray(0)
        print("VAO, VBO, and EBO created")
        return vao
