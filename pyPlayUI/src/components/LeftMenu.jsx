import { Drawer, List, ListItem, ListItemText, Toolbar } from "@mui/material";

export default function LeftMenu({ activePage, setActivePage, open, drawerWidth }) {
  return (
      <Drawer
          variant="persistent"
          anchor="left"
          open={open}
          sx={{
            flexShrink: 0,
            '& .MuiDrawer-paper': {
              width: drawerWidth,
              boxSizing: 'border-box',
            },
          }}
      >
        <Toolbar /> {/* Space for AppBar */}
        <List>
          {["status", "perspective", "shutters"].map((text) => (
              <ListItem
                  button
                  key={text}
                  selected={activePage === text}
                  onClick={() => setActivePage(text)}
              >
                <ListItemText primary={text.charAt(0).toUpperCase() + text.slice(1)} />
              </ListItem>
          ))}
        </List>
      </Drawer>
  );
}
