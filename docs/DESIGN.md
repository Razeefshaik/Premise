# Interface rationale

Premise is an architecture-review workbench. The primary question is whether engineering
guarantees still hold, so the health board leads the page; the analyst and accountability
gaps support investigation. The assessment page presents the verdict, changed inputs,
dependency path, complete remedies, and source evidence in that order.

Palette: cloud `#f4f7fa`, paper `#ffffff`, slate `#203447`, steel blue `#175a81`,
green `#24634d`, and warning amber `#785412`. Color always accompanies a written state.
Cambria/Georgia gives the main question an editorial voice; Segoe UI/Tahoma keeps dense
evidence readable. Consolas is reserved for code and exact identifiers.

The desktop uses a broad evidence table and a narrow analyst rail. On smaller screens they
stack, with horizontally scrollable tables. The dependency graph is the distinctive visual
element; the surrounding layout stays quiet. No invented counts, progress, or model results
appear. Empty and unavailable states tell the user how to get a ready graph.

The implemented board avoids a generic grid of KPI cards because scores are not part of
the verdict model. PageRank orders the guarantees but never replaces prerequisite health.
Forms have labels, loading and error feedback, keyboard focus styles, and no automatic
motion. Mermaid's readable text remains available when its CDN is unavailable.

Analyst responses label model summaries separately from deterministic prose. Model IDs and
explicit health words are checked against tool rows; other prose claims are not verified.
Manual attestation evidence displays the person's name and UTC dates rather than epoch
milliseconds. The lexical comparison derives its query terms from changed fact identifiers,
so it applies beyond the flagship S1 demonstration.
