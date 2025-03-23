#version 300 es
precision mediump float;

in vec2 vTexCoords;
out vec4 FragColor;

uniform float fr_maskStart;     // Starting position of the mask in UV coordinates
uniform float fr_rotation;     // Rotation of the mask in radians
uniform float fr_softness;     // Controls how soft the mask transition is

void main() {

    // Convert vTexCoords to range (-1, 1) for better control
    vec2 centeredCoord = vTexCoords * 2.0 - 1.0;

    // Apply rotation to the coordinate system
    float cosR = cos(fr_rotation);
    float sinR = sin(fr_rotation);
    vec2 rotatedCoord = vec2(
    cosR * centeredCoord.x - sinR * centeredCoord.y,
    sinR * centeredCoord.x + cosR * centeredCoord.y
    );

    // Compute mask effect along the rotated x-axis
    float maskFactor = rotatedCoord.x - (fr_maskStart * 2.0 - 1.0); // Convert UV to (-1,1)

    // Apply smoothstep to create the soft mask transition
    float mask = smoothstep(0.0, fr_softness, maskFactor);

    // Apply the mask to the texture color (black to transparent)
    FragColor = vec4(vec3(0.0), mask);
}
