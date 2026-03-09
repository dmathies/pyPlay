#version 300 es
precision highp float;

in vec2 vTexCoords;
out vec4 fragColor;

uniform sampler2D overlayTex;

void main() {
    vec4 color = texture(overlayTex, vTexCoords);
    fragColor = color;
}
