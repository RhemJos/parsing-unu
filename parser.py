"""Module for parsing Section B of sample files."""
import json
import re


class Parser:
    """Parser class implementation."""
    def __init__(self, input_file_name: str):
        """Initialize parser class.

        Parameters
        ----------
        input_file_name : str   Name of the json file to be parsed.
        """
        self.input_file = input_file_name

    def create_output_name(self):
        """Create the name for the output file."""
        file_name = '_'.join(self.input_file.split("_")[0:-1]) + '_002.json'
        self.output_file = file_name

    def save_output(self, records: list[dict]) -> None:
        """Save the output records in a JSON file with the specified structure.

        Parameters
        ----------
        records : list[dict]   List of records to be saved in the output file.
        """
        output = {
            "B": {
                "1": records
            }
        }

        self.create_output_name()

        with open(self.output_file, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

    def clean_text(self, text: str) -> str:
        """Clean line breaks and blank spaces. It returns an string.

        Parameters
        ----------
        text : str  Text to be cleaned.

        """
        return " ".join(text.replace("\n", " ").split())

    def normalize_for_match(self, text: str) -> str:
        """Normalize text to compare. It returns an string.

        Parameters
        ----------
        text : str  Text to be normalized.
        """
        return " ".join(text.upper().split())

    def is_inid(self, text: str) -> bool:
        """Verify if the text is an INID code of three digits.
            It returns a boolean.
        Parameters
        ----------
        text : str  Text to be checked.
        """
        return bool(re.fullmatch(r"\d{3}", text))

    def assign_column(self, x0: float, threshold: float = 300) -> int:
        """Set 1 or 2 according to its column. It returns an integer.

        Parameters
        ----------
        x0 : float  X coordinate of the text line.
        threshold : float    Threshold to assign column 1 or 2. Default is 300.
        """
        return 1 if x0 < threshold else 2

    def is_noise_block(self, text: str, top: float) -> bool:
        """Detect noise blocks based on content and position.
            It returns a boolean.
        Parameters
        ----------
        text : str  Text to be checked.
        top : float Y coordinate of the top of the text line.
        """
        t = self.clean_text(text)
        tu = self.normalize_for_match(t)

        if tu in {"PART B", "B.1.", "B.2.", "PART C", "C.1."}:
            return False

        if tu.startswith("PART B.1") or tu.startswith("PART B.2"):
            return False

        if re.fullmatch(r"\d{4}/\d{3}", t):
            return True

        if t.startswith("EUTM"):
            return True

        if re.fullmatch(r"\d{1,3}", t) and (top > 780 or top < 70):
            return True

        if top < 60:
            if not (
                tu in {"PART B", "B.1.", "B.2.", "PART C", "C.1."}
                or tu.startswith("PART B.1")
                or tu.startswith("PART B.2")
            ):
                return True

        if top > 800:
            return True

        return False

    def is_noise_line(self, text: str) -> bool:
        """Detect if a line is useless based on content. It returns a boolean.
        Parameters
        ----------
        text : str  Text to be checked.
        """
        t = self.clean_text(text)
        tu = self.normalize_for_match(t)

        if not t:
            return True

        if re.fullmatch(r"\d{1,3}", t):
            return True

        if re.fullmatch(r"\d{4}/\d{3}", t):
            return True

        if t.startswith("EUTM"):
            return True

        if tu in {"PART B", "B.1.", "B.2.", "PART C", "C.1."}:
            return True

        if tu.startswith("PART B.1") or tu.startswith("PART B.2"):
            return True

        return False

    def is_b1_start(self, text: str) -> bool:
        """Detect the start of sub-section B.1. It returns a boolean.

        Parameters
        ----------
        text : str  Text to be checked.
        """
        t = self.normalize_for_match(text)

        return t == "B.1." or "PART B.1" in t or "B.1." in t

    def is_b1_end(self, text: str) -> bool:
        """Detect the end of sub-section B.1. It returns a boolean.

        Parameters
        ----------
        text : str  Text to be checked.
        """
        t = self.normalize_for_match(text)

        return "B.2." in t or "PART C" in t or "C.1." in t

    def load_blocks(self, json_path: str) -> list[dict]:
        """Load all useful text blocks from the JSON file.
            It returns a list of dictionaries.
        Parameters
        ----------
        json_path : str  Path to the JSON file to be parsed.
        """
        with open(json_path, "r", encoding="utf-8") as f:
            pages = json.load(f)

        blocks = []

        for page_obj in pages:
            page_num = page_obj["page"]

            for tb in page_obj.get("textboxhorizontal", []):
                text = self.clean_text(tb.get("text", ""))
                if not text:
                    continue

                if self.is_noise_block(text, tb["top"]):
                    continue

                blocks.append({
                    "page": page_num,
                    "text": text,
                    "x0": tb["x0"],
                    "x1": tb["x1"],
                    "top": tb["top"],
                    "bottom": tb["bottom"],
                    "column": self.assign_column(tb["x0"])
                })

        return blocks

    def sort_blocks(self, blocks: list[dict]) -> list[dict]:
        """Order blocks by page, column, top and x0.
            It returns a list of dictionaries.
        Parameters
        ----------
        blocks : list[dict]   List of text blocks to be sorted.
        """
        return sorted(blocks, key=lambda b: (
                                            b["page"], b["column"],
                                            b["top"], b["x0"]))

    def group_blocks_into_lines(self, blocks: list[dict],
                                tolerance: float = 1.0) -> list[dict]:
        """Group blocks that are close vertically as the same line.
            It returns a list[dict]
        Parameters
        ----------
        blocks : list[dict]   List of text blocks to be grouped into lines.
        tolerance : float    Vertical distance to consider the same line.
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

    def filter_section_b1(self, lines: list[dict]) -> list[dict]:
        """Filter only the lines belonging to section B.1.
            It returns a list of dictionaries.
        Parameters
        ----------
        lines : list[dict]   List of text lines to be filtered.
        """
        filtered = []
        in_b1 = False

        for line in lines:
            text = line["text"]

            if not in_b1 and self.is_b1_start(text):
                in_b1 = True
                continue

            if in_b1 and self.is_b1_end(text):
                break

            if in_b1:
                filtered.append(line)

        return filtered

    def parse_line(self, line: dict) -> tuple[str | None, str]:
        """Verify if the line starts with an INID code and extract its value.
            It returns a tuple.
        Parameters
        ----------
        line : dict    Line to be parsed.
        """
        blocks = line["blocks"]

        if not blocks:
            return None, ""

        first_text = blocks[0]["text"]

        if self.is_inid(first_text):
            value = " ".join(b["text"] for b in blocks[1:]).strip()
            return first_text, value

        return None, line["text"].strip()

    def build_records(self, lines: list[dict]) -> list[dict]:
        """Build structured records from the lines.
            It returns a list of dictionaries.
        Parameters
        ----------
        lines : list[dict]   List of text lines to be processed.
        """
        records = []
        current_record = None
        current_field = None

        for line in lines:
            inid, value = self.parse_line(line)

            if inid == "111":
                if current_record:
                    records.append(current_record)

                current_record = {
                    "_PAGE": line["page"],
                    "111": value
                }
                current_field = "111"
                continue

            if current_record is None:
                continue

            if inid:
                current_field = inid

                if inid == "400":
                    current_record.setdefault("400", [])
                    if value:
                        current_record["400"].append(value)
                else:
                    current_record[inid] = value

            else:
                if not value or self.is_noise_line(value):
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

    def normalize_records(self, records: list[dict]) -> list[dict]:
        """Normalize records to have a consistent output format.
            It returns a list of dictionaries.
        Parameters
        ----------
        records : list[dict]   List of records to be normalized.
        """
        normalized = []

        for record in records:
            clean_record = {"_PAGE": int(record["_PAGE"])}

            for key, value in record.items():
                if key == "_PAGE":
                    continue

                if key == "400":
                    if isinstance(value, list):
                        clean_record[key] = [
                            str(v).strip() for v in value if str(v).strip()]
                    else:
                        clean_record[key] = [
                            str(value).strip()] if str(value).strip() else []
                else:
                    clean_record[key] = str(value).strip()

            normalized.append(clean_record)

        return normalized

    def parse(self):
        """Execute the full parsing process from loading
            the JSON file to saving the output records.
        """
        blocks = self.load_blocks(self.input_file)
        ordered_blocks = self.sort_blocks(blocks)
        lines = self.group_blocks_into_lines(ordered_blocks)
        b1_lines = self.filter_section_b1(lines)
        records = self.build_records(b1_lines)
        records = self.normalize_records(records)
        self.save_output(records)


if __name__ == "__main__":
    parser = Parser(input_file_name="BUL_EM_TM_2024000001_001.json")
    parser.parse()
