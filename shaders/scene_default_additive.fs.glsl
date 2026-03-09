#version 300 es
#pragma blend SRC_ALPHA ONE
precision highp float;

in vec2 vBaseUV;
out vec4 fragColor;

uniform int video1Format;
uniform sampler2D video1RGB;
uniform sampler2D video1Y;
uniform sampler2D video1UV;
uniform sampler2D video1U;
uniform sampler2D video1V;

uniform int video2Format;
uniform sampler2D video2RGB;
uniform sampler2D video2Y;
uniform sampler2D video2UV;
uniform sampler2D video2U;
uniform sampler2D video2V;

uniform float alpha;
uniform int alphaMode;
uniform float alphaSoftness;
uniform float dimmer;
uniform vec2 scale;
uniform vec2 offset;
uniform float rotation;
uniform float brightness;
uniform float contrast;
uniform float gamma;
uniform vec3 dmxColor;

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

vec3 getVideo1Color(vec2 finalTexCoord) {
    if (video1Format == 0) {
        return texture(video1RGB, finalTexCoord).rgb;
    } else if (video1Format == 1) {
        float y = texture(video1Y, finalTexCoord).r;
        vec2 uv = texture(video1UV, finalTexCoord).rg;
        return NV12ToRGB(y, uv);
    } else if (video1Format == 2) {
        float y = texture(video1Y, finalTexCoord).r;
        float u = texture(video1U, finalTexCoord).r;
        float v = texture(video1V, finalTexCoord).r;
        return YUV420pToRGB(y, u, v);
    }

    float y = texture(video1Y, finalTexCoord).r;
    return vec3(y, y, y);
}

vec3 getVideo2Color(vec2 finalTexCoord) {
    if (video2Format == 0) {
        return texture(video2RGB, finalTexCoord).rgb;
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

    float y = texture(video2Y, finalTexCoord).r;
    return vec3(y, y, y);
}

void main() {
    vec2 centered = (vBaseUV - 0.5) * scale;
    float c = cos(rotation);
    float s = sin(rotation);
    vec2 videoTC = mat2(c, -s, s, c) * centered + 0.5 + offset;

    vec3 color1 = getVideo1Color(videoTC);
    vec4 color;
    switch (alphaMode) {
        default:
        case 0:
            color = vec4(color1, alpha);
            break;
        case 1:
            color = vec4(color1, alpha);
            break;
        case 2: {
            vec3 color2 = getVideo2Color(videoTC);
            color = vec4(color1, color2.r * alpha);
            break;
        }
        case 3: {
            vec3 color2 = getVideo2Color(videoTC);
            float newAlpha = smoothstep(color2.r, color2.r + alphaSoftness, alpha * (1.0 + alphaSoftness));
            color = vec4(color1, newAlpha);
            break;
        }
    }

    color.rgb *= dmxColor;
    color.rgb *= brightness;
    color.rgb = (color.rgb - 0.5) * contrast + 0.5;
    color.rgb = pow(color.rgb, vec3(1.0 / gamma));

    fragColor = vec4(max(color.rgb, vec3(0.0)), color.a * dimmer);
}
