import { createTheme } from '@mui/material/styles'

export const theme = createTheme({
  palette: {
    mode: 'light',
    primary: { main: '#2f5d50' },
    secondary: { main: '#b4703a' },
    background: { default: '#f6f5f1', paper: '#ffffff' },
  },
  typography: {
    fontFamily: '"Inter", system-ui, -apple-system, "Segoe UI", sans-serif',
    h1: { fontSize: '1.75rem', fontWeight: 600 },
    h2: { fontSize: '1.375rem', fontWeight: 600 },
  },
  shape: { borderRadius: 10 },
  components: {
    MuiCard: {
      defaultProps: { elevation: 0 },
      styleOverrides: {
        root: { border: '1px solid rgba(0,0,0,0.08)' },
      },
    },
    MuiButton: {
      defaultProps: { disableElevation: true },
    },
  },
})
