from app.ai.llm import llm_client


BOM_SCHEMA = {
    "type": "object",
    "properties": {
        "records": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "equipment_name": {"type": "string"},
                    "part_number": {"type": "string"},
                    "quantity": {"type": "integer"},
                    "manufacturer": {"type": "string"},
                },
                "required": [
                    "equipment_name",
                    "part_number",
                    "quantity",
                    "manufacturer",
                ],
            },
        }
    },
    "required": ["records"],
}


def main():

    # Deliberately use DIFFERENT column names.
    document_text = """
    Equipment | SKU | Count | Vendor

    Dell PowerEdge Server | DL380-G10 | 4 | Dell
    Cisco Switch | C9300 | 2 | Cisco
    """

    prompt = f"""
You are an inventory extraction system.

Your job is to extract equipment records from the document.

IMPORTANT:
The source document may use completely different column names
from our canonical database fields.

Use the MEANING of the column and its values to determine
the correct canonical field.

Canonical fields:

- equipment_name
- part_number
- quantity
- manufacturer

Semantic mapping example:

"Equipment", "Product", "Item", "Device", "Equipment Name"
    -> equipment_name

"SKU", "Part No", "Part Number", "Item Code", "Product Code"
    -> part_number

"Count", "Qty", "Quantity", "Units", "Number of Items"
    -> quantity

"Vendor", "Mfr", "Manufacturer", "Supplier", "Brand"
    -> manufacturer

Rules:

1. Extract every equipment record.
2. Semantically map source columns to canonical fields.
3. Do NOT depend on exact column names.
4. Do NOT depend on column position.
5. Do NOT invent missing information.
6. Preserve the original values.
7. Return only the requested structured JSON.

Document:

{document_text}
"""

    result = llm_client.generate_json(
        prompt=prompt,
        response_schema=BOM_SCHEMA,
    )

    print("\nSemantic Mapping Result:")
    print(result)


if __name__ == "__main__":
    main()