"""
CDSCO Recall Scraper — Runs as a daily Railway cron job.
Fetches recall notices from cdsco.gov.in and writes structured records
to the cdsco_recalls table in Supabase.

Usage (Railway cron service):
  python -m scripts.scrape_cdsco_recalls
"""
import asyncio
import re
import httpx
from datetime import datetime, timezone
from bs4 import BeautifulSoup


CDSCO_RECALLS_URL = "https://cdsco.gov.in/opencms/opencms/en/Alerts/Drugs-Alerts/"
# Fallback: CDSCO also publishes recall notices at these URLs
CDSCO_FALLBACK_URLS = [
    "https://cdsco.gov.in/opencms/opencms/en/Alerts/Not-of-Standard-Quality-Drugs/",
    "https://cdsco.gov.in/opencms/opencms/en/Alerts/Spurious-Drugs/",
]


async def scrape_cdsco_recalls() -> list[dict]:
    """
    Scrape the CDSCO alerts pages for drug recall notices.
    Returns a list of structured recall records.
    """
    records = []

    async with httpx.AsyncClient(
        timeout=30.0,
        follow_redirects=True,
        headers={
            "User-Agent": "PharmaTrace/1.0 (Drug Safety Monitor; contact@pharmatrace.app)"
        }
    ) as client:
        for url in [CDSCO_RECALLS_URL] + CDSCO_FALLBACK_URLS:
            try:
                resp = await client.get(url)
                if resp.status_code != 200:
                    print(f"[CDSCO] Failed to fetch {url}: HTTP {resp.status_code}")
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")

                # CDSCO pages typically list recalls in tables or unordered lists
                # Strategy 1: Parse tables
                for table in soup.find_all("table"):
                    rows = table.find_all("tr")
                    headers = []
                    for th in rows[0].find_all(["th", "td"]) if rows else []:
                        headers.append(th.get_text(strip=True).lower())

                    for row in rows[1:]:
                        try:
                            cells = row.find_all("td")
                            if len(cells) < 3:
                                continue

                            record = _parse_table_row(cells, headers, url)
                            if record and record.get("drug_name"):
                                records.append(record)
                        except Exception as e:
                            records.append({"error": str(e), "raw_html": str(row)[:1000], "source": url})

                # Strategy 2: Parse list items with PDF links (common CDSCO format)
                for link in soup.find_all("a", href=True):
                    try:
                        href = link["href"]
                        text = link.get_text(strip=True)
                        if href.endswith(".pdf") and any(
                            kw in text.lower()
                            for kw in ["recall", "not of standard", "spurious", "alert", "batch"]
                        ):
                            record = _parse_alert_link(text, href, url)
                            if record:
                                records.append(record)
                    except Exception as e:
                        records.append({"error": str(e), "raw_html": str(link)[:1000], "source": url})

            except Exception as e:
                print(f"[CDSCO] Error scraping {url}: {e}")
                continue

    # Deduplicate by drug_name + batch_no
    seen = set()
    unique = []
    for r in records:
        if "error" in r:
            unique.append(r)
            continue
            
        key = (r.get("drug_name", "").lower(), r.get("batch_no", "").lower())
        if key not in seen:
            seen.add(key)
            unique.append(r)

    print(f"[CDSCO] Scraped {len(unique)} unique recall records")
    return unique


def _parse_table_row(cells: list, headers: list, source_url: str) -> dict:
    """Extract a recall record from a table row."""
    record = {
        "drug_name": "",
        "batch_no": "",
        "manufacturer": "",
        "reason": "",
        "date_issued": None,
        "url": source_url,
    }

    for i, cell in enumerate(cells):
        text = cell.get_text(strip=True)
        header = headers[i] if i < len(headers) else ""

        if any(k in header for k in ["drug", "name", "product"]):
            record["drug_name"] = text
        elif any(k in header for k in ["batch", "lot", "b.no"]):
            record["batch_no"] = text
        elif any(k in header for k in ["manufacturer", "firm", "company"]):
            record["manufacturer"] = text
        elif any(k in header for k in ["reason", "ground", "category"]):
            record["reason"] = text
        elif any(k in header for k in ["date", "month"]):
            record["date_issued"] = _parse_date(text)

    # Fallback: if no header matched, use positional heuristic
    if not record["drug_name"] and len(cells) >= 3:
        record["drug_name"] = cells[1].get_text(strip=True)
        record["batch_no"] = cells[2].get_text(strip=True) if len(cells) > 2 else ""
        record["manufacturer"] = cells[3].get_text(strip=True) if len(cells) > 3 else ""
        record["reason"] = cells[4].get_text(strip=True) if len(cells) > 4 else "Not of Standard Quality"

    return record


def _parse_alert_link(text: str, href: str, source_url: str) -> dict:
    """Extract a recall record from an alert PDF link text."""
    # Common format: "Alert regarding Batch No. XYZ of Drug ABC manufactured by..."
    drug_match = re.search(r"(?:drug|regarding|for)\s+(.+?)(?:\s+manufactured|\s+batch|\s*$)", text, re.I)
    batch_match = re.search(r"batch\s*(?:no\.?|number)\s*[:\s]*([A-Z0-9\-/]+)", text, re.I)
    mfr_match = re.search(r"manufactured\s+by\s+(.+?)(?:\s*$|\s*,)", text, re.I)

    full_url = href if href.startswith("http") else f"https://cdsco.gov.in{href}"

    return {
        "drug_name": drug_match.group(1).strip() if drug_match else text[:100],
        "batch_no": batch_match.group(1).strip() if batch_match else "",
        "manufacturer": mfr_match.group(1).strip() if mfr_match else "",
        "reason": "CDSCO Safety Alert",
        "date_issued": None,
        "url": full_url,
    }


def _parse_date(text: str):
    """Try to parse an Indian-format date string."""
    for fmt in ["%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%B %Y", "%b %Y", "%Y-%m-%d"]:
        try:
            return datetime.strptime(text.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


async def persist_to_supabase(records: list[dict], source_run_id: str = None):
    """Write scraped records to Supabase, skipping duplicates."""
    import sys
    sys.path.insert(0, ".")

    from services.supabase import get_supabase
    db = get_supabase()

    if not db.available:
        print("[CDSCO] Supabase not configured — skipping persistence")
        from services.data_governance import finish_source_run
        await finish_source_run(source_run_id, status="failed", records_seen=len(records), error_summary="Supabase not configured")
        return

    inserted = 0
    errors = 0
    for r in records:
        if "error" in r:
            try:
                await db.insert("scrape_errors", {
                    "source": r["source"],
                    "raw_html": r["raw_html"],
                    "error_message": r["error"]
                })
                errors += 1
            except:
                pass
            continue
            
        try:
            await db.insert("cdsco_recalls", r, upsert=True)
            inserted += 1

            # Pipeline C: Seed the vernacular_aliases table as a side-effect
            if r.get("drug_name"):
                try:
                    from services.vernacular_resolver import seed_from_cdsco_row
                    await seed_from_cdsco_row({
                        "brand_name": r.get("drug_name"),
                        "generic_name": r.get("drug_name"),  # Best we have from recalls
                        "active_ingredients": [r.get("drug_name")]
                    })
                except Exception:
                    pass  # Non-critical
        except Exception as e:
            print(f"[CDSCO] Upsert failed for {r.get('drug_name')}: {e}")

    print(f"[CDSCO] Upserted {inserted} recalls. Logged {errors} parse errors. Aliases seeded.")
    from services.data_governance import finish_source_run
    await finish_source_run(source_run_id, status="partial" if errors else "succeeded", records_seen=len(records), records_upserted=inserted)


async def main():
    print(f"[CDSCO] Starting recall scrape at {datetime.now(timezone.utc).isoformat()}")
    from services.data_governance import start_source_run, finish_source_run
    run_id = await start_source_run("CDSCO alerts", CDSCO_RECALLS_URL)
    try:
        records = await scrape_cdsco_recalls()
        if records:
            await persist_to_supabase(records, run_id)
        else:
            print("[CDSCO] No records scraped — check if CDSCO page structure has changed")
            await finish_source_run(run_id, status="partial", error_summary="No records parsed; source layout may have changed")
    except Exception as exc:
        await finish_source_run(run_id, status="failed", error_summary=str(exc)[:1000])
        raise
    print(f"[CDSCO] Done at {datetime.now(timezone.utc).isoformat()}")


if __name__ == "__main__":
    asyncio.run(main())
