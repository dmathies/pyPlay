#version 300 es
#pragma blend SRC_ALPHA ONE
precision highp float;
in vec2 vBaseUV;
in vec3 vProjTex;
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

uniform sampler2D dmxLookup;
uniform int dmxGroupMapEnabled;

uniform float alpha;
uniform int alphaMode;
uniform float alphaSoftness;
uniform float dimmer;
uniform mat3 homographyMatrix;
uniform vec2 scale;
uniform vec2 offset;
uniform float rotation;
uniform float brightness;
uniform float contrast;
uniform float gamma;
uniform vec3 dmxColor;
uniform int video1Linear;
uniform int tungstenStart;
uniform float tungstenIntensity;

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

vec3 getVideo1Color(vec2 finalTexCoord) {
    vec3 color;
    if (video1Format == 0) {
        color = texture(video1RGB, finalTexCoord).rgb;
    } else if (video1Format == 1) {
        float y = texture(video1Y, finalTexCoord).r;
        vec2 uv = texture(video1UV, finalTexCoord).rg;
        color = NV12ToRGB(y, uv);
    } else if (video1Format == 2) {
        float y = texture(video1Y, finalTexCoord).r;
        float u = texture(video1U, finalTexCoord).r;
        float v = texture(video1V, finalTexCoord).r;
        color = YUV420pToRGB(y, u, v);
    } else {
        color = vec3(texture(video1Y, finalTexCoord).r);
    }
    if (video1Linear == 0) color = sRGBToLinear(color);
    return color;
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

int getDmxGroupIndex(vec2 finalTexCoord) {
    float groupSample = getVideo2Color(finalTexCoord).r;
    return clamp(int(floor(groupSample * 255.0 + 0.5)), 0, 127);
}

vec4 getDmxGroupRGBA(vec2 finalTexCoord) {
    if (dmxGroupMapEnabled == 0) {
        return vec4(dmxColor, 1.0);
    }

    int groupIndex = getDmxGroupIndex(finalTexCoord);
    return texelFetch(dmxLookup, ivec2(groupIndex, 0), 0);
}

vec3 applyTungstenDimShift(vec3 rgb, float level, int groupIndex) {
    if (groupIndex < clamp(tungstenStart, 0, 127)) {
        return rgb;
    }

    float warmFactor = pow(clamp(1.0 - level, 0.0, 1.0), 1.3);
    float intensity = clamp(tungstenIntensity / 255.0, 0.0, 1.0);
    float tintAmount = warmFactor * intensity;
    vec3 tungstenTint = mix(vec3(1.0), vec3(1.0, 0.58, 0.18), tintAmount);
    return rgb * tungstenTint;
}

void main() {
    vec2 tc = vProjTex.xy / vProjTex.z;
    if (tc.x < 0.0 || tc.x > 1.0 || tc.y < 0.0 || tc.y > 1.0) {
        discard;
    }

    vec2 centered = (vBaseUV - 0.5) * scale;
    float c = cos(rotation);
    float s = sin(rotation);
    mat2 rotM = mat2(c, -s, s, c);
    vec2 rotated = rotM * centered;
    vec2 videoTC = rotated + 0.5 + offset;

    vec3 plateColor = getVideo1Color(videoTC);
    int groupIndex = dmxGroupMapEnabled == 0 ? 0 : getDmxGroupIndex(videoTC);
    vec4 dmxGroup = getDmxGroupRGBA(videoTC);
    vec3 dmxRgb = applyTungstenDimShift(dmxGroup.rgb, dmxGroup.a, groupIndex);
    float dmxAlpha = dmxGroup.a;

    vec3 color = plateColor * dmxRgb;
    color *= brightness;
    color = (color - 0.5) * contrast + 0.5;
    color = pow(color, vec3(1.0 / gamma));

    fragColor = vec4(max(color, vec3(0.0)), alpha * dimmer * dmxAlpha);
}
