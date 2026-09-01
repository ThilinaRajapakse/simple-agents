# The design

## What it does, step by step

A claim arrives, `extract` reads its fields, `policy_check` looks the category's limits up,
`decide` says approve, reject or escalate, `audit` checks that decision against the policy and
can send it back once, `dispatch` routes it, `finance` settles what needs a person, `book`
posts an approved claim to the ledger, and `notify` tells the claimant.

## What it holds on to between runs

The ledger, which every approved claim is posted to, and the supplier registry and the policy,
which are read and never written.

## The product

**The finance inbox** is where a claim arrives. Each submitted claim starts one run.

**The finance desk** is the person the agent asks when it cannot settle a claim alone. Their
answer resumes the waiting run.

## What the builder said about it

> "The thing I care about is that it never quietly approves something over the limit. If it is
> not sure, I would rather it asked me than guessed."
