#version 300 es
precision highp float;

in vec2 vTexCoords;
out vec4 fragColor;

uniform sampler2D hdrScene;
uniform float threshold;
uniform float knee;

vec3 prefilterSample(vec2 uv) {
    vec2 texel = vec2(1.0) / vec2(textureSize(hdrScene, 0));
    vec2 x = vec2(texel.x, 0.0);
    vec2 y = vec2(0.0, texel.y);

    vec3 center = texture(hdrScene, uv).rgb * 0.125;

    vec3 ring1 =
        texture(hdrScene, uv + x).rgb +
        texture(hdrScene, uv - x).rgb +
        texture(hdrScene, uv + y).rgb +
        texture(hdrScene, uv - y).rgb;

    vec3 ring2 =
        texture(hdrScene, uv + x + y).rgb +
        texture(hdrScene, uv + x - y).rgb +
        texture(hdrScene, uv - x + y).rgb +
        texture(hdrScene, uv - x - y).rgb;

    vec3 ring3 =
        texture(hdrScene, uv + x * 2.0).rgb +
        texture(hdrScene, uv - x * 2.0).rgb +
        texture(hdrScene, uv + y * 2.0).rgb +
        texture(hdrScene, uv - y * 2.0).rgb;

    return center + ring1 * 0.09375 + ring2 * 0.0625 + ring3 * 0.03125;
}

void main() {
    vec2 uv = vec2(vTexCoords.x, 1.0 - vTexCoords.y);
    vec3 hdr = prefilterSample(uv);
    float kneeClamped = max(knee, 1e-5);
    vec3 soft = clamp(hdr - vec3(threshold - kneeClamped), vec3(0.0), vec3(2.0 * kneeClamped));
    soft = (soft * soft) / vec3(4.0 * kneeClamped + 1e-5);
    vec3 bright = max(soft, hdr - vec3(threshold));
    fragColor = vec4(bright, 1.0);
}
