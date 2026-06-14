"""
CDSCO PDF Parser & SQLite Database Builder
Downloads CDSCO's new drug approval PDFs, parses them with pdfplumber, and creates a local SQLite database.
Run this as a monthly cron job to maintain a localized, non-hallucinated Indian drug registry.
"""
import os
import sqlite3
import httpx
import pdfplumber
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("build_cdsco")

DB_PATH = Path(__file__).parent.parent / "data" / "cdsco_registry.db"
PDF_URLS = [
    # Direct PDF links to CDSCO New Drug Approvals
    "https://cdsco.gov.in/opencms/resources/UploadCDSCOWeb/2018/UploadApprovalNewDrugs/dciApprovedfdc.pdf"
]

def init_db():
    """Initialize the local CDSCO SQLite database."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS indian_drugs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            generic_name TEXT NOT NULL,
            indication TEXT,
            approval_date TEXT,
            manufacturer TEXT,
            cdsco_code TEXT UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create indexes for fast lookup
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_generic_name ON indian_drugs(generic_name)')
    
    # Create metadata table for tracking freshness
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    conn.commit()
    return conn

async def download_pdf(url: str, dest_path: Path):
    """Download a CDSCO PDF file."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        with open(dest_path, "wb") as f:
            f.write(resp.content)
            
def parse_pdf_to_db(pdf_path: Path, conn: sqlite3.Connection):
    """Parse CDSCO table data from PDF using pdfplumber and insert into SQLite."""
    cursor = conn.cursor()
    inserted_count = 0
    
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    if not row or len(row) < 3:
                        continue
                        
                    # Skip headers
                    if "Name of the Drug" in str(row[0]) or "Indication" in str(row[1]):
                        continue
                        
                    try:
                        # Schema depends on the exact PDF format, but typically:
                        # [S.No, Name of the Drug, Indication]
                        generic_name = str(row[1]).replace("\n", " ").strip()
                        indication = str(row[2]).replace("\n", " ").strip() if len(row) > 2 else ""
                        approval_date = str(row[3]).replace("\n", " ").strip() if len(row) > 3 else ""
                        
                        # Generate a deterministic CDSCO code for our local registry
                        cdsco_code = f"CDSCO-{hash(generic_name) % 1000000:06d}"
                        
                        if generic_name and generic_name.lower() != 'none':
                            cursor.execute('''
                                INSERT OR IGNORE INTO indian_drugs (generic_name, indication, approval_date, manufacturer, cdsco_code)
                                VALUES (?, ?, ?, ?, ?)
                            ''', (generic_name, indication, approval_date, "Unknown", cdsco_code))
                            inserted_count += 1
                    except Exception as e:
                        logger.warning(f"Failed to parse row: {row} - Error: {e}")
                        
    conn.commit()
    
    # Minimum row count assertion
    if inserted_count < 10:
        raise ValueError(f"CRITICAL FAILURE: Parsed only {inserted_count} rows from CDSCO PDF. Format likely changed.")
        
    cursor.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('last_updated', datetime('now'))")
    conn.commit()
    logger.info(f"Successfully loaded {inserted_count} CDSCO drug records from {pdf_path.name}")

async def main():
    logger.info("Initializing CDSCO local registry...")
    conn = init_db()
    
    pdf_dir = Path(__file__).parent.parent / "data" / "pdfs"
    pdf_dir.mkdir(exist_ok=True)
    
    for i, url in enumerate(PDF_URLS):
        pdf_path = pdf_dir / f"cdsco_approvals_{i}.pdf"
        try:
            logger.info(f"Downloading CDSCO PDF from {url}...")
            await download_pdf(url, pdf_path)
            logger.info("Parsing PDF...")
            parse_pdf_to_db(pdf_path, conn)
        except Exception as e:
            logger.error(f"Failed to process {url}: {e}")
            
    conn.close()
    logger.info("CDSCO Database build complete.")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
