
const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');
const coordsDiv = document.getElementById('coords');

function resizeCanvas() {
    canvas.width = window.innerWidth * 0.95;
    canvas.height = window.innerHeight * 0.85;
}
window.addEventListener('resize', resizeCanvas);
resizeCanvas();

let corners = [
    { x: 0.1, y: 0.1 },
    { x: 0.9, y: 0.1 },
    { x: 0.9, y: 0.9 },
    { x: 0.1, y: 0.9 }
];

let selectedCorner = -1;

function normalizedToPixel(pt) {
    return {
        x: pt.x * canvas.width,
        y: pt.y * canvas.height
    };
}

function pixelToNormalized(x, y) {
    return {
        x: x / canvas.width,
        y: y / canvas.height
    };
}

function clamp(n) {
    return Math.min(1.1, Math.max(-0.1, n));
}

function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    ctx.beginPath();
    corners.forEach((pt, i) => {
        const p = normalizedToPixel(pt);
        if (i === 0) ctx.moveTo(p.x, p.y);
        else ctx.lineTo(p.x, p.y);
    });
    const first = normalizedToPixel(corners[0]);
    ctx.lineTo(first.x, first.y);
    ctx.strokeStyle = "#000";
    ctx.stroke();

    ctx.font = "16px sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";

    corners.forEach((pt, i) => {
        const p = normalizedToPixel(pt);
        ctx.fillStyle = (i === selectedCorner) ? "red" : "blue";
        ctx.beginPath();
        ctx.arc(p.x, p.y, 10, 0, Math.PI * 2);
        ctx.fill();

        // Draw label
        ctx.fillStyle = "#fff";
        ctx.fillText((i + 1).toString(), p.x, p.y);
    });

    // Update coordinates display
    coordsDiv.innerHTML = corners.map((pt, i) =>
        `Corner ${i + 1}: (${pt.x.toFixed(3)}, ${pt.y.toFixed(3)})`
    ).join("<br>");
}

function sendCorners() {
    if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
            corners: corners.map(pt => [pt.x, pt.y])
        }));
    }
}

canvas.addEventListener("mousedown", (e) => {
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    for (let i = 0; i < corners.length; i++) {
        const p = normalizedToPixel(corners[i]);
        if (Math.hypot(p.x - mx, p.y - my) < 15) {
            selectedCorner = i;
            break;
        }
    }
});

canvas.addEventListener("mouseup", () => {
    selectedCorner = -1;
});

canvas.addEventListener("mousemove", (e) => {
    if (selectedCorner === -1) return;

    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    const norm = pixelToNormalized(x, y);
    corners[selectedCorner].x = clamp(norm.x);
    corners[selectedCorner].y = clamp(norm.y);

    draw();
    sendCorners();
});

window.addEventListener("keydown", (e) => {
    if (selectedCorner === -1) return;

    const delta = e.shiftKey ? 0.01 : 0.005;
    if (e.key === "ArrowLeft") corners[selectedCorner].x = clamp(corners[selectedCorner].x - delta);
    if (e.key === "ArrowRight") corners[selectedCorner].x = clamp(corners[selectedCorner].x + delta);
    if (e.key === "ArrowUp") corners[selectedCorner].y = clamp(corners[selectedCorner].y - delta);
    if (e.key === "ArrowDown") corners[selectedCorner].y = clamp(corners[selectedCorner].y + delta);

    draw();
    sendCorners();
});

// WebSocket setup
const ws = new WebSocket(`ws://${location.hostname}:8765`);
ws.onopen = () => console.log("WebSocket connected.");
ws.onerror = (e) => console.error("WebSocket error:", e);

draw();
