# Which pipeline a run is

`plan.md` §1 P3-75's record. **Nothing is built.**

## Where it came from

Six candidates from dogfood #6's sitting of 2026-09-02, all about the checks on a project with
six pipelines: [`DF6-I07`](../runs/dogfood-6/inventory.md#L54), [`DF6-I04`](../runs/dogfood-6/inventory.md#L55), [`DF6-I06`](../runs/dogfood-6/inventory.md#L57), [`DF6-I05`](../runs/dogfood-6/inventory.md#L56), [`DF6-I11`](../runs/dogfood-6/inventory.md#L61),
[`DF6-I08`](../runs/dogfood-6/inventory.md#L58). Thilina ruled `DF6-I05` and `DF6-I11` at the sitting: FT-42 reads every role
and names which recorded each name; a scripted client's runs are marked and excluded by default.

## What the problem is

- **Neither the manifest nor the results file records the registered pipeline's name**
  ([`DF6-D7`](../runs/dogfood-6/findings.md#L222)), so FT-25, FT-37 and FT-38 read the newest agent run of any pipeline and fire
  on most mornings of a project with a daily pass; the workaround was a paid run before every
  gate. `DF5-D5` and `DF5-D17` met the same absence.
- **FT-01 passes on a pipeline the project registers nowhere** ([`DF6-D4`](../runs/dogfood-6/findings.md#L174)).
- **FT-42 reads `role="agent"` only** ([`DF6-D6`](../runs/dogfood-6/findings.md#L201)) and a corpus decision names another
  role's nodes: ten of eleven reported names were recorded.
- **A `FakeModelClient` run is an agent run with model `test/model`** ([`DF6-D11`](../runs/dogfood-6/findings.md#L294)),
  counted as spend and as produced-nothing work.
- **The view offers a one-click on a constant no current run carries** ([`DF6-D8`](../runs/dogfood-6/findings.md#L240)), and
  eight one-clicks wrote eight near-identical decisions.

## What has to be decided

- **The name on the record**: the `pipeline_factory` name on the manifest and the results file's
  `config`, and what an unregistered pipeline records (`null`, and FT-01 reads it).
- **Within-pipeline reading**: FT-25, FT-37 and FT-38 select the newest run whose name matches
  the results file's, and what they do on a project written before the field existed.
- **FT-42 across roles**, per the ruling, and the report line naming the role.
- **The scripted mark**: a manifest field, set by `FakeModelClient`'s identity, and the default
  exclusion in `runs()`, `report` and the checks, with a flag to include.
- **The view's constants**: a name absent from the newest run of its pipeline is shown as gone
  and offered no one-click; a one-click decision's `considered` and `because` carry the click
  once and no boilerplate.

## What it waits on

none
