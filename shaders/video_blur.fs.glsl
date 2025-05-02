#version 300 es
precision highp float;
in vec2 vTexCoords;
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
    if (video2Format == 0) {
        return texture(video2RGB, finalTexCoord).rgb;
    } else if (video2Format == 1) {
        float y = texture(video2Y, finalTexCoord).r;
        vec2 uv = texture(video2UV, finalTexCoord).rg;
        return NV12ToRGB(y, uv);
    } else if (video2Format == 2) {
        float y = texture(video2Y, finalTexCoord).r;
        vec2 uvCoords = finalTexCoord;
        float u = texture(video2U, uvCoords).r;
        float v = texture(video2V, uvCoords).r;
        return YUV420pToRGB(y, u, v);
    } else {
        float y = texture(video2Y, finalTexCoord).r;
        return vec3(y, y, y);
    }
}

void main() {
    vec2 centeredCoord = (vTexCoords - 0.5) * scale;

    // Apply rotation matrix
    float cosA = cos(rotation);
    float sinA = sin(rotation);
    mat2 rotationMatrix = mat2(cosA, -sinA, sinA, cosA);

    vec2 rotatedCoord = rotationMatrix * centeredCoord;

    // Move back to original texture space and apply offset
    vec2 newTexCoord = rotatedCoord + 0.5 + offset;

    vec3 warpedTexCoord = homographyMatrix * vec3(newTexCoord, 1.0);
    vec2 finalTexCoord = warpedTexCoord.xy / warpedTexCoord.z;

    // Lens blur
    vec2 ar = resolution.xy / resolution.yy;
    float blurShape = .4;
    float blurSamples = blurSize * blurQuality;
    float blurDist = blurSize / (pow(blurSamples - 1., blurShape) * resolution.x);

    vec3 color1 = vec3(0.);  // getVideo1Color(finalTexCoord);
    if (blurSamples >= 1.) {
        for (float i = 0.; i < blurSamples; i += 1.) {
            // Spiral sampling
            float t = i * 1.6869;
            float r = pow(i, blurShape) * blurDist;
            vec2 o = finalTexCoord + vec2(cos(t), sin(t)) * r / ar;

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
        color1 = getVideo1Color(finalTexCoord);
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
            vec3 color2 = getVideo2Color(finalTexCoord);
            color = vec4(color1, color2.r * alpha);
            break;
        }
        case 3:  // Wipe
        {
            vec3 color2 = getVideo2Color(finalTexCoord);
            float newAlpha = smoothstep(color2.r, color2.r + alphaSoftness, alpha * (1. + alphaSoftness));
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
