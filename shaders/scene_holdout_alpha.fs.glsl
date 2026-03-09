#version 300 es
#pragma blend ZERO ONE_MINUS_SRC_ALPHA
precision highp float;

in vec2 vBaseUV;
out vec4 fragColor;

uniform int video1Format;
uniform sampler2D video1RGB;
uniform sampler2D video1Y;
uniform sampler2D video1UV;
uniform sampler2D video1U;
uniform sampler2D video1V;

uniform float alpha;
uniform vec2 scale;
uniform vec2 offset;

vec4 NV12ToRGBA(float y, vec2 uv) {
    float Y = y;
    float U = uv.x - 0.5;
    float V = uv.y - 0.5;
    return vec4(
        Y + 1.402 * V,
        Y - 0.344136 * U - 0.714136 * V,
        Y + 1.772 * U,
        1.0
    );
}

vec4 YUV420pToRGBA(float y, float u, float v) {
    float Y = y;
    float U = u - 0.5;
    float V = v - 0.5;
    return vec4(
        Y + 1.402 * V,
        Y - 0.344136 * U - 0.714136 * V,
        Y + 1.772 * U,
        1.0
    );
}

vec4 getVideo1Sample(vec2 finalTexCoord) {
    if (video1Format == 0) {
        return texture(video1RGB, finalTexCoord);
    } else if (video1Format == 1) {
        float y = texture(video1Y, finalTexCoord).r;
        vec2 uv = texture(video1UV, finalTexCoord).rg;
        return NV12ToRGBA(y, uv);
    } else if (video1Format == 2) {
        float y = texture(video1Y, finalTexCoord).r;
        float u = texture(video1U, finalTexCoord).r;
        float v = texture(video1V, finalTexCoord).r;
        return YUV420pToRGBA(y, u, v);
    }

    float y = texture(video1Y, finalTexCoord).r;
    return vec4(y, y, y, 1.0);
}

void main() {
    vec2 videoTC = (vBaseUV - 0.5) * scale + 0.5 + offset;
    vec4 srcSample = getVideo1Sample(videoTC);
    fragColor = vec4(0.0, 0.0, 0.0, clamp(srcSample.a * alpha, 0.0, 1.0));
}
