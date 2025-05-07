// App.jsx
import { useEffect, useRef, useState } from "react";
import {
  AppBar,
  Toolbar,
  Typography,
  CssBaseline,
  Box,
  IconButton,
  Grid,
  useMediaQuery
} from "@mui/material";
import MenuIcon from "@mui/icons-material/Menu";
import LeftMenu from "./components/LeftMenu";
import StatusPage from "./components/StatusPage";
import PerspectivePage from "./components/PerspectivePage";
import ShuttersPage from "./components/ShuttersPage";
import StatusBar from "./components/StatusBar";

export default function App() {
  const [status, setStatus] = useState("Connecting...");
  const [activePage, setActivePage] = useState("perspective");
  const [menuOpen, setMenuOpen] = useState(true);
  const [corners, setCorners] = useState([
    { x: 0.0, y: 0.0 },
    { x: 1.0, y: 0.0 },
    { x: 1.0, y: 1.0 },
    { x: 0.0, y: 1.0 },
  ]);
  const [shutters, setShutters] = useState({
    top: { in: 0, angle: 0, softness: 0 },
    right: { in: 0, angle: 0, softness: 0 },
    bottom: { in: 0, angle: 0, softness: 0 },
    left: { in: 0, angle: 0, softness: 0 }
  });

  const [statusData, setStatusData] = useState({});
  const [wsConnected, setWsConnected] = useState(false);
  const wsRef = useRef(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const drawerWidth = 240;

  const isMobile = useMediaQuery(theme => theme.breakpoints.down('sm'));
  useEffect(() => {
    if (isMobile) setSidebarOpen(false);
  }, [isMobile]);

  const connectWebSocket = () => {
    const ws = new WebSocket(`ws://${location.hostname}:8765`);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log("WebSocket connected");
      setWsConnected(true);
      ws.send(JSON.stringify({ status: "update" }));
    };

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      console.log("WebSocket message", msg);
      if ("Active Cue Count" in msg || msg.status === "Running") {
        setStatusData(msg);
      } else if ("corners" in msg) {
        const corrected = [...msg.corners];
        // Swap index 2 and 3 (3rd and 4th corners)
        [corrected[2], corrected[3]] = [corrected[3], corrected[2]];
        setCorners(corrected);
      } else if ("framing" in msg && msg.framing[0]?.maskStart !== undefined) {
        // Convert list of FramingShutter objects to side-named dict
        const order = ["right", "top", "left", "bottom"];
        const newShutters = {};
        for (let i = 0; i < 4; i++) {
          const shutter = msg.framing[i] || { rotation: 0, maskStart: 0, softness: 0 };
          const side = order[i];
          newShutters[side] = {
            in: +(shutter.maskStart * 100).toFixed(1),
            angle: +(-shutter.rotation).toFixed(1),
            softness: shutter.softness ?? 0
          };
        }
        setShutters(newShutters);
      }
    };

    ws.onclose = () => {
      console.warn("WebSocket closed");
      setWsConnected(false);
      setStatusData(null);
    };

    ws.onerror = (e) => {
      console.error("WebSocket error", e);
      setWsConnected(false);
      setStatusData(null);
    };
  };

  useEffect(() => {
    connectWebSocket();
    return () => {
      wsRef.current?.close();
    };
  }, []);

  const renderPage = () => {
    switch (activePage) {
      case "status":
        return <StatusPage statusData={statusData} wsRef={wsRef} />;
      case "perspective":
        return <PerspectivePage corners={corners} setCorners={setCorners} wsRef={wsRef} />;
      case "shutters":
        return <ShuttersPage shutters={shutters} setShutters={setShutters} wsRef={wsRef} />;
      default:
        return null;
    }
  };

  return (
      <Box sx={{ display: 'flex', width: '100vw', height: '100svh', flexDirection: 'column' }}>
        <CssBaseline />
        <AppBar position="fixed" sx={{ zIndex: (theme) => theme.zIndex.drawer + 1 }}>
          <Toolbar>
            <IconButton sx={{ mr: 2 }} color="inherit" aria-label="open drawer" edge="start" onClick={() => setMenuOpen(!menuOpen)}>
              <MenuIcon />
            </IconButton>
            <Typography variant="h6" noWrap component="div" sx={{ ml: 2 }}>
              pyPlayUI
            </Typography>
          </Toolbar>
        </AppBar>
        <Toolbar />
        <Box sx={{ display: 'flex', flexGrow: 1, paddingBottom: '60px'
        }}>
          <LeftMenu activePage={activePage} setActivePage={setActivePage} open={menuOpen} drawerWidth={drawerWidth}/>
          <Box
              component="main"
              sx={{
                flexGrow: 1,
                p: 2,
                transition: 'margin-left 0.3s',
                marginLeft: menuOpen ? `${drawerWidth}px` : 0,
              }}
          >
            <Grid container columns={12} rowSpacing={4} columnSpacing={4}>
              <Grid size={12}>{renderPage()}</Grid>
            </Grid>
          </Box>
        </Box>
        <StatusBar   connected={wsConnected}
                     reconnect={() => {
                       wsRef.current?.close(); // Triggers cleanup + onclose
                       setTimeout(() => connectWebSocket(), 200); // Delay slightly to avoid race
                     }} />
      </Box>
  );
}
