---
name: mui-components
description: How to build UI in this frontend — MUI components only, emotion via the sx prop, theme tokens instead of hardcoded values, DataGrid for tables and x-charts for charts. Load before writing any component, style, or layout.
---

# UI components

**MUI is the component library. Emotion is the styling engine, used through MUI.** Do not
introduce Tailwind, Bootstrap, plain CSS files, CSS modules, or another component kit.

## Rules

- Build from MUI primitives: `Stack`, `Box`, `Grid`, `Card`, `Typography`, `TextField`, `Button`,
  `Dialog`, `Alert`, `Skeleton`, `Chip`. Reach for a raw `<div>` only when no MUI component fits.
- Style with the `sx` prop. For a component you restyle repeatedly, use `styled()` from
  `@mui/material/styles`. Never a `.css` file, never inline `style={{}}`.
- **Use theme tokens, not literals.** `sx={{ p: 2, color: 'text.secondary', bgcolor: 'background.paper' }}`
  — not `padding: '16px'` or `color: '#666'`. Spacing is the theme's 8px scale. If you need a new
  color or radius, add it to `src/theme.ts` instead of hardcoding it at the call site.
- Layout with `Stack` (`spacing`, `direction`) and `Grid`. Don't hand-roll flexbox in `sx` when
  `Stack` says it more clearly.
- Text is always `<Typography>` with a variant. No bare strings styled with `fontSize`.
- Tables: `@mui/x-data-grid` (already installed) for anything paginated/sortable/filterable. Plain
  `<Table>` is fine for a short static list. For server-side data, set
  `paginationMode="server"` / `filterMode="server"` and drive it off the query — don't pull the
  whole table into the browser and paginate client-side.
- Charts: `@mui/x-charts` (`BarChart`, `LineChart`, `PieChart`). Don't add recharts or chart.js.
- Feedback states: `<Skeleton>` while pending, `<Alert severity="error">` on failure,
  `<Snackbar>` for transient success. Never a bare "Loading..." string.
- Icons come from `@mui/icons-material`.

## Do not

- Do not use `!important`, or fight the theme with high-specificity selectors.
- Do not set `elevation` shadows ad hoc — this theme uses flat, bordered cards by default.
- Do not build a custom modal, select, or date input when MUI ships one.
