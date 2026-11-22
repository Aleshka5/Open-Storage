# AGENTS.md

Ground truth rules. The rules themselves live in the documents below.

Spec Driven Development - Sepecs First approach. You have to separate development on at least four different turns:
 1) Examine [docs](/docs/)
 2) Prepare [User Story](/docs/user_stories/) (If changes are clear and are approved, else - ask questions)
 3) Develop
 4) Update docs
Except in cases where you are acting as a specialized sub-agent. In such a situation, clear boundaries must be established for you regarding permissible changes and files.

Documents
 - Docs says AS IS not TO BE.
 - Avoid WIP comments, only technical info.
 - Highlight mismatches docs and fact code every time you catch it. 

While editing
 - Write every document in this repository in English.
 - Keep the document short. Add another short document instead of extending a long one. Avoid "Master Documetnts".
 - Link to the document that owns a fact. Do not copy the fact. For docs use [name](relative/path) for references instead of `relative/path`.
 - Record a decision in an ([ADR](adrs/init.md)) before implementing it.
 - Update the contract in the same change as the behavior it describes.
 - Do not add application code in a documentation-only change.
 - A credential does not go in JavaScript, a URL, or a log.
 - Read [constitution.md](constitution.md) first.
 - Read [repository-layout.md](/docs/repository-layout.md) if you want to add a new file/service/namespace into a repository.
 - Read [User Story Example](/docs/user_stories/us-00-example/init.md) if you want to add a new US or feature.
 - Add architecture schemas as Mermaid description, use subgraphs to union some nodes into one namespace (docker network)