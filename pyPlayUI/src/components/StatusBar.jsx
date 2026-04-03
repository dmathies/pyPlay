import { Box, Typography, Button } from "@mui/material";
import { useTheme } from '@mui/material';


  export default function StatusBar({ connected, reconnect }) {

    const theme = useTheme();
  return (
      <Box sx={{
        position: 'fixed',
        bottom: 0,
        left: 0,

        width: "100%",
        p: 1,
        bgcolor: connected ? theme.palette.success.main : theme.palette.error.main,
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
