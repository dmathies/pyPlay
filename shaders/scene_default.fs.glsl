#version 300 es
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
uniform int video1Linear;  // 1 = already linear (EXR/HDR), 0 = sRGB gamma-encoded

vec3 sRGBToLinear(vec3 c) {
    return pow(max(c, vec3(0.0)), vec3(2.2));
}

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

vec4 getVideo1Sample(vec2 finalTexCoord) {
    vec4 sampleColor;
    if (video1Format == 0) {
        sampleColor = texture(video1RGB, finalTexCoord);
    } else if (video1Format == 1) {
        float y = texture(video1Y, finalTexCoord).r;
        vec2 uv = texture(video1UV, finalTexCoord).rg;
        sampleColor = vec4(NV12ToRGB(y, uv), 1.0);
    } else if (video1Format == 2) {
        float y = texture(video1Y, finalTexCoord).r;
        float u = texture(video1U, finalTexCoord).r;
        float v = texture(video1V, finalTexCoord).r;
        sampleColor = vec4(YUV420pToRGB(y, u, v), 1.0);
    } else {
        float y = texture(video1Y, finalTexCoord).r;
        sampleColor = vec4(y, y, y, 1.0);
    }
    if (video1Linear == 0) sampleColor.rgb = sRGBToLinear(sampleColor.rgb);
    return sampleColor;
}

vec3 getVideo2Color(vec2 finalTexCoord) {
    vec3 color;
    if (video2Format == 0) {
        color = texture(video2RGB, finalTexCoord).rgb;
    } else if (video2Format == 1) {
        float y = texture(video2Y, finalTexCoord).r;
        vec2 uv = texture(video2UV, finalTexCoord).rg;
        color = NV12ToRGB(y, uv);
    } else if (video2Format == 2) {
        float y = texture(video2Y, finalTexCoord).r;
        float u = texture(video2U, finalTexCoord).r;
        float v = texture(video2V, finalTexCoord).r;
        color = YUV420pToRGB(y, u, v);
    } else {
        float y = texture(video2Y, finalTexCoord).r;
        color = vec3(y, y, y);
    }
    if (video1Linear == 0) color = sRGBToLinear(color);
    return color;
}

float getVideo2MaskValue(vec2 finalTexCoord) {
    if (video2Format == 0) {
        return texture(video2RGB, finalTexCoord).r;
    } else if (video2Format == 1) {
        return texture(video2Y, finalTexCoord).r;
    } else if (video2Format == 2) {
        return texture(video2Y, finalTexCoord).r;
    }
    return texture(video2Y, finalTexCoord).r;
}

void main() {
    vec2 centered = (vBaseUV - 0.5) * scale;
    float c = cos(rotation);
    float s = sin(rotation);
    vec2 videoTC = mat2(c, -s, s, c) * centered + 0.5 + offset;

    vec4 sample1 = getVideo1Sample(videoTC);
    vec3 color1 = sample1.rgb;
    vec4 color;
    switch (alphaMode) {
        default:
        case 0:
            color = vec4(color1, alpha);
            break;
        case 1:
            color = vec4(color1, sample1.a * alpha);
            break;
        case 2: {
            float mask = getVideo2MaskValue(videoTC);
            color = vec4(color1, mask * alpha);
            break;
        }
        case 3: {
            float mask = getVideo2MaskValue(videoTC);
            float softness = max(alphaSoftness, 1e-4);
            float compensatedAlpha = mix(-0.5 * softness, 1.0 + 0.5 * softness, alpha);
            float newAlpha = clamp((compensatedAlpha - mask) / softness + 0.5, 0.0, 1.0);
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
