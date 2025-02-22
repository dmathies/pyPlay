import pygame
from pygame.locals import DOUBLEBUF, OPENGL
import numpy as np
import ctypes

def main():
    pygame.init()
    # Set OpenGL context attributes before creating the window:
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE)
    
    window_size = (800, 600)
    pygame.display.set_mode(window_size, DOUBLEBUF | OPENGL)
    pygame.display.set_caption("Minimal OpenGL Test")
    pygame.display.flip()
    
    # Now import OpenGL after the context is created:
    import OpenGL.GL as GL
    
    # Verify the context:
    version = GL.glGetString(GL.GL_VERSION)
    print("OpenGL version:", version)
    GL.glViewport(0, 0, window_size[0], window_size[1])
    
    # Define vertex data:
    vertices = np.array([
        -1.0,  1.0, 0.0, 1.0,
        -1.0, -1.0, 0.0, 0.0,
         1.0, -1.0, 1.0, 0.0,
         1.0,  1.0, 1.0, 1.0,
    ], dtype=np.float32)
    
    # Create and bind a VAO:
    VAO = GL.glGenVertexArrays(1)
    GL.glBindVertexArray(VAO)
    
    # Create a VBO and upload the vertex data:
    VBO = GL.glGenBuffers(1)
    GL.glBindBuffer(GL.GL_ARRAY_BUFFER, VBO)
    GL.glBufferData(GL.GL_ARRAY_BUFFER, vertices.nbytes, vertices, GL.GL_STATIC_DRAW)
    
    # Instead of using: 4 * vertices.itemsize and 2 * vertices.itemsize,
    # use literal values:
    stride = 16  # 4 floats * 4 bytes per float
    offset0 = ctypes.c_void_p(0)
    offset1 = ctypes.c_void_p(8)  # 2 floats * 4 bytes per float

    GL.glVertexAttribPointer(0, 2, GL.GL_FLOAT, GL.GL_FALSE, stride, offset0)
    GL.glEnableVertexAttribArray(0)
    GL.glVertexAttribPointer(1, 2, GL.GL_FLOAT, GL.GL_FALSE, stride, offset1)
    GL.glEnableVertexAttribArray(1)
    
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
        
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)
        GL.glBindVertexArray(VAO)
        GL.glDrawArrays(GL.GL_TRIANGLE_FAN, 0, 4)
        pygame.display.flip()
    
    pygame.quit()

if __name__ == '__main__':
    main()

