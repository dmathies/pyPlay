#version 300 es
precision highp float;

in vec2 vTexCoords;
out vec4 fragColor;

uniform sampler2D baseTex;
uniform sampler2D lowTex;
uniform vec2 baseTexelSize;
uniform vec2 lowTexelSize;
uniform float baseWeight;

vec3 tentSample(sampler2D tex, vec2 uv, vec2 texelSize) {
    vec2 x = vec2(texelSize.x, 0.0);
    vec2 y = vec2(0.0, texelSize.y);

    vec3 result = texture(tex, uv).rgb * 4.0;
    result += texture(tex, uv + x).rgb * 2.0;
    result += texture(tex, uv - x).rgb * 2.0;
    result += texture(tex, uv + y).rgb * 2.0;
    result += texture(tex, uv - y).rgb * 2.0;
    result += texture(tex, uv + x + y).rgb;
    result += texture(tex, uv + x - y).rgb;
    result += texture(tex, uv - x + y).rgb;
    result += texture(tex, uv - x - y).rgb;
    return result / 16.0;
}

void main() {
    vec2 uv = vTexCoords;
    vec3 base = tentSample(baseTex, uv, baseTexelSize) * baseWeight;
    vec3 low = tentSample(lowTex, uv, lowTexelSize);
    fragColor = vec4(base + low, 1.0);
}
