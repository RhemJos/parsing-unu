import json
import re


# =========================
# CONFIGURACIÓN
# =========================

INPUT_FILE = "BUL_EM_TM_2024000001_001.json"
OUTPUT_FILE = "BUL_EM_TM_2024000001_002_GENERADO.json"

COLUMN_SPLIT_X = 300
LINE_TOLERANCE = 0.0


# =========================
# UTILIDADES
# =========================

def clean_text(text: str) -> str:
    """Limpia saltos de línea y espacios extra."""
    return " ".join(text.replace("\n", " ").split())


def normalize_for_match(text: str) -> str:
    """Normaliza texto para comparaciones robustas."""
    return " ".join(text.upper().split())


def is_inid(text: str) -> bool:
    """Valida si el texto es un código INID de 3 dígitos."""
    return bool(re.fullmatch(r"\d{3}", text))


def assign_column(x0: float, split_x: float = COLUMN_SPLIT_X) -> int:
    """Asigna columna 1 o 2 según coordenada horizontal."""
    return 1 if x0 < split_x else 2


# =========================
# FILTRADO DE RUIDO
# =========================

def is_noise_block(text: str, top: float, bottom: float) -> bool:
    """
    Detecta ruido real (encabezados/pies irrelevantes),
    pero conserva marcadores estructurales necesarios
    como B.1, B.2, PART B, etc.
    """
    t = clean_text(text)
    tu = normalize_for_match(t)

    # =========================
    # NO FILTRAR: estructura útil
    # =========================
    if tu in {"PART B", "B.1.", "B.2.", "PART C", "C.1."}:
        return False

    if tu.startswith("PART B.1") or tu.startswith("PART B.2"):
        return False

    # =========================
    # FILTRO POR CONTENIDO
    # =========================
    if re.fullmatch(r"\d{4}/\d{3}", t):  # ej. 2024/001
        return True

    if t.startswith("EUTM"):
        return True

    # Números de página aislados
    if re.fullmatch(r"\d{1,3}", t) and (top > 780 or top < 70):
        return True

    # =========================
    # FILTRO POR POSICIÓN
    # =========================
    # OJO: arriba no todo es basura, porque ahí puede estar Part B.1
    # así que solo filtramos arriba si además parece irrelevante
    if top < 60:
        if not (
            tu in {"PART B", "B.1.", "B.2.", "PART C", "C.1."}
            or tu.startswith("PART B.1")
            or tu.startswith("PART B.2")
        ):
            return True

    # Pie de página
    if top > 800:
        return True

    return False


def is_noise_line(text: str) -> bool:
    """
    Detecta líneas que NO deben agregarse como contenido
    de un campo de registro.
    """
    t = clean_text(text)
    tu = normalize_for_match(t)

    if not t:
        return True

    # Números de página aislados
    if re.fullmatch(r"\d{1,3}", t):
        return True

    # Ej. 2024/001
    if re.fullmatch(r"\d{4}/\d{3}", t):
        return True

    # Encabezado típico
    if t.startswith("EUTM"):
        return True

    # Marcadores estructurales que sirven para secciones,
    # pero NO para contenido de campos
    if tu in {"PART B", "B.1.", "B.2.", "PART C", "C.1."}:
        return True

    if tu.startswith("PART B.1") or tu.startswith("PART B.2"):
        return True

    return False


# =========================
# DETECCIÓN DE SECCIÓN B.1
# =========================

def is_b1_start(text: str) -> bool:
    """
    Detecta el inicio de la sub-sección B.1
    """
    t = normalize_for_match(text)

    return (
        t == "B.1."
        or "PART B.1" in t
        or "B.1." in t
    )


def is_b1_end(text: str) -> bool:
    """
    Detecta el final de la sub-sección B.1
    """
    t = normalize_for_match(text)

    return (
        "B.2." in t
        or "PART C" in t
        or "C.1." in t
    )


# =========================
# CARGA Y NORMALIZACIÓN
# =========================

def load_blocks(json_path: str) -> list[dict]:
    """Carga todos los bloques de texto útiles del archivo JSON."""
    with open(json_path, "r", encoding="utf-8") as f:
        pages = json.load(f)

    blocks = []

    for page_obj in pages:
        page_num = page_obj["page"]

        for tb in page_obj.get("textboxhorizontal", []):
            text = clean_text(tb.get("text", ""))
            if not text:
                continue

            if is_noise_block(text, tb["top"], tb["bottom"]):
                continue

            blocks.append({
                "page": page_num,
                "text": text,
                "x0": tb["x0"],
                "x1": tb["x1"],
                "top": tb["top"],
                "bottom": tb["bottom"],
                "column": assign_column(tb["x0"])
            })

    return blocks


# =========================
# ORDEN DE LECTURA
# =========================

def sort_blocks(blocks: list[dict]) -> list[dict]:
    """
    Orden de lectura correcto:
    página -> columna -> top -> x0
    """
    return sorted(blocks, key=lambda b: (b["page"], b["column"], b["top"], b["x0"]))


# =========================
# AGRUPACIÓN EN LÍNEAS
# =========================

def group_blocks_into_lines(blocks: list[dict], tolerance: float = LINE_TOLERANCE) -> list[dict]:
    """
    Agrupa bloques cercanos verticalmente como una misma línea visual.
    """
    lines = []

    for block in blocks:
        placed = False

        for line in lines:
            ref = line[0]

            same_page = block["page"] == ref["page"]
            same_column = block["column"] == ref["column"]
            close_top = abs(block["top"] - ref["top"]) <= tolerance

            if same_page and same_column and close_top:
                line.append(block)
                placed = True
                break

        if not placed:
            lines.append([block])

    parsed_lines = []

    for line in lines:
        line.sort(key=lambda b: b["x0"])
        parsed_lines.append({
            "page": line[0]["page"],
            "column": line[0]["column"],
            "top": min(b["top"] for b in line),
            "blocks": line,
            "text": " ".join(b["text"] for b in line)
        })

    return parsed_lines


# =========================
# FILTRO DE SECCIÓN B.1
# =========================

def filter_section_b1(lines: list[dict]) -> list[dict]:
    """
    Filtra solo las líneas pertenecientes a la sección B.1
    usando encabezados textuales, sin depender de páginas.
    """
    filtered = []
    in_b1 = False

    for line in lines:
        text = line["text"]

        if not in_b1 and is_b1_start(text):
            in_b1 = True
            continue

        if in_b1 and is_b1_end(text):
            break

        if in_b1:
            filtered.append(line)

    return filtered


# =========================
# PARSEO DE LÍNEAS
# =========================

def parse_line(line: dict) -> tuple[str | None, str]:
    """
    Si la línea empieza con un INID, devuelve (codigo, valor).
    Si no, devuelve (None, texto_completo).
    """
    blocks = line["blocks"]

    if not blocks:
        return None, ""

    first_text = blocks[0]["text"]

    if is_inid(first_text):
        value = " ".join(b["text"] for b in blocks[1:]).strip()
        return first_text, value

    return None, line["text"].strip()


# =========================
# CONSTRUCCIÓN DE REGISTROS
# =========================

def build_records(lines: list[dict]) -> list[dict]:
    """
    Construye registros usando:
    - 111 como inicio de nuevo registro
    - 400 como lista de strings
    - continuidad multilineal si una línea no trae nuevo INID
    """
    records = []
    current_record = None
    current_field = None

    for line in lines:
        inid, value = parse_line(line)

        # Nuevo registro
        if inid == "111":
            if current_record:
                records.append(current_record)

            current_record = {
                "_PAGE": line["page"],
                "111": value
            }
            current_field = "111"
            continue

        # Ignorar contenido antes del primer registro
        if current_record is None:
            continue

        # Línea con nuevo INID
        if inid:
            current_field = inid

            if inid == "400":
                current_record.setdefault("400", [])
                if value:
                    current_record["400"].append(value)
            else:
                current_record[inid] = value

        # Línea de continuación
        else:
            if not value or is_noise_line(value):
                continue

            if current_field == "400":
                current_record.setdefault("400", [])
                current_record["400"].append(value)
            elif current_field:
                current_record[current_field] = (
                    current_record.get(current_field, "") + " " + value
                ).strip()

    if current_record:
        records.append(current_record)

    return records


# =========================
# NORMALIZACIÓN FINAL
# =========================

def normalize_records(records: list[dict]) -> list[dict]:
    """
    Garantiza formato de salida:
    - _PAGE int
    - 400 list[str]
    - demás campos str
    """
    normalized = []

    for record in records:
        clean_record = {"_PAGE": int(record["_PAGE"])}

        for key, value in record.items():
            if key == "_PAGE":
                continue

            if key == "400":
                if isinstance(value, list):
                    clean_record[key] = [str(v).strip() for v in value if str(v).strip()]
                else:
                    clean_record[key] = [str(value).strip()] if str(value).strip() else []
            else:
                clean_record[key] = str(value).strip()

        normalized.append(clean_record)

    return normalized


# =========================
# EXPORTACIÓN
# =========================

def save_output(records: list[dict], output_path: str) -> None:
    output = {
        "B": {
            "1": records
        }
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)


# =========================
# DEBUG / VALIDACIÓN
# =========================

def print_sample(records: list[dict], n: int = 5) -> None:
    print(f"\n=== MUESTRA DE {n} REGISTROS ===")
    for i, record in enumerate(records[:n], start=1):
        print(f"\nRegistro {i}")
        for k, v in record.items():
            print(f"  {k}: {v}")


def validate_records(records: list[dict]) -> None:
    assert all("_PAGE" in r for r in records), "Hay registros sin _PAGE"
    assert all("111" in r for r in records), "Hay registros sin campo 111"
    assert all(isinstance(r["_PAGE"], int) for r in records), "_PAGE no es int"
    assert all(("400" not in r or isinstance(r["400"], list)) for r in records), "400 no es lista"
    print("Validaciones básicas: OK")


# =========================
# MAIN
# =========================

def main():
    blocks = load_blocks(INPUT_FILE)
    ordered_blocks = sort_blocks(blocks)
    lines = group_blocks_into_lines(ordered_blocks)

    b1_lines = filter_section_b1(lines)

    records = build_records(b1_lines)
    records = normalize_records(records)

    validate_records(records)
    print_sample(records, n=5)

    save_output(records, OUTPUT_FILE)

    print(f"\nLíneas totales: {len(lines)}")
    print(f"Líneas B.1: {len(b1_lines)}")
    print(f"Registros extraídos: {len(records)}")
    print(f"Archivo generado: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()