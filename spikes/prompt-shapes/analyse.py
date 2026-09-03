"""What each placeholder syntax would cost across the corpus, and what the record holds."""
import json, re
import spike
from spike import Part

seen = []
orig = Part.__init__
def patched(self, template, values=None, name=None):
    orig(self, template, values, name)
    seen.append(template)
Part.__init__ = patched

import corpus
corpus.main()

# The fixed text a builder writes, with escapes resolved and holes removed.
fixed = []
for t in seen:
    text = re.sub(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}", "", t)
    fixed.append(text.replace("{{", "{").replace("}}", "}"))

def burden(marks):
    return sum(1 for t in fixed if any(m in t for m in marks))

print()
print(f"{len(fixed)} distinct fixed texts across the corpus")
for label, marks in [("{ or }", ("{", "}")), ("<< or >>", ("<<", ">>")), ("$", ("$",)), ("%", ("%",))]:
    print(f"  contain {label:9} : {burden(marks)}")

ctx = spike.Ctx()
print("\n--- the record for the rag case ---")
p = corpus.rag_proposed(ctx, corpus.D)
print(json.dumps([m.content.record() for m in p], indent=2)[:1200])
print("\n--- the record for the conditional-sections case ---")
p = corpus.sections_proposed(ctx, corpus.D)
print(json.dumps([m.content.record() for m in p], indent=2)[:1200])
