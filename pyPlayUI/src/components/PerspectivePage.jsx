// PerspectivePage.jsx
import {Box, Button, Grid, TextField, Typography} from "@mui/material";
import { useEffect, useRef, useState } from "react";

export default function PerspectivePage({ corners, setCorners, wsRef }) {
  const canvasRef = useRef(null);
  const [selectedCorner, setSelectedCorner] = useState(-1);

  useEffect(() => {
    const interval = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ status: "perspective" }));
      }
    }, 500); // 500 ms

    return () => clearInterval(interval); // Clean up on unmount
  }, []);

  const clamp = (n) => Math.round(1000* Math.max(-0.1, Math.min(1.1, n)))/ 1000;

  const draw = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const size = canvas.clientWidth;
    canvas.width = size;
    canvas.height = size / 1.6; // 16:10 aspect ratio
    const ctx = canvas.getContext("2d");

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = '#f0f0f0';
    ctx.fillRect(0.08333 * canvas.width, 0.08333 * canvas.height, 0.83333 * canvas.width, 0.83333 * canvas.height);
    ctx.strokeStyle = '#aaa';
    ctx.lineWidth = 2;
    ctx.strokeRect(0.08333 * canvas.width, 0.08333 * canvas.height, 0.83333 * canvas.width, 0.83333 * canvas.height);

    ctx.beginPath();
    corners.forEach((pt, i) => {
      const x = (pt.x + 0.1) * canvas.width * 0.83333;
      const y = (pt.y + 0.1) * canvas.height * 0.83333;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    const first = corners[0];
    ctx.lineTo((first.x + 0.1) * canvas.width * 0.83333, (first.y + 0.1) * canvas.height * 0.83333);
    ctx.stroke();

    ctx.font = "14px sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    corners.forEach((pt, i) => {
      const x = (pt.x + 0.1) * canvas.width * 0.83333;
      const y = (pt.y + 0.1) * canvas.height * 0.83333;
      ctx.fillStyle = selectedCorner === i ? "red" : "blue";
      ctx.beginPath();
      ctx.arc(x, y, 10, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = "white";
      ctx.fillText((i + 1).toString(), x, y);
    });
  };

  const sendCorners = (updated) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        corners: updated.map((pt) => [ +pt.x.toFixed(3), +pt.y.toFixed(3) ])
      }));
    }
  };

  const handleCornerChange = (index, axis, value) => {
    const updated = [...corners];
    updated[index][axis] = clamp(parseFloat(value));
    setCorners(updated);
    sendCorners(updated);
  };

  useEffect(() => {
    const resizeCanvas = () => draw();
    resizeCanvas();
    window.addEventListener("resize", resizeCanvas);
    return () => window.removeEventListener("resize", resizeCanvas);
  }, [corners]);

  useEffect(() => draw(), [corners, selectedCorner]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const onMouseDown = (e) => {
      const rect = canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      const idx = corners.findIndex((pt) => {
        const x = (pt.x + 0.1) * canvas.width * 0.83333;
        const y = (pt.y + 0.1) * canvas.height * 0.83333;
        return Math.hypot(x - mx, y - my) < 15;
      });
      if (idx !== -1) setSelectedCorner(idx);
    };
    const onMouseMove = (e) => {
      if (selectedCorner === -1) return;
      const rect = canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      const normX = clamp((mx / canvas.width - 0.1) / 0.83333);
      const normY = clamp((my / canvas.height - 0.1) / 0.83333);
      const updated = [...corners];
      updated[selectedCorner] = { x: normX, y: normY };
      setCorners(updated);
      sendCorners(updated);
    };

    const onMouseUp = () => setSelectedCorner(-1);


    const getTouchPos = (e) => {
      const rect = canvas.getBoundingClientRect();
      const touch = e.touches[0];
      return {
        x: touch.clientX - rect.left,
        y: touch.clientY - rect.top
      };
    };

    const onTouchStart = (e) => {
      const { x: mx, y: my } = getTouchPos(e);
      const idx = corners.findIndex((pt) => {
        const cx = (pt.x + 0.1) * canvas.width * 0.83333;
        const cy = (pt.y + 0.1) * canvas.height * 0.83333;
        return Math.hypot(cx - mx, cy - my) < 15;
      });
      if (idx !== -1) setSelectedCorner(idx);
    };

    const onTouchMove = (e) => {
      if (selectedCorner === -1) return;
      const { x: mx, y: my } = getTouchPos(e);
      const normX = clamp((mx / canvas.width - 0.1) / 0.83333);
      const normY = clamp((my / canvas.height - 0.1) / 0.83333);
      const updated = [...corners];
      updated[selectedCorner] = { x: normX, y: normY };
      setCorners(updated);
      sendCorners(updated);
    };

    const onTouchEnd = () => setSelectedCorner(-1);

    canvas.addEventListener("mousedown", onMouseDown);
    canvas.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    canvas.addEventListener("touchstart", onTouchStart);
    canvas.addEventListener("touchmove", onTouchMove);
    window.addEventListener("touchend", onTouchEnd);

    return () => {
      canvas.removeEventListener("mousedown", onMouseDown);
      canvas.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
      canvas.removeEventListener("touchstart", onTouchStart);
      canvas.removeEventListener("touchmove", onTouchMove);
      window.removeEventListener("touchend", onTouchEnd);

    };
  }, [corners, selectedCorner]);

  return (
      <Grid container columnSpacing={4} rowSpacing={2}>
        <Grid size={{ xs: 12, md: 4 }}>
          <Typography variant="h6">Perspective Adjustment</Typography>
          {corners.map((pt, i) => (
              <Grid container spacing={1} alignItems="center" key={i}>
                <Grid size={12}><Typography>Corner {i + 1}</Typography></Grid>
                <Grid size={6}>
                  <TextField
                      label="X"
                      type="number"
                      value={pt.x}
                      onChange={(e) => handleCornerChange(i, 'x', e.target.value)}
                      inputProps={{ step: 0.01, min: -0.1, max: 1.1 }}
                      size="small"
                      fullWidth
                  />
                </Grid>
                <Grid size={6}>
                  <TextField
                      label="Y"
                      type="number"
                      value={pt.y}
                      onChange={(e) => handleCornerChange(i, 'y', e.target.value)}
                      inputProps={{ step: 0.01, min: -0.1, max: 1.1 }}
                      size="small"
                      fullWidth
                  />
                </Grid>
              </Grid>
          ))}
          <Button
              variant="outlined"
              onClick={() => {
                const reset = [
                  { x: 0.0, y: 0.0 },
                  { x: 1.0, y: 0.0 },
                  { x: 1.0, y: 1.0 },
                  { x: 0.0, y: 1.0 },
                ];
                setCorners(reset);
                sendCorners(reset);
              }}
              sx={{ mt: 2 }}
          >
            Reset Corners
          </Button>
        </Grid>
        <Grid size={{ xs: 12, md: 8 }}>
          <Box
              sx={{
                width: '100%',
                border: '1px solid #ccc',
                backgroundColor: '#fafafa',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}
          >
            <canvas
                ref={canvasRef}
                style={{ width: '100%', height: '100%', display: 'block' }}
            />
          </Box>
        </Grid>
      </Grid>
  );
}
