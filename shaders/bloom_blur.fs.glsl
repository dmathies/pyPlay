#version 300 es
precision highp float;

in vec2 vTexCoords;
out vec4 fragColor;

uniform sampler2D image;
uniform int horizontal;
uniform vec2 texelSize;

void main() {
    vec2 uv = vTexCoords;
    vec2 dir = (horizontal == 1) ? vec2(texelSize.x, 0.0) : vec2(0.0, texelSize.y);

    vec3 result = texture(image, uv).rgb * 0.227027;
    result += texture(image, uv + dir * 1.384615).rgb * 0.316216;
    result += texture(image, uv - dir * 1.384615).rgb * 0.316216;
    result += texture(image, uv + dir * 3.230769).rgb * 0.070270;
    result += texture(image, uv - dir * 3.230769).rgb * 0.070270;

    fragColor = vec4(result, 1.0);
}
