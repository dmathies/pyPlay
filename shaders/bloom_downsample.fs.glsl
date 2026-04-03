#version 300 es
precision highp float;

in vec2 vTexCoords;
out vec4 fragColor;

uniform sampler2D sourceTex;
uniform vec2 sourceTexelSize;

void main() {
    vec2 uv = vTexCoords;
    vec2 x = vec2(sourceTexelSize.x, 0.0);
    vec2 y = vec2(0.0, sourceTexelSize.y);

    vec3 center = texture(sourceTex, uv).rgb * 0.25;
    vec3 cross =
        texture(sourceTex, uv + x).rgb +
        texture(sourceTex, uv - x).rgb +
        texture(sourceTex, uv + y).rgb +
        texture(sourceTex, uv - y).rgb;
    vec3 corners =
        texture(sourceTex, uv + x + y).rgb +
        texture(sourceTex, uv + x - y).rgb +
        texture(sourceTex, uv - x + y).rgb +
        texture(sourceTex, uv - x - y).rgb;

    vec3 result = center + cross * 0.125 + corners * 0.0625;
    fragColor = vec4(result, 1.0);
}
