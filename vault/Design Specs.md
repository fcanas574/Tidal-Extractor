# Design Specs

Inventory of design documents and implementation plans in `docs/superpowers/`.

**See:** [[Work Log]] · [[Roadmap]]

## Location

```
docs/superpowers/
├── specs/    # Design documents (the "what" and "why")
└── plans/    # Implementation plans (the "how", step-by-step)
```

These follow the superpowers workflow: **brainstorm → spec → plan → execute**.

## Specs (`docs/superpowers/specs/`)

| Date | Spec | Status |
|------|------|--------|
| 2026-05-17 | `tidal-extractor-design.md` | ✅ Built — core app |
| 2026-05-18 | `link-paste-design.md` | ✅ Built — URL resolve |
| 2026-05-18 | `queue-management-design.md` | ✅ Built — queue CRUD |
| 2026-06-17 | `tidal-extractor-enhancements-design.md` | ✅ Built |
| 2026-06-19 | `search-improvements-design.md` | ✅ Built — scoring + enrichment |
| 2026-06-23 | `dj-search-filters-design.md` | ✅ Built — see [[DJ Filters]] |
| 2026-06-23 | `search-pagination-design.md` | ✅ Built — see [[Search Subsystem]] |

## Plans (`docs/superpowers/plans/`)

| Date | Plan | Status |
|------|------|--------|
| 2026-05-17 | `tidal-extractor.md` | ✅ Executed |
| 2026-05-18 | `link-paste.md` | ✅ Executed |
| 2026-05-18 | `queue-management.md` | ✅ Executed |
| 2026-06-17 | `tidal-extractor-enhancements-impl.md` | ✅ Executed |
| 2026-06-19 | `search-improvements-plan.md` | ✅ Executed |
| 2026-06-23 | `dj-search-filters-design.md` *(in specs)* | ✅ Executed |
| 2026-06-23 | `search-pagination-plan.md` | ✅ Executed — see [[Search Subsystem]] |

## Plan Structure (example: search-pagination-plan.md)

The pagination plan is the most recent and a good template. Each plan has:
- **Goal** + **Architecture** summary
- **Global Constraints** (invariants that must hold)
- **Tasks** broken into steps with checkboxes (`- [ ]`)
- Each step: Files to modify, Interfaces (consumes/produces), exact code
- **Plan Self-Review** (spec coverage, placeholder scan, type consistency)
- Two execution options: subagent-driven (recommended) or inline

## Workflow Recommendation

For new features, follow the established pattern:
1. **Brainstorm** requirements + design (use the brainstorming skill)
2. **Write a spec** in `docs/superpowers/specs/{date}-{feature}-design.md`
3. **Write a plan** in `docs/superpowers/plans/{date}-{feature}-plan.md`
4. **Execute** via subagent-driven-development or executing-plans skills
5. **Write a handoff** in `handoff/Session-{date}-{feature}.md` on completion

See the `superpowers` plugin skills for the structured workflows.

## Untracked Docs

> ⚠️ `docs/superpowers/specs/2026-06-23-search-pagination-design.md` and `docs/superpowers/plans/2026-06-23-search-pagination-plan.md` are **untracked** in git. Commit them with the feature work.

## See Also

- [[Work Log]] · [[Roadmap]] · [[Active Work]]
