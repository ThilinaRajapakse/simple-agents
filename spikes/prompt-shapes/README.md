# Prompt shapes

A throwaway spike, kept because it is the evidence behind one ruling: that writing a prompt as
fixed text with named values makes nothing inexpressible, so the freeform string can be refused
rather than kept as an escape hatch.

`spike.py` is a small stand-in for the API. `corpus.py` writes 29 prompt shapes twice, once the
way each is written today and once through the API, and compares what reaches the wire.
`analyse.py` counts what each placeholder syntax would cost across the corpus and prints the
record two of the shapes produce.

    python3 corpus.py     # 29/29 identical
    python3 analyse.py

`prompts-page.html` is the wireframe of the prompt page, published for review.

This directory is deleted when the corpus becomes `tests/test_prompt_shapes.py` against the real
API.
