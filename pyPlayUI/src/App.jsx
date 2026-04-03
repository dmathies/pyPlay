import { useEffect, useRef, useState } from "react";
import {
  AppBar,
  Toolbar,
  Typography,
  CssBaseline,
  Box,
  IconButton,
  Grid,
  useMediaQuery,
  useTheme,
} from "@mui/material";

import MenuIcon from "@mui/icons-material/Menu";
import LeftMenu from "./components/LeftMenu";
import StatusPage from "./components/StatusPage";
import PerspectivePage from "./components/PerspectivePage";
import ShuttersPage from "./components/ShuttersPage";
import StatusBar from "./components/StatusBar";
import MeshPage from "./components/MeshPage";

export default function App() {
  const theme = useTheme();
  const [activePage, setActivePage] = useState("perspective");
  const [menuOpen, setMenuOpen] = useState(true);

  // perspective state coming from server
  const [perspectiveData, setPerspectiveData] = useState({
    leftCorners: [
      { x: 0.0, y: 0.0 },
      { x: 1.0, y: 0.0 },
      { x: 1.0, y: 1.0 },
      { x: 0.0, y: 1.0 },
    ],
    rightCorners: [
      { x: 0.0, y: 0.0 },
      { x: 1.0, y: 0.0 },
      { x: 1.0, y: 1.0 },
      { x: 0.0, y: 1.0 },
    ],
  });

  const [shutters, setShutters] = useState({
    top: { in: 0, angle: 0, softness: 0 },
    right: { in: 0, angle: 0, softness: 0 },
    bottom: { in: 0, angle: 0, softness: 0 },
    left: { in: 0, angle: 0, softness: 0 },
  });

  const [statusData, setStatusData] = useState({});
  const [wsConnected, setWsConnected] = useState(false);
  const wsRef = useRef(null);
  const drawerWidth = 240;

  const isMobile = useMediaQuery((theme) => theme.breakpoints.down("sm"));
  useEffect(() => {
    if (isMobile) setMenuOpen(false);
  }, [isMobile]);

  const connectWebSocket = () => {
    const ws = new WebSocket(`ws://${location.hostname}:8765`);
    wsRef.current = ws;

    ws.onopen = () => {
      setWsConnected(true);

      // ask for current status
      ws.send(JSON.stringify({ status: "update" }));

      // ask for current perspective (so ui shows latest)
      ws.send(JSON.stringify({ status: "perspective" }));

      // ask for both meshes on startup
      ws.send(JSON.stringify({ type: "mesh_request", screen: "left" }));
      ws.send(JSON.stringify({ type: "mesh_request", screen: "right" }));
    };

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);

      if ("Active Cue Count" in msg || msg.status === "Running") {
        setStatusData(msg);
      }
      else if (msg.type === "perspective") {
        // msg.leftCorners / msg.rightCorners are arrays of {x,y} (we sent that from backend)
        setPerspectiveData({
          leftCorners: msg.leftCorners ?? perspectiveData.leftCorners,
          rightCorners: msg.rightCorners ?? perspectiveData.rightCorners,
        });
      }
      else if ("framing" in msg && msg.framing[0]?.maskStart !== undefined) {
        const order = ["right", "top", "left", "bottom"];
        const newShutters = {};
        for (let i = 0; i < 4; i++) {
          const shutter =
            msg.framing[i] || { rotation: 0, maskStart: 0, softness: 0 };
          const side = order[i];
          newShutters[side] = {
            in: +(shutter.maskStart * 100).toFixed(1),
            angle: +(-shutter.rotation).toFixed(1),
            softness: shutter.softness ?? 0,
          };
        }
        setShutters(newShutters);
      }
    };

    ws.onclose = () => {
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
        return (
          <PerspectivePage
            wsRef={wsRef}
            serverPerspective={perspectiveData}
          />
        );
      case "shutters":
        return (
          <ShuttersPage
            shutters={shutters}
            setShutters={setShutters}
            wsRef={wsRef}
          />
        );
      case "mesh":
        return (
          <MeshPage
            wsRef={wsRef}
          />
        );
      default:
        return null;
    }
  };

  return (
    <Box
      sx={{
        display: "flex",
        width: "100vw",
        height: "100svh",
        flexDirection: "column",
      }}
    >
      <CssBaseline />
      <AppBar
        position="fixed"
        sx={{ zIndex: (theme) => theme.zIndex.drawer + 1 }}
      >
        <Toolbar>
          <IconButton
            sx={{ mr: 2 }}
            color="inherit"
            aria-label="open drawer"
            edge="start"
            onClick={() => setMenuOpen(!menuOpen)}
          >
            <MenuIcon />
          </IconButton>
          <Typography variant="h6" noWrap component="div" sx={{ ml: 2 }}>
            pyPlayUI
          </Typography>
        </Toolbar>
      </AppBar>
      <Toolbar />
      <Box
        sx={{
          bgcolor: theme.palette.background.paper,
          display: "flex",
          flexGrow: 1,
          paddingBottom: "60px",
        }}
      >
        <LeftMenu
          activePage={activePage}
          setActivePage={setActivePage}
          open={menuOpen}
          drawerWidth={drawerWidth}
        />
        <Box
          component="main"
          sx={{
            flexGrow: 1,
            p: 2,
            transition: "margin-left 0.3s",
            marginLeft: menuOpen ? `${drawerWidth}px` : 0,
          }}
        >
          <Grid container columns={12} rowSpacing={4} columnSpacing={4}>
            <Grid xs={12}>{renderPage()}</Grid>
          </Grid>
        </Box>
      </Box>
      <StatusBar
        connected={wsConnected}
        reconnect={() => {
          wsRef.current?.close();
          setTimeout(() => connectWebSocket(), 200);
        }}
      />
    </Box>
  );
}
