import React, { useEffect, useRef, useState } from "react";
import {
  Box,
  Button,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from "@mui/material";

const DIVS = 16;
const MARGIN = 0.05;

function makeDefaultPoints() {
  const arr = [];
  for (let i = 0; i <= DIVS; i++) {
    const row = [];
    for (let j = 0; j <= DIVS; j++) {
      row.push({ x: j / DIVS, y: i / DIVS });
    }
    arr.push(row);
  }
  return arr;
}

export default function MeshPage({ wsRef }) {
  const containerRef = useRef(null);
  const canvasRef = useRef(null);

  const [selectedScreen, setSelectedScreen] = useState("left");
  const [leftPoints, setLeftPoints] = useState(() => makeDefaultPoints());
  const [rightPoints, setRightPoints] = useState(() => makeDefaultPoints());
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [version, setVersion] = useState(null);
  const [showGridOverlay, setShowGridOverlay] = useState(false);

  const pointsRef = useRef(leftPoints);
  const draggingRef = useRef(null);
  const panningRef = useRef(false);
  const lastMouseRef = useRef({ x: 0, y: 0 });
  const panRef = useRef(pan);

  useEffect(() => {
    const ws = wsRef?.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "mesh_request", screen: "left" }));
      ws.send(JSON.stringify({ type: "mesh_request", screen: "right" }));
      ws.send(JSON.stringify({ type: "mesh_grid_status" }));
    }
  }, [wsRef]);

  useEffect(() => {
    panRef.current = pan;
  }, [pan]);

  useEffect(() => {
    pointsRef.current = selectedScreen === "left" ? leftPoints : rightPoints;
  }, [selectedScreen, leftPoints, rightPoints]);

  const draw = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    const w = canvas.width;
    const h = canvas.height;

    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = "#111";
    ctx.fillRect(0, 0, w, h);

    const pts = pointsRef.current;
    const offX = (1 - zoom) * 0.5 + pan.x;
    const offY = (1 - zoom) * 0.5 + pan.y;

    const toScreen = (gx, gy) => {
      const sx = (gx * zoom + offX) * w;
      const sy = (gy * zoom + offY) * h;
      return [sx, sy];
    };

    ctx.strokeStyle =
      selectedScreen === "left"
        ? "rgba(255,0,0,0.8)"
        : "rgba(0,255,0,0.6)";
    ctx.lineWidth = 1;

    for (let i = 0; i <= DIVS; i++) {
      ctx.beginPath();
      const row = pts[i];
      let [sx, sy] = toScreen(row[0].x, row[0].y);
      ctx.moveTo(sx, sy);
      for (let j = 1; j <= DIVS; j++) {
        [sx, sy] = toScreen(row[j].x, row[j].y);
        ctx.lineTo(sx, sy);
      }
      ctx.stroke();
    }

    for (let j = 0; j <= DIVS; j++) {
      ctx.beginPath();
      let [sx, sy] = toScreen(pts[0][j].x, pts[0][j].y);
      ctx.moveTo(sx, sy);
      for (let i = 1; i <= DIVS; i++) {
        [sx, sy] = toScreen(pts[i][j].x, pts[i][j].y);
        ctx.lineTo(sx, sy);
      }
      ctx.stroke();
    }

    for (let i = 0; i <= DIVS; i++) {
      for (let j = 0; j <= DIVS; j++) {
        const p = pts[i][j];
        const [sx, sy] = toScreen(p.x, p.y);
        const isBorder = i === 0 || j === 0 || i === DIVS || j === DIVS;
        ctx.beginPath();
        ctx.fillStyle = isBorder ? "#ffcc66" : "#fff";
        ctx.arc(sx, sy, 5, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  };

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const onWheel = (e) => {
      e.preventDefault();
      const delta = e.deltaY < 0 ? 0.1 : -0.1;
      setZoom((z) => Math.min(3, Math.max(0.4, z + delta)));
    };

    canvas.addEventListener("wheel", onWheel, { passive: false });
    return () => canvas.removeEventListener("wheel", onWheel);
  }, []);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "+" || e.key === "=") {
        setZoom((z) => Math.min(3, z + 0.1));
      } else if (e.key === "-") {
        setZoom((z) => Math.max(0.4, z - 0.1));
      }
    };

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    const resize = () => {
      const container = containerRef.current;
      const canvas = canvasRef.current;
      if (!container || !canvas) return;

      const rect = container.getBoundingClientRect();
      const w = Math.floor(rect.width);
      const h = Math.floor(rect.height);
      if (w > 0 && h > 0) {
        canvas.width = w;
        canvas.height = h;
        draw();
      }
    };

    resize();
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, []);

  useEffect(() => {
    draw();
  }, [selectedScreen, leftPoints, rightPoints, zoom, pan]);

  useEffect(() => {
    const ws = wsRef?.current;
    if (!ws) return;

    const onMessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === "mesh_data") {
          const { screen, points, version: meshVersion } = msg;
          const mappedPoints = points.map((row) =>
            row.map(([x, y]) => ({ x, y }))
          );

          if (screen === "left") {
            setLeftPoints(mappedPoints);
          } else if (screen === "right") {
            setRightPoints(mappedPoints);
          }

          if (meshVersion) setVersion(meshVersion);
        } else if (msg.type === "mesh_saved") {
          setVersion(msg.version);
        } else if (msg.type === "mesh_grid_state") {
          setShowGridOverlay(Boolean(msg.enabled));
        }
      } catch {
        // Ignore unrelated websocket messages.
      }
    };

    ws.addEventListener("message", onMessage);
    return () => ws.removeEventListener("message", onMessage);
  }, [wsRef]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const getRect = () => canvas.getBoundingClientRect();

    const findPoint = (sx, sy) => {
      const rect = getRect();
      const w = canvas.width;
      const h = canvas.height;
      const offX = (1 - zoom) * 0.5 + panRef.current.x;
      const offY = (1 - zoom) * 0.5 + panRef.current.y;
      const mx = sx - rect.left;
      const my = sy - rect.top;
      const pts = pointsRef.current;
      let hit = null;
      let best = 9999;

      for (let i = 0; i <= DIVS; i++) {
        for (let j = 0; j <= DIVS; j++) {
          const p = pts[i][j];
          const px = (p.x * zoom + offX) * w;
          const py = (p.y * zoom + offY) * h;
          const d = Math.hypot(px - mx, py - my);
          if (d < 10 && d < best) {
            best = d;
            hit = { i, j };
          }
        }
      }

      return hit;
    };

    const screenToGrid = (sx, sy) => {
      const rect = getRect();
      const w = canvas.width;
      const h = canvas.height;
      const mx = sx - rect.left;
      const my = sy - rect.top;
      const offX = (1 - zoom) * 0.5 + panRef.current.x;
      const offY = (1 - zoom) * 0.5 + panRef.current.y;
      const gx = (mx / w - offX) / zoom;
      const gy = (my / h - offY) / zoom;
      return [gx, gy];
    };

    const onDown = (e) => {
      const button = e.button;
      const sx = e.clientX ?? e.touches?.[0]?.clientX;
      const sy = e.clientY ?? e.touches?.[0]?.clientY;

      if (button === 1) {
        panningRef.current = true;
        lastMouseRef.current = { x: sx, y: sy };
        e.preventDefault();
        return;
      }

      const hit = findPoint(sx, sy);
      if (hit) draggingRef.current = hit;
      e.preventDefault();
    };

    const onMove = (e) => {
      const sx = e.clientX ?? e.touches?.[0]?.clientX;
      const sy = e.clientY ?? e.touches?.[0]?.clientY;

      if (panningRef.current) {
        e.preventDefault();
        const dx = sx - lastMouseRef.current.x;
        const dy = sy - lastMouseRef.current.y;
        lastMouseRef.current = { x: sx, y: sy };

        const w = canvas.width;
        const h = canvas.height;
        setPan((prev) => ({
          x: prev.x + dx / w / zoom,
          y: prev.y + dy / h / zoom,
        }));
        return;
      }

      const drag = draggingRef.current;
      if (!drag) return;

      e.preventDefault();
      let [gx, gy] = screenToGrid(sx, sy);
      gx = Math.min(1 + MARGIN, Math.max(-MARGIN, gx));
      gy = Math.min(1 + MARGIN, Math.max(-MARGIN, gy));

      if (selectedScreen === "left") {
        setLeftPoints((prev) => {
          const copy = prev.map((row) => row.map((p) => ({ ...p })));
          copy[drag.i][drag.j] = { x: gx, y: gy };
          return copy;
        });
      } else {
        setRightPoints((prev) => {
          const copy = prev.map((row) => row.map((p) => ({ ...p })));
          copy[drag.i][drag.j] = { x: gx, y: gy };
          return copy;
        });
      }

      if (wsRef?.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(
          JSON.stringify({
            type: "mesh_update",
            screen: selectedScreen,
            i: drag.i,
            j: drag.j,
            x: gx,
            y: gy,
          })
        );
      }
    };

    const onUp = () => {
      draggingRef.current = null;
      panningRef.current = false;
    };

    canvas.addEventListener("mousedown", onDown);
    canvas.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    canvas.addEventListener("touchstart", onDown, { passive: false });
    canvas.addEventListener("touchmove", onMove, { passive: false });
    window.addEventListener("touchend", onUp);

    return () => {
      canvas.removeEventListener("mousedown", onDown);
      canvas.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      canvas.removeEventListener("touchstart", onDown);
      canvas.removeEventListener("touchmove", onMove);
      window.removeEventListener("touchend", onUp);
    };
  }, [selectedScreen, wsRef, zoom]);

  const handleScreenChange = (_e, value) => {
    if (!value) return;
    setSelectedScreen(value);
    const ws = wsRef?.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "mesh_request", screen: value }));
    }
  };

  const handleGridOverlayChange = (_e, value) => {
    if (!value) return;
    const enabled = value === "on";
    setShowGridOverlay(enabled);
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(
        JSON.stringify({ type: "mesh_grid_toggle", enabled })
      );
    }
  };

  return (
    <Box sx={{ p: 2 }}>
      <Typography variant="h6" sx={{ mb: 2 }}>
        Mesh Adjust {version ? `(v${version})` : ""}
      </Typography>

      <ToggleButtonGroup
        value={selectedScreen}
        exclusive
        onChange={handleScreenChange}
        size="small"
        sx={{ mb: 2 }}
      >
        <ToggleButton value="left">Left</ToggleButton>
        <ToggleButton value="right">Right</ToggleButton>
      </ToggleButtonGroup>

      <Box
        sx={{
          display: "flex",
          flexWrap: "wrap",
          gap: 2,
          alignItems: "center",
          mb: 2,
        }}
      >
        <Typography variant="body2">Grid Overlay</Typography>
        <ToggleButtonGroup
          value={showGridOverlay ? "on" : "off"}
          exclusive
          onChange={handleGridOverlayChange}
          size="small"
        >
          <ToggleButton value="off">Off</ToggleButton>
          <ToggleButton value="on">On</ToggleButton>
        </ToggleButtonGroup>

        <Button
          variant="outlined"
          size="small"
          onClick={() => {
            if (wsRef.current?.readyState === WebSocket.OPEN) {
              wsRef.current.send(
                JSON.stringify({ type: "mesh_save", screen: selectedScreen })
              );
            }
          }}
        >
          Save Mesh
        </Button>

        <Button
          variant="outlined"
          size="small"
          onClick={() => {
            if (wsRef.current?.readyState === WebSocket.OPEN) {
              wsRef.current.send(
                JSON.stringify({ type: "mesh_revert", screen: selectedScreen })
              );
            }
          }}
        >
          Revert
        </Button>
      </Box>

      <Box
        ref={containerRef}
        sx={{
          width: "100%",
          height: "70vh",
          border: "1px solid #555",
          borderRadius: 1,
          background: "#111",
          overflow: "hidden",
        }}
      >
        <canvas
          ref={canvasRef}
          style={{
            width: "100%",
            height: "100%",
            display: "block",
          }}
        />
      </Box>
    </Box>
  );
}
