#version 300 es
precision highp float;

layout(location = 0) in vec2 position;   // mesh vertex positions (0..1)
layout(location = 1) in vec2 texCoords;  // base texture coordinates (0..1)

uniform mat3 homographyMatrix;

out vec2 vBaseUV;
out vec3 vProjTex;

void main() {
    // Use unflipped texCoords for homography and geometry
    vBaseUV = texCoords;

    // Invert homography (screen→source)
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

    // Apply inverse H to position to get warped geometry
    vec3 warped = invH * vec3(position, 1.0);
    vec2 uv = warped.xy / warped.z;

    // Map 0..1 → clip space (keep Y consistent with grid)
    float x = uv.x * 2.0 - 1.0;
    float y = 1.0 - uv.y * 2.0;
    
    gl_Position = vec4(x, y, 0.0, 1.0);

    // Pass projected texture coordinates (same orientation)
    vProjTex = invH * vec3(texCoords, 1.0);
}
