# Glossary Format

## Structure

The glossary is `docs/glossary.md`, a page of the Sphinx docs site. Each group of terms is a MyST
`{glossary}` directive under its own subheading. A term line is followed by its indented definition:

````md
# Glossary

{One or two sentence description of what this context is and why it exists.}

## Orders

```{glossary}
:sorted:

Order
  {A one or two sentence description of the term.}
  _Avoid_: Purchase, transaction

Invoice
  A request for payment sent to a customer after delivery.
  _Avoid_: Bill, payment request
```
````

Other pages refer to a term with `` {term}`Invoice` ``, and the reference is checked by the build. To
let Sphinx resolve a synonym too, add it as an extra term line above the definition (a line each,
no blank line between them). Words to avoid are written as `_Avoid_` text, never as term lines.

## Rules

- **Be opinionated.** When multiple words exist for the same concept, pick the best one and list the others under `_Avoid_`.
- **Keep definitions tight.** One or two sentences max. Define what it IS, not what it does.
- **Only include terms specific to this project's context.** General programming concepts (timeouts, error types, utility patterns) don't belong even if the project uses them extensively. Before adding a term, ask: is this a concept unique to this context, or a general programming concept? Only the former belongs.
- **Group terms under subheadings** when natural clusters emerge, each subheading with its own `{glossary}` block. If all terms belong to a single cohesive area, one block is fine.
