"""An MCP server for the Polish volunteer indexes of vital records.

Three indexes, each built by volunteers from the registers themselves:
Geneteka (Polskie Towarzystwo Genealogiczne), with its per-parish list of
registers and years indexed; the Poznań Project's marriages of 1800-1899 in
Wielkopolska and Kujawy; and BaSIA (Wielkopolskie Towarzystwo Genealogiczne
"Gniazdo"), whose entries name the archive call number and scan. The server
also downloads a full-size scan from Szukaj w Archiwach's open photo host,
given the scan's hash. Nothing here writes anywhere, and nothing here keeps a
family tree.
"""

__version__ = "0.1.0"
