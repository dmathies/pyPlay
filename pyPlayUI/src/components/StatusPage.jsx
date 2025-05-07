import {
  Box,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Divider,
} from "@mui/material";

import {useEffect} from "react";

export default function StatusPage({ statusData, wsRef }) {

  useEffect(() => {
    const interval = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ status: "update" }));
      }
    }, 250); // 250 ms

    return () => clearInterval(interval); // Clean up on unmount
  }, []);

  const activeCues = statusData?.["Active Cues"] || [];

  return (
      <Box p={2}>
        <Typography variant="h6" gutterBottom>
          Playback Status
        </Typography>
        <Divider sx={{mb: 2}}/>

        <Typography variant="body1">
          Status: {statusData?.status || "—"}
        </Typography>
        <Typography variant="body1">
          Active Cue Count: {statusData?.["Active Cue Count"] ?? 0}
        </Typography>

        {activeCues.length > 0 && (
            <TableContainer component={Paper} sx={{mt: 3}}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>ID</TableCell>
                    <TableCell>Name</TableCell>
                    <TableCell>Type</TableCell>
                    <TableCell>Time</TableCell>
                    <TableCell>State</TableCell>
                    <TableCell>Video State</TableCell>
                    <TableCell>Uniforms</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {activeCues.map((cue) => (
                      <TableRow key={cue.id}>
                        <TableCell>{cue.id}</TableCell>
                        <TableCell>{cue.Name}</TableCell>
                        <TableCell>{cue.type}</TableCell>
                        <TableCell>{cue.time?.toFixed(2) ?? "—"}</TableCell>
                        <TableCell>{cue.state}</TableCell>
                        <TableCell>{cue.video_state}</TableCell>
                        <TableCell>
                          {cue.uniforms &&
                              Object.entries(cue.uniforms).map(([key, val]) => (
                                  <div key={key}>
                                    {key}: {val}
                                  </div>
                              ))}
                        </TableCell>
                      </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
        )}
      </Box>
  );
}