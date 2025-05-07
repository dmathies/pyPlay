import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createTheme, ThemeProvider } from '@mui/material/styles';
import './index.css'
import App from './App.jsx'

const theme = createTheme();

createRoot(document.getElementById('root')).render(
    <ThemeProvider theme={theme}>
      <App />
    </ThemeProvider>
)
