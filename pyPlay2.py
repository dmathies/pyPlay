import os
import av.error

# Force SDL2 to use EGL instead of GLX on X11.
os.environ["SDL_VIDEO_X11_FORCE_EGL"] = "1"


import av
import av.container
import av.format
import av.video
import av.stream
import pygame
import numpy as np
import time
import ctypes
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

# --- Updated VideoData Dataclass ---
@dataclass
class VideoData:
    container: av.container.InputContainer | av.container.OutputContainer
    videoStream: av.VideoStream
    gen: Iterator[av.VideoFrame]
    framePixFormat: VideoFrameFormat
    width: int
    height: int
    textures: dict = field(default_factory=dict)   # Now holds multiple texture IDs (one per plane)
    loaded: bool = False

# --- Video Loading Functions ---
def load_video_async(video_path: str, video_data: VideoData):

    video_data.loaded = False

    my_video_data = load_video(video_path)
    video_data.container = my_video_data.container
    video_data.videoStream = my_video_data.videoStream
    video_data.gen = my_video_data.gen
    video_data.width = my_video_data.width
    video_data.height = my_video_data.height
    video_data.framePixFormat = my_video_data.framePixFormat
    print(f"Async Loaded video {video_path}")

    video_data.loaded = True  # Flag for main thread to create textures

def load_video(video_path):
    try:
        if video_path.lower().endswith((".jpg", ".jpeg", ".png")):
            container = av.open(video_path, format="image2")
            video_stream = container.streams.video[0]
            framePixFormat = VideoFrameFormat.RGB
        else:
            container = av.open(video_path)
            video_stream = container.streams.video[0]
            # Default to NV12 then adjust if needed.
            framePixFormat = VideoFrameFormat.NV12

        if video_stream.format.is_rgb:
            framePixFormat = VideoFrameFormat.RGB
        else:
            if video_stream.format.name == "yuvj420p":
                framePixFormat = VideoFrameFormat.YUVJ420p

        gen = container.decode(video=0)

        video_data = VideoData(
            container, video_stream, gen, framePixFormat,
            video_stream.width, video_stream.height, textures=None, loaded=True
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
        vec2 uvCoords = vTexCoords * 0.5;
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
        vec2 uvCoords = vTexCoords * 0.5;
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

def create_shader_program():
    shader = compileProgram(
        compileShader(vertex_shader, GL_VERTEX_SHADER),
        compileShader(fragment_shader, GL_FRAGMENT_SHADER)
    )
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
        y_plane = np.frombuffer(frame.planes[0], dtype=np.uint8).reshape(video_data.height, video_data.width)
        u_plane = np.frombuffer(frame.planes[1], dtype=np.uint8).reshape(video_data.height // 2, video_data.width // 2)
        v_plane = np.frombuffer(frame.planes[2], dtype=np.uint8).reshape(video_data.height // 2, video_data.width // 2)

        textures['Y'] = create_texture(video_data.width, video_data.height, y_plane,  GL_R8, GL_RED)
        textures['U'] = create_texture(video_data.width//2, video_data.height//2, u_plane,  GL_R8, GL_RED)
        textures['V'] = create_texture(video_data.width//2, video_data.height//2, v_plane,  GL_R8, GL_RED)
        video_data.framePixFormat=VideoFrameFormat.YUVJ420p


    elif frame.format.is_rgb:
        rgb_data = frame.to_ndarray()
        textures['RGB'] = create_texture(video_data.width, video_data.height, rgb_data,  GL_RGB8, GL_RGB)
        video_data.framePixFormat=VideoFrameFormat.RGB

    video_data.textures = textures

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
        y_plane = np.frombuffer(frame.planes[0], dtype=np.uint8).reshape(video_data.height, video_data.width)
        u_plane = np.frombuffer(frame.planes[1], dtype=np.uint8).reshape(video_data.height // 2, video_data.width // 2)
        v_plane = np.frombuffer(frame.planes[2], dtype=np.uint8).reshape(video_data.height // 2, video_data.width // 2)

        glBindTexture(GL_TEXTURE_2D, video_data.textures['Y'])
        glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, video_data.width, video_data.height, GL_RED, GL_UNSIGNED_BYTE, y_plane)
        glBindTexture(GL_TEXTURE_2D, video_data.textures['U'])
        glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, video_data.width//2, video_data.height//2, GL_RED, GL_UNSIGNED_BYTE, u_plane)
        glBindTexture(GL_TEXTURE_2D, video_data.textures['V'])
        glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, video_data.width//2, video_data.height//2, GL_RED, GL_UNSIGNED_BYTE, v_plane)
        glBindTexture(GL_TEXTURE_2D, 0)

    else:
        rgb_data = frame.to_ndarray()
        glBindTexture(GL_TEXTURE_2D, video_data.textures['RGB'])
        glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, video_data.width, video_data.height, GL_RGB, GL_UNSIGNED_BYTE, rgb_data)
        glBindTexture(GL_TEXTURE_2D, 0)


# --- Main Program ---
def main():
    video_playlist = ["video1.mp4", "lecture2.jpg", "Market1.jpg", "MemberStates.png", "video2.mp4", "video3.mp4", "video4.mp4"]
    video_index = 0
    frames=0

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
    # For YUV formats, extract individual planes from the frame.
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

    # Define a full-screen quad.
    vertices = np.array([
        -1.0,  1.0,   0.0, 0.0,
        -1.0, -1.0,   0.0, 1.0,
         1.0, -1.0,   1.0, 1.0,
         1.0,  1.0,   1.0, 0.0,
    ], dtype=np.float32)
    indices = np.array([0, 1, 2, 2, 3, 0], dtype=np.uint32)

    VAO = glGenVertexArrays(1)
    VBO = glGenBuffers(1)
    EBO = glGenBuffers(1)
    glBindVertexArray(VAO)
    glBindBuffer(GL_ARRAY_BUFFER, VBO)
    glBufferData(GL_ARRAY_BUFFER, vertices.nbytes, vertices, GL_STATIC_DRAW)
    glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, EBO)
    glBufferData(GL_ELEMENT_ARRAY_BUFFER, indices.nbytes, indices, GL_STATIC_DRAW)

    glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 4 * vertices.itemsize, ctypes.c_void_p(0))
    glEnableVertexAttribArray(0)
    glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, 4 * vertices.itemsize, ctypes.c_void_p(2 * vertices.itemsize))
    glEnableVertexAttribArray(1)
    glBindVertexArray(0)
    print("VAO, VBO, and EBO created")

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
        try:
            frame1 = next(video1_data.gen)
        except StopIteration:
            video1_data.container.seek(0)
            video1_data.gen = video1_data.container.decode(video=0)
            frame1 = next(video1_data.gen)
        
        update_textures(video1_data, frame1)

        # --- Decode and update textures for video2 if transitioning ---
        if transitioning:
            try:
                frame2 = next(video2_data.gen)
            except StopIteration:
                video2_data.container.seek(0)
                video2_data.gen = video2_data.container.decode(video=0)
                frame2 = next(video2_data.gen)

            update_textures(video2_data, frame2)

            elapsed = time.time() - transition_start_time
            alpha = min(elapsed / transition_duration, 1.0)
            if alpha >= 1.0:
                transitioning = False
                # Swap video1 and video2
                video1_data, video2_data = video2_data, video1_data
                alpha = 0.0
                if video2_data.textures is not None:
                    # Delete old textures.
                    for tex in video2_data.textures.values():
                        glDeleteTextures([tex])

                threading.Thread(target=load_video_async, args=(video_playlist[video_index], video2_data)).start()
                print(f"Loading new video: {video_playlist[video_index]}")
                video_index = (video_index + 1) % len(video_playlist)

        # If a new video has been loaded asynchronously, re-create its textures.
        if video2_data.loaded and video2_data is None:
            print("New video loaded, creating textures...")
            # Grab the first frame to initialize textures.
            try:
                frame2 = next(video2_data.gen)
            except StopIteration:
                video2_data.container.seek(0)
                video2_data.gen = video2_data.container.decode(video=0)
                frame2 = next(video2_data.gen)

            create_textures(video2_data, frame2)
            video2_data.loaded = False

        # --- Bind textures and set shader uniforms ---
        glClear(GL_COLOR_BUFFER_BIT)
        glUseProgram(shader)

        glUniform1i(glGetUniformLocation(shader, "video1Format"), video1_data.framePixFormat.value)
        glUniform1i(glGetUniformLocation(shader, "video2Format"), video2_data.framePixFormat.value)
        glUniform1f(glGetUniformLocation(shader, "alpha"), alpha)

        # For each video, bind its textures to designated texture units and set sampler uniforms.
        # Video1 textures.
        if video1_data.framePixFormat == VideoFrameFormat.RGB:
            glActiveTexture(GL_TEXTURE0)
            glBindTexture(GL_TEXTURE_2D, video1_data.textures['RGB'])
            glUniform1i(glGetUniformLocation(shader, "video1RGB"), 0)
        elif video1_data.framePixFormat == VideoFrameFormat.NV12:
            glActiveTexture(GL_TEXTURE0)
            glBindTexture(GL_TEXTURE_2D, video1_data.textures['Y'])
            glUniform1i(glGetUniformLocation(shader, "video1Y"), 0)
            glActiveTexture(GL_TEXTURE1)
            glBindTexture(GL_TEXTURE_2D, video1_data.textures['UV'])
            glUniform1i(glGetUniformLocation(shader, "video1UV"), 1)
        else:  # YUVJ420p
            glActiveTexture(GL_TEXTURE0)
            glBindTexture(GL_TEXTURE_2D, video1_data.textures['Y'])
            glUniform1i(glGetUniformLocation(shader, "video1Y"), 0)
            glActiveTexture(GL_TEXTURE1)
            glBindTexture(GL_TEXTURE_2D, video1_data.textures['U'])
            glUniform1i(glGetUniformLocation(shader, "video1U"), 1)
            glActiveTexture(GL_TEXTURE2)
            glBindTexture(GL_TEXTURE_2D, video1_data.textures['V'])
            glUniform1i(glGetUniformLocation(shader, "video1V"), 2)

        # Video2 textures.
        if transitioning:
            if video2_data.framePixFormat == VideoFrameFormat.RGB:
                glActiveTexture(GL_TEXTURE3)
                glBindTexture(GL_TEXTURE_2D, video2_data.textures['RGB'])
                glUniform1i(glGetUniformLocation(shader, "video2RGB"), 3)
            elif video2_data.framePixFormat == VideoFrameFormat.NV12:
                glActiveTexture(GL_TEXTURE3)
                glBindTexture(GL_TEXTURE_2D, video2_data.textures['Y'])
                glUniform1i(glGetUniformLocation(shader, "video2Y"), 3)
                glActiveTexture(GL_TEXTURE4)
                glBindTexture(GL_TEXTURE_2D, video2_data.textures['UV'])
                glUniform1i(glGetUniformLocation(shader, "video2UV"), 4)
            else:  # YUVJ420p
                glActiveTexture(GL_TEXTURE3)
                glBindTexture(GL_TEXTURE_2D, video2_data.textures['Y'])
                glUniform1i(glGetUniformLocation(shader, "video2Y"), 3)
                glActiveTexture(GL_TEXTURE4)
                glBindTexture(GL_TEXTURE_2D, video2_data.textures['U'])
                glUniform1i(glGetUniformLocation(shader, "video2U"), 4)
                glActiveTexture(GL_TEXTURE5)
                glBindTexture(GL_TEXTURE_2D, video2_data.textures['V'])
                glUniform1i(glGetUniformLocation(shader, "video2V"), 5)

        # --- Render the quad ---
        glBindVertexArray(VAO)
        glDrawElements(GL_TRIANGLES, 6, GL_UNSIGNED_INT, None)
        glBindVertexArray(0)
        pygame.display.flip()
        crrent_fps = clock.get_fps()
        frames += 1

        if frames > crrent_fps:
            #print(f"fps = {crrent_fps:.2f}")
            frames=0

        #clock.tick(fps)

    video1_data.container.close()
    video2_data.container.close()
    pygame.quit()

if __name__ == "__main__":
    main()
