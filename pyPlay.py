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
from dataclasses import dataclass
from enum import Enum

from OpenGL.GL import *
from OpenGL.GL.shaders import compileProgram, compileShader
# import pygame.locals
from pygame.locals import *


class VideoFrameFormat(Enum):
    RGB = 0,
    RGBA = 1,
    JPEG = 2,
    NV12 = 3,
    YUVJ420p = 4


@dataclass
class VideoData:
    container: av.container.InputContainer | av.container.OutputContainer
    videoStream: av.VideoStream
    gen: Iterator[av.VideoFrame]
    framePixFormat: VideoFrameFormat
    width: int
    height: int
    texture: int
    loaded: bool


def load_video_async(video_path: str, video_data: VideoData):
    """Loads a video asynchronously and updates the dictionary."""

    my_video_data = load_video(video_path)
    video_data.container = my_video_data.container
    video_data.videoStream = my_video_data.videoStream
    video_data.gen = my_video_data.gen
    video_data.width = my_video_data.width
    video_data.height = my_video_data.height
    video_data.loaded = True  # Flag for main thread to create texture

    print(f"Async Loaded video {video_path}")

def load_video(video_path):
    """Loads a video asynchronously."""
    try:
        if video_path.lower().endswith((".jpg", ".jpeg", ".png")):
            container = av.open(video_path, format="image2")
            video_stream = container.streams.video[0]
            framePixFormat = VideoFrameFormat.RGB

        else:
            container = av.open(video_path)
            video_stream = container.streams.video[0]
            framePixFormat = VideoFrameFormat.NV12

        if video_stream.format.is_rgb:
            framePixFormat = VideoFrameFormat.RGB
        else:
            if video_stream.format.name =="yuvj420p":
                framePixFormat = VideoFrameFormat.YUVJ420p

        gen = container.decode(video=0)

        # Data structure for async video loading
        video_data = VideoData(container, video_stream, gen, framePixFormat, video_stream.width, video_stream.height, None
                               , True)

        return video_data

    except av.OSError as e:
        print(f"Error opening video {video_path}: {e}")


# --- Shader Sources ---
vertex_shader = """
#version 300 es
precision highp float; // Optional in vertex shaders, but recommended

layout(location = 0) in vec2 position;
layout(location = 1) in vec2 texCoords;

out vec2 vTexCoords;

void main() {
    gl_Position = vec4(position, 0.0, 1.0);
    vTexCoords = texCoords;
}
"""

fragment_shader = """
#version 300 es
precision mediump float; // Define default precision for floats

in vec2 vTexCoords;
out vec4 fragColor;

uniform sampler2D tex1;
uniform sampler2D tex2;
uniform float alpha; // 0.0: show tex1, 1.0: show tex2

void main() {
    vec4 color1 = texture(tex1, vTexCoords);
    vec4 color2 = texture(tex2, vTexCoords);
    fragColor = mix(color1, color2, alpha);
}

"""

# --- Helper Functions ---
def create_shader_program():
    """Compile and link the vertex and fragment shaders."""
    shader = compileProgram(
        compileShader(vertex_shader, GL_VERTEX_SHADER),
        compileShader(fragment_shader, GL_FRAGMENT_SHADER)
    )
    return shader

def create_texture(video_data: VideoData, data=None):
    """Create an empty texture (or initialize with data)."""
    video_data.texture = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, video_data.texture)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
    if video_data.framePixFormat in (VideoFrameFormat.NV12, VideoFrameFormat.YUVJ420p):
        glTexImage2D(GL_TEXTURE_2D, 0, GL_R8, video_data.width, video_data.height + video_data.height // 2, 0, GL_RED, GL_UNSIGNED_BYTE, data)
    else:
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, video_data.width, video_data.height, 0, GL_RGB, GL_UNSIGNED_BYTE, data)
    glBindTexture(GL_TEXTURE_2D, 0)


def update_texture(video_data: VideoData, frame_array):
    """
    Updates the given texture with the new frame.
    OpenGL will automatically scale it to fit the viewport.
    """
    glBindTexture(GL_TEXTURE_2D, video_data.texture)
    if video_data.framePixFormat in (VideoFrameFormat.NV12, VideoFrameFormat.YUVJ420p):
        glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, frame_array.shape[1], frame_array.shape[0], GL_RED, GL_UNSIGNED_BYTE, frame_array)
    else:
        glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, frame_array.shape[1], frame_array.shape[0], GL_RGB, GL_UNSIGNED_BYTE, frame_array)
    glBindTexture(GL_TEXTURE_2D, 0)


# --- Main Program ---
def main():
    video_playlist = ["video4.mp4", "video1.mp4", "lecture2.jpg", "Market1.jpg", "MemberStates.png", "video2.mp4", "video3.mp4", "video4.mp4"]  # Add more videos if needed
    video_index = 0  # Track current video

    # Initialize Pygame and create an OpenGL context.
    pygame.init()

    # pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
    # pygame.display.gl_set_attribute( pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 0)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_ES)

    window_size = (1024, 768)  # Window size for display
    pygame.display.set_mode(window_size, DOUBLEBUF | OPENGL, vsync=1)
    pygame.display.set_caption("Video Crossfade with libav (PyAV)")
    glViewport(0, 0, window_size[0], window_size[1])

    version = glGetString(GL_VERSION)
    print("GL version:", version)
    print(f"Driver {pygame.display.get_driver()}")

    # Open the video files using PyAV.
    video1_data = load_video(video_playlist[video_index])
    create_texture(video1_data)

    video_index = (video_index + 1) % len(video_playlist)

    video2_data = load_video(video_playlist[video_index])
    video_index = (video_index + 1) % len(video_playlist)
    create_texture(video2_data)

    # Get video dimensions and frame rate (use video1's properties).
    fps = float(video1_data.videoStream.average_rate) if video1_data.videoStream.average_rate else 50.0

    # Create and use the shader program.
    shader = create_shader_program()
    glUseProgram(shader)
    print("Shader created")

    # Define a full-screen quad (with positions and texture coordinates).
    vertices = np.array([
        # positions    # texCoords
        -1.0,  1.0,     0.0, 0.0,
        -1.0, -1.0,     0.0, 1.0,
         1.0, -1.0,     1.0, 1.0,
         1.0,  1.0,     1.0, 0.0,
    ], dtype=np.float32)
    indices = np.array([0, 1, 2, 2, 3, 0], dtype=np.uint32)

    # Set up VAO, VBO, and EBO.
    VAO = glGenVertexArrays(1)
    VBO = glGenBuffers(1)
    EBO = glGenBuffers(1)
    glBindVertexArray(VAO)
    glBindBuffer(GL_ARRAY_BUFFER, VBO)
    glBufferData(GL_ARRAY_BUFFER, vertices.nbytes, vertices, GL_STATIC_DRAW)
    glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, EBO)
    glBufferData(GL_ELEMENT_ARRAY_BUFFER, indices.nbytes, indices, GL_STATIC_DRAW)

    print("VAO, VBO, and EBO created")
    # Vertex positions (location = 0).
    glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 4 * vertices.itemsize, ctypes.c_void_p(0))
    glEnableVertexAttribArray(0)

    # Texture coordinates (location = 1).
    glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, 4 * vertices.itemsize, ctypes.c_void_p(2 * vertices.itemsize))
    glEnableVertexAttribArray(1)
    glBindVertexArray(0)

    # Set texture uniforms in the shader.
    glUseProgram(shader)
    glUniform1i(glGetUniformLocation(shader, "tex1"), 0)
    glUniform1i(glGetUniformLocation(shader, "tex2"), 1)

    # Transition control variables.
    transitioning = False
    transition_start_time = 0
    transition_duration = 2.0  # seconds

    clock = pygame.time.Clock()
    running = True
    alpha = 0.0
    frames =0

    while running:
        # Process events.
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
                        # If already transitioning, immediately finish transition.
                        transition_start_time = time.time() - transition_duration
            elif event.type == MOUSEBUTTONDOWN:
                # Check for a double-click (Pygame 2.0+ supports the 'clicks' attribute).
                if event.button == 1 and getattr(event, 'clicks', 1) == 2:
                    pygame.display.toggle_fullscreen()


        # --- Decode and Update Textures ---
        # Handle looping logic for video1
        try:
            frame1 = next(video1_data.gen)
        except StopIteration:
            # Reset generator when video1 finishes
            video1_data.container.seek(0)
            video1_data.gen = video1_data.container.decode(video=0)
            frame1 = next(video1_data.gen)

        #frame1 = frame1.reformat(format="rgb24")
        img1 = frame1.to_ndarray()
        update_texture(video1_data, img1)

        # Handle looping logic for video2
        if transitioning:
            try:
                frame2 = next(video2_data.gen)
            except StopIteration:
                # Reset generator when video2 finishes
                video2_data.container.seek(0)
                video2_data.gen = video2_data.container.decode(video=0)
                frame2 = next(video2_data.gen)

            #frame2 = frame2.reformat(format="rgb24")
            img2 = frame2.to_ndarray()

            update_texture(video2_data, img2)

            # Determine blending alpha.
            elapsed = time.time() - transition_start_time
            alpha = min(elapsed / transition_duration, 1.0)
            if alpha >= 1.0:
                transitioning = False  # End transition

                # Swap container1 and container2
                video1_data , video2_data = video2_data, video1_data
                alpha = 0.0
                # Start loading video2 in the background
                threading.Thread(target=load_video_async, args=(video_playlist[video_index], video2_data)).start()
                print(f"Loading new video: {video_playlist[video_index]}")
                video_index = (video_index + 1) % len(video_playlist)


        if video2_data.loaded:  # Async video is ready
            print("New video loaded, creating texture...")

            # Delete old texture before creating a new one
            if video2_data.texture:
                glDeleteTextures([video2_data.texture])

            # Create a new texture now that we have the correct size
            create_texture(video2_data)

            video2_data.loaded = False  # Reset flag

        # --- Render ---
        glClear(GL_COLOR_BUFFER_BIT)
        glUseProgram(shader)
        glUniform1f(glGetUniformLocation(shader, "alpha"), alpha)

        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, video1_data.texture)
        glActiveTexture(GL_TEXTURE1)
        glBindTexture(GL_TEXTURE_2D, video2_data.texture)

        glBindVertexArray(VAO)
        glDrawElements(GL_TRIANGLES, 6, GL_UNSIGNED_INT, None)
        glBindVertexArray(0)

        pygame.display.flip()
        
        crrent_fps = clock.get_fps()
        frames += 1

        if frames > crrent_fps:
            print(f"fps = {crrent_fps:.2f}")
            frames=0

        clock.tick(fps)

    # Cleanup.
    video1_data.container.close()
    video2_data.container.close()
    pygame.quit()



if __name__ == "__main__":
    main()

