#version 300 es
precision highp float;
in vec2 vTexCoords;
out vec4 fragColor;

uniform int video1Format;  // 0: RGB, 1: NV12, 2: YUVJ420p
uniform int video1ColourSpace;  // 0: RGB, 1: bt601, 2: bt709
uniform sampler2D video1RGB;
uniform sampler2D video1Y;
uniform sampler2D video1UV;  // For NV12
uniform sampler2D video1U;   // For YUVJ420p
uniform sampler2D video1V;   // For YUVJ420p

vec3 BT601ToRGB(vec3 yuv) {
    float Y = (yuv.x - 16.0 / 255.0) * (255.0 / (235.0 - 16.0));
    float U = yuv.y - 0.5;
    float V = yuv.z - 0.5;
    float r = Y + 1.402 * V;
    float g = Y - 0.344136 * U - 0.714136 * V;
    float b = Y + 1.772 * U;
    return vec3(r, g, b);
}

vec3 BT709ToRGB(vec3 yuv) {
    float Y = yuv.x;
    float U = yuv.y - 0.5;
    float V = yuv.z - 0.5;
    float r = Y + 1.402 * V;
    float g = Y - 0.344136 * U - 0.714136 * V;
    float b = Y + 1.772 * U;
    return vec3(r, g, b);
}

vec3 getVideo1Color(vec2 finalTexCoord) {
    vec3 col;
    if (video1Format == 0) {
        col = texture(video1RGB, finalTexCoord).rgb;
    } else if (video1Format == 1) {
        float y = texture(video1Y, finalTexCoord).r;
        vec2 uv = texture(video1UV, finalTexCoord).rg;
        col = vec3(y, uv);
    } else if (video1Format == 2) {
        float y = texture(video1Y, finalTexCoord).r;
        vec2 uvCoords = finalTexCoord;
        float u = texture(video1U, uvCoords).r;
        float v = texture(video1V, uvCoords).r;
        col = vec3(y, u, v);
    } else {
        float y = texture(video1Y, finalTexCoord).r;
        col = vec3(y);
    }

    switch (video1ColourSpace) {
        default:
        case 0: // RGB
        return col;
        case 1: // BT601
        return BT601ToRGB(col);
        case 2: // BT709
        return BT709ToRGB(col);
    }
    return col;
}

void main() {
    vec3 color = getVideo1Color(vTexCoords);
    fragColor = vec4(clamp(color, 0.0, 1.0), 1.0);
}
