from pathlib import Path
import re

KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "knowledge"
DOCUMENT_FILENAMES = (
    "amenity_policy.md",
    "community_handbook.md",
    "maintenance_guide.md",
    "parking_policy.md",
    "pet_policy.md",
    "resident_services_guide.md",
    "amenity_access_guide.md",
    "move_in_and_services.md",
    "community_access_guide.md",
)


def get_document_sections(document_path: Path) -> list[dict]:
    text = document_path.read_text(encoding="utf-8")

    header = text.split("\n## ", 1)[0]
    metadata = {}

    for line in header.splitlines():
        key, separator, value = line.partition(":")
        if separator:
            metadata[key.strip()] = value.strip()

    required_fields = {
        "Document ID",
        "Property",
        "Version",
        "Effective date",
        "Access level",
    }
    
    missing_fields = required_fields - metadata.keys()
    
    if missing_fields:
        raise ValueError(
            f"{document_path.name}: missing metadata fields: "
            f"{', '.join(sorted(missing_fields))}"
        )

    sections = []

    for block in text.split("\n## ")[1:]:
        heading, _, content = block.partition("\n")
        sections.append({
            "section": heading.strip(),
            "content": content.strip(),
            "document_id": metadata["Document ID"],
            "property": metadata["Property"],
            "version": metadata["Version"],
            "effective_date": metadata["Effective date"],
            "access_level": metadata["Access level"],
            "source": document_path.name,
        })

    return sections

def get_community_sections() -> list[dict]:
    sections = []

    # Explicitly select demo documents; do not expose every file in the folder.
    for filename in DOCUMENT_FILENAMES:
        document_path = KNOWLEDGE_DIR / filename
        sections.extend(get_document_sections(document_path))

    return sections


def tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))

def search_policy(query: str, limit: int = 3) -> list[dict]:
    if not isinstance(query, str) or not query.strip():
        raise ValueError("Query must be a non-empty string.")

    if type(limit) is not int or not 1 <= limit <= 5:
        raise ValueError("Limit must be an integer from 1 to 5.")

    query_words = tokenize(query)
    if not query_words:
        raise ValueError("Query must contain words or numbers.")

    matches = []

    for passage in get_community_sections():
        passage_words = tokenize(
            passage["section"] + " " + passage["content"]
        )
        score = len(query_words & passage_words)

        if score > 0:
            matches.append({**passage, "score": score})

    matches.sort(key=lambda match: match["score"], reverse=True)
    return matches[:limit]

