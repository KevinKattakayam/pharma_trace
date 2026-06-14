"""
DrugBank XML Parser & SQLite Database Builder
Parses the free DrugBank Community Edition XML dataset into a localized SQLite cache.
Extracts drug names, generic names, interactions, and side effects.
Requires the 'full database.xml' downloaded from go.drugbank.com.
"""
import os
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("build_drugbank")

DB_PATH = Path(__file__).parent.parent / "data" / "drugbank_ce.db"
XML_PATH = Path(__file__).parent.parent / "data" / "full_database.xml"

# DrugBank uses an XML namespace
NS = {'db': 'http://www.drugbank.ca'}

def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create Drugs Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS drugs (
            drugbank_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            state TEXT
        )
    ''')
    
    # Create Interactions Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            drug_a_id TEXT,
            drug_b_id TEXT,
            drug_b_name TEXT,
            description TEXT,
            FOREIGN KEY(drug_a_id) REFERENCES drugs(drugbank_id)
        )
    ''')

    # Indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_drug_name ON drugs(name)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_interaction_a ON interactions(drug_a_id)')
    
    # Metadata Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    conn.commit()
    return conn

def parse_drugbank_xml(conn: sqlite3.Connection):
    if not XML_PATH.exists():
        logger.error(f"DrugBank XML file not found at {XML_PATH}. Please download it from go.drugbank.com.")
        return
        
    logger.info("Parsing DrugBank XML... This may take a while.")
    cursor = conn.cursor()
    
    context = ET.iterparse(XML_PATH, events=('end',))
    
    drug_count = 0
    interaction_count = 0
    
    for event, elem in context:
        # Strip namespace for tag checking
        tag = elem.tag.split('}', 1)[1] if '}' in elem.tag else elem.tag
        
        if tag == 'drug':
            # Check if this is a primary drug entry (has type attribute)
            if 'type' not in elem.attrib:
                elem.clear()
                continue
                
            # Extract DrugBank ID
            db_id_elem = elem.find('db:drugbank-id[@primary="true"]', NS)
            if db_id_elem is None:
                elem.clear()
                continue
            db_id = db_id_elem.text
            
            # Extract Name
            name_elem = elem.find('db:name', NS)
            name = name_elem.text if name_elem is not None else "Unknown"
            
            # Extract Description
            desc_elem = elem.find('db:description', NS)
            desc = desc_elem.text if desc_elem is not None else ""
            
            # Insert Drug
            cursor.execute('''
                INSERT OR REPLACE INTO drugs (drugbank_id, name, description, state)
                VALUES (?, ?, ?, ?)
            ''', (db_id, name, desc, elem.attrib.get('type', '')))
            drug_count += 1
            
            # Extract Interactions
            interactions = elem.find('db:drug-interactions', NS)
            if interactions is not None:
                for interaction in interactions.findall('db:drug-interaction', NS):
                    int_id_elem = interaction.find('db:drugbank-id', NS)
                    int_name_elem = interaction.find('db:name', NS)
                    int_desc_elem = interaction.find('db:description', NS)
                    
                    if int_id_elem is not None and int_name_elem is not None:
                        cursor.execute('''
                            INSERT INTO interactions (drug_a_id, drug_b_id, drug_b_name, description)
                            VALUES (?, ?, ?, ?)
                        ''', (db_id, int_id_elem.text, int_name_elem.text, int_desc_elem.text if int_desc_elem is not None else ""))
                        interaction_count += 1
                        
            # Periodically commit and clear memory
            if drug_count % 1000 == 0:
                conn.commit()
                logger.info(f"Processed {drug_count} drugs...")
                
            # Clear element to free memory
            elem.clear()
            
    conn.commit()
    
    if drug_count < 1000:
        raise ValueError(f"CRITICAL FAILURE: Parsed only {drug_count} drugs from DrugBank XML. File may be corrupted.")
        
    cursor.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('last_updated', datetime('now'))")
    conn.commit()
    logger.info(f"Successfully loaded {drug_count} drugs and {interaction_count} interactions.")

def main():
    conn = init_db()
    try:
        # Note: XML parsing is heavy, usually takes 5-10 minutes for the full 1GB+ XML
        parse_drugbank_xml(conn)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
