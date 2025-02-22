import os
# Force SDL2 to use EGL instead of GLX on X11.
os.environ["SDL_VIDEO_X11_FORCE_EGL"] = "1"

import pygame
from pygame.locals import DOUBLEBUF, OPENGL, KEYDOWN, K_ESCAPE, QUIT
import numpy as np
import ctypes
from OpenGL.GL import *
from OpenGL.GL.shaders import compileProgram, compileShader

def main():
    pygame.init()
    
    # Request an OpenGL ES 3.0 context.
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 0)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_ES)
    
    window_size = (640, 480)
    pygame.display.set_mode(window_size, DOUBLEBUF | OPENGL)
    pygame.display.set_caption("OpenGL ES with PyGame on Pi")
    
    # Print GL version info.
    version = glGetString(GL_VERSION)
    print("GL version:", version)
    
    # Define shaders (using OpenGL ES 3.0).
    vertex_shader = """
    #version 300 es
    layout(location = 0) in vec2 pos;
    void main() {
        gl_Position = vec4(pos, 0.0, 1.0);
    }
    """
    
    fragment_shader = """
    #version 300 es
    precision mediump float;
    out vec4 fragColor;
    void main() {
        fragColor = vec4(0.0, 0.7, 1.0, 1.0);
    }
    """
    
    # Compile shaders and create program.
    shader = compileProgram(
        compileShader(vertex_shader, GL_VERTEX_SHADER),
        compileShader(fragment_shader, GL_FRAGMENT_SHADER)
    )
    
    # Define a quad as a triangle strip.
    vertices = np.array([
        -0.5, -0.5,  # Bottom-left
         0.5, -0.5,  # Bottom-right
        -0.5,  0.5,  # Top-left
         0.5,  0.5   # Top-right
    ], dtype=np.float32)
    
    # Generate and bind a Vertex Buffer Object.
    VBO = glGenBuffers(1)
    glBindBuffer(GL_ARRAY_BUFFER, VBO)
    glBufferData(GL_ARRAY_BUFFER, vertices.nbytes, vertices, GL_STATIC_DRAW)
    
    # Use ctypes.c_void_p(0) for the offset.
    glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 0, ctypes.c_void_p(0))
    glEnableVertexAttribArray(0)
    
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == QUIT:
                running = False
            elif event.type == KEYDOWN and event.key == K_ESCAPE:
                running = False
        
        glClearColor(0.1, 0.1, 0.1, 1.0)
        glClear(GL_COLOR_BUFFER_BIT)
        
        glUseProgram(shader)
        glDrawArrays(GL_TRIANGLE_STRIP, 0, 4)
        
        pygame.display.flip()
        pygame.time.wait(10)
    
    glDeleteBuffers(1, [VBO])
    glDeleteProgram(shader)
    pygame.quit()

if __name__ == '__main__':
    main()

