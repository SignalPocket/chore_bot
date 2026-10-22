# Reusable Sprig page templates

For screen purposes, control behavior and task acceptance criteria, see [Interface specification](INTERFACE-SPEC.md).
`chore_pages.py` owns the reusable layout framework. `chore_workspace.py` supplies
screen data and existing protected callbacks. Domain rules, points, schedules,
permissions, and database changes stay in their existing modules.

## Configurable page types

| Type | Use | Configuration |
| --- | --- | --- |
| Dashboard | Household starting page | Purple frame, named action groups, top-right help |
| List | My/Pick up/Household/Manage chores, history, reviews, points | Content rows, page count, fixed paging, filters/search, common navigation |
| Detail | Chore cards and dated occurrences | Readable information, common buttons, named occasional-action dropdowns |
| Calendar | Day, week, month | Readable day rows with Details, date controls, scope controls |
| Form/settings | Reminders, selections, specialized editors | Named fields/choices, explicit Save/Apply where appropriate |
| Help | Context help and topic guide | Page-specific instructions and a Help topic dropdown |
| Confirmation | Deliberate consequential changes | Proposed change, Confirm/Cancel, safe return |

A `PageSpec` declares the type, title, help topic, accent, action groups, and
whether a screen retains native selectors. Register a source screen in
`SCREEN_KINDS`; uncommon editors default to the form type. `CHORE_ACTIONS`
configures visible occurrence buttons and the Responsibility / Schedule & details
menus. Changing a grouping must retain every original callback exactly once.

## Fixed slots

Every `PagePlan` assembles slots in this order, regardless of configuration order:

1. `header`: title, short context/notice, and the **?** accessory at top right.
2. `toolbar`: page-wide controls such as Add chore / Archive chore / Archived chores.
3. `content`: a readable framed list, detail fields, or calendar.
4. `footer`: page number/count and relevant timing information.
5. `paging`: fixed Previous/Next buttons; boundary buttons are disabled.
6. `actions`: view/date controls, search/filters, common actions, named dropdowns.
7. `navigation`: Back when applicable, Refresh, Dashboard; Dashboard stays last.
8. `undo`: temporary Undo controls, always last and combined into one row when possible.

The Dashboard has its own configured landing-page pattern: its help is beside the
title and Refresh belongs to My settings. Pop-up Discord modals keep their titles;
the launching page provides contextual help.

## Adding a page

Use the existing workspace View/adaptation path so permissions and recovery remain
in effect. Provide a title, a help topic, a serializable recovery context, and
callbacks using the existing guarded domain operations. Populate a PagePlan; do
not append extra controls to an already rendered page.

```python
from chore_pages import PageKind, PageSpec, PagePlan

spec = PageSpec(PageKind.LIST, 'Example list', help_topic='Pick up a chore')
plan = PagePlan(spec)
plan.heading(title_text, contextual_help_button)
plan.rows(toolbar_buttons, slot='toolbar')
plan.add_item(content_frame, slot='content')
plan.add_item(page_counter_text, slot='footer')
plan.paging(('Previous', 'Next'), available_paging_buttons)
plan.rows(filter_buttons)
refresh = plan.navigation(navigation_buttons)
if undo_button is not None:
    plan.undo(undo_button)
plan.commit(panel)
recovery.attach(panel, source, resume=refresh)
```

The example uses items/callbacks supplied by the screen. The production adapter
retains source callbacks instead of duplicating their permission or mutation rules.
Dropdown callbacks check ownership/access and invoke those same actions. Recovery
registers dropdowns, Undo, and existing buttons together. Expired controls restore
a fresh screen without replaying an old action.

## Capacity and validation

The complete page is counted before it is attached to a LayoutView. Nested section
accessories count too. The framework validates the 40-component maximum, 4,000 text
characters, row widths, and duplicate control instances. Oversized plans fail before
any item is attached, so a partial screen is never transmitted.

Only an explicitly optional decorative divider can be omitted. Content, help,
paging, actions, and Undo cannot be silently dropped. Dense chore-list capacity is
calculated from its header, tabs, filters, footer, navigation, and available Undo
controls before slicing the data. Saved page length is a maximum; smaller effective
pages preserve all records through paging and include their effective size in the
recovery bookmark.

The Refresh button is created and budgeted by the template. Recovery attaches its
handler to that existing button rather than increasing the rendered component count.

## Regression contracts

The offline suite covers page types and titles, help placement, common navigation,
preflight counting with nested sections, no partial rendering, private dropdown
callbacks, expired menu recovery, dense lists with both Undo types, complete paging,
and chore-name-to-details behavior. Run `python run_tests.py --suite focused --match
page_templates --match undo_dense` during layout work. Run the full suite and retain
its exact-source report before a release, as described in TESTING.md.
