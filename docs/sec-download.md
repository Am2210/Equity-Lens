# Manual SEC JSON download

For an exact replay of the first snapshot, use the packaged archive described in the README. To build from newly saved SEC responses, open each URL in a browser and save the raw JSON using the listed path. Start with an empty cache directory if rebuilding from a new set of files.

- Save [SEC ticker mapping](https://www.sec.gov/files/company_tickers.json) as `data/raw/company_tickers.json`.
- Save [Visa Company Facts](https://data.sec.gov/api/xbrl/companyfacts/CIK0001403161.json) as `data/raw/companyfacts/CIK0001403161.json`.
- Save [Mastercard Company Facts](https://data.sec.gov/api/xbrl/companyfacts/CIK0001141391.json) as `data/raw/companyfacts/CIK0001141391.json`.
- Save [PayPal Company Facts](https://data.sec.gov/api/xbrl/companyfacts/CIK0001633917.json) as `data/raw/companyfacts/CIK0001633917.json`.
- Save [Visa submissions](https://data.sec.gov/submissions/CIK0001403161.json) as `data/raw/submissions/CIK0001403161.json`.
- Save [Mastercard submissions](https://data.sec.gov/submissions/CIK0001141391.json) as `data/raw/submissions/CIK0001141391.json`.
- Save [PayPal submissions](https://data.sec.gov/submissions/CIK0001633917.json) as `data/raw/submissions/CIK0001633917.json`.

Save the JSON response itself and preserve the filename extension. Run the following command once the files are in place.

```powershell
.\.venv\Scripts\python.exe -m src.equitylens --offline
```

The initial run needed only these seven files. Submissions history rotates into archive files. If a later cache requires one for the scoped history, the offline run prints its exact SEC URL and destination.
