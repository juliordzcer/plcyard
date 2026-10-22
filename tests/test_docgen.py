from plcyard import docgen


def test_reference_pages_are_up_to_date():
    for name, text in docgen.generate().items():
        assert (docgen.OUT / name).read_text(encoding="utf-8") == text, f"run python -m plcyard.docgen ({name})"


def test_reference_covers_everything_and_names_no_vendor():
    from plcyard.core import fbd, isa
    from plcyard.sims import MODELS
    pages = docgen.generate()
    assert all(f"`{m}`" in pages["instructions.md"] for m in isa.SPECS)
    assert all(f"`{b}`" in pages["function-blocks.md"] for b in fbd.LIBRARY)
    assert all(f"`{k}`" in pages["simulations.md"] for k in MODELS)
    wiki = "".join(p.read_text(encoding="utf-8") for p in docgen.OUT.parent.rglob("*.md")).lower()
    for brand in ("allen", "rockwell", "siemens", "logix", "tia portal", "slc", "step 7"):
        assert brand not in wiki, brand
