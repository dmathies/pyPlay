#version 300 es
#pragma blend ONE ZERO
precision highp float;
in vec2 vBaseUV;
out vec4 fragColor;

uniform int video2Format;
uniform sampler2D video2RGB;
uniform sampler2D video2Y;
uniform sampler2D video2UV;
uniform sampler2D video2U;
uniform sampler2D video2V;

uniform vec2 scale;
uniform vec2 offset;
uniform float rotation;

vec3 NV12ToRGB(float y, vec2 uv) {
    float Y = y;
    float U = uv.x - 0.5;
    float V = uv.y - 0.5;
    return vec3(
        Y + 1.402 * V,
        Y - 0.344136 * U - 0.714136 * V,
        Y + 1.772 * U
    );
}

vec3 YUV420pToRGB(float y, float u, float v) {
    float Y = y;
    float U = u - 0.5;
    float V = v - 0.5;
    return vec3(
        Y + 1.402 * V,
        Y - 0.344136 * U - 0.714136 * V,
        Y + 1.772 * U
    );
}

vec3 getVideo2Color(vec2 finalTexCoord) {
    if (video2Format == 0) {
        ivec2 size = textureSize(video2RGB, 0);
        ivec2 texel = ivec2(
            clamp(int(finalTexCoord.x * float(size.x)), 0, size.x - 1),
            clamp(int(finalTexCoord.y * float(size.y)), 0, size.y - 1)
        );
        return texelFetch(video2RGB, texel, 0).rgb;
    } else if (video2Format == 1) {
        float y = texture(video2Y, finalTexCoord).r;
        vec2 uv = texture(video2UV, finalTexCoord).rg;
        return NV12ToRGB(y, uv);
    } else if (video2Format == 2) {
        float y = texture(video2Y, finalTexCoord).r;
        float u = texture(video2U, finalTexCoord).r;
        float v = texture(video2V, finalTexCoord).r;
        return YUV420pToRGB(y, u, v);
    }

    ivec2 size = textureSize(video2Y, 0);
    ivec2 texel = ivec2(
        clamp(int(finalTexCoord.x * float(size.x)), 0, size.x - 1),
        clamp(int(finalTexCoord.y * float(size.y)), 0, size.y - 1)
    );
    float y = texelFetch(video2Y, texel, 0).r;
    return vec3(y, y, y);
}

void main() {
    vec2 centered = (vBaseUV - 0.5) * scale;
    float c = cos(rotation);
    float s = sin(rotation);
    vec2 videoTC = mat2(c, -s, s, c) * centered + 0.5 + offset;

    float groupSample = getVideo2Color(videoTC).r;
    int groupIndex = clamp(int(floor(groupSample * 255.0 + 0.5)), 0, 127);
    float normalized = float(groupIndex) / 127.0;
    fragColor = vec4(vec3(normalized), 1.0);
}
