#version 300 es
precision highp float;

in vec2 vTexCoords;
out vec4 fragColor;

uniform sampler2D hdrScene;
uniform sampler2D bloomTex;
uniform float exposure;
uniform float gammaOut;
uniform float whitePoint;
uniform float bloomStrength;
uniform float sceneGammaIn;

vec3 aces_film(vec3 x) {
    const float a = 2.51;
    const float b = 0.03;
    const float c = 2.43;
    const float d = 0.59;
    const float e = 0.14;
    return clamp((x * (a * x + b)) / (x * (c * x + d) + e), 0.0, 1.0);
}

void main() {
    // Keep scene and bloom in the same texture-space orientation before the final
    // output warp stage applies its own vertical convention.
    vec2 scene_uv = vec2(vTexCoords.x, 1.0 - vTexCoords.y);
    vec2 bloom_uv = scene_uv;
    vec3 hdr = texture(hdrScene, scene_uv).rgb;
    vec3 bloom = texture(bloomTex, bloom_uv).rgb * bloomStrength;
    vec3 scene = pow(max(hdr + bloom, vec3(0.0)), vec3(max(sceneGammaIn, 1e-4)));
    vec3 scaled = scene * exposure / max(whitePoint, 1e-4);
    vec3 mapped = aces_film(scaled);
    vec3 out_rgb = pow(mapped, vec3(1.0 / max(gammaOut, 1e-4)));
    fragColor = vec4(out_rgb, 1.0);
}
