import { Box, Typography, Button } from "@mui/material";

  export default function StatusBar({ connected, reconnect }) {

  return (
      <Box sx={{
        position: 'fixed',
        bottom: 0,
        left: 0,

        width: "100%",
        p: 1,
        bgcolor: connected ? "#e0ffe0" : "#ffe0e0",
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center"
      }}>
        <Typography variant="body2">
          {connected ? "Connected" : "Disconnected"}
        </Typography>

        {!connected && (
            <Button size="small" variant="outlined" onClick={reconnect}>
              Reconnect
            </Button>
        )}
      </Box>
  );
}
