// ShuttersPage.jsx
import { Box, Grid, Slider, Typography } from "@mui/material";
import { useEffect, useRef } from "react";

export default function ShuttersPage({ shutters, setShutters, wsRef }) {
  const shutterCanvasRef = useRef(null);

  useEffect(() => {
    const interval = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ status: "framing" }));
      }
    }, 250); // 250 ms

    return () => clearInterval(interval); // Clean up on unmount
  }, []);

  const sendShutters = (data) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        shutters: data
      }));
    }
  };

  useEffect(() => {
    const canvas = shutterCanvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const w = canvas.width = canvas.clientWidth;
    const h = canvas.height = canvas.clientHeight;
    ctx.clearRect(0, 0, w, h);

    ctx.strokeStyle = "#ccc";
    ctx.strokeRect(0, 0, w, h);

    const drawShutter = (side, insetPx, angle, softness = 0.0) => {
      ctx.save();
      ctx.translate(w / 2, h / 2);
      ctx.rotate((angle * Math.PI) / 180);

      const overdraw = 1000; // large enough to extend past visible area
      const softnessPx = softness * 200;
      // insetPx -= softnessPx/2

      ctx.fillStyle = "black";
      switch (side) {
        case "top":
          ctx.fillRect(-w / 2 - 1000, -h / 2 - 1000, w + 2000, insetPx + 1000);
          break;
        case "bottom":
          ctx.fillRect(-w / 2 - 1000, h / 2 - insetPx, w + 2000, insetPx + 1000);
          break;
        case "left":
          ctx.fillRect(-w / 2 - 1000, -h / 2 - 1000, insetPx + 1000, h + 2000);
          break;
        case "right":
          ctx.fillRect(w / 2 - insetPx, -h / 2 - 1000, insetPx + 1000, h + 2000);
          break;
      }

      if (softnessPx > 0) {
        let grad;

        switch (side) {
          case "top":
            grad = ctx.createLinearGradient(0, -h / 2 + insetPx, 0, -h / 2 + insetPx + softnessPx);
            break;
          case "bottom":
            grad = ctx.createLinearGradient(0, h / 2 - insetPx, 0, h / 2 - insetPx - softnessPx);
            break;
          case "left":
            grad = ctx.createLinearGradient(-w / 2 + insetPx, 0, -w / 2 + insetPx + softnessPx, 0);
            break;
          case "right":
            grad = ctx.createLinearGradient(w / 2 - insetPx, 0, w / 2 - insetPx - softnessPx, 0);
            break;
        }

        grad.addColorStop(0, "rgba(0,0,0,1)");
        grad.addColorStop(1, "rgba(0,0,0,0)");
        ctx.fillStyle = grad;

        switch (side) {
          case "top":
            ctx.fillRect(-w / 2 - 1000, -h / 2 + insetPx, w + 2000, softnessPx);
            break;
          case "bottom":
            ctx.fillRect(-w / 2 - 1000, h / 2 - insetPx - softnessPx, w + 2000, softnessPx);
            break;
          case "left":
            ctx.fillRect(-w / 2 + insetPx, -h / 2 - 1000, softnessPx, h + 2000);
            break;
          case "right":
            ctx.fillRect(w / 2 - insetPx - softnessPx, -h / 2 - 1000, softnessPx, h + 2000);
            break;
        }
      }


      ctx.restore();
    };

    Object.entries(shutters).forEach(([side, { in: inset, angle, softness }]) => {
      const length = (side === "top" || side === "bottom") ? h * (inset / 100) : w * (inset / 100);
      drawShutter(side, length, angle, softness);
    });
  }, [shutters]);

  return (
      <Grid container columnSpacing={4} rowSpacing={4}>
        <Grid size={12}>
          <Typography variant="h4" gutterBottom>Framing Shutters</Typography>
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          {Object.entries(shutters).map(([side, values]) => (
              <Box key={side} mb={3}>
                <Typography variant="subtitle1">{side}</Typography>
                <Grid container columnSpacing={2} rowSpacing={2}>
                  <Grid size={{ xs: 12, md: 4 }}>
                    <Typography>In (%)</Typography>
                    <Slider
                        valueLabelDisplay="auto"
                        value={values.in}
                        onChange={(_, val) => {
                          const updated = {
                            ...shutters,
                            [side]: {...shutters[side], in: val}
                          };
                          setShutters(updated);
                          sendShutters(updated);
                        }}
                        min={0}
                        max={100}
                    />
                  </Grid>
                  <Grid size={{ xs: 12, md: 4 }}>
                    <Typography>Angle (°)</Typography>
                    <Slider
                        valueLabelDisplay="auto"
                        value={values.angle}
                        onChange={(_, val) => {
                          const updated = {
                            ...shutters,
                            [side]: {...shutters[side], angle: val}
                          };
                          setShutters(updated);
                          sendShutters(updated);
                        }}
                        min={-90}
                        max={90}
                    />
                  </Grid>
                  <Grid size={{ xs: 12, md: 4 }}>
                    <Typography>Softness (%)</Typography>
                    <Slider
                        valueLabelDisplay="auto"
                        value={values.softness}
                        onChange={(_, val) => {
                          const updated = {
                            ...shutters,
                            [side]: {...shutters[side], softness: val}
                          };
                          setShutters(updated);
                          sendShutters(updated);
                        }}
                        min={0}
                        max={1.0}
                        step={0.1}
                    />
                  </Grid>
                </Grid>
              </Box>
          ))}
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <Box
              sx={{
                width: '100%',
                aspectRatio: '16 / 10',
                border: '1px solid #ccc',
                backgroundColor: '#f9f9f9',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}
          >
            <canvas
                ref={shutterCanvasRef}
                style={{ width: '100%', height: '100%', display: 'block' }}
            />
          </Box>
        </Grid>
      </Grid>
  );
}
