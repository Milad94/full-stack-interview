# Frontend conventions

React 19 + TypeScript (strict) + Vite. These are hard rules, not preferences — code that ignores
them will be sent back in review.

Detailed guidance lives in `.claude/skills/` and applies to any agent, Codex included. **Read the
relevant one before you write code:**

| Doing this | Read first |
| --- | --- |
| Any form, input, or validation rule | `.claude/skills/forms-and-validation/SKILL.md` |
| Any component, style, layout, table, or chart | `.claude/skills/mui-components/SKILL.md` |
| Any API call, cache, or mutation | `.claude/skills/data-fetching/SKILL.md` |

## The short version

- **Forms → react-hook-form.** No Formik, no per-field `useState`, no manual `onChange`.
- **Validation → yup**, via `@hookform/resolvers/yup`. Derive the type with `yup.InferType`.
  No zod. Server field errors get mapped back onto fields with `setError`.
- **Components and styling → MUI + emotion `sx`.** No Tailwind, no CSS files, no CSS modules,
  no second component library. Use theme tokens from `src/theme.ts`, not hardcoded px/hex.
- **Server state → TanStack Query.** No `useEffect` fetching, no Redux/Zustand/SWR. axios appears
  only inside a feature's `api.ts`, and only via the shared `apiClient`.

## Structure

```
src/
  lib/          apiClient.ts, queryClient.ts    — shared plumbing
  components/   cross-feature UI
  features/<x>/ api.ts, queries.ts, components  — one folder per feature
```

`src/features/health/` is a small working example of the whole pattern. Delete it once real
features exist.

## Non-negotiables

- `strict` TypeScript. No `any`, no `@ts-ignore`, no non-null `!` to silence a real problem.
- Render pending, error, and empty states for every piece of server data.
- `npm run typecheck` and `npm run lint` must pass before you call something done.
- Do not add dependencies beyond what's in `package.json` without saying why in the README.
