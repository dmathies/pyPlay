#version 300 es
precision highp float;

layout(location = 0) in vec2 position;
layout(location = 1) in vec2 texCoords;

uniform mat3 homographyMatrix;

out vec2 vBaseUV;
out vec3 vProjTex;

void main() {
    vBaseUV = texCoords;

    mat3 H = homographyMatrix;
    float det = H[0][0] * (H[1][1] * H[2][2] - H[1][2] * H[2][1])
              - H[0][1] * (H[1][0] * H[2][2] - H[1][2] * H[2][0])
              + H[0][2] * (H[1][0] * H[2][1] - H[1][1] * H[2][0]);

    mat3 invH = mat3(1.0);
    if (abs(det) > 1e-8) {
        invH = mat3(
            (H[1][1] * H[2][2] - H[1][2] * H[2][1]) / det,
            (H[0][2] * H[2][1] - H[0][1] * H[2][2]) / det,
            (H[0][1] * H[1][2] - H[0][2] * H[1][1]) / det,

            (H[1][2] * H[2][0] - H[1][0] * H[2][2]) / det,
            (H[0][0] * H[2][2] - H[0][2] * H[2][0]) / det,
            (H[0][2] * H[1][0] - H[0][0] * H[1][2]) / det,

            (H[1][0] * H[2][1] - H[1][1] * H[2][0]) / det,
            (H[0][1] * H[2][0] - H[0][0] * H[2][1]) / det,
            (H[0][0] * H[1][1] - H[0][1] * H[1][0]) / det
        );
    }

    vec3 warped = invH * vec3(position, 1.0);
    vec2 uv = warped.xy / warped.z;

    float x = uv.x * 2.0 - 1.0;
    float y = 1.0 - uv.y * 2.0;

    gl_Position = vec4(x, y, 0.0, 1.0);
    vProjTex = invH * vec3(texCoords, 1.0);
}
