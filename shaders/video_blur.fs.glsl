#version 300 es
precision highp float;

in vec2 vBaseUV;
in vec3 vProjTex;
out vec4 fragColor;

uniform int video1Format;  // 0: RGB, 1: NV12, 2: YUVJ420p
uniform sampler2D video1RGB;
uniform sampler2D video1Y;
uniform sampler2D video1UV;  // For NV12
uniform sampler2D video1U;   // For YUVJ420p
uniform sampler2D video1V;   // For YUVJ420p

uniform int video2Format;  // 0: RGB, 1: NV12, 2: YUVJ420p
uniform sampler2D video2RGB;
uniform sampler2D video2Y;
uniform sampler2D video2UV;  // For NV12
uniform sampler2D video2U;
uniform sampler2D video2V;

uniform vec2 resolution;

uniform float alpha;          // Blending factor between video1 and video2
uniform int alphaMode;        // Use alpha as alpha or use alpha for gradient Mask progression
uniform float alphaSoftness;  // for gradient Mask
uniform float dimmer;         // Dimmer
uniform mat3 homographyMatrix;

// Uniforms for scale, position, and rotation
uniform vec2 scale;        // (scaleX, scaleY)
uniform vec2 offset;       // (offsetX, offsetY)
uniform float rotation;    // Rotation in radians
uniform float brightness;  // Range: [-1.0, 1.0]
uniform float contrast;    // Range: [0.0, 2.0] (1.0 = no change)
uniform float gamma;       // Range: [0.1, 5.0] (1.0 = no change)

uniform float blurSize;     // 64.
uniform float blurQuality;  // 5.

vec3 NV12ToRGB(float y, vec2 uv) {
    float Y = y;
    float U = uv.x - 0.5;
    float V = uv.y - 0.5;
    float r = Y + 1.402 * V;
    float g = Y - 0.344136 * U - 0.714136 * V;
    float b = Y + 1.772 * U;
    return vec3(r, g, b);
}

vec3 YUV420pToRGB(float y, float u, float v) {
    float Y = y;
    float U = u - 0.5;
    float V = v - 0.5;
    float r = Y + 1.402 * V;
    float g = Y - 0.344136 * U - 0.714136 * V;
    float b = Y + 1.772 * U;
    return vec3(r, g, b);
}

vec3 getVideo1Color(vec2 finalTexCoord) {
    if (video1Format == 0) {
        vec3 color = texture(video1RGB, finalTexCoord).rgb;
        return color;
    } else if (video1Format == 1) {
        float y = texture(video1Y, finalTexCoord).r;
        vec2 uv = texture(video1UV, finalTexCoord).rg;
        vec3 color = NV12ToRGB(y, uv);
        return color;
    } else if (video1Format == 2) {
        float y = texture(video1Y, finalTexCoord).r;
        // Since U and V textures are half size, scale texture coordinates.
        vec2 uvCoords = finalTexCoord;
        float u = texture(video1U, uvCoords).r;
        float v = texture(video1V, uvCoords).r;
        vec3 color = YUV420pToRGB(y, u, v);
        return color;
    } else {
        float y = texture(video1Y, finalTexCoord).r;
        return vec3(y, y, y);
    }
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
        vec2 uvCoords = finalTexCoord;
        float u = texture(video2U, uvCoords).r;
        float v = texture(video2V, uvCoords).r;
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

    // ---- 3. Perspective correction (per-pixel) ----
    vec2 tc = vProjTex.xy / vProjTex.z;
    if (tc.x < 0.0 || tc.x > 1.0 || tc.y < 0.0 || tc.y > 1.0)
        discard;

    // ---- 1. Content transform (scale / offset / rotation) ----
    vec2 centered = (vBaseUV - 0.5) * scale;
    float c = cos(rotation);
    float s = sin(rotation);
    mat2 rotM = mat2(c, -s, s, c);
    vec2 rotated = rotM * centered;
    vec2 videoTC = rotated + 0.5 + offset;

    // Lens blur
    vec2 ar = resolution.xy / resolution.yy;
    float blurShape = .4;
    float blurSamples = blurSize * blurQuality;
    float blurDist = blurSize / (pow(blurSamples - 1., blurShape) * resolution.x);

    vec3 color1 = vec3(0.);  // getVideo1Color(videoTC);
    if (blurSamples >= 1.) {
        for (float i = 0.; i < blurSamples; i += 1.) {
            // Spiral sampling
            float t = i * 1.6869;
            float r = pow(i, blurShape) * blurDist;
            vec2 o = videoTC + vec2(cos(t), sin(t)) * r / ar;

            vec3 samp = getVideo1Color(o);
            color1 += samp;
            // Lazy inefficient masking
            /*if (samp.a < .5)
            {
                col += samp.rgb;
                nAccumulated += 1.;
            } else if (i == 0.)
            {
                col += samp.rgb;
                nAccumulated += 1.;
                break;
            }*/
            // col += vec3(smoothstep(.004, .003, length((uv - o)*ar)));
        }
        color1 /= blurSamples;
    } else {
        color1 = getVideo1Color(videoTC);
    }

    vec4 color;
    switch (alphaMode) {
        default:
        case 0:  // Alpha
            color = vec4(color1, alpha);
            break;
        case 1:  // Video 1 Alpha
            // TODO: Implement
            color = vec4(color1, alpha);
            break;
        case 2:  // Video 2 Red -> Alpha
        {
            float mask = getVideo2MaskValue(videoTC);
            color = vec4(color1, mask * alpha);
            break;
        }
        case 3:  // Wipe
        {
            float mask = getVideo2MaskValue(videoTC);
            float softness = max(alphaSoftness, 1e-4);
            float compensatedAlpha = mix(-0.5 * softness, 1.0 + 0.5 * softness, alpha);
            float newAlpha = clamp((compensatedAlpha - mask) / softness + 0.5, 0.0, 1.0);
            color = vec4(color1, newAlpha);
            break;
        }
    }

    // Apply brightness
    color.rgb *= brightness;

    // Apply contrast
    color.rgb = (color.rgb - 0.5) * contrast + 0.5;

    // Apply gamma correction
    color.rgb = pow(color.rgb, vec3(1.0 / gamma));

    // Ensure color stays in valid range
    fragColor = vec4(clamp(color.rgb, 0.0, 1.0), color.a * dimmer);
}
