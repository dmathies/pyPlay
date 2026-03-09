#version 300 es
precision highp float;

out vec4 fragColor;

uniform vec3 gridColor;   // e.g., red for left, green for right
uniform float opacity;    // e.g., 0.7

void main() {

    fragColor = vec4(gridColor, opacity);
}
