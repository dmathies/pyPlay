#version 300 es
precision highp float;

layout(location = 0) in vec2 position;   // 0..1 mesh positions
layout(location = 1) in vec2 texCoords;  // 0..1 UVs – base for homography

uniform mat3 homographyMatrix;

void main() {

    mat3 H = homographyMatrix;
    float det = H[0][0]*(H[1][1]*H[2][2] - H[1][2]*H[2][1])
            - H[0][1]*(H[1][0]*H[2][2] - H[1][2]*H[2][0])
            + H[0][2]*(H[1][0]*H[2][1] - H[1][1]*H[2][0]);

    mat3 invH = mat3(1.0);
    if (abs(det) > 1e-8) {
        invH = mat3(
            (H[1][1]*H[2][2] - H[1][2]*H[2][1]) / det,
            (H[0][2]*H[2][1] - H[0][1]*H[2][2]) / det,
            (H[0][1]*H[1][2] - H[0][2]*H[1][1]) / det,

            (H[1][2]*H[2][0] - H[1][0]*H[2][2]) / det,
            (H[0][0]*H[2][2] - H[0][2]*H[2][0]) / det,
            (H[0][2]*H[1][0] - H[0][0]*H[1][2]) / det,

            (H[1][0]*H[2][1] - H[1][1]*H[2][0]) / det,
            (H[0][1]*H[2][0] - H[0][0]*H[2][1]) / det,
            (H[0][0]*H[1][1] - H[0][1]*H[1][0]) / det
        );
    }

    // apply inverse homography in 2D
    vec3 h = invH * vec3(position, 1.0);
    vec2 uv = h.xy / h.z;        // now in 0..1 space, WARPED

    // map warped 0..1 → clip space
    float x = uv.x * 2.0 - 1.0;
    float y = 1.0 - uv.y * 2.0;

    gl_Position = vec4(x, y, 0.0, 1.0);
}
