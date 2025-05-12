import { createTheme, ThemeProvider, CssBaseline, useMediaQuery } from '@mui/material';
import { useMemo } from 'react';
import App from '../App';

export default function ThemeWrapper() {
  const prefersDarkMode = useMediaQuery('(prefers-color-scheme: dark)');

  const theme = useMemo(() => createTheme({
    palette: {
      mode: prefersDarkMode ? 'dark' : 'light',
    },
  }), [prefersDarkMode]);

  return (
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <App />
      </ThemeProvider>
  );
}
