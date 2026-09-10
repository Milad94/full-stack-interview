import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import {
  AppBar,
  Box,
  Container,
  Drawer,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Stack,
  Toolbar,
  Typography,
} from '@mui/material'
import InsightsIcon from '@mui/icons-material/Insights'
import TuneIcon from '@mui/icons-material/Tune'

const DRAWER_WIDTH = 232

const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', icon: <InsightsIcon /> },
  { to: '/adjustments', label: 'Manual adjustments', icon: <TuneIcon /> },
]

export function AppLayout({ children }: { children: ReactNode }) {
  return (
    <Stack direction="row" sx={{ minHeight: '100vh' }}>
      <AppBar
        position="fixed"
        color="inherit"
        elevation={0}
        sx={{
          zIndex: (t) => t.zIndex.drawer + 1,
          borderBottom: '1px solid',
          borderColor: 'divider',
        }}
      >
        <Toolbar>
          <Typography variant="h6" component="span" fontWeight={600}>
            Accounting
          </Typography>
        </Toolbar>
        <Stack
          component="nav"
          direction="row"
          sx={{ display: { xs: 'flex', md: 'none' } }}
          aria-label="Main navigation"
        >
          {NAV_ITEMS.map((item) => (
            <ListItemButton
              key={item.to}
              component={NavLink}
              to={item.to}
              end={item.to === '/'}
              sx={{ '&.active': { bgcolor: 'action.selected' } }}
            >
              <ListItemText primary={item.label} />
            </ListItemButton>
          ))}
        </Stack>
      </AppBar>

      <Drawer
        variant="permanent"
        sx={{
          display: { xs: 'none', md: 'block' },
          width: DRAWER_WIDTH,
          flexShrink: 0,
          [`& .MuiDrawer-paper`]: {
            width: DRAWER_WIDTH,
            boxSizing: 'border-box',
          },
        }}
      >
        <Toolbar />
        <List>
          {NAV_ITEMS.map((item) => (
            <ListItemButton
              key={item.to}
              component={NavLink}
              to={item.to}
              end={item.to === '/'}
              sx={{
                '&.active': { bgcolor: 'action.selected', fontWeight: 600 },
              }}
            >
              <ListItemIcon>{item.icon}</ListItemIcon>
              <ListItemText primary={item.label} />
            </ListItemButton>
          ))}
        </List>
      </Drawer>

      <Box
        component="main"
        sx={{ flexGrow: 1, minWidth: 0, bgcolor: 'background.default' }}
      >
        <Toolbar />
        <Container maxWidth="xl" sx={{ py: 4, mt: { xs: 6, md: 0 } }}>
          {children}
        </Container>
      </Box>
    </Stack>
  )
}
