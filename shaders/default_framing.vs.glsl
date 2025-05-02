#version 300 es
precision highp float;

layout(location = 0) in vec2 position;
layout(location = 1) in vec2 texCoords;
out vec2 vTexCoords;

void main() {
    gl_Position = vec4(position.xy, 0.0, 1.0);
    vTexCoords = texCoords;
}
