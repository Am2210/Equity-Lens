# EquityLens showcase

Run the app and open the overview before the demo. The frozen source build supports the walkthrough offline after dependencies are installed.

## FAQ

### 1. How do you avoid comparing the wrong fiscal periods?

The pipeline anchors each year to the original annual accession in SEC submissions. It validates the reporting date and checks that income-statement and cash-flow facts cover the correct duration. Balance-sheet facts use an instant. The UI displays dates because Visa’s September close differs from the December closes of Mastercard and PayPal. YoY calculations use contiguous periods within one issuer.

### 2. What happens when XBRL tags change or a later filing revises a value?

Approved mappings are scoped by issuer and metric. A source value carries its concept, unit, context dates and accession. The main analytics uses original 10-Ks. The research warehouse preserves eligible later comparative observations independently. It can return both $6.340 billion and $5.797 billion for PayPal FY2021 operating cash flow and identify their respective filing records. Missing or conflicting inputs can result in null.

### 3. Where does the AI come in, and how do you measure grounding?

SQLite FTS5 retrieves authored filing text and DuckDB supplies approved numerical results. Python rules assemble typed answers and attach sources. The current mode makes zero LLM calls. Tests check expected numbers, claim classes, SEC accessions, filing dates, and exact excerpt placement. A later model could summarize these vetted inputs after separate tests for grounding, abstention and prompt injection.

### 4. How can another analyst reproduce your results?

The repository includes pinned Python dependencies and compact source archives. The offline build verifies SHA-256 manifests for the original JSON and HTML before whole-snapshot regeneration. The final audit reproduced all 16 ingestion and analytics exports and the SQLite index byte-for-byte on the tested machine. The app reads local stores without needing an SEC contact or inference service.

### 5. What should someone conclude from the DCF screen?

It shows how the modeled present value of a free-cash-flow proxy changes with forecast growth, horizon, discount rate and terminal growth. The model requires the discount rate to exceed terminal growth. A full enterprise-to-equity bridge, funding and other claim adjustments, and diluted shares lie outside the scenario. The defensible use is illustration of sensitivity under the named assumptions.
