#version 300 es
precision highp float;

layout(location = 0) in vec2 position;
layout(location = 1) in vec2 texCoords;
out vec2 vTexCoords;

void main() {
    // position is in 0..1, convert to clip space
    // x: 0..1 -> -1..1
    float x = position.x * 2.0 - 1.0;
    // y: 0..1 (top->bottom) -> 1..-1
    float y = 1.0 - position.y * 2.0;

    gl_Position = vec4(x, y, 0.0, 1.0);
    vTexCoords = texCoords;
}
