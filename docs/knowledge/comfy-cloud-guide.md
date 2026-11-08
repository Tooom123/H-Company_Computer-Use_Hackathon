# Comfy Cloud coaching reference

Reference checked on 2026-11-08. Experimental product context; no authenticated
Cloud walkthrough has been validated by these notes. The current visible UI
wins over this reference. Answer in English and preserve exact control labels.

## Environment and workflow safety

Comfy Cloud is the hosted service at https://cloud.comfy.org. It is not a local
ComfyUI installation. It has managed models and custom node packs. Do not advise
installing arbitrary packs, running terminal commands or downloading model files
to a local folder as a Cloud remedy. Unsupported packs are reported on the canvas
and in the Errors tab of the right side panel. Identify the actual error first.
Source: https://docs.comfy.org/get_started/cloud

## Inspect the current graph before explaining it

The canvas contains connected nodes. Nodes, their inputs, outputs and widgets
must be observed, not inferred from a generic tutorial. Some canvas content may
not be exposed through macOS Accessibility. If it is absent from the observed
controls, explicitly say it cannot be read; do not invent a node or its position.
Source: https://docs.comfy.org/interface/overview

## Find a parameter or understand a node

The right side panel can show Parameters, Info, Settings and Errors for the
selection. The Node Library helps discover nodes. Node Docs / Info can explain
the selected node. Ask the user to select the relevant visible node when needed;
never assume that a search result proves that node is used by the current graph.
Source: https://docs.comfy.org/interface/overview

## First image and output

The official first-generation tutorial describes a local Stable Diffusion 1.5
graph, but links to a Z-Image-Turbo template for Cloud. Do not transplant its
checkpoint filename, dimensions or node list into an unseen Cloud workflow.
Save Image saves an output; a preview alone does not prove a file was downloaded.
Source: https://docs.comfy.org/get_started/first_generation

## Queue and deliberate execution

The Run bar includes a batch count, a Run control and queue modes. On Change and
Instant modes can enqueue automatically. A request to show or explain controls
does not authorize running a workflow, changing queue mode, clearing jobs,
importing models or spending credits. Browser sandboxes share the same account
and may share its compute queue. Read-only inspection can run in parallel;
mutating workflows requires separate fixtures and scheduling.
Source: https://docs.comfy.org/interface/overview
