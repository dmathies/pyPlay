from __future__ import annotations

import av
import numpy as np
import pygame
from OpenGL.GL import *
from OpenGL.GL.shaders import compileProgram, compileShader

import sys
import os
if sys.version_info >= (3, 9):
    from importlib.resources import files
else:
    from importlib.resources import open_binary, read_text

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from cue_engine import ActiveCue
from qplayer_config import FramingShutter, Point
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

        self.framing = None
        self.transitioning = None
        self.transition_duration = None
        self.dimmer = 1.0
        self.alpha = 0.0
        self.SHADERS = {}
        self.current_shader = None

        pygame.init()
        self.window_size = (1024, 640)
        self.screen = pygame.display.set_mode(
            self.window_size, pygame.DOUBLEBUF | pygame.OPENGL, vsync=1
        )
        pygame.display.set_caption("GAOS ArtNet Video Player")

        glViewport(0, 0, *self.window_size)
        print("GL version:", glGetString(GL_VERSION))
        print(f"Driver {pygame.display.get_driver()}")

        self.clock = pygame.time.Clock()
        self.VAO = self.setup_geometry()
        self.register_shader_program("default")
        self.register_shader_program("default_framing")
        self.set_shader("default")
        self.src_pts = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float32)
        self.homography_matrix = self.compute_homography_manual(
            self.src_pts, self.src_pts
        ).T.flatten()  # Identity
        self.set_parameters(
            {
                "dimmer": 1.0,
                "alpha": 0.5,
                "scale": (1, 1),
                "brightness": 0.0,
                "contrast": 1.0,
                "gamma": 1.0,
                "homographyMatrix": self.homography_matrix,
            }
        )

    def render_frame(self, active_cues: list[ActiveCue]):
        glClear(GL_COLOR_BUFFER_BIT)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        active_cues = [
            cue for cue in active_cues if not cue.complete
        ]  # Remove completed cues

        for active_cue in active_cues:

            if active_cue.video_data.status == VideoStatus.LOADED:
                self.create_textures(active_cue.video_data)
                active_cue.video_data.status = VideoStatus.READY

            if active_cue.video_data.status == VideoStatus.READY:
                frame = active_cue.video_data.get_next_frame()
                self.update_textures(active_cue.video_data, frame)

            if active_cue.alpha_video_data.status == VideoStatus.LOADED:
                self.create_textures(active_cue.alpha_video_data)
                active_cue.alpha_video_data.status = VideoStatus.READY

            if active_cue.alpha_video_data.status == VideoStatus.READY:
                frame = active_cue.alpha_video_data.get_next_frame()
                self.update_textures(active_cue.alpha_video_data, frame)

            if active_cue.alpha_video_data.status == VideoStatus.EMPTY:
                if active_cue.video_data.status == VideoStatus.READY:
                    self.draw_texture(active_cue.video_data, active_cue.alpha)
            else:
                if (
                    active_cue.video_data.status == VideoStatus.READY
                    and active_cue.alpha_video_data.status == VideoStatus.READY
                ):
                    self.draw_texture(
                        active_cue.video_data,
                        active_cue.alpha,
                        active_cue.alpha_video_data,
                    )

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

    def draw_texture(
        self, video: VideoData, alpha: float, alpha_video: VideoData | None = None
    ):
        glBindVertexArray(self.VAO)

        self.bind_texture(alpha, self.dimmer, video)

        if alpha_video:
            if alpha_video.status == VideoStatus.READY:
                self.bind_texture_layer(alpha_video, 1)

        glDrawElements(GL_TRIANGLES, 6, GL_UNSIGNED_INT, None)
        glBindVertexArray(0)

    def set_framing(self, framing: list[FramingShutter]):
        self.framing = framing
        pass

    def set_corners(self, corners: list[Point]):
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
        ).T.flatten()  # Identity
        self.set_parameters({"homographyMatrix": self.homography_matrix})

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
        self.current_shader = shader_name
        glUseProgram(self.SHADERS[shader_name]["shader"])

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
            print(f"Couldn't find/read the shader: '{path}'. \n"
                                    f"Inner exception: {e}")
            # raise FileNotFoundError(f"Couldn't find/read the shader: '{path}'. \n"
            #                         f"Inner exception: {e}")
        return None

    def register_shader_program(self, shader_name):
        vertex_shader = self.load_shader_source(f"{shader_name}.vs.glsl")
        if not vertex_shader:
            vertex_shader = self.load_shader_source("default.vs.glsl")

        fragment_shader = self.load_shader_source(f"{shader_name}.fs.glsl")

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

        self.SHADERS[shader_name] = {
            "shader": shader,
            "uniforms": uniforms,
            "uniform_locators": locators,
            "uniform_types": uniform_types,
        }

        return shader

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
        return vao

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

        elif frame.format.name in ("yuv420p", "yuvj420p"):
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

        elif frame.format.name in "rgb":
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

        elif frame.format.name in "rgba":
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

        elif frame.format.name in ("yuv420p", "yuvj420p"):

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

        elif frame.format.name in "rgba":
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
        else:
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

    def bind_texture_layer(self, video_data, layer, clamp=GL_CLAMP_TO_BORDER):

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

    def compute_homography_manual(self, src, dst):
        """Computes a homography matrix manually without OpenCV."""
        A = []
        for i in range(4):
            x, y = src[i][0], src[i][1]
            u, v = dst[i][0], dst[i][1]
            A.append([-x, -y, -1, 0, 0, 0, x * u, y * u, u])
            A.append([0, 0, 0, -x, -y, -1, x * v, y * v, v])

        A = np.array(A)
        U, S, V = np.linalg.svd(A)
        H = V[-1, :].reshape(3, 3)
        return H / H[2, 2]
