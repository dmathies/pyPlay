import os
import platform
if platform.system() == "Linux":
    # Force SDL2 to use EGL instead of GLX on X11.
    os.environ["SDL_VIDEO_X11_FORCE_EGL"] = "1"
    os.environ["PYOPENGL_PLATFORM"]="egl"
    os.environ["MESA_D3D12_DEFAULT_ADAPTER_NAME"]="nvidia"
    os.environ["DISPLAY"]=":0.0"

import av
import av.codec
import av.codec.hwaccel
import av.container
import av.error
import av.format
import av.stream
import av.video
import pygame
import numpy as np
import time
import threading
from typing import Iterator
from dataclasses import dataclass, field
from enum import Enum

from OpenGL.GL import *
from OpenGL.GL.shaders import compileProgram, compileShader
from pygame.locals import *


# --- Video Format Enum ---
class VideoFrameFormat(Enum):
    RGB = 0
    NV12 = 1
    YUVJ420p = 2

class VideoStatus(Enum):
    LOADING = 0
    LOADED = 1
    READY = 2
    NOT_READY = -1

TEXTURE_UNIT_LOOKUP = [GL_TEXTURE0,  GL_TEXTURE1,  GL_TEXTURE2,  GL_TEXTURE3,
                     GL_TEXTURE4,  GL_TEXTURE5,  GL_TEXTURE6,  GL_TEXTURE7,
                     GL_TEXTURE8,  GL_TEXTURE9,  GL_TEXTURE10, GL_TEXTURE11,
                     GL_TEXTURE12, GL_TEXTURE13, GL_TEXTURE14, GL_TEXTURE15]

# --- Updated VideoData Dataclass ---
@dataclass
class VideoData:
    container: av.container.InputContainer | av.container.OutputContainer
    videoStream: av.VideoStream
    gen: Iterator[av.VideoFrame]
    framePixFormat: VideoFrameFormat
    width: int
    height: int
    isStill: False
    textures: dict = field(default_factory=dict)   # Now holds multiple texture IDs (one per plane)
    status: VideoStatus = VideoStatus.NOT_READY

# --- Video Loading Functions ---
def load_video_async(video_path: str, video_data: VideoData):

    video_data.status = VideoStatus.LOADING

    my_video_data = load_video(video_path)
    video_data.container = my_video_data.container
    video_data.videoStream = my_video_data.videoStream
    video_data.gen = my_video_data.gen
    video_data.width = my_video_data.width
    video_data.height = my_video_data.height
    video_data.isStill = my_video_data.isStill
    video_data.framePixFormat = my_video_data.framePixFormat
    print(f"Async Loaded video {video_path}")

    video_data.status = VideoStatus.LOADED  # Flag for main thread to create textures

def load_video(video_path):
    try:
        if video_path.lower().endswith((".jpg", ".jpeg", ".png")):
            container = av.open(video_path, format="image2")
            video_stream = container.streams.video[0]
            frame_pix_format = VideoFrameFormat.RGB
            still = True
        else:
            hwaccel = av.codec.hwaccel.HWAccel("drm", allow_software_fallback=True)
            container = av.open(video_path, hwaccel=hwaccel)
            video_stream = container.streams.video[0]
            # Default to NV12 then adjust if needed.
            frame_pix_format = VideoFrameFormat.NV12
            still = False

        if video_stream.format.is_rgb:
            frame_pix_format = VideoFrameFormat.RGB
        else:
            if video_stream.format.name == "yuvj420p":
                frame_pix_format = VideoFrameFormat.YUVJ420p

        gen = container.decode(video=0)

        video_data = VideoData(
            container, video_stream, gen, frame_pix_format,
            video_stream.width, video_stream.height, still, textures={}, status=VideoStatus.LOADED
        )
        return video_data

    except av.OSError as e:
        print(f"Error opening video {video_path}: {e}")

# --- Shader Sources ---
vertex_shader = """
#version 300 es
precision highp float;

layout(location = 0) in vec2 position;
layout(location = 1) in vec2 texCoords;
out vec2 vTexCoords;
void main() {
    gl_Position = vec4(position, 0.0, 1.0);
    vTexCoords = texCoords;
}
"""

# The fragment shader now supports either a single RGB texture or multiple YUV textures.
# videoXFormat: 0 = RGB, 1 = NV12, 2 = YUVJ420p.
fragment_shader = """
#version 300 es
precision mediump float;
in vec2 vTexCoords;
out vec4 fragColor;

uniform int video1Format; // 0: RGB, 1: NV12, 2: YUVJ420p
uniform sampler2D video1RGB;
uniform sampler2D video1Y;
uniform sampler2D video1UV; // For NV12
uniform sampler2D video1U;  // For YUVJ420p
uniform sampler2D video1V;  // For YUVJ420p

uniform int video2Format; // 0: RGB, 1: NV12, 2: YUVJ420p
uniform sampler2D video2RGB;
uniform sampler2D video2Y;
uniform sampler2D video2UV; // For NV12
uniform sampler2D video2U;
uniform sampler2D video2V;

uniform float alpha; // Blending factor between video1 and video2

vec3 NV12ToRGB(float y, vec2 uv) {
    float Y = y;
    float U = uv.x - 0.5;
    float V = uv.y - 0.5;
    float r = Y + 1.402 * V;
    float g = Y - 0.344136 * U - 0.714136 * V;
    float b = Y + 1.772 * U;
    return vec3(r, g, b);
}

vec3 YUV420pToRGB(float y, float u, float v) {
    float Y = y;
    float U = u - 0.5;
    float V = v - 0.5;
    float r = Y + 1.402 * V;
    float g = Y - 0.344136 * U - 0.714136 * V;
    float b = Y + 1.772 * U;
    return vec3(r, g, b);
}

vec3 getVideo1Color() {
    if(video1Format == 0) {
        return texture(video1RGB, vTexCoords).rgb;
    } else if(video1Format == 1) {
        float y = texture(video1Y, vTexCoords).r;
        vec2 uv = texture(video1UV, vTexCoords).rg;
        return NV12ToRGB(y, uv);
    } else {
        float y = texture(video1Y, vTexCoords).r;
        // Since U and V textures are half size, scale texture coordinates.
        vec2 uvCoords = vTexCoords;
        float u = texture(video1U, uvCoords).r;
        float v = texture(video1V, uvCoords).r;
        return YUV420pToRGB(y, u, v);
    }
}

vec3 getVideo2Color() {
    if(video2Format == 0) {
        return texture(video2RGB, vTexCoords).rgb;
    } else if(video2Format == 1) {
        float y = texture(video2Y, vTexCoords).r;
        vec2 uv = texture(video2UV, vTexCoords).rg;
        return NV12ToRGB(y, uv);
    } else {
        float y = texture(video2Y, vTexCoords).r;
        vec2 uvCoords = vTexCoords;
        float u = texture(video2U, uvCoords).r;
        float v = texture(video2V, uvCoords).r;
        return YUV420pToRGB(y, u, v);
    }
}

void main() {
    vec3 color1 = getVideo1Color();
    vec3 color2 = getVideo2Color();
    fragColor = vec4(mix(color1, color2, alpha), 1.0);
}
"""

UNIFORMS = [
    "video1Format", "video1RGB", "video1Y", "video1UV", "video1U", "video1V",
    "video2Format", "video2RGB", "video2Y", "video2UV", "video2U", "video2V",
    "alpha"]

UNIFORM_LOCATORS = {}

def create_shader_program():
    shader = compileProgram(
        compileShader(vertex_shader, GL_VERTEX_SHADER),
        compileShader(fragment_shader, GL_FRAGMENT_SHADER)
    )

    for u in UNIFORMS:
        UNIFORM_LOCATORS[u] = glGetUniformLocation(shader, u)

    return shader


def create_texture(width:int, height:int, data: np.ndarray, internalFormat:int, externalFormat: int):
    tex = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, tex)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
    glTexImage2D(GL_TEXTURE_2D, 0, internalFormat, width, height, 0, externalFormat, GL_UNSIGNED_BYTE, data)
    glBindTexture(GL_TEXTURE_2D, 0)

    return tex



# --- New Texture Creation / Update Functions ---
def create_textures(video_data: VideoData, frame: av.VideoFrame):

    textures = {}

    if frame.format.name == "NV12":
        y_plane = np.frombuffer(frame.planes[0], dtype=np.uint8).reshape(video_data.height, video_data.width)
        uv_raw = np.frombuffer(frame.planes[1], dtype=np.uint8).reshape(video_data.height // 2, video_data.width //2)
        uv_plane = uv_raw.reshape(video_data.height//2, video_data.width//2)
        textures['Y'] = create_texture(video_data.width, video_data.height, y_plane,  GL_R8, GL_RED)

        # UV plane texture (dimensions are width/2 x height/2)
        textures['UV'] = create_texture(video_data.width//2, video_data.height//2, uv_plane,  GL_RG8, GL_RG)
        video_data.framePixFormat=VideoFrameFormat.NV12

    elif frame.format.name in ("yuv420p", "yuvj420p"):
        planes = ['Y', 'U', 'V']
        for p in range(3):
            plane = np.frombuffer(frame.planes[p], dtype=np.uint8).reshape(get_video_plane_size(frame, p))
            textures[planes[p]] = create_texture(plane.shape[1], plane.shape[0], plane,  GL_R8, GL_RED)

        video_data.framePixFormat=VideoFrameFormat.YUVJ420p

    elif frame.format.name in "rgb":
        rgb_data = frame.to_ndarray()
        textures['RGB'] = create_texture(video_data.width, video_data.height, rgb_data,  GL_RGB8, GL_RGB)
        video_data.framePixFormat=VideoFrameFormat.RGB

    elif frame.format.name in "rgba":
        rgb_data = frame.to_ndarray()
        textures['RGB'] = create_texture(video_data.width, video_data.height, rgb_data,  GL_RGBA8, GL_RGBA)
        video_data.framePixFormat=VideoFrameFormat.RGB

    video_data.textures = textures


def get_video_plane_size(frame: av.VideoFrame, plane: int):
    (h, w) = (frame.planes[plane].buffer_size // frame.planes[plane].line_size,
              frame.planes[plane].line_size)

    # (h, w) = (frame.planes[plane].buffer_size // frame.width, frame.width)

    return h, w

def update_textures(video_data: VideoData, frame: av.VideoFrame):

    if frame.format.name == "NV12":
        y_plane = np.frombuffer(frame.planes[0], dtype=np.uint8).reshape(video_data.height, video_data.width)
        uv_raw = np.frombuffer(frame.planes[1], dtype=np.uint8).reshape(video_data.height // 2, video_data.width //2)
        uv_plane = uv_raw.reshape(video_data.height//2, video_data.width//2)

        glBindTexture(GL_TEXTURE_2D, video_data.textures['Y'])
        glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, video_data.width, video_data.height, GL_RED, GL_UNSIGNED_BYTE, y_plane)
        glBindTexture(GL_TEXTURE_2D, video_data.textures['UV'])
        glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, video_data.width//2, video_data.height//2, GL_RG, GL_UNSIGNED_BYTE, uv_plane)
        glBindTexture(GL_TEXTURE_2D, 0)

    elif frame.format.name in ("yuv420p", "yuvj420p"):

        planes = ['Y', 'U', 'V']
        for p in range(3):
            (h,w) = get_video_plane_size(frame, p)
            plane = np.frombuffer(frame.planes[p], dtype=np.uint8).reshape(get_video_plane_size(frame, p))
            glBindTexture(GL_TEXTURE_2D, video_data.textures[planes[p]])
            glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, w, h, GL_RED, GL_UNSIGNED_BYTE, plane)

        glBindTexture(GL_TEXTURE_2D, 0)

    elif frame.format.name in "rgba":
        rgb_data = frame.to_ndarray()
        glBindTexture(GL_TEXTURE_2D, video_data.textures['RGB'])
        glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, video_data.width, video_data.height, GL_RGBA, GL_UNSIGNED_BYTE, rgb_data)
        glBindTexture(GL_TEXTURE_2D, 0)
    else:
        rgb_data = frame.to_ndarray()
        glBindTexture(GL_TEXTURE_2D, video_data.textures['RGB'])
        glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, video_data.width, video_data.height, GL_RGB, GL_UNSIGNED_BYTE, rgb_data)
        glBindTexture(GL_TEXTURE_2D, 0)


# --- Main Program ---
def main():
    video_playlist = [ "lecture2.jpg", "Market1.jpg", "MemberStates.png", "lecture2.jpg", "vide1_h265.mp4", "video2.mp4", "video3.mp4", "video4.mp4"]
    #video_playlist = [ "video4.mp4", "video4.mp4", "MemberStates.png", "lecture2.jpg", "Market1.jpg", "MemberStates.png", "vide1_h265.mp4", "video2.mp4", "video3.mp4", "video4.mp4"]
    video_index = 0
    frames=0
    seconds=0

    pygame.init()
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 0)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_ES)

    window_size = (1024, 768)
    pygame.display.set_mode(window_size, DOUBLEBUF | OPENGL, vsync=0)
    pygame.display.set_caption("Video Crossfade with libav (PyAV)")
    glViewport(0, 0, window_size[0], window_size[1])

    print("GL version:", glGetString(GL_VERSION))
    print(f"Driver {pygame.display.get_driver()}")

    # Load the first two videos.
    video1_data = load_video(video_playlist[video_index])
    video_index = (video_index + 1) % len(video_playlist)
    video2_data = load_video(video_playlist[video_index])
    video_index = (video_index + 1) % len(video_playlist)

    # Initially create textures for video1 and video2.
    frame1 = next(video1_data.gen)
    create_textures(video1_data, frame1)

    frame2 = next(video2_data.gen)
    create_textures(video2_data, frame2)

    # Get fps from video1.
    fps = float(video1_data.videoStream.average_rate) if video1_data.videoStream.average_rate else 50.0

    # Create shader program.
    shader = create_shader_program()
    glUseProgram(shader)
    print("Shader created")

    VAO = setup_geometry()

    # Transition variables.
    transitioning = False
    transition_start_time = 0
    transition_duration = 2.0  # seconds

    clock = pygame.time.Clock()
    running = True
    alpha = 0.0

    while running:
        for event in pygame.event.get():
            if event.type == QUIT:
                running = False
            elif event.type == KEYDOWN:
                if event.key == K_q:
                    running = False
                elif event.key == K_F11:
                    pygame.display.toggle_fullscreen()
                elif event.key == K_SPACE:
                    if not transitioning:
                        transitioning = True
                        transition_start_time = time.time()
                    else:
                        transition_start_time = time.time() - transition_duration
            elif event.type == MOUSEBUTTONDOWN:
                if event.button == 1 and getattr(event, 'clicks', 1) == 2:
                    pygame.display.toggle_fullscreen()

        # --- Decode and update textures for video1 ---
        process_frame(video1_data)

        # --- Decode and update textures for video2 if transitioning ---
        if transitioning:
            if video2_data.status== VideoStatus.READY:
                process_frame(video2_data)

            elapsed = time.time() - transition_start_time
            alpha = min(elapsed / transition_duration, 1.0)
            if alpha >= 1.0:
                transitioning = False
                # Swap video1 and video2
                video1_data, video2_data = video2_data, video1_data
                alpha = 0.0
                video2_data.status = VideoStatus.NOT_READY
                if video2_data.textures is not None:
                    # Delete old textures.
                    for tex in video2_data.textures.values():
                        glDeleteTextures([tex])

                    video2_data.textures = {}

                    if video2_data.container is not None:
                        video2_data.container.close()

                threading.Thread(target=load_video_async, args=(video_playlist[video_index], video2_data)).start()
                print(f"Loading new video: {video_playlist[video_index]}")
                video_index = (video_index + 1) % len(video_playlist)

        # If a new video has been loaded asynchronously, re-create its textures.
        if video2_data.status == VideoStatus.LOADED:
            print("New video loaded, creating textures...")
            # Grab the first frame to initialize textures.
            try:
                frame2 = next(video2_data.gen)
            except StopIteration:
                video2_data.container.seek(0)
                video2_data.gen = video2_data.container.decode(video=0)
                frame2 = next(video2_data.gen)

            create_textures(video2_data, frame2)
            video2_data.status = VideoStatus.READY

        # Clear
        glClear(GL_COLOR_BUFFER_BIT)
        glUseProgram(shader)

        bind_textures(alpha, transitioning, video1_data, video2_data)

        # --- Render the quad ---
        glBindVertexArray(VAO)
        glDrawElements(GL_TRIANGLES, 6, GL_UNSIGNED_INT, None)
        glBindVertexArray(0)
        pygame.display.flip()
        current_fps = clock.get_fps()
        frames += 1

        if 0 < current_fps < frames:
            print(f"fps = {current_fps:.2f}")
            frames=0
            seconds +=1
            if seconds >5:
                seconds=0
                if not transitioning:
                    transitioning = True
                    transition_start_time = time.time()
                else:
                    transition_start_time = time.time() - transition_duration


        clock.tick(300)

    if video1_data.container is not None:
        video1_data.container.close()
    if video2_data.container is not None:
        video2_data.container.close()

    pygame.quit()


def process_frame(video_data):
    if not video_data.isStill:
        try:
            frame1 = next(video_data.gen)
        except StopIteration:
            video_data.container.seek(0)
            video_data.gen = video_data.container.decode(video=0)
            frame1 = next(video_data.gen)

        update_textures(video_data, frame1)


def bind_textures(alpha, transitioning, video1_data, video2_data):
    # --- Bind textures and set shader uniforms ---
    glUniform1f(UNIFORM_LOCATORS["alpha"], alpha)

    # For each video, bind its textures to designated texture units and set sampler uniforms.
    # Video1 textures.
    bind_texture(video1_data, 0)

    # Video2 textures.
    if transitioning and video2_data.status == VideoStatus.READY:
        bind_texture(video2_data, 1)


def bind_texture(video_data, layer):

    tex_unit = layer *3
    locator_base = f"video{(layer+1)}"

    glUniform1i(UNIFORM_LOCATORS[locator_base+"Format"], video_data.framePixFormat.value)

    if video_data.framePixFormat == VideoFrameFormat.RGB:
        glActiveTexture(TEXTURE_UNIT_LOOKUP[tex_unit])
        glBindTexture(GL_TEXTURE_2D, video_data.textures['RGB'])
        glUniform1i(UNIFORM_LOCATORS[locator_base+"RGB"], tex_unit)
    elif video_data.framePixFormat == VideoFrameFormat.NV12:
        glActiveTexture(TEXTURE_UNIT_LOOKUP[tex_unit])
        glBindTexture(GL_TEXTURE_2D, video_data.textures['Y'])
        glUniform1i(UNIFORM_LOCATORS[locator_base+"Y"], tex_unit)
        glActiveTexture(TEXTURE_UNIT_LOOKUP[tex_unit+1])
        glBindTexture(GL_TEXTURE_2D, video_data.textures['UV'])
        glUniform1i(UNIFORM_LOCATORS[locator_base+"UV"], tex_unit+1)
    else:  # YUVJ420p
        glActiveTexture(TEXTURE_UNIT_LOOKUP[tex_unit])
        glBindTexture(GL_TEXTURE_2D, video_data.textures['Y'])
        glUniform1i(UNIFORM_LOCATORS[locator_base+"Y"], tex_unit)
        glActiveTexture(TEXTURE_UNIT_LOOKUP[tex_unit+1])
        glBindTexture(GL_TEXTURE_2D, video_data.textures['U'])
        glUniform1i(UNIFORM_LOCATORS[locator_base+"U"], tex_unit+1)
        glActiveTexture(TEXTURE_UNIT_LOOKUP[tex_unit+2])
        glBindTexture(GL_TEXTURE_2D, video_data.textures['V'])
        glUniform1i(UNIFORM_LOCATORS[locator_base+"V"], tex_unit+2)


def setup_geometry():
    # Define a full-screen quad.
    vertices = np.array([
        -1.0, 1.0, 0.0, 0.0,
        -1.0, -1.0, 0.0, 1.0,
        1.0, -1.0, 1.0, 1.0,
        1.0, 1.0, 1.0, 0.0,
    ], dtype=np.float32)
    indices = np.array([0, 1, 2, 2, 3, 0], dtype=np.uint32)
    VAO = glGenVertexArrays(1)
    VBO = glGenBuffers(1)
    EBO = glGenBuffers(1)
    glBindVertexArray(VAO)
    glBindBuffer(GL_ARRAY_BUFFER, VBO)
    glBufferData(GL_ARRAY_BUFFER, vertices.nbytes, vertices, GL_STATIC_DRAW)
    glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, EBO)
    glBufferData(GL_ELEMENT_ARRAY_BUFFER, indices.nbytes, indices,
                 GL_STATIC_DRAW)
    glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 4 * vertices.itemsize,
                          ctypes.c_void_p(0))
    glEnableVertexAttribArray(0)
    glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, 4 * vertices.itemsize,
                          ctypes.c_void_p(2 * vertices.itemsize))
    glEnableVertexAttribArray(1)
    glBindVertexArray(0)
    print("VAO, VBO, and EBO created")
    return VAO


if __name__ == "__main__":
    main()
