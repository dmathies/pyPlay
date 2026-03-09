#version 300 es
precision highp float;

in vec2 vTexCoords;
out vec4 fragColor;

uniform sampler2D hdrScene;
uniform float threshold;
uniform float sceneGammaIn;

void main() {
    vec2 uv = vec2(vTexCoords.x, 1.0 - vTexCoords.y);
    vec3 hdr = texture(hdrScene, uv).rgb;
    vec3 scene = pow(max(hdr, vec3(0.0)), vec3(max(sceneGammaIn, 1e-4)));
    vec3 bright = max(scene - vec3(threshold), vec3(0.0));
    fragColor = vec4(bright, 1.0);
}
