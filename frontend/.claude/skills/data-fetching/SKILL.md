---
name: data-fetching
description: How to talk to the Django API in this frontend — TanStack Query for all server state, axios only inside a feature's api.ts. Load before writing any fetch, useEffect-based loading, mutation, or cache invalidation.
---

# Data fetching

**All server state goes through TanStack Query.** No `useEffect` + `useState` fetching, no
`fetch()` in components, no hand-rolled loading booleans, no global store mirroring server data.

## Layering

Every feature follows the same three files (see `src/features/health/` for a working example):

```
src/features/<feature>/
  api.ts       # typed request functions + response interfaces. The only place axios appears.
  queries.ts   # query keys + useQuery/useMutation hooks. The only place TanStack Query appears.
  <X>Page.tsx  # components. Call the hooks; never call api.ts directly.
```

## Rules

- Use the shared `apiClient` from `@/lib/apiClient` — never `axios` directly, never a raw URL.
- Type the response on the request, not at the call site: `apiClient.get<Invoice[]>(...)`.
  Never `any`; `unknown` plus narrowing if the shape is genuinely unknown.
- Export a `<feature>Keys` object rather than scattering array literals:

  ```ts
  export const invoiceKeys = {
    all: ['invoices'] as const,
    list: (filters: InvoiceFilters) => [...invoiceKeys.all, 'list', filters] as const,
    detail: (id: number) => [...invoiceKeys.all, 'detail', id] as const,
  }
  ```

- Server-driven lists put their filter/page state **in the query key**, so pagination and
  filtering are cache-correct. Reach for `placeholderData: keepPreviousData` so the table
  doesn't blank out between pages.
- Mutations invalidate, they don't hand-patch — `queryClient.invalidateQueries({ queryKey: invoiceKeys.all })`
  in `onSuccess`. Only reach for `setQueryData` when you have a reason to say out loud.
- Render all three states. `isPending` gets a `<Skeleton>`, `error` gets an `<Alert>` whose text
  comes from `toApiError(error).message`, empty results get an explicit empty state — not a bare
  table with no rows.
- Polling (e.g. watching a sync finish) is `refetchInterval`, not a `setInterval`.

## Do not

- Do not add another data-fetching or state library (SWR, Redux, Zustand, RTK Query).
- Do not disable `staleTime` globally or set `retry: false` project-wide to work around a bug.
