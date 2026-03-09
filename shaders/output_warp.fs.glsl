#version 300 es
precision highp float;

in vec2 vBaseUV;
in vec3 vProjTex;
out vec4 fragColor;

uniform sampler2D sceneTex;
uniform int flipY;

void main() {
    vec2 tc = vProjTex.xy / vProjTex.z;
    if (tc.x < 0.0 || tc.x > 1.0 || tc.y < 0.0 || tc.y > 1.0) {
        discard;
    }

    vec2 uv = flipY == 1 ? vec2(vBaseUV.x, 1.0 - vBaseUV.y) : vBaseUV;
    fragColor = vec4(clamp(texture(sceneTex, uv).rgb, 0.0, 1.0), 1.0);
}
