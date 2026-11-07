# Holo grounding check on Odoo 20 — 2026-11-07

Each YAML `element` description sent to `holo4-35b-a3b` (thinking off, `locate` tool, 1024-px image) on a
full-resolution screenshot of `h-companion.odoo.com`, compared with the control's DOM rect.
Coverage: **yes** = box centre on the control and ≥50 % of the box on it; **partial** = overlaps; **no** = elsewhere.
Boxes are in CSS px of a 1512×771 viewport. Rows marked *rewrite* are the replacement wording now in the YAMLs.

| Screen | Description | Found | Covers control | Latency | Holo saw | Box | DOM rect |
| --- | --- | --- | --- | --- | --- | --- | --- |
| pipeline | the New button at the top-left of the CRM pipeline, left of the Generate dropdown | yes | yes | 1.72 s | New button at top-left of CRM pipeline | [15, 62, 50, 25] | [16, 56, 51, 33] |
| pipeline | the pipeline card titled Zz Test Guide | yes | yes | 0.82 s | Pipeline card titled Zz Test Guide | [392, 191, 322, 102] | [382, 183, 334, 116] |
| pipeline | the column header New at the top of the first pipeline column | yes | partial | 0.74 s | Column header "New" at top of first pipeline column | [20, 136, 36, 21] | [16, 118, 284, 25] |
| pipeline | the column header Qualified at the top of the second pipeline column | yes | yes | 0.78 s | Qualified column header | [383, 126, 88, 19] | [382, 118, 284, 25] |
| pipeline | the Pipeline breadcrumb link, or the CRM app name, at the top-left of the Odoo page | yes | yes | 0.72 s | CRM app name at top-left | [39, 15, 47, 19] | [47, 10, 36, 26] |
| pipeline | the colored Odoo logo (home menu) at the far top-left of the Odoo top bar, left of the app name | yes | yes | 1.01 s | colored Odoo logo | [15, 11, 35, 25] | [1, 10, 44, 26] |
| pipeline | the CRM app icon or menu entry | yes | yes | 0.71 s | CRM menu entry in top navigation bar | [45, 19, 41, 14] | [1, 10, 82, 26] |
| quick-create | the Opportunity's Name field (second line, briefcase icon) of the quick-create card in the New column | yes | yes | 1.52 s | Opportunity's Name field with briefcase icon | [60, 237, 277, 14] | [63, 229, 272, 24] |
| quick-create | the Contact field (first line, person icon) of the quick-create card | yes | yes | 1.12 s | Contact field with person icon | [60, 200, 280, 16] | [63, 197, 272, 24] |
| quick-create | the Add button at the bottom-left of the quick-create card | yes | yes | 0.9 s | Add button at bottom-left of quick-create card | [26, 359, 53, 32] | [31, 357, 48, 33] |
| form | the Activity button at the top of the chatter panel, right of Log note | yes | yes | 1.49 s | Activity button | [1194, 111, 73, 29] | [1196, 108, 72, 33] |
| form | the Log note button at the top of the chatter panel, between Send message and Activity | yes | yes | 0.91 s | Log note button | [1108, 109, 85, 30] | [1113, 108, 80, 33] |
| form | the Send message button at the top of the chatter panel | yes | yes | 0.91 s | Send message button | [987, 109, 116, 30] | [990, 108, 119, 33] |
| form | the Contact field (placeholder Select or create a contact...) in the opportunity form, under Expected Revenue | yes | yes | 0.7 s | Contact field with placeholder text | [124, 326, 296, 13] | [127, 322, 313, 24] |
| form | the Expected Revenue amount field (0.00 €) under the opportunity title | yes | no | 0.81 s | Expected Revenue amount field showing 0.00 | [278, 277, 86, 16] | [41, 270, 209, 28] |
| form | the Expected Revenue amount under the opportunity title | yes | yes | 0.73 s | Expected Revenue amount 12,000.00 € | [38, 274, 124, 19] | [41, 270, 209, 28] |
| form | the Qualified stage in the stage bar at the top of the opportunity form | yes | yes | 0.75 s | Qualified stage button in stage bar | [702, 111, 118, 28] | [695, 111, 129, 27] |
| form | the Won button at the top-left of the opportunity form | yes | yes | 0.73 s | Won button at top-left of opportunity form | [15, 111, 51, 29] | [16, 108, 51, 33] |
| form | the stage bar at the top of the form showing New, Qualified, Proposition, Won | yes | yes | 1.09 s | Stage bar with New, Qualified, Proposition, Won options | [620, 109, 351, 29] | [618, 108, 356, 33] |
| form | the chatter panel on the right of the form, with Send message, Log note and Activity | yes | yes | 0.74 s | Send message, Log note, Activity buttons | [981, 106, 531, 42] | [982, 108, 530, 663] |
| form | the Pipeline breadcrumb link, or the CRM app name, at the top-left of the Odoo page | yes | yes | 0.69 s | Pipeline breadcrumb link | [67, 19, 33, 12] | [47, 10, 90, 62] |
| activity-dialog | the To-Do chip (check-mark icon) at the top-left of the Schedule Activity dialog | yes | yes | 1.54 s | To-Do chip with check-mark icon | [464, 234, 76, 25] | [463, 233, 73, 27] |
| activity-dialog | the summary text field (tag icon, prefilled with To-Do) at the top of the Schedule Activity dialog | yes | yes | 1.3 s | summary text field with To-Do prefilled | [463, 285, 599, 19] | [486, 280, 563, 24] |
| activity-dialog | the due date field (calendar icon) under the summary in the Schedule Activity dialog | yes | yes | 0.74 s | calendar icon for due date field | [464, 322, 65, 18] | [486, 317, 563, 24] |
| activity-dialog | the Save button at the bottom-left of the Schedule Activity dialog | yes | yes | 0.94 s | Save button in Schedule Activity dialog | [463, 546, 56, 34] | [463, 549, 54, 33] |
| activity-dialog | the Mark Done button at the bottom of the Schedule Activity dialog, right of Save | yes | yes | 0.74 s | Mark Done button in Schedule Activity dialog | [520, 546, 100, 37] | [524, 549, 93, 33] |
| form *rewrite* | the Expected Revenue amount field (large number with €) under the opportunity title | yes | yes | 1.46 s | Expected Revenue amount field with € symbol | [38, 270, 124, 23] | [41, 270, 209, 28] |
| form *rewrite* | the Contact field, right of the Contact label, in the opportunity form under Expected Revenue | yes | yes | 0.97 s | Contact field with Acme Corp | [125, 330, 86, 6] | [127, 322, 313, 24] |
| pipeline *rewrite* | the word New, title of the first pipeline column, at the left above the grey progress bar | yes | partial | 1.42 s | New title of pipeline column | [20, 134, 38, 20] | [16, 118, 284, 25] |
| pipeline *rewrite* | the word Qualified, title of the second pipeline column, above its progress bar | yes | yes | 0.82 s | Qualified title of second pipeline column | [383, 127, 86, 16] | [382, 118, 284, 25] |
| composer+dirty | the 'Log an internal note...' text box in the chatter | yes | yes | 1.99 s | Log an internal note... text box | [1037, 182, 384, 29] | [1031, 174, 427, 40] |
| composer+dirty | the Log button just under the internal note composer in the chatter | yes | yes | 0.94 s | Log button in chatter | [1030, 234, 48, 20] | [1030, 227, 41, 28] |
| composer+dirty | the cloud-shaped save icon right of the breadcrumb Pipeline / Zz Test Guide at the top-left | yes | yes | 0.82 s | cloud-shaped save icon | [216, 62, 29, 31] | [212, 61, 28, 31] |

Outcome: the two misses were rewritten (amount value removed from the Expected Revenue description; column
titles described as words). The "New" title stays ~10 px low because the Odoo onboarding tour pin covers it;
it is only used for an underline annotation. Dismiss the tour on the demo database.
