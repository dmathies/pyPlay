import {
  Box,
  Button,
  Grid,
  TextField,
  Typography,
  ToggleButtonGroup,
  ToggleButton,
} from "@mui/material";
import { useEffect, useRef, useState } from "react";
import { useTheme } from "@mui/material";

const DEFAULT_CORNERS = [
  { x: 0.0, y: 0.0 },
  { x: 1.0, y: 0.0 },
  { x: 1.0, y: 1.0 },
  { x: 0.0, y: 1.0 },
];

export default function PerspectivePage({ wsRef, serverPerspective }) {
  const canvasRef = useRef(null);
  const [selectedCorner, setSelectedCorner] = useState(-1);
  const [selectedScreen, setSelectedScreen] = useState("left");
  const [leftCorners, setLeftCorners] = useState(DEFAULT_CORNERS);
  const [rightCorners, setRightCorners] = useState(DEFAULT_CORNERS);
  const theme = useTheme();

  useEffect(() => {
    const ws = wsRef?.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ status: "perspective" }));
    }
  }, [wsRef]);

  // sync from server (on startup or revert)
  useEffect(() => {
    if (!serverPerspective) return;

    const normalize = (corners) => {
      if (!corners || corners.length !== 4) return corners;
      const arr = corners.map((c) => ({ ...c })); // clone
      const tmp = arr[2];
      arr[2] = arr[3];
      arr[3] = tmp;
      return arr;
    };     

    if (serverPerspective?.leftCorners) {
      setLeftCorners(normalize(serverPerspective.leftCorners));
    }
    if (serverPerspective?.rightCorners) {
      setRightCorners(normalize(serverPerspective.rightCorners));
    }
  }, [serverPerspective]);

  const currentCorners =
    selectedScreen === "left" ? leftCorners : rightCorners;

  // helper to constrain numeric range
  const clamp = (n) =>
    Math.round(1000 * Math.max(-0.1, Math.min(1.1, n))) / 1000;

  const sendCorners = (screen, updated) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(
        JSON.stringify({
          screen,
          corners: updated.map((pt) => [pt.x, pt.y]),
        })
      );
    }
  };

  const updateCurrentCorners = (updated) => {
    if (selectedScreen === "left") setLeftCorners(updated);
    else setRightCorners(updated);
    sendCorners(selectedScreen, updated);
  };

  const handleCornerChange = (index, axis, value) => {
    const v = clamp(parseFloat(value));
    const updated = currentCorners.map((p, i) =>
      i === index ? { ...p, [axis]: v } : p
    );
    updateCurrentCorners(updated);
  };

  const handleScreenChange = (_e, value) => {
    if (!value) return;
    setSelectedScreen(value);
    setSelectedCorner(-1);
  };

  const handleReset = () => {
    updateCurrentCorners(DEFAULT_CORNERS);
  };

  const draw = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width;
    canvas.height = rect.height;

    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "#000";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // subtle tinted background depending on screen
    ctx.fillStyle =
      selectedScreen === "left"
        ? "rgba(255, 0, 0, 0.05)"
        : "rgba(0, 255, 0, 0.05)";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // border box
    ctx.strokeStyle = theme.palette.divider;
    ctx.lineWidth = 2;
    ctx.strokeRect(0, 0, canvas.width, canvas.height);

    // draw warped quad
    ctx.beginPath();
    currentCorners.forEach((pt, i) => {
      const x = pt.x * canvas.width;
      const y = pt.y * canvas.height;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.closePath();
    ctx.strokeStyle = selectedScreen === "left" ? "#ff3333" : "#33ff33";
    ctx.lineWidth = 3;
    ctx.stroke();

    // draw handles
    currentCorners.forEach((pt, i) => {
      const x = pt.x * canvas.width;
      const y = pt.y * canvas.height;
      ctx.beginPath();
      ctx.arc(x, y, 8, 0, 2 * Math.PI);
      ctx.fillStyle = selectedCorner === i ? "#ff4444" : "#0077ff";
      ctx.fill();
      ctx.strokeStyle = "white";
      ctx.lineWidth = 1.5;
      ctx.stroke();
      ctx.fillStyle = "white";
      ctx.font = "12px sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText((i + 1).toString(), x, y);
    });
  };

  // Redraw whenever corners, selected corner, or screen changes
  useEffect(() => {
    draw();
  }, [selectedScreen, leftCorners, rightCorners, selectedCorner]);

  // Auto-redraw on canvas resize
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const obs = new ResizeObserver(draw);
    obs.observe(canvas);
    return () => obs.disconnect();
  }, []);

  // --- mouse/touch handlers ---
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const toNorm = (mx, my) => ({
      x: clamp(mx / canvas.width),
      y: clamp(my / canvas.height),
    });

    const findCorner = (mx, my) =>
      currentCorners.findIndex(
        (pt) => Math.hypot(pt.x * canvas.width - mx, pt.y * canvas.height - my) < 15
      );

    const onMouseDown = (e) => {
      const rect = canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      const idx = findCorner(mx, my);
      if (idx !== -1) setSelectedCorner(idx);
    };

    const onMouseMove = (e) => {
      if (selectedCorner === -1) return;
      const rect = canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      const norm = toNorm(mx, my);
      const updated = currentCorners.map((p, i) =>
        i === selectedCorner ? { x: norm.x, y: norm.y } : p
      );
      updateCurrentCorners(updated);
    };

    const onMouseUp = () => setSelectedCorner(-1);

    const onTouchStart = (e) => {
      e.preventDefault();
      const rect = canvas.getBoundingClientRect();
      const t = e.touches[0];
      const mx = t.clientX - rect.left;
      const my = t.clientY - rect.top;
      const idx = findCorner(mx, my);
      if (idx !== -1) setSelectedCorner(idx);
    };

    const onTouchMove = (e) => {
      e.preventDefault();
      if (selectedCorner === -1) return;
      const rect = canvas.getBoundingClientRect();
      const t = e.touches[0];
      const mx = t.clientX - rect.left;
      const my = t.clientY - rect.top;
      const norm = toNorm(mx, my);
      const updated = currentCorners.map((p, i) =>
        i === selectedCorner ? { x: norm.x, y: norm.y } : p
      );
      updateCurrentCorners(updated);
    };

    const onTouchEnd = () => setSelectedCorner(-1);

    canvas.addEventListener("mousedown", onMouseDown);
    canvas.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    canvas.addEventListener("touchstart", onTouchStart, { passive: false });
    canvas.addEventListener("touchmove", onTouchMove, { passive: false });
    window.addEventListener("touchend", onTouchEnd);

    return () => {
      canvas.removeEventListener("mousedown", onMouseDown);
      canvas.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
      canvas.removeEventListener("touchstart", onTouchStart);
      canvas.removeEventListener("touchmove", onTouchMove);
      window.removeEventListener("touchend", onTouchEnd);
    };
  }, [currentCorners, selectedCorner, selectedScreen]);

  return (
      <Grid container columnSpacing={4} rowSpacing={2}>
      {/* Left side controls */}
      <Grid item xs={12} md={4}>
        <Typography variant="h6" sx={{ mb: 2 }}>
          Screen Perspective Adjustment
        </Typography>

        <ToggleButtonGroup
          value={selectedScreen}
          exclusive
          size="small"
          onChange={handleScreenChange}
          sx={{ mb: 2 }}
        >
          <ToggleButton value="left">Left Screen</ToggleButton>
          <ToggleButton value="right">Right Screen</ToggleButton>
        </ToggleButtonGroup>

        {currentCorners.map((pt, i) => (
          <Box key={i} sx={{ display: "flex", gap: 1, mb: 1 }}>
            <Typography sx={{ width: 20 }}>{i + 1}</Typography>
            <TextField
              label="X"
              size="small"
              type="number"
              value={pt.x}
              onChange={(e) => handleCornerChange(i, "x", e.target.value)}
              inputProps={{ step: 0.01 }}
            />
            <TextField
              label="Y"
              size="small"
              type="number"
              value={pt.y}
              onChange={(e) => handleCornerChange(i, "y", e.target.value)}
              inputProps={{ step: 0.01 }}
            />
          </Box>
        ))}

        <Button variant="outlined" onClick={handleReset} sx={{ mt: 1 }}>
          Reset current screen
        </Button>
      </Grid>

      <Grid size={{ xs: 12, md: 8 }}>
        <Box
            sx={{
              width: '100%',
              border: `1px solid ${theme.palette.divider}`,
              backgroundColor: '#fafafa',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}
        >
          <canvas
              ref={canvasRef}
              style={{ width: '100%', height: '100%', display: 'block', cursor: "crosshair" }}
          />
        </Box>
      </Grid>
    </Grid>
  );
}
